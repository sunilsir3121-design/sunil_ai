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
from appforge import workspace as ws
from appforge.agent import Agent, AgentError
from appforge.chat import Chat
from appforge.providers import (
    PROVIDERS,
    ProviderError,
    detect_provider,
    ollama_models,
    pick_ollama_model,
)
from appforge.safety import UnsafeAction
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
    margin: 0; height: 100vh; display: flex; flex-direction: column; overflow: hidden;
    font: 15px/1.6 system-ui, sans-serif; background: #0f1115; color: #e6e6e6;
  }
  header {
    padding: 10px 16px; border-bottom: 1px solid #1e2430;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  h1 { font-size: 18px; margin: 0; }
  .sub { color: #7d8797; font-size: 12px; }
  #app { flex: 1; display: flex; min-height: 0; }
  aside {
    width: 240px; border-right: 1px solid #1e2430; display: flex; flex-direction: column;
    min-height: 0;
  }
  .panel-title {
    padding: 8px 12px; font-size: 12px; letter-spacing: .08em; text-transform: uppercase;
    color: #7d8797; display: flex; justify-content: space-between; align-items: center;
  }
  .panel-title button { padding: 2px 8px; font-size: 12px; background: #232a36; }
  #tree { overflow: auto; padding: 0 6px 12px; flex: 1; }
  #tree div {
    padding: 3px 8px; border-radius: 6px; cursor: pointer; font-size: 13px; color: #b9c2d0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  #tree div:hover { background: #1b2130; }
  #tree div.active { background: #24304a; color: #fff; }
  #center { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  #tabs { display: flex; gap: 6px; padding: 8px 12px 0; }
  .tab {
    padding: 6px 14px; border-radius: 8px 8px 0 0; background: #161a22; color: #9aa4b2;
    cursor: pointer; font-size: 13px; border: 1px solid #232a36; border-bottom: 0;
  }
  .tab.active { background: #1f2735; color: #fff; }
  .pane { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .pane.hidden { display: none; }
  #chatlog { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column;
    gap: 14px; }
  .msg { max-width: 760px; width: 100%; margin: 0 auto; }
  .who { font-size: 12px; color: #7d8797; margin-bottom: 4px; }
  .body {
    background: #161a22; border: 1px solid #232a36; border-radius: 12px; padding: 10px 14px;
    white-space: pre-wrap; word-break: break-word;
  }
  .me .body { background: #1b2740; border-color: #26365a; }
  .body code, pre {
    font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap;
  }
  .body code { display: block; color: #9fb3d1; }
  .typing { color: #7d8797; }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; padding: 0 16px 8px; justify-content: center; }
  .chip {
    padding: 5px 12px; border-radius: 999px; background: #1b2130; color: #b9c2d0;
    cursor: pointer; font-size: 13px; border: 1px solid #2a2f3a;
  }
  form { display: flex; gap: 10px; padding: 10px 16px 14px; border-top: 1px solid #1e2430; }
  textarea, input, button { font: inherit; }
  textarea {
    flex: 1; padding: 10px 12px; border-radius: 10px; resize: none; max-height: 25vh;
    border: 1px solid #2a2f3a; background: #161a22; color: #e6e6e6;
  }
  button {
    padding: 10px 18px; border-radius: 10px; border: 0; cursor: pointer;
    background: #4f7cff; color: #fff; font-weight: 600;
  }
  button:disabled { background: #37415c; cursor: not-allowed; }
  #editorbar {
    display: flex; align-items: center; gap: 10px; padding: 8px 12px;
    border-bottom: 1px solid #1e2430;
  }
  #editpath { flex: 1; font: 13px ui-monospace, monospace; color: #9fb3d1; }
  #savemsg { color: #57d38c; font-size: 13px; }
  #code {
    flex: 1; width: 100%; border: 0; border-radius: 0; background: #0b0d12; color: #dbe3ee;
    padding: 14px; font: 13px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace; max-height: none;
    resize: none;
  }
  #terminal {
    height: 34%; min-height: 120px; border-top: 1px solid #1e2430;
    display: flex; flex-direction: column;
  }
  #terminal.closed { height: 38px; }
  #terminal.closed #termout, #terminal.closed #termform { display: none; }
  #termout {
    flex: 1; overflow: auto; margin: 0; padding: 10px 14px; background: #0b0d12;
    color: #cbd6e6; font-size: 13px;
  }
  #termform { border-top: 0; padding: 8px 12px 12px; }
  #cmd {
    flex: 1; padding: 9px 12px; border-radius: 10px; border: 1px solid #2a2f3a;
    background: #161a22; color: #e6e6e6; font-family: ui-monospace, monospace; font-size: 13px;
  }
  .dim { color: #7d8797; }
  .bad { color: #ff8f8f; }
</style>
<header>
  <h1>Forge</h1>
  <span class="sub">__PROVIDER__ &middot; __OUT__</span>
</header>
<div id="app">
  <aside>
    <div class="panel-title">Files <button id="refresh">refresh</button></div>
    <div id="tree"></div>
  </aside>
  <section id="center">
    <div id="tabs">
      <div class="tab active" data-pane="chatpane">Chat</div>
      <div class="tab" data-pane="editorpane" id="edittab">Editor</div>
    </div>

    <div class="pane" id="chatpane">
      <div id="chatlog">
        <div class="msg forge"><div class="who">Forge</div><div class="body">Namaste! Sab kuch
isi PC par chalta hai. Baat kariye, app banwaiye, files kholkar badliye, ya neeche terminal
me commands chalaiye.</div></div>
      </div>
      <div class="chips" id="chips">
        <span class="chip">ek todo app banao</span>
        <span class="chip">is folder me tests likhkar pass karao</span>
        <span class="chip">Python seekhna hai, kahan se shuru karun?</span>
      </div>
      <form id="form">
        <textarea id="text" rows="1"
          placeholder="kuch bhi likhiye... (Enter bhejne ke liye)"></textarea>
        <button id="go">Bhejo</button>
      </form>
    </div>

    <div class="pane hidden" id="editorpane">
      <div id="editorbar">
        <span id="editpath">koi file nahi khuli</span>
        <span id="savemsg"></span>
        <button id="save">Save</button>
      </div>
      <textarea id="code" spellcheck="false"
        placeholder="left se koi file kholiye..."></textarea>
    </div>

    <div id="terminal">
      <div class="panel-title">Terminal
        <button id="toggleterm">chhupao</button></div>
      <pre id="termout" class="dim">yahan command ka output aayega. Try: ls -la</pre>
      <form id="termform">
        <input id="cmd" placeholder="command likhiye, jaise: python3 app.py" autocomplete="off">
        <button>Run</button>
      </form>
    </div>
  </section>
</div>
<script>
const $ = (id) => document.getElementById(id);
const chatlog = $('chatlog');
let openPath = null;

// ---------- tabs ----------
document.querySelectorAll('.tab').forEach(tab => tab.onclick = () => showPane(tab.dataset.pane));
function showPane(id) {
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('hidden', p.id !== id));
  document.querySelectorAll('.tab').forEach(
    t => t.classList.toggle('active', t.dataset.pane === id));
}

// ---------- file tree ----------
async function loadTree() {
  const data = await (await fetch('/api/files')).json();
  const tree = $('tree');
  tree.innerHTML = '';
  if (!data.files.length) {
    const empty = document.createElement('div');
    empty.className = 'dim';
    empty.textContent = '(folder khaali hai)';
    tree.appendChild(empty);
    return;
  }
  data.files.forEach(path => {
    const item = document.createElement('div');
    item.textContent = path;
    item.title = path;
    if (path === openPath) item.classList.add('active');
    item.onclick = () => openFile(path);
    tree.appendChild(item);
  });
}

async function openFile(path) {
  const data = await (await fetch('/api/file?path=' + encodeURIComponent(path))).json();
  if (data.error) { $('savemsg').textContent = data.error; return; }
  openPath = path;
  $('editpath').textContent = path;
  $('edittab').textContent = path.split('/').pop();
  $('code').value = data.content;
  $('savemsg').textContent = '';
  showPane('editorpane');
  loadTree();
}

$('save').onclick = async () => {
  if (!openPath) return;
  const res = await fetch('/api/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path: openPath, content: $('code').value}),
  });
  const data = await res.json();
  $('savemsg').textContent = data.error ? data.error : 'save ho gaya';
  setTimeout(() => { $('savemsg').textContent = ''; }, 2500);
  loadTree();
};

$('refresh').onclick = loadTree;

// ---------- terminal ----------
$('toggleterm').onclick = () => {
  const closed = $('terminal').classList.toggle('closed');
  $('toggleterm').textContent = closed ? 'dikhao' : 'chhupao';
};

$('termform').onsubmit = async (e) => {
  e.preventDefault();
  const command = $('cmd').value.trim();
  if (!command) return;
  $('cmd').value = '';
  const out = $('termout');
  out.classList.remove('dim');
  out.textContent += (out.textContent.trim() && !out.textContent.startsWith('yahan') ? '\\n' : '');
  if (out.textContent.startsWith('yahan')) out.textContent = '';
  out.textContent += '$ ' + command + '\\n';
  out.scrollTop = out.scrollHeight;
  const res = await fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({command}),
  });
  const data = await res.json();
  let text = data.output || '';
  if (text && !text.endsWith('\\n')) text += '\\n';
  out.textContent += text + (data.ok ? '' : '[exit ' + data.code + ']\\n');
  out.scrollTop = out.scrollHeight;
  loadTree();
};

// ---------- chat ----------
function bubble(who, cls) {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + cls;
  wrap.innerHTML = '<div class="who"></div><div class="body"></div>';
  wrap.querySelector('.who').textContent = who;
  chatlog.appendChild(wrap);
  chatlog.scrollTop = chatlog.scrollHeight;
  return wrap.querySelector('.body');
}

function addLine(body, line) {
  const isLog = /^(\\s{2,}|\\[|\\||\\$)/.test(line);
  const el = document.createElement(isLog ? 'code' : 'div');
  el.textContent = line;
  body.appendChild(el);
  chatlog.scrollTop = chatlog.scrollHeight;
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
    const data = await (await fetch(`/api/log?job=${job}&from=${seen}`)).json();
    if (data.lines.length) {
      dots.remove();
      seen += data.lines.length;
      data.lines.forEach(line => addLine(body, line));
      loadTree();
    }
    if (data.done) {
      clearInterval(timer);
      dots.remove();
      $('go').disabled = false;
      $('text').focus();
      loadTree();
    }
  }, 800);
};

loadTree();
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

    def files(self) -> list[str]:
        return ws.list_files(self.workspace)

    def read_file(self, path: str) -> str:
        return ws.read_file(self.workspace, path)

    def save_file(self, path: str, content: str) -> str:
        return str(ws.save_file(self.workspace, path, content).relative_to(self.workspace))

    def run_command(self, command: str) -> ws.CommandResult:
        return ws.run(self.workspace, command)

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
            if url.path == "/api/files":
                self._json({"files": runner.files(), "root": str(runner.workspace)})
                return
            if url.path == "/api/file":
                path = parse_qs(url.query).get("path", [""])[0]
                try:
                    self._json({"path": path, "content": runner.read_file(path)})
                except (UnsafeAction, FileNotFoundError, ValueError, OSError) as exc:
                    self._json({"path": path, "error": str(exc)})
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
            if path not in {"/api/start", "/api/chat", "/api/save", "/api/run"}:
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
            if path == "/api/save":
                try:
                    saved = runner.save_file(
                        str(data.get("path", "")), str(data.get("content", ""))
                    )
                except (UnsafeAction, OSError) as exc:
                    self._json({"error": str(exc)})
                    return
                self._json({"saved": saved})
                return
            if path == "/api/run":
                result = runner.run_command(str(data.get("command", "")))
                self._json({"code": result.code, "output": result.output, "ok": result.ok})
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
