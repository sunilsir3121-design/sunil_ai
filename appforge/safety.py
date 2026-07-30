"""Agent ke liye guardrails: workspace ke andar hi kaam, khatarnak commands block."""

from __future__ import annotations

import re
import shlex
from pathlib import Path


class UnsafeAction(RuntimeError):
    """Raised when the agent asks for something we refuse to do."""


# Poore system ko chhoone wale ya irreversible commands.
BLOCKED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brm\s+(-[a-z]*\s+)*(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\s+/(\s|$)", "rm -rf / mana hai"),
    (r"\bmkfs(\.\w+)?\b", "filesystem format mana hai"),
    (r"\bdd\s+.*\bof=/dev/", "raw disk write mana hai"),
    (r">\s*/dev/(sd|nvme|hd)", "raw disk write mana hai"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "system band karna mana hai"),
    (r"\bsudo\b", "sudo mana hai"),
    (r"\bsu\s+-", "user switch mana hai"),
    (r":\(\)\s*\{.*\};:", "fork bomb mana hai"),
    (r"\bchmod\s+(-R\s+)?[0-7]{3,4}\s+/(\s|$)", "root permissions badalna mana hai"),
    (r"\bchown\s+(-R\s+)?\S+\s+/(\s|$)", "root ownership badalna mana hai"),
    (r"\bgit\s+push\b.*--force", "force push mana hai"),
    (r"\bcurl\b[^|]*\|\s*(sudo\s+)?(ba)?sh", "internet script ko seedha shell me dena mana hai"),
    (r"\bwget\b[^|]*\|\s*(sudo\s+)?(ba)?sh", "internet script ko seedha shell me dena mana hai"),
    (r"\bhistory\s+-c\b", "history mitana mana hai"),
    (r"\bcrontab\b", "cron badalna mana hai"),
    (r"\bsystemctl\b", "system services badalna mana hai"),
)

# In paths ko kabhi nahi chhedna, chahe workspace kahin bhi ho.
PROTECTED_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys", "/var")


def check_command(command: str) -> None:
    """Raise UnsafeAction agar command clearly destructive ho."""
    if not command.strip():
        raise UnsafeAction("khaali command")
    lowered = command.lower()
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, lowered):
            raise UnsafeAction(f"{reason}: {command}")
    for token in _paths_in(command):
        if token.startswith(PROTECTED_PREFIXES):
            raise UnsafeAction(f"system path chhoona mana hai: {token}")


def _paths_in(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return [token for token in tokens if token.startswith("/")]


def resolve_in_workspace(workspace: Path, relative_path: str) -> Path:
    """Workspace ke andar ka absolute path, warna UnsafeAction."""
    candidate = Path(relative_path.replace("\\", "/"))
    root = workspace.resolve()
    target = (root / candidate).resolve()
    if candidate.is_absolute() or root not in target.parents:
        raise UnsafeAction(f"workspace ke bahar likhna mana hai: {relative_path}")
    return target
