"""appforge CLI: ek command se app banao."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from appforge import ai, naming, templates
from appforge.agent import Agent, AgentError
from appforge.providers import (
    PROVIDERS,
    LLMClient,
    ProviderError,
    api_key_for,
    detect_provider,
    ollama_host,
    ollama_models,
)
from appforge.spec import AppSpec, SpecError
from appforge.writer import WriteError, run_command, write_spec

EXAMPLE = 'appforge "ek todo app banao"'
AGENT_EXAMPLE = 'appforge agent "flask blog banao aur tests likh ke pass karao"'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="appforge",
        description="Ek command se koi bhi app banao (AI ya offline templates se).",
        epilog=f"Example: {EXAMPLE}",
    )
    parser.add_argument("prompt", nargs="*", help="kya banana hai, apne shabdon me")
    parser.add_argument("-o", "--out", help="output directory (default: app ka naam)")
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDERS),
        help="LLM provider (default: jiski API key env me mile)",
    )
    parser.add_argument("--model", help="model name override")
    parser.add_argument("--offline", action="store_true", help="AI ke bina, templates se banao")
    parser.add_argument(
        "--kind",
        choices=sorted(templates.KINDS),
        help="offline template ka type (default: prompt se detect)",
    )
    parser.add_argument("--force", action="store_true", help="maujood files overwrite karo")
    parser.add_argument("--dry-run", action="store_true", help="sirf plan dikhao, likho mat")
    parser.add_argument("--json", action="store_true", help="app spec JSON me print karo")
    parser.add_argument("--run", action="store_true", help="banane ke baad app chalao")
    parser.add_argument("--list-templates", action="store_true", help="offline templates dikhao")
    parser.add_argument("--status", action="store_true", help="kaunsa AI available hai, dikhao")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="AI fail ho to template par mat girna, error do",
    )
    return parser


def build_agent_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="appforge agent",
        description="Bada task khud plan karke poora karo: files likho, commands chalao, fix karo.",
        epilog=f"Example: {AGENT_EXAMPLE}",
    )
    parser.add_argument("task", nargs="*", help="pura task apne shabdon me")
    parser.add_argument("-C", "--workspace", default=".", help="kis folder me kaam karna hai")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), help="LLM provider")
    parser.add_argument("--model", help="model name override")
    parser.add_argument("--max-steps", type=int, default=25, help="zyada se zyada steps")
    parser.add_argument(
        "--timeout", type=float, default=300.0, help="ek command ke liye seconds"
    )
    parser.add_argument(
        "--ask",
        action="store_true",
        help="har command chalane se pehle poocho",
    )
    return parser


OLLAMA_HELP = (
    "Local AI (Ollama) nahi mila. Install: `curl -fsSL https://ollama.com/install.sh | sh`, "
    "phir `ollama pull qwen2.5-coder:3b`. Ya `--offline` se templates use karein."
)


def make_client(provider: str, model: str | None) -> LLMClient:
    config = PROVIDERS[provider]
    if config.local:
        if not ollama_models():
            raise ProviderError(OLLAMA_HELP)
        return LLMClient(provider=provider, model=model, progress=sys.stderr.isatty())

    key = api_key_for(config)
    if key is None:
        env_names = " / ".join(config.env_vars)
        raise ProviderError(f"{provider} ke liye API key nahi mili (set {env_names})")
    return LLMClient(provider=provider, api_key=key, model=model)


def generate(args: argparse.Namespace, prompt: str) -> tuple[AppSpec, str]:
    """Return the generated spec and the mode used ('ai:<provider>' or 'offline')."""
    if args.offline:
        return templates.build_spec(prompt, args.kind), "offline"

    provider = args.provider or detect_provider()
    if provider is None:
        return templates.build_spec(prompt, args.kind), "offline"

    client = make_client(provider, args.model)
    if PROVIDERS[provider].local:
        print(f"local AI ({client.model}) soch raha hai... thoda time lagega", file=sys.stderr)

    try:
        spec = ai.build_spec(client, prompt, naming.project_name(prompt))
    except (ProviderError, SpecError) as exc:
        if args.strict:
            raise
        print(f"warning: AI se app nahi bana ({exc}) — template se bana raha hoon", file=sys.stderr)
        return templates.build_spec(prompt, args.kind), "offline (AI fallback)"
    return spec, f"ai:{provider} ({client.model})"


def print_status() -> None:
    provider = detect_provider()
    print(f"provider : {provider or 'koi nahi (offline templates)'}")
    models = ollama_models()
    print(f"ollama   : {ollama_host()} — {', '.join(models) if models else 'nahi chal raha'}")
    for name, config in PROVIDERS.items():
        if config.local:
            continue
        state = "key mili" if api_key_for(config) else "key nahi"
        print(f"{name:<9}: {state} ({' / '.join(config.env_vars)})")


def print_plan(spec: AppSpec, mode: str, out_dir: Path) -> None:
    print(f"\n  {spec.name} — {spec.description}")
    print(f"  mode: {mode}")
    print(f"  path: {out_dir}\n")
    for file in spec.files:
        lines = file.content.count("\n") + 1
        print(f"    + {file.path} ({lines} lines)")
    if spec.install_cmd:
        print(f"\n  install: {spec.install_cmd}")
    if spec.run_cmd:
        print(f"  run:     {spec.run_cmd}")
    for note in spec.notes:
        print(f"  note:    {note}")
    print()


def ask_user(command: str) -> bool:
    try:
        answer = input(f"    chalayein? `{command}` [Y/n] ").strip().lower()
    except EOFError:
        return True
    return answer in {"", "y", "yes", "haan", "ha"}


def run_agent(argv: list[str]) -> int:
    args = build_agent_parser().parse_args(argv)
    task = " ".join(args.task).strip()
    if not task:
        print(f"kya karna hai? example: {AGENT_EXAMPLE}", file=sys.stderr)
        return 2

    provider = args.provider or detect_provider()
    if provider is None:
        print(f"error: {OLLAMA_HELP}", file=sys.stderr)
        return 1

    try:
        client = make_client(provider, args.model)
    except ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    workspace = Path(args.workspace).expanduser().resolve()
    print(f"agent: {provider} ({client.model})")
    print(f"kaam: {task}")
    print(f"folder: {workspace}")

    agent = Agent(
        client=client,
        workspace=workspace,
        max_steps=args.max_steps,
        command_timeout=args.timeout,
        approve=ask_user if args.ask else None,
    )
    try:
        run = agent.run(task)
    except AgentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nrok diya gaya.", file=sys.stderr)
        return 130

    failed = [step for step in run.steps if not step.ok]
    print(f"\n{len(run.steps)} steps, {len(failed)} fail, files: {len(set(run.files_written))}")
    print(f"summary: {run.summary}")
    print(f"log: {workspace / '.appforge' / 'agent-log.jsonl'}")
    return 0 if run.finished else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "agent":
        return run_agent(argv[1:])

    args = build_parser().parse_args(argv)

    if args.list_templates:
        for kind in sorted(templates.KINDS):
            print(f"{kind:<8} {', '.join(templates.KIND_KEYWORDS[kind])}")
        return 0

    if args.status:
        print_status()
        return 0

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print(f'kya banana hai? example: {EXAMPLE}', file=sys.stderr)
        return 2

    try:
        spec, mode = generate(args, prompt)
    except (ProviderError, SpecError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else Path.cwd() / spec.name

    if args.json:
        print(json.dumps(spec.to_dict(), indent=2, ensure_ascii=False))
        return 0

    print_plan(spec, mode, out_dir)

    if args.dry_run:
        print("dry run — kuch likha nahi gaya.")
        return 0

    try:
        write_spec(spec, out_dir, overwrite=args.force)
    except (WriteError, SpecError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"ban gaya: {out_dir}")

    if spec.install_cmd and args.run:
        print(f"\n$ {spec.install_cmd}")
        if run_command(spec.install_cmd, out_dir) != 0:
            print("install command fail hui.", file=sys.stderr)
            return 1

    if args.run and spec.run_cmd:
        print(f"\n$ {spec.run_cmd}  (Ctrl+C se band karein)\n")
        try:
            return run_command(spec.run_cmd, out_dir)
        except KeyboardInterrupt:
            return 0
    elif spec.run_cmd:
        print(f"chalane ke liye: cd {out_dir} && {spec.run_cmd}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
