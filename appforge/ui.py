"""Browser UI: terminal ke bina AppForge chalane ke liye chhota local web app.

Sirf 127.0.0.1 par sunta hai — sab kuch aapke apne PC par rehta hai.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from appforge import ai, naming, templates
from appforge.agent import Agent, AgentError
from appforge.chat import Chat
from appforge.providers import (
    PROVIDERS,
    ProviderError,
    detect_provider,
    ollama_models,
    pick_ollama_model,
)
from appforge.spec import SpecError
from appforge.writer import WriteError, write_spec

PAGE = """<!doctype html>
<html lang="hi">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AppForge</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; height: 100vh; display: flex; flex-direction: column;
    font: 16px/1.6 system-ui, sans-serif; background: #0f1115; color: #e6e6e6;
  }
  header {
    padding: 14px 20px; border-bottom: 1px solid #1e2430;
    display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
  }
  h1 { font-size: 20px; margin: 0; }
  .sub { color: #7d8797; font-size: 13px; }
  main {
    flex: 1; overflow-y: auto; padding: 22px 16px;
    display: flex; flex-direction: column; gap: 16px;
  }
  .msg { max-width: 780px; width: 100%; margin: 0 auto; }
  .who { font-size: 12px; color: #7d8797; margin-bottom: 4px; }
  .body {
    background: #161a22; border: 1px solid #232a36; border-radius: 12px; padding: 12px 14px;
    white-space: pre-wrap; word-break: break-word;
  }
  .me .body { background: #1b2740; border-color: #26365a; }
  .body code {
    display: block; font: 13px/1.5 ui-monospace, monospace; color: #9fb3d1;
    white-space: pre-wrap;
  }
  .typing { color: #7d8797; }
  .chips {
    display: flex; gap: 8px; flex-wrap: wrap; padding: 0 16px 10px; justify-content: center;
  }
  .chip {
    padding: 6px 12px; border-radius: 999px; background: #1b2130; color: #b9c2d0;
    cursor: pointer; font-size: 14px; border: 1px solid #2a2f3a;
  }
  form {
    display: flex; gap: 10px; padding: 12px 16px 18px; border-top: 1px solid #1e2430;
    max-width: 812px; width: 100%; margin: 0 auto;
  }
  textarea, button { font: inherit; }
  textarea {
    flex: 1; padding: 12px; border-radius: 12px; resize: none; max-height: 30vh;
    border: 1px solid #2a2f3a; background: #161a22; color: #e6e6e6;
  }
  button {
    padding: 12px 22px; border-radius: 12px; border: 0; cursor: pointer;
    background: #4f7cff; color: #fff; font-weight: 600;
  }
  button:disabled { background: #37415c; cursor: not-allowed; }
</style>
<header>
  <h1>Forge</h1>
  <span class="sub">__PROVIDER__ &middot; folder: __OUT__</span>
</header>
<main id="chat">
  <div class="msg forge"><div class="who">Forge</div><div class="body">Namaste! Main aapke
computer par hi chalta hoon. Bataiye kya banana hai — ya bas aise hi baat kar lijiye.</div></div>
</main>
<div class="chips" id="chips">
  <span class="chip">ek todo app banao</span>
  <span class="chip">is folder me tests likhkar pass karao</span>
  <span class="chip">Python seekhna hai, kahan se shuru karun?</span>
</div>
<form id="form">
  <textarea id="text" rows="1"
    placeholder="kuch bhi likhiye... (Enter bhejne ke liye, Shift+Enter nayi line)"></textarea>
  <button id="go">Bhejo</button>
</form>
<script>
const $ = (id) => document.getElementById(id);
const chat = $('chat');

function bubble(who, cls) {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + cls;
  wrap.innerHTML = '<div class="who"></div><div class="body"></div>';
  wrap.querySelector('.who').textContent = who;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap.querySelector('.body');
}

function addLine(body, line) {
  const isLog = /^(\\s{2,}|\\[|\\||\\$)/.test(line) || line.startsWith('  +');
  const el = document.createElement(isLog ? 'code' : 'div');
  el.textContent = line;
  body.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

document.querySelectorAll('.chip').forEach(c =>
  c.onclick = () => { $('text').value = c.textContent; $('text').focus(); });

$('text').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('form').requestSubmit(); }
});

$('form').onsubmit = async (e) => {
  e.preventDefault();
  const text = $('text').value.trim();
  if (!text) return;
  $('chips').style.display = 'none';
  $('text').value = '';
  $('go').disabled = true;
  addLine(bubble('Aap', 'me'), text);
  const body = bubble('Forge', 'forge');
  const dots = document.createElement('div');
  dots.className = 'typing';
  dots.textContent = 'soch raha hoon...';
  body.appendChild(dots);

  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text}),
  });
  const {job} = await res.json();
  let seen = 0;
  const timer = setInterval(async () => {
    const r = await fetch(`/api/log?job=${job}&from=${seen}`);
    const data = await r.json();
    if (data.lines.length) {
      dots.remove();
      seen += data.lines.length;
      data.lines.forEach(line => addLine(body, line));
    }
    if (data.done) {
      clearInterval(timer);
      dots.remove();
      $('go').disabled = false;
      $('text').focus();
    }
  }, 800);
};
</script>
</html>
"""


@dataclass
class Job:
    """Ek background kaam aur uska live log."""

    lines: list[str] = field(default_factory=list)
    done: bool = False
    ok: bool = False
    summary: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)

    def write(self, text: str) -> None:
        with self.lock:
            self.lines.extend(text.rstrip("\n").split("\n"))

    def finish(self, ok: bool, summary: str) -> None:
        with self.lock:
            self.ok = ok
            self.summary = summary
            self.done = True

    def snapshot(self, start: int) -> dict[str, Any]:
        with self.lock:
            return {
                "lines": self.lines[start:],
                "done": self.done,
                "ok": self.ok,
                "summary": self.summary,
            }


class Runner:
    """UI se aane wale kaam chalata hai (chat, generate ya agent)."""

    def __init__(
        self,
        model: str | None = None,
        provider: str | None = None,
        workspace: Path | None = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.workspace = workspace or Path.home() / "AppForge"
        self.jobs: dict[str, Job] = {}
        self.chat: Chat | None = None
        self._next_id = 0

    def start_chat(self, text: str) -> str:
        """Ek chat turn background me chalao."""
        self._next_id += 1
        job_id = str(self._next_id)
        job = Job()
        self.jobs[job_id] = job
        threading.Thread(target=self._chat_turn, args=(job, text), daemon=True).start()
        return job_id

    def _chat_turn(self, job: Job, text: str) -> None:
        try:
            chat = self._conversation(job)
            if chat is None:
                job.finish(False, "model nahi mila")
                return
            turn = chat.send(text)
            job.finish(turn.ok, turn.detail or turn.reply)
        except (ProviderError, SpecError, WriteError, AgentError, OSError) as exc:
            job.write(f"gadbad ho gayi: {exc}")
            job.finish(False, str(exc))

    def _conversation(self, job: Job) -> Chat | None:
        if self.chat is None:
            client = self._client(job)
            if client is None:
                job.write(
                    "baat karne ke liye local model chahiye. Ollama chalu karein: "
                    "`ollama serve` aur `ollama pull qwen2.5-coder:3b`."
                )
                return None
            self.workspace.mkdir(parents=True, exist_ok=True)
            self.chat = Chat(client=client, workspace=self.workspace, printer=job.write)
        else:
            self.chat.printer = job.write
        return self.chat

    def start(self, prompt: str, mode: str, out: str) -> str:
        self._next_id += 1
        job_id = str(self._next_id)
        job = Job()
        self.jobs[job_id] = job
        target = (Path(out).expanduser() if out else Path.home() / "AppForge").resolve()
        worker = threading.Thread(
            target=self._run, args=(job, prompt, mode, target), daemon=True
        )
        worker.start()
        return job_id

    def _client(self, job: Job):  # noqa: ANN202 - LLMClient ya None
        from appforge.cli import make_client  # local import: circular import se bachne ke liye

        provider = self.provider or detect_provider()
        if provider is None:
            job.write("local AI (Ollama) nahi mila — template se bana raha hoon")
            return None
        return make_client(provider, self.model)

    def _run(self, job: Job, prompt: str, mode: str, target: Path) -> None:
        try:
            if mode == "agent":
                self._run_agent(job, prompt, target)
            else:
                self._run_generate(job, prompt, target)
        except (ProviderError, SpecError, WriteError, AgentError, OSError) as exc:
            job.write(f"error: {exc}")
            job.finish(False, str(exc))

    def _run_agent(self, job: Job, prompt: str, target: Path) -> None:
        client = self._client(job)
        if client is None:
            job.finish(False, "agent mode ke liye Ollama chahiye")
            return
        target.mkdir(parents=True, exist_ok=True)
        job.write(f"agent chalu ({client.model}) — folder: {target}")
        agent = Agent(client=client, workspace=target, printer=job.write)
        run = agent.run(prompt)
        failed = sum(1 for step in run.steps if not step.ok)
        job.write(f"\n{len(run.steps)} steps, {failed} fail — {run.summary}")
        job.finish(run.finished, f"{run.summary} ({target})")

    def _run_generate(self, job: Job, prompt: str, target: Path) -> None:
        client = self._client(job)
        name = naming.project_name(prompt)
        out_dir = target / name
        if client is not None:
            job.write(f"{client.model} soch raha hai... (thoda time lagta hai)")
            try:
                spec = ai.build_spec(client, prompt, name)
            except (ProviderError, SpecError) as exc:
                job.write(f"AI se nahi bana ({exc}) — template se bana raha hoon")
                spec = templates.build_spec(prompt, None)
        else:
            spec = templates.build_spec(prompt, None)

        write_spec(spec, out_dir, overwrite=True)
        job.write(f"\n{spec.name} — {spec.description}")
        for file in spec.files:
            job.write(f"  + {file.path}")
        if spec.install_cmd:
            job.write(f"\ninstall: {spec.install_cmd}")
        if spec.run_cmd:
            job.write(f"chalane ke liye: cd {out_dir} && {spec.run_cmd}")
        job.finish(True, str(out_dir))


def make_handler(runner: Runner, page: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:  # server ka shor band
            pass

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict[str, Any]) -> None:
            self._send(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            url = urlparse(self.path)
            if url.path == "/":
                self._send(page.encode("utf-8"), "text/html; charset=utf-8")
                return
            if url.path == "/api/log":
                query = parse_qs(url.query)
                job = runner.jobs.get(query.get("job", [""])[0])
                if job is None:
                    self._json({"lines": [], "done": True, "ok": False, "summary": "job nahi mila"})
                    return
                start = int(query.get("from", ["0"])[0])
                self._json(job.snapshot(start))
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            path = urlparse(self.path).path
            if path not in {"/api/start", "/api/chat"}:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_error(400)
                return
            if path == "/api/chat":
                self._json({"job": runner.start_chat(str(data.get("text", "")).strip())})
                return
            job_id = runner.start(
                str(data.get("prompt", "")).strip(),
                str(data.get("mode", "app")),
                str(data.get("out", "")),
            )
            self._json({"job": job_id})

    return Handler


def render_page(out_dir: Path) -> str:
    provider = detect_provider()
    models = ollama_models()
    if provider and PROVIDERS[provider].local and models:
        info = f"local model: {pick_ollama_model(models)} (private, koi internet nahi)"
    elif provider:
        info = f"provider: {provider}"
    else:
        info = "AI nahi mila — built-in templates se banega"
    return PAGE.replace("__PROVIDER__", info).replace("__OUT__", str(out_dir))


def serve(
    host: str = "127.0.0.1",
    port: int = 7788,
    out_dir: Path | None = None,
    model: str | None = None,
    provider: str | None = None,
    open_browser: bool = True,
    printer: Callable[[str], None] = print,
) -> None:
    """Local UI chalao (Ctrl+C se band)."""
    target = out_dir or Path.home() / "AppForge"
    runner = Runner(model=model, provider=provider, workspace=target)
    server = ThreadingHTTPServer((host, port), make_handler(runner, render_page(target)))
    url = f"http://{host}:{port}"
    printer(f"AppForge UI: {url}  (band karne ke liye Ctrl+C)")
    if open_browser:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        printer("\nUI band.")
    finally:
        server.server_close()
