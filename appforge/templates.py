"""Offline mode: bina API key ke bhi ek chalne wala app banata hai."""

from __future__ import annotations

from appforge.naming import keywords, project_name, project_title
from appforge.spec import AppSpec, GeneratedFile

KIND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "game": ("game", "khel", "snake", "arcade", "tetris", "pong"),
    "api": ("api", "backend", "rest", "endpoint", "server", "microservice"),
    "cli": ("cli", "terminal", "command-line", "commandline", "script"),
    "landing": ("landing", "portfolio", "website", "site", "homepage", "blog", "page"),
    "crud": ("todo", "task", "note", "notes", "list", "tracker", "expense", "diary", "contact"),
}

KINDS = tuple(KIND_KEYWORDS)


def detect_kind(prompt: str) -> str:
    words = set(keywords(prompt))
    for kind, triggers in KIND_KEYWORDS.items():
        if words.intersection(triggers):
            return kind
    return "crud"


def build_spec(prompt: str, kind: str | None = None) -> AppSpec:
    """Prompt se ek offline template app banata hai."""
    chosen = kind or detect_kind(prompt)
    builders = {
        "crud": _crud_app,
        "landing": _landing_app,
        "api": _api_app,
        "cli": _cli_app,
        "game": _game_app,
    }
    if chosen not in builders:
        raise ValueError(f"unknown template kind '{chosen}' (choose from {', '.join(builders)})")
    return builders[chosen](prompt)


def _fill(text: str, **values: str) -> str:
    for key, value in values.items():
        text = text.replace(f"__{key.upper()}__", value)
    return text


def _readme(title: str, prompt: str, run_cmd: str, extra: str = "") -> str:
    return _fill(
        README_TEMPLATE, title=title, prompt=prompt.strip(), run=run_cmd, extra=extra
    )


def _crud_app(prompt: str) -> AppSpec:
    title = project_title(prompt)
    run_cmd = "python3 -m http.server 8000"
    return AppSpec(
        name=project_name(prompt),
        description=f"{title} — browser CRUD app, data localStorage me save hota hai",
        files=[
            GeneratedFile("index.html", _fill(CRUD_HTML, title=title)),
            GeneratedFile("styles.css", BASE_CSS),
            GeneratedFile("app.js", CRUD_JS),
            GeneratedFile(
                "README.md",
                _readme(title, prompt, run_cmd, "Data browser ke localStorage me rehta hai."),
            ),
        ],
        run_cmd=run_cmd,
        notes=[f"Browser me http://localhost:8000 kholein ({title})."],
    )


def _landing_app(prompt: str) -> AppSpec:
    title = project_title(prompt)
    run_cmd = "python3 -m http.server 8000"
    return AppSpec(
        name=project_name(prompt),
        description=f"{title} — single page landing site",
        files=[
            GeneratedFile("index.html", _fill(LANDING_HTML, title=title)),
            GeneratedFile("styles.css", BASE_CSS + LANDING_CSS),
            GeneratedFile("README.md", _readme(title, prompt, run_cmd)),
        ],
        run_cmd=run_cmd,
        notes=["Text aur colors index.html / styles.css me badal sakte hain."],
    )


def _api_app(prompt: str) -> AppSpec:
    title = project_title(prompt)
    run_cmd = "python3 server.py"
    return AppSpec(
        name=project_name(prompt),
        description=f"{title} — Python stdlib REST API (zero dependencies)",
        files=[
            GeneratedFile("server.py", _fill(API_PY, title=title)),
            GeneratedFile(
                "README.md",
                _readme(title, prompt, run_cmd, API_README_EXTRA),
            ),
        ],
        run_cmd=run_cmd,
        notes=["Endpoints: GET/POST /api/items, GET/PUT/DELETE /api/items/<id>."],
    )


def _cli_app(prompt: str) -> AppSpec:
    title = project_title(prompt)
    run_cmd = "python3 main.py list"
    return AppSpec(
        name=project_name(prompt),
        description=f"{title} — Python CLI tool",
        files=[
            GeneratedFile("main.py", _fill(CLI_PY, title=title)),
            GeneratedFile("README.md", _readme(title, prompt, run_cmd, CLI_README_EXTRA)),
        ],
        run_cmd=run_cmd,
        notes=["`python3 main.py --help` se saare commands dekhein."],
    )


