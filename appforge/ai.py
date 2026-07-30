"""AI mode: ek natural language prompt se poora app spec banata hai."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from appforge.spec import AppSpec, SpecError


class ChatClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


SYSTEM_PROMPT = """You are AppForge, a senior full-stack engineer that turns a single \
natural-language request (often written in Hindi, English or Hinglish) into a complete, \
runnable application.

Rules:
- Reply with ONE JSON object and nothing else. No markdown fences, no commentary.
- Schema:
  {
    "name": "kebab-case-project-name",
    "description": "one line summary",
    "files": [{"path": "relative/path.ext", "content": "full file content"}],
    "install_cmd": "shell command or null",
    "run_cmd": "shell command that starts the app, or null",
    "notes": ["short hints for the user"]
  }
- Every file must be complete and immediately runnable. No TODOs, no placeholders.
- Prefer zero-config stacks: static HTML/CSS/JS, Python stdlib, FastAPI or Flask.
- Never invent API keys or paid services unless the user explicitly asks for them.
- Include a README.md that explains how to run the app.
- Paths must be relative and must never start with '/' or contain '..'.
"""

USER_TEMPLATE = """Build this app:

{prompt}

Target directory name: {name}
"""


def build_spec(client: ChatClient, prompt: str, name: str) -> AppSpec:
    """Ask the model for an app and parse it into an AppSpec."""
    text = client.complete(SYSTEM_PROMPT, USER_TEMPLATE.format(prompt=prompt.strip(), name=name))
    return AppSpec.from_dict(parse_spec_json(text))


def parse_spec_json(text: str) -> dict[str, Any]:
    """Parse the model reply, tolerating markdown fences and surrounding prose."""
    candidates = [text.strip(), _strip_fences(text), _first_json_object(text)]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise SpecError("model ke reply me valid JSON app spec nahi mila")


def _strip_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""
