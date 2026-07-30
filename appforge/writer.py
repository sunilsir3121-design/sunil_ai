"""Generated app ko disk par likhna aur chalana."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from appforge.spec import AppSpec, SpecError


class WriteError(RuntimeError):
    """Raised when a spec cannot be written safely."""


def safe_target(root: Path, relative_path: str) -> Path:
    """Resolve a spec path inside root, refusing traversal and absolute paths."""
    candidate = Path(relative_path.replace("\\", "/"))
    resolved_root = root.resolve()
    target = (resolved_root / candidate).resolve()
    if candidate.is_absolute() or ".." in candidate.parts or resolved_root not in target.parents:
        raise WriteError(f"unsafe path in app spec: {relative_path}")
    return target


def write_spec(spec: AppSpec, root: Path, overwrite: bool = False) -> list[Path]:
    """Write every file of the spec under root and return the written paths."""
    if not spec.files:
        raise SpecError("app spec me koi file nahi hai")

    root.mkdir(parents=True, exist_ok=True)
    targets = [(safe_target(root, f.path), f.content) for f in spec.files]

    if not overwrite:
        existing = [str(path) for path, _ in targets if path.exists()]
        if existing:
            raise WriteError(
                "ye files pehle se maujood hain (--force use karein): " + ", ".join(existing)
            )

    written: list[Path] = []
    for path, content in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def run_command(command: str, cwd: Path, timeout: float | None = None) -> int:
    """Run a shell-ish command in cwd and stream its output."""
    argv = shlex.split(command)
    if not argv:
        raise WriteError(f"invalid command: {command!r}")
    process = subprocess.run(argv, cwd=str(cwd), timeout=timeout, check=False)
    return process.returncode
