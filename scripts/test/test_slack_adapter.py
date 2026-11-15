"""Focused Slack Incoming Webhook boundary tests."""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("slack_adapter", ROOT / "adapters" / "server.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)
REAL_CALL = adapter.call


class SlackAdapterTests(unittest.TestCase):
    def setUp(self):
        adapter.CONFIG = {"alert": "https://hooks.example.invalid/opaque", "attempts": 3, "delay1": 1, "delay2": 1, "timeout_ms": 10}
        adapter.call = REAL_CALL
        self.calls = []
        self.waits = []
        adapter.wait = lambda headers, status, attempt: self.waits.append((status, attempt))

    def scripted(self, responses):
        sequence = list(responses)
        def fake(method, url, body=None, headers=None, response_format="json"):
            self.calls.append((method, url, body, response_format))
            return sequence.pop(0)
        adapter.call = fake

    @staticmethod
    def payload():
        return {"execution_id": "lf_exec_synthetic", "stage": "enrichment", "error_code": "http_502"}

    def test_plain_text_ok_and_slack_format(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(b"ok")
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            adapter.CONFIG["alert"] = f"http://127.0.0.1:{server.server_port}/webhook"
            result = adapter.deliver_alert(self.payload())
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
        self.assertEqual(result, {"delivered": True, "alert_error_code": None, "retry_count": 0})
        self.assertEqual(received, [{"text": "LeadFlow alert | execution_id=lf_exec_synthetic | stage=enrichment | error_code=http_502"}])

    def test_permanent_rejection_is_not_retried(self):
        self.scripted([(400, {}, "invalid_payload")])
        result = adapter.deliver_alert(self.payload())
        self.assertFalse(result["delivered"])
        self.assertEqual(result["retry_count"], 0)
        self.assertEqual(len(self.calls), 1)

    def test_transport_failure_is_ambiguous_and_not_retried(self):
        self.scripted([(0, {}, "")])
        result = adapter.deliver_alert(self.payload())
        self.assertFalse(result["delivered"])
        self.assertEqual(result["retry_count"], 0)
        self.assertEqual(len(self.calls), 1)

    def test_slack_mock_accepts_wire_contract(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
        env = {**os.environ, "MOCK_KIND": "slack", "MOCK_PORT": str(port)}
        process = subprocess.Popen([sys.executable, str(ROOT / "mocks" / "server.py")], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(30):
                try:
                    urlopen(f"http://127.0.0.1:{port}/healthz", timeout=.2).read(); break
                except Exception: time.sleep(.05)
            else: self.fail("slack mock did not start")
            adapter.CONFIG["alert"] = f"http://127.0.0.1:{port}/webhook"
            adapter.CONFIG["timeout_ms"] = 1000
            self.assertTrue(adapter.deliver_alert(self.payload())["delivered"])
            stats = json.loads(urlopen(f"http://127.0.0.1:{port}/stats", timeout=1).read())
            self.assertEqual(stats["last_alert"], self.payload())
        finally:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)

    def test_explicit_temporary_rejection_uses_retry_budget(self):
        self.scripted([(503, {}, "unavailable"), (200, {}, "ok")])
        result = adapter.deliver_alert(self.payload())
        self.assertTrue(result["delivered"])
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(self.waits, [(503, 1)])


if __name__ == "__main__":
    unittest.main()
