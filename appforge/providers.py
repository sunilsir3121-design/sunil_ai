"""LLM providers. Zero dependencies: plain urllib + JSON over HTTPS."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class ProviderError(RuntimeError):
    """Raised when an LLM API call fails."""


@dataclass(frozen=True)
class ProviderConfig:
    """Describes how to talk to one LLM vendor."""

    name: str
    env_vars: tuple[str, ...]
    default_model: str


PROVIDERS: dict[str, ProviderConfig] = {
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


def api_key_for(config: ProviderConfig, env: dict[str, str] | None = None) -> str | None:
    environ = os.environ if env is None else env
    for var in config.env_vars:
        value = environ.get(var, "").strip()
        if value:
            return value
    return None


def detect_provider(env: dict[str, str] | None = None) -> str | None:
    """Return the first provider name that has an API key available."""
    preferred = (os.environ if env is None else env).get("APPFORGE_PROVIDER", "").strip().lower()
    order = [preferred] if preferred in PROVIDERS else []
    order += [name for name in PROVIDERS if name not in order]
    for name in order:
        if api_key_for(PROVIDERS[name], env):
            return name
    return None


class LLMClient:
    """Minimal chat client that works across Anthropic, OpenAI and Gemini."""

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str | None = None,
        timeout: float = 180.0,
        max_tokens: int = 8000,
    ) -> None:
        if provider not in PROVIDERS:
            raise ProviderError(f"unknown provider '{provider}'")
        self.config = PROVIDERS[provider]
        self.provider = provider
        self.api_key = api_key
        self.model = model or self.config.default_model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        url, payload, headers = self._request(system, user)
        raw = self._post(url, payload, headers)
        return self._extract_text(raw)

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
