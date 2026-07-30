"""Workspace ko dekhne, likhne aur usme command chalane ke helpers.

UI ka file tree, editor aur terminal isi par chalte hain. Har rasta
`safety.resolve_in_workspace` se hokar jata hai, isliye folder ke bahar kuch nahi hota.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from appforge.safety import UnsafeAction, check_command, resolve_in_workspace

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".appforge", ".mypy_cache"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".pyc", ".so", ".woff"}
MAX_READ_BYTES = 400_000


@dataclass
class CommandResult:
    command: str
    code: int
    output: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def list_files(root: Path, limit: int = 400) -> list[str]:
    """Workspace ki files (relative paths), noise wale folders chhod kar."""
    if not root.is_dir():
        return []
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if SKIP_DIRS & set(relative.parts):
            continue
        found.append(str(relative))
        if len(found) >= limit:
            break
    return found


def read_file(root: Path, relative_path: str) -> str:
    """File ka text; folder ke bahar ya binary file par UnsafeAction/ValueError."""
    target = resolve_in_workspace(root, relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"{relative_path} nahi mili")
    if target.suffix.lower() in BINARY_SUFFIXES:
        raise ValueError(f"{relative_path} text file nahi hai")
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"{relative_path} bahut badi hai (editor me nahi khulegi)")
    return target.read_text(encoding="utf-8", errors="replace")


def save_file(root: Path, relative_path: str, content: str) -> Path:
    """File likho (naya folder bhi bana do), sirf workspace ke andar."""
    target = resolve_in_workspace(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def run(root: Path, command: str, timeout: float = 120.0) -> CommandResult:
    """Workspace me ek command chalao; khatarnak commands safety.py rok deti hai."""
    command = command.strip()
    if not command:
        return CommandResult(command, 1, "khaali command")
    try:
        check_command(command)
    except UnsafeAction as exc:
        return CommandResult(command, 1, f"ye command allowed nahi: {exc}")

    root.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(  # noqa: S602 - safety.py guards the shell
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(command, 124, f"command {timeout:.0f}s me khatam nahi hua")
    except OSError as exc:
        return CommandResult(command, 1, str(exc))

    output = (completed.stdout or "") + (completed.stderr or "")
    return CommandResult(command, completed.returncode, output)
