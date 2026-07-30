"""Autonomous agent: ek command se bada task khud plan karke poora karta hai.

Model har step par ek JSON action deta hai (file likho / command chalao / padho / khatam),
AppForge use workspace ke andar chalata hai aur result wapas model ko feed karta hai.
"""

from __future__ import annotations

import ast
import builtins
import json
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from appforge.ai import ChatClient, parse_spec_json
from appforge.safety import UnsafeAction, check_command, resolve_in_workspace
from appforge.spec import SpecError

ACTIONS = ("write_file", "read_file", "run", "list_files", "finish")

ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "action": {"type": "string", "enum": list(ACTIONS)},
        "path": {"type": "string"},
        "content": {"type": "string"},
        "command": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["thought", "action"],
}

SYSTEM_PROMPT = """You are AppForge Agent, an autonomous senior engineer working inside one \
workspace directory on the user's own computer. The user's request may be in Hindi, English \
or Hinglish.

Every reply is ONE JSON object and nothing else:
  {"thought": "...", "action": "<action>", ...action fields}

Actions:
  write_file  -> fields: path (relative), content (complete file, no placeholders)
  read_file   -> fields: path
  list_files  -> no extra fields
  run         -> fields: command (non-interactive shell command, runs in the workspace)
  finish      -> fields: summary (what you built and how to run it)

Rules:
- One action per reply. Wait for its result before deciding the next step.
- Work only with relative paths inside the workspace. Never touch system paths.
- Commands must exit on their own: no servers in the foreground, no interactive prompts.
  Test a server with `timeout 5 python3 app.py &` style checks or a quick curl instead.
- Prefer stdlib and zero-config stacks. Do not install packages unless the task needs them.
- Run Python files as `python3 file.py`. Never use `./file.py` or chmod.
- Run tests as `python3 -m unittest -q` (or `python3 -m pytest -q` if pytest is set up).
- After writing code, actually verify it (run the tests, run the script, curl the endpoint).
- Real tests only: a unittest file needs `class X(unittest.TestCase)` with `def test_*` methods
  and must import what it tests (`from fizzbuzz import fizzbuzz`).
  "Ran 0 tests" means you wrote no tests — fix the test file.
- The current content of every file is shown to you. Read it before rewriting anything, and
  fix the file that actually has the bug (often the test file, not the module).
- If a command fails, read the error and fix it. Never repeat a command that already failed;
  change the approach instead.
- When the whole task is done and verified, reply with the finish action.
"""

TASK_TEMPLATE = """TASK:
{task}

Workspace: {workspace}
{files}

{contents}
Steps so far:
{history}
{warnings}
Reply with the next JSON action."""


class AgentError(RuntimeError):
    """Raised when the agent cannot continue."""


@dataclass
class Step:
    index: int
    thought: str
    action: str
    detail: str
    ok: bool
    output: str

    def as_history(self, limit: int = 700) -> str:
        output = self.output.strip()
        if len(output) > limit:
            output = output[:limit] + f"\n...[{len(output) - limit} more chars]"
        status = "ok" if self.ok else "FAILED"
        return f"[{self.index}] {self.action} {self.detail} -> {status}\n{output}".strip()


@dataclass
class AgentRun:
    task: str
    workspace: Path
    steps: list[Step] = field(default_factory=list)
    finished: bool = False
    summary: str = ""

    @property
    def files_written(self) -> list[str]:
        return [s.detail for s in self.steps if s.action == "write_file" and s.ok]


