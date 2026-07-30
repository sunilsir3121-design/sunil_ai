"""Data model for a generated app."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SpecError(ValueError):
    """Raised when a model or template produces an unusable app spec."""


@dataclass(frozen=True)
class GeneratedFile:
    path: str
    content: str


@dataclass
class AppSpec:
    name: str
    description: str
    files: list[GeneratedFile]
    install_cmd: str | None = None
    run_cmd: str | None = None
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSpec:
        if not isinstance(data, dict):
            raise SpecError("app spec JSON object nahi hai")

        raw_files = data.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise SpecError("app spec me 'files' list missing hai")

        files: list[GeneratedFile] = []
        for entry in raw_files:
            if not isinstance(entry, dict):
                raise SpecError("har file ek object honi chahiye")
            path = entry.get("path")
            content = entry.get("content")
            if not isinstance(path, str) or not path.strip():
                raise SpecError("file entry me valid 'path' nahi hai")
            if not isinstance(content, str):
                raise SpecError(f"file '{path}' ka 'content' string nahi hai")
            files.append(GeneratedFile(path=path.strip(), content=content))

        notes = data.get("notes") or []
        if not isinstance(notes, list):
            raise SpecError("'notes' list honi chahiye")

        return cls(
            name=str(data.get("name") or "app").strip() or "app",
            description=str(data.get("description") or "").strip(),
            files=files,
            install_cmd=_optional_str(data.get("install_cmd")),
            run_cmd=_optional_str(data.get("run_cmd")),
            notes=[str(note) for note in notes],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "files": [{"path": f.path, "content": f.content} for f in self.files],
            "install_cmd": self.install_cmd,
            "run_cmd": self.run_cmd,
            "notes": self.notes,
        }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
