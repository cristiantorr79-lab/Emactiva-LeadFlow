"""Focused isolated tests for the stateless Web Bridge QA receiver."""
from __future__ import annotations

import http.client
import importlib.util
import io
import json
import sys
import threading
import unittest
from unittest import mock
from contextlib import redirect_stderr
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_receiver():
    path = ROOT / "bridge" / "qa_receiver.py"
    spec = importlib.util.spec_from_file_location("leadflow_qa_receiver", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_egress():
    path = ROOT / "bridge" / "qa_egress_proxy.py"
    spec = importlib.util.spec_from_file_location("leadflow_qa_egress", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class QaReceiverTests(unittest.TestCase):
    def setUp(self):
        self.module = load_receiver()
        self.key = "synthetic-webhook-key-" + "k" * 32
        self.config = self.module.ReceiverConfig.from_env({
            "QA_RECEIVER_BIND_HOST": "127.0.0.1",
            "QA_RECEIVER_PORT": "8090",
            "QA_RECEIVER_PATH": "/qa/receive",
            "QA_RECEIVER_MAX_BODY_BYTES": "4096",
            "QA_RECEIVER_TIMEOUT_SECONDS": "1",
            "LEADFLOW_WEBHOOK_KEY": self.key,
        })
        self.server = self.module.ReceiverServer(("127.0.0.1", 0), self.config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2); self.server = None

    @staticmethod
    def payload():
        return {
            "event_id": "web_" + "a" * 64,
            "source": "website",
            "lead": {"email": "synthetic@example.test", "first_name": "Synthetic"},
            "interaction": {"interest": "automatizacion", "message": "Synthetic request"},
        }

    def request(self, method="POST", payload=None, key=None, headers=None):
        body = json.dumps(self.payload() if payload is None else payload).encode() if not isinstance(payload, bytes) else payload
        values = {"Content-Type": "application/json", "Content-Length": str(len(body)), "X-LeadFlow-Key": self.key if key is None else key}
        values.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request(method, "/qa/receive", body=body, headers=values)
        response = connection.getresponse(); result = json.loads(response.read()); connection.close()
        return response.status, result

    def test_valid_post_returns_only_controlled_receipt(self):
        self.assertEqual(self.request(), (202, {"ok": True, "status": "received_qa"}))

    def test_authentication_missing_or_incorrect_is_rejected_without_sensitive_output(self):
        for key in ("", "wrong-key"):
            output = io.StringIO()
            with self.subTest(key=bool(key)), redirect_stderr(output):
                status, response = self.request(key=key)
            self.assertEqual((status, response), (403, {"ok": False, "error": "request_rejected"}))
            self.assertNotIn(key or self.key, output.getvalue() + json.dumps(response))

    def test_methods_invalid_json_and_oversized_payload_fail_closed(self):
        for method in ("PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
                connection.request(method, "/qa/receive")
                response = connection.getresponse(); body = json.loads(response.read()); connection.close()
                self.assertEqual((response.status, body), (405, {"ok": False, "error": "request_rejected"}))
        self.assertEqual(self.request(payload=b"{")[0], 400)
        self.assertEqual(self.request(headers={"Content-Length": "5000"})[0], 400)

    def test_invalid_payload_contract_is_rejected(self):
        cases = (
            {**self.payload(), "unexpected": True},
            {**self.payload(), "lead": {"email": "synthetic@example.test", "unknown": "x"}},
            {**self.payload(), "interaction": {}},
        )
        for payload in cases:
            with self.subTest(keys=set(payload)):
                self.assertEqual(self.request(payload=payload)[0], 400)

    def test_configuration_is_fail_closed(self):
        for change in ({"LEADFLOW_WEBHOOK_KEY": ""}, {"QA_RECEIVER_PATH": ""}, {"QA_RECEIVER_PORT": "invalid"}):
            values = {
                "QA_RECEIVER_PATH": "/qa/receive", "QA_RECEIVER_PORT": "8090",
                "LEADFLOW_WEBHOOK_KEY": self.key, **change,
            }
            with self.subTest(change=tuple(change)), self.assertRaises(self.module.ReceiverError):
                self.module.ReceiverConfig.from_env(values)

    def test_compose_is_internal_hardened_and_has_no_outbound_or_persistence(self):
        compose = (ROOT / "compose.web-bridge-qa-receiver.yaml").read_text(encoding="utf-8")
        source = (ROOT / "bridge" / "qa_receiver.py").read_text(encoding="utf-8")
        for expected in ('restart: "no"', "read_only: true", "cap_drop: [ALL]", "no-new-privileges:true", "internal: true"):
            self.assertIn(expected, compose)
        self.assertNotIn("\n    ports:", compose)
        self.assertNotIn("emactiva-leadflow", compose)
        self.assertNotIn("urllib", source)
        self.assertNotIn("HTTPSConnection", source)
        self.assertNotIn("open(", source)


class QaEgressTests(unittest.TestCase):
    def setUp(self):
        self.module = load_egress()

    def test_proxy_rejects_every_authority_except_cloudflare_siteverify(self):
        config = self.module.EgressConfig("127.0.0.1", 8899, 1, 65536)
        server = self.module.ProxyServer(("127.0.0.1", 0), config)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=2)))
        with mock.patch.object(self.module, "connect_allowed") as connect:
            client = __import__("socket").create_connection(server.server_address, timeout=2)
            client.sendall(b"CONNECT metadata.google.internal:80 HTTP/1.1\r\n\r\n")
            self.assertIn(b"403 Forbidden", client.recv(1024)); client.close()
            connect.assert_not_called()
        proxy_side, remote_side = __import__("socket").socketpair()
        with mock.patch.object(self.module, "connect_allowed", return_value=proxy_side) as connect:
            client = __import__("socket").create_connection(server.server_address, timeout=2)
            client.sendall(b"CONNECT challenges.cloudflare.com:443 HTTP/1.1\r\n\r\n")
            self.assertIn(b"200 Connection Established", client.recv(1024))
            client.close(); remote_side.close()
            connect.assert_called_once_with(1)

    def test_dns_results_must_all_be_global_and_compose_has_no_public_port(self):
        private = [(2, 1, 6, "", ("169.254.169.254", 443))]
        with mock.patch.object(self.module.socket, "getaddrinfo", return_value=private), self.assertRaises(self.module.EgressError):
            self.module.public_addresses("challenges.cloudflare.com", 443)
        compose = (ROOT / "compose.web-bridge-qa-receiver.yaml").read_text(encoding="utf-8")
        self.assertIn("dockerfile: Dockerfile.qa-egress", compose)
        self.assertIn("WEB_BRIDGE_QA_EGRESS_NETWORK", compose)
        self.assertNotIn("\n    ports:", compose)


if __name__ == "__main__":
    unittest.main(verbosity=2)