class Agent:
    """Plan -> act -> observe loop, sab kuch ek workspace ke andar."""

    def __init__(
        self,
        client: ChatClient,
        workspace: Path,
        max_steps: int = 25,
        command_timeout: float = 300.0,
        approve: Callable[[str], bool] | None = None,
        printer: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.workspace = workspace
        self.max_steps = max_steps
        self.command_timeout = command_timeout
        self.approve = approve
        self.printer = printer or _stream_print

    def run(self, task: str) -> AgentRun:
        self.workspace.mkdir(parents=True, exist_ok=True)
        run = AgentRun(task=task, workspace=self.workspace)
        rejections = 0

        for index in range(1, self.max_steps + 1):
            action = self._next_action(task, run)
            thought = str(action.get("thought", "")).strip()
            name = str(action.get("action", "")).strip()
            if thought:
                self.printer(f"\n[{index}] {thought}")

            if name == "finish":
                complaint = _finish_blocker(run.steps) if rejections < 2 else None
                if complaint:
                    rejections += 1
                    run.steps.append(Step(index, thought, "finish", "", False, complaint))
                    self.printer(f"    FAILED: finish -> {complaint}")
                    continue
                run.finished = True
                run.summary = str(action.get("summary", "")).strip() or "task poora hua"
                self.printer(f"[{index}] finish: {run.summary}")
                break

            step = self._execute(index, name, thought, action, run.steps)
            run.steps.append(step)
            self._log(step)
            self.printer(f"    {'ok' if step.ok else 'FAILED'}: {step.action} {step.detail}")
            if step.output.strip():
                self.printer(_indent(step.output, limit=1500))

        if not run.finished:
            run.summary = f"{self.max_steps} steps ke baad bhi finish nahi hua"
        return run

    def _next_action(self, task: str, run: AgentRun) -> dict[str, Any]:
        history = "\n\n".join(step.as_history() for step in run.steps[-4:]) or "(abhi kuch nahi)"
        message = TASK_TEMPLATE.format(
            task=task.strip(),
            workspace=self.workspace,
            files=self._workspace_listing(),
            contents=self._file_contents(),
            history=history,
            warnings=_loop_warnings(run.steps),
        )
        for _ in range(2):
            reply = self.client.complete(SYSTEM_PROMPT, message, ACTION_SCHEMA)
            try:
                action = parse_spec_json(reply)
            except SpecError:
                message += "\n\nYour last reply was not valid JSON. Reply with JSON only."
                continue
            if str(action.get("action")) in ACTIONS:
                return action
            message += (
                f"\n\n'{action.get('action')}' is not a valid action. "
                f"Use one of: {', '.join(ACTIONS)}"
            )
        raise AgentError("model se valid action nahi mila")

    def _execute(
        self, index: int, name: str, thought: str, action: dict[str, Any], steps: list[Step]
    ) -> Step:
        try:
            if name == "write_file":
                return self._write_file(index, thought, action, steps)
            if name == "read_file":
                return self._read_file(index, thought, action)
            if name == "list_files":
                listing = self._workspace_listing()
                return Step(index, thought, name, "", True, listing)
            if name == "run":
                return self._run_command(index, thought, action)
        except UnsafeAction as exc:
            return Step(index, thought, name, "", False, f"blocked: {exc}")
        except OSError as exc:
            return Step(index, thought, name, "", False, f"error: {exc}")
        return Step(index, thought, name or "unknown", "", False, f"unknown action: {name}")

    def _write_file(
        self, index: int, thought: str, action: dict[str, Any], steps: list[Step]
    ) -> Step:
        path = str(action.get("path", "")).strip()
        content = action.get("content")
        if not path or not isinstance(content, str):
            return Step(index, thought, "write_file", path, False, "path ya content missing hai")
        target = resolve_in_workspace(self.workspace, path)

        if target.is_file() and target.read_text(encoding="utf-8") == content:
            return Step(
                index, thought, "write_file", path, False,
                f"file pehle se bilkul aisi hi hai — ab `run` action se `python3 {path}` chalao",
            )
        if _rewrites_without_running(steps, path) >= 2:
            return Step(
                index, thought, "write_file", path, False,
                f"{path} bina chalaye baar-baar likh rahe ho — pehle `run` action bhejo",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        lines = content.count("\n") + 1

        problem = _python_syntax_error(path, content) or self._missing_import(path, content)
        if problem:
            return Step(index, thought, "write_file", path, False, problem)
        return Step(index, thought, "write_file", path, True, f"{lines} lines likhi")

    def _missing_import(self, path: str, content: str) -> str | None:
        """Sabse common bug: test file jis function ko test karti hai use import hi nahi karti."""
        if not path.endswith(".py"):
            return None
        unresolved = _unresolved_names(content)
        if not unresolved:
            return None
        for other in self._workspace_files():
            if not other.endswith(".py") or other == path:
                continue
            try:
                exported = _module_level_names((self.workspace / other).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            shared = sorted(unresolved & exported)
            if shared:
                module = other[:-3].replace("/", ".")
                names = ", ".join(shared)
                return (
                    f"{names} kahin se import nahi hua — file ke top par "
                    f"`from {module} import {names}` add karo"
                )
        return None

    def _read_file(self, index: int, thought: str, action: dict[str, Any]) -> Step:
        path = str(action.get("path", "")).strip()
        target = resolve_in_workspace(self.workspace, path)
        if not target.is_file():
            return Step(index, thought, "read_file", path, False, "file nahi mili")
        return Step(index, thought, "read_file", path, True, target.read_text(encoding="utf-8"))

    def _run_command(self, index: int, thought: str, action: dict[str, Any]) -> Step:
        command = str(action.get("command", "")).strip()
        check_command(command)
        if self.approve and not self.approve(command):
            return Step(index, thought, "run", command, False, "user ne mana kar diya")

        self.printer(f"    $ {command}")
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S602 - agent shell is guarded by safety.py
                command,
                shell=True,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
            )
        except subprocess.TimeoutExpired:
            return Step(
                index, thought, "run", command, False,
                f"command {self.command_timeout:.0f}s me khatam nahi hua",
            )
        elapsed = time.monotonic() - started
        output = (completed.stdout + completed.stderr).strip()
        detail = f"{command} ({elapsed:.1f}s, exit {completed.returncode})"
        ok = completed.returncode == 0
        complaint = _test_output_problem(output) if ok else None
        if complaint:
            return Step(index, thought, "run", detail, False, f"{output}\n\n({complaint})")
        return Step(index, thought, "run", detail, ok, output)

    def _file_contents(self, max_files: int = 6, budget: int = 4000) -> str:
        """Chhote model ko yaad nahi rehta ki usne kya likha — files dikha dete hain."""
        chunks: list[str] = []
        used = 0
        for path in self._workspace_files()[:max_files]:
            try:
                text = (self.workspace / path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            room = budget - used
            if room <= 0:
                break
            if len(text) > room:
                text = text[:room] + "\n...[truncated]"
            used += len(text)
            chunks.append(f"--- {path} ---\n{text.rstrip()}")
        if not chunks:
            return "Current file contents: (abhi koi file nahi)"
        return "Current file contents:\n" + "\n\n".join(chunks)

    def _workspace_files(self) -> list[str]:
        if not self.workspace.exists():
            return []
        return sorted(
            str(p.relative_to(self.workspace))
            for p in self.workspace.rglob("*")
            if p.is_file()
            and ".appforge" not in p.parts
            and "__pycache__" not in p.parts
            and not p.name.startswith(".")
        )

    def _workspace_listing(self, limit: int = 60) -> str:
        paths = self._workspace_files()
        if not paths:
            return "Files: (khaali)"
        shown = paths[:limit]
        extra = "" if len(paths) <= limit else f" (+{len(paths) - limit} more)"
        return "Files: " + ", ".join(shown) + extra

    def _log(self, step: Step) -> None:
        log_dir = self.workspace / ".appforge"
        log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "index": step.index,
            "action": step.action,
            "detail": step.detail,
            "ok": step.ok,
            "thought": step.thought,
            "output": step.output[:4000],
        }
        with (log_dir / "agent-log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


VACUOUS_TEST_OUTPUT = ("ran 0 tests", "no tests ran", "collected 0 items")
FAILED_TEST_OUTPUT = ("failed (failures=", "failed (errors=", "= failures =", " failed,")


def _test_output_problem(output: str) -> str | None:
    """Exit code 0 hone par bhi test output jhooth bol sakta hai — use pakadte hain."""
    lowered = output.lower()
    if any(marker in lowered for marker in VACUOUS_TEST_OUTPUT):
        return "koi test chala hi nahi — asli TestCase class likho"
    if any(marker in lowered for marker in FAILED_TEST_OUTPUT):
        return (
            "exit code 0 tha par tests fail hue (unittest.main(exit=False) error chhupa deta "
            "hai) — `python3 -m unittest -q` se chalao aur failure theek karo"
        )
    return None


def _unresolved_names(content: str) -> set[str]:
    """Jo naam use hue par kahin bind nahi hue (na import, na def, na assignment)."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()

    bound: set[str] = set(dir(builtins))
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            (used if isinstance(node.ctx, ast.Load) else bound).add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)
    return used - bound


def _module_level_names(content: str) -> set[str]:
    """Ek module top level par kya-kya export karta hai."""
    tree = ast.parse(content)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _python_syntax_error(path: str, content: str) -> str | None:
    if not path.endswith(".py"):
        return None
    try:
        compile(content, path, "exec")
    except SyntaxError as exc:
        return f"SyntaxError line {exc.lineno}: {exc.msg} — file theek karo"
    return None


def _finish_blocker(steps: list[Step]) -> str | None:
    """Finish tabhi maano jab agent ne apna kaam actually chalakar dekha ho."""
    if not any(step.action == "write_file" and step.ok for step in steps):
        return "abhi tak koi file nahi likhi — pehle kaam karo, phir finish"
    if not any(step.action == "run" and step.ok for step in steps):
        return "finish se pehle apna code chalakar verify karo (run action)"
    return None


def _rewrites_without_running(steps: list[Step], path: str) -> int:
    """Pichhle run ke baad ye file kitni baar likhi gayi."""
    count = 0
    for step in reversed(steps):
        if step.action == "run":
            break
        if step.action == "write_file" and step.detail == path:
            count += 1
    return count


def _loop_warnings(steps: list[Step]) -> str:
    """Chhote models loop me phas jate hain — unhe saaf-saaf bata dete hain."""
    lines: list[str] = []
    since_write = steps[_last_write_index(steps) + 1 :]
    commands = [
        (step.detail.split(" (")[0], step.ok) for step in since_write if step.action == "run"
    ]

    for command, count in Counter(cmd for cmd, ok in commands if not ok).items():
        if count >= 2:
            lines.append(
                f"- `{command}` {count} baar fail hui hai aur beech me koi file nahi badli. "
                "Pehle code theek karo, tab chalao."
            )
    for command, count in Counter(cmd for cmd, ok in commands if ok).items():
        if count >= 2:
            lines.append(
                f"- `{command}` {count} baar pass ho chuki hai. Ab agla kaam karo ya finish karo."
            )

    stale = _stale_failure(steps)
    if stale:
        lines.append(f"- Code badal chuka hai: `{stale}` ab dobara chalakar dekho.")

    writes = Counter(step.detail for step in steps if step.action == "write_file" and step.ok)
    for path, count in writes.items():
        if count >= 3:
            lines.append(
                f"- `{path}` {count} baar likh chuke ho. Ab use `python3 {path}` se chalakar dekho."
            )

    if not lines:
        return ""
    return "\nWARNINGS:\n" + "\n".join(lines) + "\n"


def _last_write_index(steps: list[Step]) -> int:
    for i in range(len(steps) - 1, -1, -1):
        if steps[i].action == "write_file" and steps[i].ok:
            return i
    return -1


def _stale_failure(steps: list[Step]) -> str | None:
    """Jo command fail hui thi, uske baad file badli ho to usko dobara chalana chahiye."""
    write_at = _last_write_index(steps)
    if write_at < 0:
        return None
    for step in reversed(steps[:write_at]):
        if step.action == "run" and not step.ok:
            command = step.detail.split(" (")[0]
            already_retried = any(
                later.action == "run" and later.detail.startswith(command)
                for later in steps[write_at + 1 :]
            )
            return None if already_retried else command
    return None


def _stream_print(text: str) -> None:
    print(text, flush=True)


def _indent(text: str, limit: int) -> str:
    body = text.strip()
    if len(body) > limit:
        body = body[:limit] + f"\n...[{len(body) - limit} more chars]"
    return "\n".join(f"    | {line}" for line in body.splitlines())
