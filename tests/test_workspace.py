"""File tree, editor aur terminal ke helpers ke tests."""

import tempfile
import unittest
from pathlib import Path

from appforge import workspace as ws
from appforge.safety import UnsafeAction


class ListFilesTests(unittest.TestCase):
    def test_lists_files_and_skips_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print(1)")
            (root / "src").mkdir()
            (root / "src" / "util.py").write_text("x = 1")
            (root / "node_modules" / "pkg").mkdir(parents=True)
            (root / "node_modules" / "pkg" / "index.js").write_text("//")
            (root / ".appforge").mkdir()
            (root / ".appforge" / "agent-log.jsonl").write_text("{}")

            self.assertEqual(ws.list_files(root), ["app.py", "src/util.py"])

    def test_missing_folder_is_empty(self):
        self.assertEqual(ws.list_files(Path("/tmp/appforge-nahi-hai-xyz")), [])


class ReadWriteTests(unittest.TestCase):
    def test_read_and_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws.save_file(root, "notes/hello.txt", "namaste")
            self.assertEqual(ws.read_file(root, "notes/hello.txt"), "namaste")
            self.assertEqual(ws.list_files(root), ["notes/hello.txt"])

    def test_outside_workspace_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(UnsafeAction):
                ws.read_file(root, "../../etc/passwd")
            with self.assertRaises(UnsafeAction):
                ws.save_file(root, "/etc/passwd", "hack")

    def test_missing_file_and_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                ws.read_file(root, "nope.txt")
            (root / "pic.png").write_bytes(b"\x89PNG")
            with self.assertRaises(ValueError):
                ws.read_file(root, "pic.png")


class RunTests(unittest.TestCase):
    def test_command_runs_in_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("hi")
            result = ws.run(Path(tmp), "ls")

            self.assertTrue(result.ok)
            self.assertIn("a.txt", result.output)

    def test_failing_command_keeps_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ws.run(Path(tmp), "python3 -c 'import sys; sys.exit(3)'")
            self.assertFalse(result.ok)
            self.assertEqual(result.code, 3)

    def test_dangerous_command_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ws.run(Path(tmp), "sudo rm -rf /")
            self.assertFalse(result.ok)
            self.assertIn("allowed nahi", result.output)

    def test_timeout_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ws.run(Path(tmp), "sleep 5", timeout=0.5)
            self.assertEqual(result.code, 124)
            self.assertIn("khatam nahi hua", result.output)

    def test_empty_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(ws.run(Path(tmp), "  ").ok)


if __name__ == "__main__":
    unittest.main()
