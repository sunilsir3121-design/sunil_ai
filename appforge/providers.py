"""LLM providers. Zero dependencies: plain urllib + JSON over HTTP(S).

Default provider Ollama hai: aapke apne computer par chalta hai, free hai, aur koi data
bahar nahi jata. Cloud providers tabhi use hote hain jab unki API key set ho.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from appforge.spec import JSON_SCHEMA


class ProviderError(RuntimeError):
    """Raised when an LLM API call fails."""


@dataclass(frozen=True)
class ProviderConfig:
    """Describes how to talk to one LLM vendor."""

    name: str
    env_vars: tuple[str, ...]
    default_model: str
    local: bool = False


PROVIDERS: dict[str, ProviderConfig] = {
    "ollama": ProviderConfig(
        name="ollama",
        env_vars=(),
        default_model="qwen2.5-coder:3b",
        local=True,
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        env_vars=("ANTHROPIC_API_KEY",),
        default_model="claude-sonnet-4-20250514",
    ),
    "openai": ProviderConfig(
        name="openai",
        env_vars=("OPENAI_API_KEY",),
        default_model="gpt-4o-mini",
    ),
    "gemini": ProviderConfig(
        name="gemini",
        env_vars=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        default_model="gemini-2.0-flash",
    ),
}


DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# Jo pehle mile wahi use hoga; sab local aur free hain.
PREFERRED_OLLAMA_MODELS = (
    "qwen2.5-coder:7b",
    "qwen2.5-coder:3b",
    "qwen3:4b",
    "llama3.1:8b",
    "llama3.2:3b",
)

# In models me reasoning by default on hota hai — CPU par slow, isliye band kar dete hain.
THINKING_MODEL_PREFIXES = ("qwen3", "deepseek-r1", "magistral", "gpt-oss", "phi4-reasoning")


def _model_matches(installed: str, wanted: str) -> bool:
    return installed == wanted or installed.split(":")[0] == wanted.split(":")[0]


def api_key_for(config: ProviderConfig, env: dict[str, str] | None = None) -> str | None:
    environ = os.environ if env is None else env
    for var in config.env_vars:
        value = environ.get(var, "").strip()
        if value:
            return value
    return None


def ollama_host(env: dict[str, str] | None = None) -> str:
    host = (os.environ if env is None else env).get("OLLAMA_HOST", "").strip()
    if not host:
        return DEFAULT_OLLAMA_HOST
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.rstrip("/")


def ollama_models(env: dict[str, str] | None = None, timeout: float = 2.0) -> list[str]:
    """Locally pulled Ollama models, ya empty list agar daemon nahi chal raha."""
    try:
        with urllib.request.urlopen(f"{ollama_host(env)}/api/tags", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return []
    models = data.get("models") if isinstance(data, dict) else None
    return [m["name"] for m in models or [] if isinstance(m, dict) and m.get("name")]


def pick_ollama_model(installed: list[str], env: dict[str, str] | None = None) -> str:
    """Best locally available model chunta hai (APPFORGE_MODEL sabse upar)."""
    wanted = (os.environ if env is None else env).get("APPFORGE_MODEL", "").strip()
    if wanted:
        return next((m for m in installed if _model_matches(m, wanted)), wanted)
    if not installed:
        return PROVIDERS["ollama"].default_model
    for preferred in PREFERRED_OLLAMA_MODELS:
        match = next((m for m in installed if _model_matches(m, preferred)), None)
        if match:
            return match
    return installed[0]


def detect_provider(env: dict[str, str] | None = None, probe_local: bool = True) -> str | None:
    """Pick a provider: local Ollama pehle, phir jiski API key mile."""
    preferred = (os.environ if env is None else env).get("APPFORGE_PROVIDER", "").strip().lower()
    if preferred in PROVIDERS:
        return preferred
    if probe_local and ollama_models(env):
        return "ollama"
    for name, config in PROVIDERS.items():
        if not config.local and api_key_for(config, env):
            return name
    return None


class LLMClient:
    """Minimal chat client for local Ollama plus Anthropic, OpenAI and Gemini."""

    def __init__(
        self,
        provider: str,
        api_key: str = "",
        model: str | None = None,
        timeout: float = 900.0,
        max_tokens: int = 8000,
        progress: bool = False,
    ) -> None:
        if provider not in PROVIDERS:
            raise ProviderError(f"unknown provider '{provider}'")
        self.config = PROVIDERS[provider]
        self.provider = provider
        self.api_key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.progress = progress
        self.model = model or self._default_model()

    def _default_model(self) -> str:
        if self.provider != "ollama":
            return self.config.default_model
        return pick_ollama_model(ollama_models())

    def complete(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str:
        if self.provider == "ollama":
            return self._complete_ollama(system, user, schema)
        url, payload, headers = self._request(system, user)
        raw = self._post(url, payload, headers)
        return self._extract_text(raw)

    def _complete_ollama(
        self, system: str, user: str, schema: dict[str, Any] | None = None
    ) -> str:
        """Stream from the local daemon so slow CPU generations show progress."""
        payload = {
            "model": self.model,
            "stream": True,
            "format": schema or JSON_SCHEMA,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"num_ctx": 8192, "num_predict": self.max_tokens, "temperature": 0.2},
        }
        if self.model.startswith(THINKING_MODEL_PREFIXES):
            payload["think"] = False
        request = urllib.request.Request(
            f"{ollama_host()}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        chunks: list[str] = []
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for line in response:
                    text = self._ollama_chunk(line)
                    if not text:
                        continue
                    chunks.append(text)
                    if self.progress and len(chunks) % 20 == 0:
                        print(".", end="", file=sys.stderr, flush=True)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ProviderError(f"ollama error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(
                "ollama se connect nahi hua — `ollama serve` chalayein ya OLLAMA_HOST set karein "
                f"({exc.reason})"
            ) from exc
        if self.progress and chunks:
            print(file=sys.stderr)
        if not chunks:
            raise ProviderError(f"ollama ne khaali jawab diya (model: {self.model})")
        return "".join(chunks)

    @staticmethod
    def _ollama_chunk(line: bytes) -> str:
        stripped = line.strip()
        if not stripped:
            return ""
        try:
            data = json.loads(stripped.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(f"ollama stream parse nahi hua: {stripped[:200]!r}") from exc
        if data.get("error"):
            raise ProviderError(f"ollama error: {data['error']}")
        message = data.get("message") or {}
        return str(message.get("content") or "")

    def _request(self, system: str, user: str) -> tuple[str, dict[str, Any], dict[str, str]]:
        if self.provider == "anthropic":
            return (
                "https://api.anthropic.com/v1/messages",
                {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
        if self.provider == "openai":
            return (
                "https://api.openai.com/v1/chat/completions",
                {
                    "model": self.model,
                    "max_completion_tokens": self.max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                },
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "content-type": "application/json",
                },
            )
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "maxOutputTokens": self.max_tokens,
                    "responseMimeType": "application/json",
                },
            },
            {"x-goog-api-key": self.api_key, "content-type": "application/json"},
        )

    def _post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ProviderError(f"{self.provider} API error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"{self.provider} API tak pahunch nahi paya: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.provider} ne invalid JSON bheja") from exc

    def _extract_text(self, raw: dict[str, Any]) -> str:
        try:
            if self.provider == "anthropic":
                blocks = raw["content"]
                return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            if self.provider == "openai":
                return raw["choices"][0]["message"]["content"] or ""
            parts = raw["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.provider} response parse nahi hua: {raw}") from exc
