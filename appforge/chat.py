"""Baat-cheet wala mode: user normal bhasha me baat kare, AI khud kaam bhi kar de.

Model har turn me tay karta hai ki sirf jawab dena hai, chhota app banana hai,
ya poora agent chalana hai. Sab kuch usi workspace folder ke andar hota hai.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from appforge import ai, naming, templates
from appforge.agent import Agent, AgentError
from appforge.ai import ChatClient, parse_spec_json
from appforge.providers import ProviderError
from appforge.spec import SpecError
from appforge.writer import WriteError, write_spec

MODES = ("baat", "app", "agent")

CHAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "mode": {"type": "string", "enum": list(MODES)},
        "task": {"type": "string"},
    },
    "required": ["reply", "mode"],
}

CHAT_SYSTEM = """Tum "Forge" ho — user ke apne computer par chalne wala coding partner.
Tum ek AI ho, par baat ekdum normal insaan ki tarah karo: chhoti, seedhi, dost jaisi.

Har jawab sirf ek JSON object hoga:
  {"reply": "...", "mode": "baat|app|agent", "task": "..."}

reply  -> user se baat. Usi bhasha me jisme usne likha (Hindi/Hinglish/English).
          1-3 line, aasan shabdon me. Bullet points aur bhaari technical bhasha se bacho.
          Kaam shuru kar rahe ho to bata do ki kya karne ja rahe ho.
mode   -> "baat"  = bas jawab dena hai, koi file nahi banani (sawaal, salah, hello, dhanyavaad)
          "app"   = user ne ek chhota app/website/script maanga hai (ek hi baar me ban jaye)
          "agent" = bada kaam: multi-file project, tests likhna, bug fix, maujooda code badalna
task   -> "app"/"agent" ke liye kaam ka saaf-saaf ek paragraph. "baat" me khaali chhod do.

Rules:
- Jhooth mat bolo. Jo kaam nahi hua use "ho gaya" mat kaho.
- User ki baat samajh na aaye to pehle ek chhota sawaal poochho (mode "baat").
- Chhoti chizen (ek page, ek script) = "app". Jahan chalakar test karna zaroori ho = "agent".
- reply hamesha user ki bhasha me. User Hinglish likhe to tum bhi Hinglish likho, English nahi.

Misaalein:
User: bhai ek dice roller page bana do
{"reply": "theek hai, ek chhota dice roller page bana deta hoon.", "mode": "app",
 "task": "dice roller web page: button dabao to 1-6 ka random number dikhe"}

User: build me a dice roller page
{"reply": "Sure, I'll put together a small dice roller page.", "mode": "app",
 "task": "dice roller web page with a roll button showing 1-6"}

User: tum kaun ho?
{"reply": "Main Forge hoon — isi computer par chalta hoon aur code likhne me madad karta hoon.",
 "mode": "baat"}
"""

TURN_TEMPLATE = """Workspace: {workspace}
{files}

Baat-cheet ab tak:
{history}

User: {text}

