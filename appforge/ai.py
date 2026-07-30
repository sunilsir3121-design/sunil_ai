"""AI mode: ek natural language prompt se poora app spec banata hai."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from appforge.spec import JSON_SCHEMA, AppSpec, SpecError


class ChatClient(Protocol):
    def complete(
        self, system: str, user: str, schema: dict[str, Any] | None = None
    ) -> str: ...


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
- Besides README.md there must be at least one real source file with working code.
- install_cmd must be null unless a file actually declares those dependencies.
"""

USER_TEMPLATE = """Build this app:

{prompt}

Target directory name: {name}
"""

RETRY_TEMPLATE = """{original}

Your previous answer was rejected: {problem}
Return the corrected JSON object only, with every source file fully written out.
"""

CODE_SUFFIXES = (
    ".html", ".css", ".js", ".jsx", ".ts", ".tsx", ".py", ".json", ".sh",
    ".go", ".rs", ".java", ".rb", ".php", ".vue", ".svelte", ".toml", ".yml", ".yaml",
)


def build_spec(client: ChatClient, prompt: str, name: str, attempts: int = 2) -> AppSpec:
    """Ask the model for an app, retrying once if the reply is unusable."""
    user = USER_TEMPLATE.format(prompt=prompt.strip(), name=name)
    last_error: SpecError | None = None
    for attempt in range(max(1, attempts)):
        message = user if attempt == 0 else RETRY_TEMPLATE.format(original=user, problem=last_error)
        try:
            reply = client.complete(SYSTEM_PROMPT, message, JSON_SCHEMA)
            spec = AppSpec.from_dict(parse_spec_json(reply))
            validate_spec(spec)
            return sanitize_commands(spec)
        except SpecError as exc:
            last_error = exc
    raise last_error if last_error else SpecError("model se app spec nahi mila")


def validate_spec(spec: AppSpec) -> None:
    """Reject replies that describe an app instead of writing it."""
    code_files = [
        file
        for file in spec.files
        if file.path.lower() != "readme.md" and file.path.lower().endswith(CODE_SUFFIXES)
    ]
    if not code_files:
        raise SpecError("README ke alawa koi source file nahi hai")
    if not any(len(file.content.strip()) >= 40 for file in code_files):
        raise SpecError("source files khaali ya adhoori hain")


NODE_COMMANDS = ("npm", "yarn", "pnpm", "npx")
STATIC_RUN_CMD = "python3 -m http.server 8000"


def sanitize_commands(spec: AppSpec) -> AppSpec:
    """Drop install/run commands jinke liye zaroori files hi nahi hain."""
    paths = {file.path.lower() for file in spec.files}
    has_node = "package.json" in paths
    has_index = "index.html" in paths

    if spec.install_cmd:
        first = spec.install_cmd.split()[0]
        needs_node = first in NODE_COMMANDS and not has_node
        needs_reqs = "requirements.txt" in spec.install_cmd and "requirements.txt" not in paths
        if needs_node or needs_reqs:
            spec.install_cmd = None

    if spec.run_cmd:
        first = spec.run_cmd.split()[0]
        broken_node = first in NODE_COMMANDS and not has_node
        opens_file = first in {"open", "xdg-open", "start"}
        if (broken_node or opens_file) and has_index:
            spec.run_cmd = STATIC_RUN_CMD
            spec.notes.append("Browser me http://localhost:8000 kholein.")
        elif broken_node or opens_file:
            spec.run_cmd = None

    return spec


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
