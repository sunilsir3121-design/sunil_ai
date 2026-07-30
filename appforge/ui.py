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
  body { margin: 0; font: 16px/1.5 system-ui, sans-serif; background: #0f1115; color: #e6e6e6; }
  main { max-width: 860px; margin: 0 auto; padding: 24px 16px 64px; }
  h1 { font-size: 26px; margin: 0 0 4px; }
  p.sub { margin: 0 0 20px; color: #9aa4b2; }
  textarea, input, select, button { font: inherit; }
  textarea {
    width: 100%; min-height: 92px; padding: 12px; border-radius: 10px;
    border: 1px solid #2a2f3a; background: #161a22; color: #e6e6e6; resize: vertical;
  }
  .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin: 12px 0; }
  .row label { color: #9aa4b2; }
  input[type=text] {
    flex: 1; min-width: 220px; padding: 10px 12px; border-radius: 10px;
    border: 1px solid #2a2f3a; background: #161a22; color: #e6e6e6;
  }
  button {
    padding: 12px 22px; border-radius: 10px; border: 0; cursor: pointer;
    background: #4f7cff; color: #fff; font-weight: 600;
  }
  button:disabled { background: #37415c; cursor: not-allowed; }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
  .chip {
    padding: 6px 12px; border-radius: 999px; background: #1b2130; color: #b9c2d0;
    cursor: pointer; font-size: 14px; border: 1px solid #2a2f3a;
  }
  pre {
    background: #0b0d12; border: 1px solid #2a2f3a; border-radius: 10px; padding: 14px;
    min-height: 220px; max-height: 55vh; overflow: auto; white-space: pre-wrap;
    word-break: break-word; font-size: 14px;
  }
  .status { margin: 10px 0; color: #9aa4b2; }
  .ok { color: #57d38c; } .bad { color: #ff7a7a; }
</style>
<main>
  <h1>AppForge</h1>
  <p class="sub">Hindi/English me likhiye, app ban jayega. Sab kuch aapke PC par — __PROVIDER__</p>

  <div class="chips">
    <span class="chip">ek todo app banao</span>
    <span class="chip">ek calculator web app banao</span>
    <span class="chip">ek notes REST API banao</span>
    <span class="chip">ek portfolio landing page banao</span>
  </div>

  <textarea id="prompt"
    placeholder="jaise: ek todo app banao jisme task add aur delete ho"></textarea>

  <div class="row">
    <label><input type="radio" name="mode" value="app" checked> App banao (tez)</label>
    <label><input type="radio" name="mode" value="agent">
      Agent — bada kaam (files + tests + fix)</label>
  </div>
  <div class="row">
    <label for="out">Folder</label>
    <input type="text" id="out" value="__OUT__">
    <button id="go">Banao</button>
  </div>

  <div class="status" id="status">taiyaar</div>
  <pre id="log">yahan live progress dikhega...</pre>
</main>
<script>
const $ = (id) => document.getElementById(id);
let timer = null;

document.querySelectorAll('.chip').forEach(c =>
  c.onclick = () => { $('prompt').value = c.textContent; });

$('go').onclick = async () => {
  const prompt = $('prompt').value.trim();
  if (!prompt) { $('status').textContent = 'pehle likhiye kya banana hai'; return; }
  $('go').disabled = true;
  $('log').textContent = '';
  $('status').textContent = 'chal raha hai... (local model soch raha hai)';
  const mode = document.querySelector('input[name=mode]:checked').value;
  const res = await fetch('/api/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({prompt, mode, out: $('out').value.trim()}),
  });
  const {job} = await res.json();
  let seen = 0;
  timer = setInterval(async () => {
    const r = await fetch(`/api/log?job=${job}&from=${seen}`);
    const data = await r.json();
    if (data.lines.length) {
      seen += data.lines.length;
      $('log').textContent += data.lines.join('\\n') + '\\n';
      $('log').scrollTop = $('log').scrollHeight;
    }
    if (data.done) {
      clearInterval(timer);
      $('go').disabled = false;
      $('status').innerHTML = data.ok
        ? '<span class="ok">ho gaya:</span> ' + data.summary
        : '<span class="bad">gadbad:</span> ' + data.summary;
    }
  }, 900);
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
    """UI se aane wale kaam chalata hai (generate ya agent)."""

    def __init__(self, model: str | None = None, provider: str | None = None) -> None:
        self.model = model
        self.provider = provider
        self.jobs: dict[str, Job] = {}
        self._next_id = 0

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
            if urlparse(self.path).path != "/api/start":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_error(400)
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
    runner = Runner(model=model, provider=provider)
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
