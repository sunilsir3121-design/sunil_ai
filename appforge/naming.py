"""Prompt se project ka naam aur title nikalne ke helpers."""

from __future__ import annotations

import re

# Hinglish/English filler words jo naam me nahi chahiye.
STOP_WORDS = {
    "a", "an", "the", "app", "application", "please", "banao", "bana", "banado",
    "banaado", "de", "do", "dedo", "ek", "koi", "kuch", "mujhe", "muje", "chahiye",
    "create", "make", "build", "generate", "new", "simple", "aisa", "jo", "ke",
    "ka", "ki", "liye", "with", "for", "me", "my", "and", "aur", "hai",
}


def slugify(text: str, fallback: str = "app") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:40].strip("-") or fallback


def keywords(prompt: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", prompt.lower())
    return [word for word in words if word not in STOP_WORDS]


def project_name(prompt: str) -> str:
    picked = keywords(prompt)[:4]
    return slugify("-".join(picked) or "app") + "-app" if picked else "my-app"


def project_title(prompt: str) -> str:
    picked = keywords(prompt)[:4]
    if not picked:
        return "My App"
    return " ".join(word.capitalize() for word in picked)
