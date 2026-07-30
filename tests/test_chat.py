"""Baat-cheet mode ke tests — fake model se, koi Ollama zaroori nahi."""

import json
import tempfile
import unittest
from pathlib import Path

from appforge.chat import CHAT_SCHEMA, Chat, detect_language


class FakeChatModel:
    """Pehle chat turn ka jawab, phir baaki calls ke jawab (app spec / agent actions)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []
        self.schemas = []

    def complete(self, system, user, schema=None):
        self.prompts.append(user)
        self.schemas.append(schema)
        if not self.replies:
            raise AssertionError("model se zyada calls ho gayi")
        reply = self.replies.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply)


def make_chat(tmp, replies):
    lines = []
    model = FakeChatModel(replies)
    chat = Chat(client=model, workspace=Path(tmp), printer=lines.append)
    return chat, model, lines


class ChatTalkTests(unittest.TestCase):
    def test_plain_talk_does_not_touch_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat, model, lines = make_chat(
                tmp, [{"reply": "Namaste! kaise ho?", "mode": "baat"}]
            )
            turn = chat.send("hello")

            self.assertEqual(turn.mode, "baat")
            self.assertEqual(turn.reply, "Namaste! kaise ho?")
            self.assertEqual(lines, ["Namaste! kaise ho?"])
            self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertEqual(model.schemas[0], CHAT_SCHEMA)

    def test_history_goes_back_to_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat, model, _ = make_chat(
                tmp,
                [
                    {"reply": "main Forge hoon", "mode": "baat"},
                    {"reply": "haan, abhi bataya tha", "mode": "baat"},
                ],
            )
            chat.send("tumhara naam kya hai?")
            chat.send("phir se batao")

            self.assertIn("tumhara naam kya hai?", model.prompts[1])
            self.assertIn("main Forge hoon", model.prompts[1])
            self.assertEqual(len(chat.history), 4)

    def test_empty_message_is_handled(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat, model, _ = make_chat(tmp, [])
            turn = chat.send("   ")
            self.assertEqual(turn.mode, "baat")
            self.assertEqual(model.prompts, [])

    def test_unknown_mode_falls_back_to_talk(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat, _, _ = make_chat(tmp, [{"reply": "hmm", "mode": "kuch-bhi"}])
            self.assertEqual(chat.send("kya haal").mode, "baat")

    def test_broken_json_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat, _, _ = make_chat(tmp, ["ye JSON nahi hai"])
            turn = chat.send("kuch bhi")

            self.assertFalse(turn.ok)
            self.assertEqual(turn.mode, "baat")


class LanguageTests(unittest.TestCase):
    def test_language_detection(self):
        self.assertEqual(detect_language("नमस्ते, ऐप बनाओ"), "Hindi (Devanagari me)")
        self.assertTrue(detect_language("bhai ek todo app banao").startswith("Hinglish"))
        self.assertEqual(detect_language("build me a todo list"), "English")

    def test_language_hint_reaches_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat, model, _ = make_chat(tmp, [{"reply": "theek hai", "mode": "baat"}])
            chat.send("bhai kya haal hai")
            self.assertIn("Hinglish", model.prompts[0])


class ChatBuildTests(unittest.TestCase):
    def test_app_mode_writes_files(self):
        spec = {
            "name": "notes-app",
            "description": "chhota notes app",
            "files": [
                {
                    "path": "index.html",
                    "content": "<!doctype html><h1>notes</h1><ul id='list'></ul><script></script>",
                },
                {"path": "README.md", "content": "# notes"},
            ],
            "run_cmd": "python3 -m http.server 8000",
        }
        with tempfile.TemporaryDirectory() as tmp:
            chat, _, lines = make_chat(
                tmp,
                [
                    {"reply": "theek hai, notes app banata hoon", "mode": "app",
                     "task": "ek notes app banao"},
                    spec,
                ],
            )
            turn = chat.send("ek notes app banao")

            self.assertEqual(turn.mode, "app")
            self.assertTrue(turn.ok)
            out = Path(tmp) / "notes-app"
            self.assertTrue((out / "index.html").is_file())
            self.assertTrue(any("chalane ke liye" in line for line in lines))
            self.assertIn("theek hai", lines[0])

    def test_agent_mode_runs_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat, _, lines = make_chat(
                tmp,
                [
                    {"reply": "chalo hello.py banata hoon", "mode": "agent",
                     "task": "hello.py banao aur chalao"},
                    {"thought": "file", "action": "write_file", "path": "hello.py",
                     "content": "print('hi')\n"},
                    {"thought": "chalao", "action": "run", "command": "python3 hello.py"},
                    {"thought": "ho gaya", "action": "finish", "summary": "hello.py chal gaya"},
                ],
            )
            turn = chat.send("hello.py banao aur chalao")

            self.assertEqual(turn.mode, "agent")
            self.assertTrue(turn.ok, lines)
            self.assertEqual((Path(tmp) / "hello.py").read_text(), "print('hi')\n")
            self.assertIn("hello.py chal gaya", turn.detail)
            self.assertTrue(any("hi" in line for line in lines))

    def test_unfinished_agent_is_reported_honestly(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = []
            model = FakeChatModel(
                [
                    {"reply": "dekhta hoon", "mode": "agent", "task": "kuch karo"},
                    {"thought": "likhta hoon", "action": "write_file", "path": "a.txt",
                     "content": "kuch"},
                    {"thought": "aur likhta hoon", "action": "write_file", "path": "b.txt",
                     "content": "kuch aur"},
                ]
            )
            chat = Chat(
                client=model, workspace=Path(tmp), printer=lines.append, max_steps=2
            )
            turn = chat.send("kuch karo")

            self.assertFalse(turn.ok, "bina verify hue kaam poora nahi maana jana chahiye")
            self.assertIn("finish nahi hua", turn.detail)


if __name__ == "__main__":
    unittest.main()