def _game_app(prompt: str) -> AppSpec:
    title = project_title(prompt)
    run_cmd = "python3 -m http.server 8000"
    return AppSpec(
        name=project_name(prompt),
        description=f"{title} — browser snake game (arrow keys / WASD)",
        files=[
            GeneratedFile("index.html", _fill(GAME_HTML, title=title)),
            GeneratedFile("styles.css", BASE_CSS + GAME_CSS),
            GeneratedFile("game.js", GAME_JS),
            GeneratedFile(
                "README.md", _readme(title, prompt, run_cmd, "Arrow keys ya WASD chalao.")
            ),
        ],
        run_cmd=run_cmd,
        notes=["http://localhost:8000 par khelein."],
    )


README_TEMPLATE = """# __TITLE__

AppForge se generate hua app.

> Prompt: __PROMPT__

## Chalane ka tarika

```bash
__RUN__
```

__EXTRA__
"""

API_README_EXTRA = """## Endpoints

| Method | Path              | Kaam                  |
| ------ | ----------------- | --------------------- |
| GET    | /api/items        | saare items           |
| POST   | /api/items        | naya item banayein    |
| GET    | /api/items/{id}   | ek item               |
| PUT    | /api/items/{id}   | item update           |
| DELETE | /api/items/{id}   | item delete           |

Data `data.json` me save hota hai.
"""

CLI_README_EXTRA = """## Commands

```bash
python3 main.py add "doodh lena hai"
python3 main.py list
python3 main.py done 1
python3 main.py remove 1
```
"""

BASE_CSS = """:root {
  --bg: #0f172a;
  --panel: #1e293b;
  --accent: #38bdf8;
  --text: #e2e8f0;
  --muted: #94a3b8;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100vh;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
  display: flex;
  justify-content: center;
  padding: 32px 16px;
}

main {
  width: 100%;
  max-width: 640px;
}

h1 { margin: 0 0 4px; font-size: 1.8rem; }

.subtitle { margin: 0 0 24px; color: var(--muted); }

.card {
  background: var(--panel);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
}

form { display: flex; gap: 8px; }

input[type="text"] {
  flex: 1;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid #334155;
  background: #0b1220;
  color: var(--text);
  font-size: 1rem;
}

button {
  padding: 12px 18px;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: #04283a;
  font-weight: 600;
  cursor: pointer;
}

button:hover { filter: brightness(1.08); }

ul { list-style: none; margin: 20px 0 0; padding: 0; }

li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 4px;
  border-bottom: 1px solid #334155;
}

li:last-child { border-bottom: none; }

li.done .label { text-decoration: line-through; color: var(--muted); }

.label { flex: 1; }

.ghost {
  background: transparent;
  color: var(--muted);
  padding: 6px 10px;
}

.empty { color: var(--muted); padding: 16px 4px; }
"""

LANDING_CSS = """
.hero { text-align: center; padding: 48px 0 16px; }
.hero h1 { font-size: 2.6rem; }
.features { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.feature h3 { margin: 0 0 6px; color: var(--accent); }
footer { text-align: center; color: var(--muted); padding: 32px 0 0; }
"""

GAME_CSS = """
canvas {
  display: block;
  margin: 16px auto 0;
  background: #04283a;
  border-radius: 12px;
  max-width: 100%;
}
.score { text-align: center; font-size: 1.2rem; }
"""

CRUD_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>__TITLE__</title>
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <main>
      <h1>__TITLE__</h1>
      <p class="subtitle">Add, complete aur delete karein. Sab kuch browser me save rehta hai.</p>
      <section class="card">
        <form id="form">
          <input id="input" type="text" placeholder="Naya item likhein..." autocomplete="off" />
          <button type="submit">Add</button>
        </form>
        <ul id="list"></ul>
        <p class="empty" id="empty">Abhi kuch nahi hai. Pehla item add karein.</p>
      </section>
    </main>
    <script src="app.js"></script>
  </body>
</html>
"""

CRUD_JS = """const STORAGE_KEY = "appforge.items";

const form = document.getElementById("form");
const input = document.getElementById("input");
const list = document.getElementById("list");
const empty = document.getElementById("empty");

let items = load();

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (error) {
    console.warn("stored data padha nahi ja saka", error);
    return [];
  }
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

