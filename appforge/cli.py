"""appforge CLI: ek command se app banao."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from appforge import ai, naming, templates
from appforge.providers import PROVIDERS, LLMClient, ProviderError, api_key_for, detect_provider
from appforge.spec import AppSpec, SpecError
from appforge.writer import WriteError, run_command, write_spec

EXAMPLE = 'appforge "ek todo app banao"'


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
    return parser


def generate(args: argparse.Namespace, prompt: str) -> tuple[AppSpec, str]:
    """Return the generated spec and the mode used ('ai:<provider>' or 'offline')."""
    if args.offline:
        return templates.build_spec(prompt, args.kind), "offline"

    provider = args.provider or detect_provider()
    if provider is None:
        return templates.build_spec(prompt, args.kind), "offline"

    key = api_key_for(PROVIDERS[provider])
    if key is None:
        env_names = " / ".join(PROVIDERS[provider].env_vars)
        raise ProviderError(f"{provider} ke liye API key nahi mili (set {env_names})")

    client = LLMClient(provider=provider, api_key=key, model=args.model)
    return ai.build_spec(client, prompt, naming.project_name(prompt)), f"ai:{provider}"


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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_templates:
        for kind in sorted(templates.KINDS):
            print(f"{kind:<8} {', '.join(templates.KIND_KEYWORDS[kind])}")
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
