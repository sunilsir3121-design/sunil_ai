"""Browser UI ke tests — offline (bina model ke) chalte hain."""

import json
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from appforge.ui import Job, Runner, make_handler, render_page


def wait_for(job: Job, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = job.snapshot(0)
        if snap["done"]:
            return snap
        time.sleep(0.05)
    raise AssertionError("job time par khatam nahi hua")


class JobTests(unittest.TestCase):
    def test_lines_stream_from_offset(self):
        job = Job()
        job.write("pehla\ndusra")
        self.assertEqual(job.snapshot(0)["lines"], ["pehla", "dusra"])
        self.assertEqual(job.snapshot(1)["lines"], ["dusra"])
        self.assertFalse(job.snapshot(0)["done"])

        job.finish(True, "ho gaya")
        snap = job.snapshot(2)
        self.assertEqual(snap["lines"], [])
        self.assertTrue(snap["done"])
        self.assertTrue(snap["ok"])
        self.assertEqual(snap["summary"], "ho gaya")


class RunnerTests(unittest.TestCase):
    def test_generate_without_model_uses_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner()
            runner._client = lambda job: None  # koi AI nahi
            job_id = runner.start("ek todo app banao", "app", tmp)
            snap = wait_for(runner.jobs[job_id])

            self.assertTrue(snap["ok"], snap["lines"])
            out_dir = Path(snap["summary"])
            self.assertTrue(out_dir.is_dir())
            self.assertTrue(any(out_dir.iterdir()))
            self.assertTrue(any("chalane ke liye" in line for line in snap["lines"]))

    def test_chat_without_model_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(workspace=Path(tmp))
            runner._client = lambda job: None
            job_id = runner.start_chat("namaste")
            snap = wait_for(runner.jobs[job_id])

            self.assertFalse(snap["ok"])
            self.assertTrue(any("Ollama" in line for line in snap["lines"]), snap["lines"])

    def test_chat_turn_streams_reply(self):
        replies = [json.dumps({"reply": "namaste! kya banana hai?", "mode": "baat"})]

        class Model:
            model = "fake"

            def complete(self, system, user, schema=None):
                return replies.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(workspace=Path(tmp))
            runner._client = lambda job: Model()
            job_id = runner.start_chat("namaste")
            snap = wait_for(runner.jobs[job_id])

            self.assertTrue(snap["ok"], snap["lines"])
            self.assertEqual(snap["lines"], ["namaste! kya banana hai?"])
            self.assertIsNotNone(runner.chat)

    def test_agent_needs_local_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner()
            runner._client = lambda job: None
            job_id = runner.start("kuch bada karo", "agent", tmp)
            snap = wait_for(runner.jobs[job_id])

            self.assertFalse(snap["ok"])
            self.assertIn("Ollama", snap["summary"])


class HttpTests(unittest.TestCase):
    def setUp(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread

        self.tmp = tempfile.TemporaryDirectory()
        self.runner = Runner(workspace=Path(self.tmp.name))
        self.runner._client = lambda job: None
        handler = make_handler(self.runner, render_page(Path(self.tmp.name)))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_page_loads(self):
        with urllib.request.urlopen(self.url) as response:
            body = response.read().decode("utf-8")
        self.assertIn("AppForge", body)
        self.assertNotIn("__PROVIDER__", body)
        self.assertIn(self.tmp.name, body)

    def test_start_and_poll_job(self):
        payload = json.dumps(
            {"prompt": "ek landing page banao", "mode": "app", "out": self.tmp.name}
        ).encode()
        request = urllib.request.Request(
            f"{self.url}/api/start", data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request) as response:
            job_id = json.loads(response.read())["job"]

        wait_for(self.runner.jobs[job_id])
        with urllib.request.urlopen(f"{self.url}/api/log?job={job_id}&from=0") as response:
            data = json.loads(response.read())

        self.assertTrue(data["done"])
        self.assertTrue(data["ok"], data["lines"])
        self.assertTrue(Path(data["summary"]).is_dir())

    def test_chat_endpoint_starts_job(self):
        payload = json.dumps({"text": "namaste"}).encode()
        request = urllib.request.Request(
            f"{self.url}/api/chat", data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request) as response:
            job_id = json.loads(response.read())["job"]

        snap = wait_for(self.runner.jobs[job_id])
        self.assertFalse(snap["ok"])  # is test me koi model nahi hai
        self.assertTrue(any("Ollama" in line for line in snap["lines"]))

    def test_unknown_job_reports_done(self):
        with urllib.request.urlopen(f"{self.url}/api/log?job=nope&from=0") as response:
            data = json.loads(response.read())
        self.assertTrue(data["done"])
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