function render() {
  list.innerHTML = "";
  empty.hidden = items.length > 0;

  items.forEach((item) => {
    const li = document.createElement("li");
    li.className = item.done ? "done" : "";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = item.done;
    checkbox.addEventListener("change", () => toggle(item.id));

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = item.text;

    const remove = document.createElement("button");
    remove.className = "ghost";
    remove.type = "button";
    remove.textContent = "delete";
    remove.addEventListener("click", () => destroy(item.id));

    li.append(checkbox, label, remove);
    list.append(li);
  });
}

function add(text) {
  items = [...items, { id: Date.now().toString(36), text, done: false }];
  save();
  render();
}

function toggle(id) {
  items = items.map((item) => (item.id === id ? { ...item, done: !item.done } : item));
  save();
  render();
}

function destroy(id) {
  items = items.filter((item) => item.id !== id);
  save();
  render();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  add(text);
  input.value = "";
  input.focus();
});

render();
"""

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>__TITLE__</title>
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <main>
      <section class="hero">
        <h1>__TITLE__</h1>
        <p class="subtitle">Ek command se bana hua landing page. Content yahin edit karein.</p>
        <button type="button" onclick="alert('Shukriya!')">Get started</button>
      </section>
      <section class="card features">
        <div class="feature">
          <h3>Fast</h3>
          <p>Sirf HTML aur CSS, koi build step nahi.</p>
        </div>
        <div class="feature">
          <h3>Responsive</h3>
          <p>Mobile aur desktop dono par theek dikhta hai.</p>
        </div>
        <div class="feature">
          <h3>Yours</h3>
          <p>Text, colors aur sections aap badal sakte hain.</p>
        </div>
      </section>
      <footer>AppForge se bana</footer>
    </main>
  </body>
</html>
"""

GAME_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>__TITLE__</title>
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <main>
      <h1>__TITLE__</h1>
      <p class="subtitle">Arrow keys ya WASD se snake chalao. Space se restart.</p>
      <section class="card">
        <p class="score">Score: <span id="score">0</span></p>
        <canvas id="board" width="400" height="400"></canvas>
      </section>
    </main>
    <script src="game.js"></script>
  </body>
</html>
"""

GAME_JS = """const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const scoreEl = document.getElementById("score");

const CELL = 20;
const COLS = canvas.width / CELL;
const ROWS = canvas.height / CELL;

let snake, direction, pending, food, score, alive;

function reset() {
  snake = [{ x: 8, y: 10 }, { x: 7, y: 10 }, { x: 6, y: 10 }];
  direction = { x: 1, y: 0 };
  pending = direction;
  score = 0;
  alive = true;
  placeFood();
  scoreEl.textContent = score;
}

function placeFood() {
  do {
    food = { x: Math.floor(Math.random() * COLS), y: Math.floor(Math.random() * ROWS) };
  } while (snake.some((part) => part.x === food.x && part.y === food.y));
}

function step() {
  if (!alive) return;
  direction = pending;
  const head = { x: snake[0].x + direction.x, y: snake[0].y + direction.y };

  const hitWall = head.x < 0 || head.y < 0 || head.x >= COLS || head.y >= ROWS;
  const hitSelf = snake.some((part) => part.x === head.x && part.y === head.y);
  if (hitWall || hitSelf) {
    alive = false;
    return;
  }

  snake.unshift(head);
  if (head.x === food.x && head.y === food.y) {
    score += 1;
    scoreEl.textContent = score;
    placeFood();
  } else {
    snake.pop();
  }
}

function draw() {
  ctx.fillStyle = "#04283a";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = "#f472b6";
  ctx.fillRect(food.x * CELL, food.y * CELL, CELL, CELL);

  ctx.fillStyle = "#38bdf8";
  snake.forEach((part) => ctx.fillRect(part.x * CELL, part.y * CELL, CELL - 2, CELL - 2));

  if (!alive) {
    ctx.fillStyle = "rgba(2, 6, 23, 0.75)";
    ctx.fillRect(0, canvas.height / 2 - 40, canvas.width, 80);
    ctx.fillStyle = "#e2e8f0";
    ctx.font = "20px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Game over - Space se restart", canvas.width / 2, canvas.height / 2 + 7);
  }
}

const KEYS = {
  ArrowUp: { x: 0, y: -1 }, w: { x: 0, y: -1 },
  ArrowDown: { x: 0, y: 1 }, s: { x: 0, y: 1 },
  ArrowLeft: { x: -1, y: 0 }, a: { x: -1, y: 0 },
  ArrowRight: { x: 1, y: 0 }, d: { x: 1, y: 0 },
};

