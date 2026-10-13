import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile

from mini_se_workflow.demo import DEMO_TASK, DemoClient
from mini_se_workflow.store import RunStore
from mini_se_workflow.web import BusyError, WebApp, create_server
from mini_se_workflow.workflow import MiniSEWorkflow


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workflow = MiniSEWorkflow(DemoClient(), RunStore(self.temp.name), mode="demo")
        self.server = create_server(self.workflow, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, path, payload=None, headers=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read(), response.headers

    def test_page_health_and_invalid_requests(self):
        status, body, _ = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("Mini SE", body.decode())
        self.assertNotIn("innerHTML", body.decode())
        self.assertEqual(json.loads(self.request("/api/health")[1])["mode"], "demo")
        self.assertEqual(self.request("/api/run", {"task": ""})[0], 400)
        self.assertEqual(self.request("/api/run", {"task": "自由需求"})[0], 400)
        self.assertEqual(self.request("/api/run", {"task": DEMO_TASK}, {"Origin": "https://example.org"})[0], 403)
        self.assertEqual(self.request("/", headers={"Host": "example.org"})[0], 403)
        self.assertEqual(self.request("/api/runs/invalid")[0], 400)
        self.assertEqual(self.request("/api/runs/" + "0" * 16)[0], 404)

    def test_async_run_progress_history_and_zip_download(self):
        status, body, _ = self.request("/api/run", {"task": DEMO_TASK, "example_id": "todo"})
        self.assertEqual(status, 202)
        self.assertTrue(json.loads(body)["ok"])
        deadline = time.monotonic() + 20
        seen_running = False
        while time.monotonic() < deadline:
            result = json.loads(self.request("/api/status")[1])
            seen_running |= result["busy"]
            if not result["busy"]:
                break
            time.sleep(0.05)
        self.assertTrue(seen_running)
        self.assertFalse(result["busy"])
        self.assertEqual(result["state"]["status"], "approved")
        run_id = result["state"]["run_id"]
        history = json.loads(self.request("/api/runs")[1])["runs"]
        self.assertEqual(history[0]["run_id"], run_id)
        loaded = json.loads(self.request("/api/runs/" + run_id)[1])["state"]
        self.assertEqual(len(loaded["iterations"]), 2)
        status, body, headers = self.request("/api/download/" + run_id)
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIn("main.py", archive.namelist())
            self.assertIn("_workflow/design.json", archive.namelist())


class BusyTests(unittest.TestCase):
    def test_concurrent_run_is_rejected(self):
        entered = threading.Event()
        release = threading.Event()

        class WaitingClient(DemoClient):
            def complete_json(self, **kwargs):
                if kwargs["agent_name"] == "requirements":
                    entered.set()
                    release.wait(timeout=5)
                    return {"questions": ["需要确认"]}
                return super().complete_json(**kwargs)

        with tempfile.TemporaryDirectory() as temp:
            app = WebApp(MiniSEWorkflow(WaitingClient(), RunStore(temp), mode="demo"))
            app.start(DEMO_TASK)
            self.assertTrue(entered.wait(timeout=2))
            try:
                with self.assertRaises(BusyError):
                    app.start(DEMO_TASK)
            finally:
                release.set()
            deadline = time.monotonic() + 3
            while app.status()["busy"] and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(app.status()["busy"])


if __name__ == "__main__":
    unittest.main()
