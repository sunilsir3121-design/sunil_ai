import json
import tempfile
import unittest
from pathlib import Path

from appforge import ai, naming, templates
from appforge.cli import main
from appforge.providers import PROVIDERS, LLMClient, ProviderError, api_key_for, detect_provider
from appforge.spec import AppSpec, SpecError
from appforge.writer import WriteError, safe_target, write_spec


class NamingTests(unittest.TestCase):
    def test_strips_hinglish_filler_words(self):
        self.assertEqual(naming.keywords("ek todo app banao"), ["todo"])

    def test_project_name_is_slug(self):
        self.assertEqual(naming.project_name("ek Todo List banao"), "todo-list-app")

    def test_empty_prompt_falls_back(self):
        self.assertEqual(naming.project_name("banao app"), "my-app")
        self.assertEqual(naming.project_title("banao app"), "My App")


class TemplateTests(unittest.TestCase):
    def test_detect_kind(self):
        self.assertEqual(templates.detect_kind("snake game banao"), "game")
        self.assertEqual(templates.detect_kind("items ka rest api banao"), "api")
        self.assertEqual(templates.detect_kind("terminal script banao"), "cli")
        self.assertEqual(templates.detect_kind("mera portfolio website"), "landing")
        self.assertEqual(templates.detect_kind("ek todo banao"), "crud")
        self.assertEqual(templates.detect_kind("kuch bhi random cheez"), "crud")

    def test_every_kind_builds_non_empty_files(self):
        for kind in templates.KINDS:
            spec = templates.build_spec("ek app banao", kind=kind)
            self.assertTrue(spec.files, kind)
            self.assertTrue(all(f.content.strip() for f in spec.files), kind)
            self.assertTrue(any(f.path == "README.md" for f in spec.files), kind)
            self.assertTrue(spec.run_cmd, kind)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            templates.build_spec("app", kind="hologram")

    def test_python_templates_are_valid_syntax(self):
        for kind in ("api", "cli"):
            spec = templates.build_spec("ek app banao", kind=kind)
            for file in spec.files:
                if file.path.endswith(".py"):
                    compile(file.content, file.path, "exec")


class SpecTests(unittest.TestCase):
    def test_round_trip(self):
        spec = templates.build_spec("todo app banao")
        restored = AppSpec.from_dict(json.loads(json.dumps(spec.to_dict())))
        self.assertEqual(restored.to_dict(), spec.to_dict())

    def test_missing_files_rejected(self):
        with self.assertRaises(SpecError):
            AppSpec.from_dict({"name": "x", "files": []})

    def test_bad_file_entry_rejected(self):
        with self.assertRaises(SpecError):
            AppSpec.from_dict({"files": [{"path": "a.py", "content": 3}]})


class AiParseTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(ai.parse_spec_json('{"name": "x"}'), {"name": "x"})

    def test_fenced_json(self):
        text = 'Sure!\n```json\n{"name": "x"}\n```\n'
        self.assertEqual(ai.parse_spec_json(text), {"name": "x"})

    def test_json_with_surrounding_prose(self):
        text = 'Here you go: {"name": "x", "note": "} not the end"} thanks!'
        self.assertEqual(ai.parse_spec_json(text)["name"], "x")

    def test_invalid_reply(self):
        with self.assertRaises(SpecError):
            ai.parse_spec_json("sorry, no json here")


class ProviderTests(unittest.TestCase):
    def test_detect_prefers_configured_provider(self):
        env = {"OPENAI_API_KEY": "a", "ANTHROPIC_API_KEY": "b", "APPFORGE_PROVIDER": "openai"}
        self.assertEqual(detect_provider(env), "openai")

    def test_detect_without_keys(self):
        self.assertIsNone(detect_provider({}))

    def test_gemini_accepts_google_key(self):
        self.assertEqual(api_key_for(PROVIDERS["gemini"], {"GOOGLE_API_KEY": "k"}), "k")

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ProviderError):
            LLMClient(provider="skynet", api_key="k")

    def test_request_shape_per_provider(self):
        expected_auth = {
            "anthropic": "x-api-key",
            "openai": "Authorization",
            "gemini": "x-goog-api-key",
        }
        for provider, header in expected_auth.items():
            client = LLMClient(provider=provider, api_key="secret")
            url, payload, headers = client._request("sys", "user")
            self.assertTrue(url.startswith("https://"), provider)
            self.assertIn(header, headers, provider)
            self.assertTrue(payload, provider)

    def test_extract_text_per_provider(self):
        samples = {
            "anthropic": {"content": [{"type": "text", "text": "hi"}]},
            "openai": {"choices": [{"message": {"content": "hi"}}]},
            "gemini": {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
        }
        for provider, raw in samples.items():
            client = LLMClient(provider=provider, api_key="secret")
            self.assertEqual(client._extract_text(raw), "hi", provider)

    def test_extract_text_on_garbage(self):
        client = LLMClient(provider="openai", api_key="secret")
        with self.assertRaises(ProviderError):
            client._extract_text({"unexpected": True})


class FakeClient:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user):
        self.system = system
        self.user = user
        return self.reply


class AiBuildTests(unittest.TestCase):
    def test_build_spec_from_model_reply(self):
        reply = json.dumps(
            {
                "name": "chat-app",
                "description": "demo",
                "files": [{"path": "index.html", "content": "<h1>hi</h1>"}],
                "run_cmd": "python3 -m http.server",
            }
        )
        client = FakeClient(reply)
        spec = ai.build_spec(client, "ek chat app banao", "chat-app")
        self.assertEqual(spec.name, "chat-app")
        self.assertEqual(spec.files[0].path, "index.html")
        self.assertIn("ek chat app banao", client.user)


class WriterTests(unittest.TestCase):
    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ("../evil.py", "/etc/passwd", "nested/../../evil.py"):
                with self.assertRaises(WriteError):
                    safe_target(Path(tmp), bad)

    def test_writes_nested_files(self):
        spec = templates.build_spec("snake game banao")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "out"
            written = write_spec(spec, root)
            self.assertEqual(len(written), len(spec.files))
            self.assertTrue((root / "game.js").exists())

    def test_refuses_overwrite_without_force(self):
        spec = templates.build_spec("todo app banao")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "out"
            write_spec(spec, root)
            with self.assertRaises(WriteError):
                write_spec(spec, root)
            write_spec(spec, root, overwrite=True)


class CliTests(unittest.TestCase):
    def test_requires_prompt(self):
        self.assertEqual(main([]), 2)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            args = ["ek todo app banao", "--offline", "-o", str(out), "--dry-run"]
            self.assertEqual(main(args), 0)
            self.assertFalse(out.exists())

    def test_offline_generation_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            self.assertEqual(main(["ek todo app banao", "--offline", "-o", str(out)]), 0)
            self.assertTrue((out / "index.html").exists())
            self.assertTrue((out / "README.md").exists())

    def test_list_templates(self):
        self.assertEqual(main(["--list-templates"]), 0)


if __name__ == "__main__":
    unittest.main()