document.addEventListener("keydown", (event) => {
  if (event.key === " ") {
    reset();
    return;
  }
  const next = KEYS[event.key];
  if (!next) return;
  event.preventDefault();
  if (next.x === -direction.x && next.y === -direction.y) return;
  pending = next;
});

reset();
setInterval(() => {
  step();
  draw();
}, 120);
"""

API_PY = '''"""__TITLE__ - zero dependency REST API (Python stdlib)."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
PORT = int(os.environ.get("PORT", "8000"))


def load_items():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, encoding="utf-8") as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError:
            return []


def save_items(items):
    with open(DATA_FILE, "w", encoding="utf-8") as handle:
        json.dump(items, handle, indent=2, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _item_id(self):
        parts = [part for part in self.path.split("/") if part]
        if len(parts) == 3 and parts[:2] == ["api", "items"]:
            return parts[2]
        return None

    def do_GET(self):
        items = load_items()
        item_id = self._item_id()
        if item_id is None:
            if self.path.rstrip("/") == "/api/items":
                self._send(200, items)
            else:
                self._send(404, {"error": "not found"})
            return
        for item in items:
            if item["id"] == item_id:
                self._send(200, item)
                return
        self._send(404, {"error": "item not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/api/items":
            self._send(404, {"error": "not found"})
            return
        payload = self._body()
        if payload is None or not str(payload.get("title", "")).strip():
            self._send(400, {"error": "'title' required"})
            return
        items = load_items()
        item = {
            "id": str(max([int(i["id"]) for i in items] or [0]) + 1),
            "title": str(payload["title"]).strip(),
            "done": bool(payload.get("done", False)),
        }
        items.append(item)
        save_items(items)
        self._send(201, item)

    def do_PUT(self):
        item_id = self._item_id()
        payload = self._body()
        if item_id is None or payload is None:
            self._send(400, {"error": "bad request"})
            return
        items = load_items()
        for item in items:
            if item["id"] == item_id:
                if "title" in payload:
                    item["title"] = str(payload["title"]).strip()
                if "done" in payload:
                    item["done"] = bool(payload["done"])
                save_items(items)
                self._send(200, item)
                return
        self._send(404, {"error": "item not found"})

    def do_DELETE(self):
        item_id = self._item_id()
        if item_id is None:
            self._send(400, {"error": "bad request"})
            return
        items = load_items()
        remaining = [item for item in items if item["id"] != item_id]
        if len(remaining) == len(items):
            self._send(404, {"error": "item not found"})
            return
        save_items(remaining)
        self._send(200, {"deleted": item_id})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("__TITLE__ API http://localhost:%d/api/items par chal raha hai" % PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
'''

CLI_PY = '''"""__TITLE__ - ek chhota CLI tool (Python stdlib)."""

import argparse
import json
import os
import sys

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.json")


def load():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, encoding="utf-8") as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError:
            return []


def save(items):
    with open(DATA_FILE, "w", encoding="utf-8") as handle:
        json.dump(items, handle, indent=2, ensure_ascii=False)


def cmd_add(args):
    items = load()
    items.append({"id": len(items) + 1, "text": args.text, "done": False})
    save(items)
    print("added: %s" % args.text)


def cmd_list(args):
    items = load()
    if not items:
        print("kuch nahi hai. `add` se item banayein.")
        return
    for item in items:
        mark = "x" if item["done"] else " "
        print("[%s] %d. %s" % (mark, item["id"], item["text"]))


def cmd_done(args):
    items = load()
    for item in items:
        if item["id"] == args.id:
            item["done"] = True
            save(items)
            print("done: %s" % item["text"])
            return
    sys.exit("id %d nahi mila" % args.id)


def cmd_remove(args):
    items = load()
    remaining = [item for item in items if item["id"] != args.id]
    if len(remaining) == len(items):
        sys.exit("id %d nahi mila" % args.id)
    save(remaining)
    print("removed %d" % args.id)


def build_parser():
    parser = argparse.ArgumentParser(description="__TITLE__")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="naya item")
    add.add_argument("text")
    add.set_defaults(func=cmd_add)

    listing = subparsers.add_parser("list", help="saare items")
    listing.set_defaults(func=cmd_list)

    done = subparsers.add_parser("done", help="item complete")
    done.add_argument("id", type=int)
    done.set_defaults(func=cmd_done)

    remove = subparsers.add_parser("remove", help="item delete")
    remove.add_argument("id", type=int)
    remove.set_defaults(func=cmd_remove)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
'''