reply is bhasha me likho: {language}
Ab tumhara JSON jawab."""

# Roman Hindi pehchanne ke liye aam shabd.
HINGLISH_WORDS = frozenset(
    """aap hai hain ho kya kaise kar karo karna banao bana banana mujhe mera meri tum tumhara
    nahi nhi haan acha accha theek thik kyun kyu bhai yaar chahiye dena dedo bata batao bolo
    abhi phir wala wali koi kuch sab thoda zara jaldi ek do teen chalega chalu band""".split()
)


def detect_language(text: str) -> str:
    """User ki bhasha pehchano taaki jawab usi me aaye (chhote models bhool jate hain)."""
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        return "Hindi (Devanagari me)"
    words = {word.strip(".,!?").lower() for word in text.split()}
    if words & HINGLISH_WORDS:
        return "Hinglish (roman Hindi, jaise user ne likha)"
    return "English"


@dataclass
class Message:
    role: str
    text: str


@dataclass
class Turn:
    reply: str
    mode: str
    task: str = ""
    ok: bool = True
    detail: str = ""


@dataclass
class Chat:
    """Ek conversation, ek workspace."""

    client: ChatClient
    workspace: Path
    printer: Callable[[str], None] = print
    max_steps: int = 20
    history: list[Message] = field(default_factory=list)

    def send(self, text: str) -> Turn:
        text = text.strip()
        if not text:
            return Turn(reply="kuch likhiye to sahi 🙂", mode="baat")

        turn = self._decide(text)
        self.history.append(Message("user", text))
        self.history.append(Message("forge", turn.reply))
        self.printer(turn.reply)

        if turn.mode == "app":
            return self._build_app(turn)
        if turn.mode == "agent":
            return self._run_agent(turn)
        return turn

    def _decide(self, text: str) -> Turn:
        message = TURN_TEMPLATE.format(
            workspace=self.workspace,
            files=self._files(),
            history=self._history_text(),
            text=text,
            language=detect_language(text),
        )
        try:
            reply = self.client.complete(CHAT_SYSTEM, message, CHAT_SCHEMA)
            data = parse_spec_json(reply)
        except (ProviderError, SpecError) as exc:
            return Turn(reply=f"model se jawab nahi aaya ({exc})", mode="baat", ok=False)

        mode = str(data.get("mode", "baat")).strip()
        if mode not in MODES:
            mode = "baat"
        answer = str(data.get("reply", "")).strip() or "theek hai."
        task = str(data.get("task", "")).strip() or text
        return Turn(reply=answer, mode=mode, task=task)

    def _build_app(self, turn: Turn) -> Turn:
        name = naming.project_name(turn.task)
        out_dir = self.workspace / name
        try:
            spec = ai.build_spec(self.client, turn.task, name)
        except (ProviderError, SpecError) as exc:
            self.printer(f"(AI se nahi bana: {exc} — apne template se bana raha hoon)")
            spec = templates.build_spec(turn.task, None)
        try:
            write_spec(spec, out_dir, overwrite=True)
        except (WriteError, SpecError, OSError) as exc:
            turn.ok = False
            turn.detail = str(exc)
            self.printer(f"nahi ban paya: {exc}")
            return turn

        self.printer(f"\n{spec.name} — {spec.description}")
        for file in spec.files:
            self.printer(f"  + {file.path}")
        if spec.run_cmd:
            self.printer(f"chalane ke liye: cd {out_dir} && {spec.run_cmd}")
        turn.detail = str(out_dir)
        self.history.append(Message("forge", f"(banaya: {out_dir})"))
        return turn

    def _run_agent(self, turn: Turn) -> Turn:
        agent = Agent(
            client=self.client,
            workspace=self.workspace,
            max_steps=self.max_steps,
            printer=self.printer,
        )
        try:
            run = agent.run(turn.task)
        except AgentError as exc:
            turn.ok = False
            turn.detail = str(exc)
            self.printer(f"ruk gaya: {exc}")
            return turn

        turn.ok = run.finished
        turn.detail = run.summary
        files = sorted(set(run.files_written))
        self.printer(f"\n{run.summary}")
        self.history.append(
            Message("forge", f"(agent: {run.summary}; files: {', '.join(files) or 'koi nahi'})")
        )
        return turn

    def _history_text(self, keep: int = 8) -> str:
        if not self.history:
            return "(abhi kuch nahi)"
        return "\n".join(f"{m.role}: {m.text}" for m in self.history[-keep:])

    def _files(self, limit: int = 40) -> str:
        if not self.workspace.exists():
            return "Files: (folder abhi bana nahi)"
        paths = sorted(
            str(p.relative_to(self.workspace))
            for p in self.workspace.rglob("*")
            if p.is_file() and ".appforge" not in p.parts and not p.name.startswith(".")
        )
        if not paths:
            return "Files: (khaali)"
        shown = paths[:limit]
        extra = "" if len(paths) <= limit else f" (+{len(paths) - limit} more)"
        return "Files: " + ", ".join(shown) + extra
