"""Focused local QA for the Caddy Web Bridge gateway policy."""
from __future__ import annotations

import http.client
import importlib.util
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_gate():
    path = ROOT / "gateway" / "rate_gate.py"
    spec = importlib.util.spec_from_file_location("leadflow_local_rate_gate", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UpstreamHandler(BaseHTTPRequestHandler):
    requests = []
    def log_message(self, _format, *_args): return
    def do_POST(self): self._capture()
    def do_OPTIONS(self): self._capture()
    def _capture(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.__class__.requests.append((self.command, dict(self.headers), self.rfile.read(length)))
        body = b'{"ok":true,"status":"received_qa"}'
        self.send_response(202); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


class WebGatewayTests(unittest.TestCase):
    def setUp(self):
        self.module = load_gate()
        UpstreamHandler.requests = []
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        self.upstream_thread = threading.Thread(target=self.upstream.serve_forever, daemon=True); self.upstream_thread.start()
        self.clock = [100.0]
        self.token = "authorized-boundary-token-" + "x" * 32
        self.config = self.module.GateConfig(
            "127.0.0.1", 8081, "/lead", "127.0.0.1", self.upstream.server_port, "/lead",
            frozenset({"https://form.example.invalid"}), self.token, 1024, 1, 2, 10,
            100,
        )
        self.server = self.module.GateServer(("127.0.0.1", 0), self.config, lambda: self.clock[0])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.upstream.shutdown(); self.upstream.server_close(); self.upstream_thread.join(timeout=2)

    def request(self, method="POST", path="/lead", origin="https://form.example.invalid", body=b"{}", extra=None):
        headers = {"Origin": origin, "Content-Type": "application/json", "X-LeadFlow-Rate-Key": "127.0.0.1"}
        headers.update(extra or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse(); raw = response.read(); connection.close()
        return response.status, dict(response.headers), json.loads(raw)

    def test_internal_header_spoofing_is_removed_and_boundary_token_is_injected(self):
        status, _, _ = self.request(extra={"X-LeadFlow-Abuse-Token": "attacker-value"})
        self.assertEqual(status, 202)
        _, headers, _ = UpstreamHandler.requests[0]
        self.assertEqual(headers["X-LeadFlow-Abuse-Token"], self.token)
        self.assertNotIn("attacker-value", json.dumps(headers))
        self.assertNotIn("X-LeadFlow-Rate-Key", headers)

    def test_methods_origin_size_and_missing_configuration_fail_closed(self):
        self.assertEqual(self.request("GET")[0], 405)
        self.assertEqual(self.request(origin="https://evil.example.invalid")[0], 403)
        self.assertEqual(self.request(body=b"x" * 1025)[0], 413)
        base = {
            "WEB_GATEWAY_POLICY_PORT": "8081", "WEB_GATEWAY_PUBLIC_PATH": "/lead",
            "WEB_GATEWAY_ALLOWED_ORIGINS": "https://form.example.invalid",
            "WEB_GATEWAY_UPSTREAM_URL": "http://web-bridge:8080/lead",
            "WEB_GATEWAY_MAX_BODY_BYTES": "1024", "WEB_GATEWAY_UPSTREAM_TIMEOUT_SECONDS": "1",
            "WEB_GATEWAY_RATE_REQUESTS": "2", "WEB_GATEWAY_RATE_WINDOW_SECONDS": "10",
            "WEB_GATEWAY_RATE_MAX_KEYS": "100",
            "WEB_BRIDGE_ABUSE_TOKEN": self.token,
        }
        for missing in ("WEB_GATEWAY_ALLOWED_ORIGINS", "WEB_GATEWAY_RATE_REQUESTS", "WEB_GATEWAY_RATE_MAX_KEYS", "WEB_BRIDGE_ABUSE_TOKEN"):
            with self.subTest(missing=missing), self.assertRaises(self.module.GateError):
                self.module.GateConfig.from_env({name: value for name, value in base.items() if name != missing})

    def test_rate_limit_is_effective_and_recovers_after_window(self):
        self.assertEqual(self.request()[0], 202)
        self.assertEqual(self.request()[0], 202)
        status, headers, body = self.request()
        self.assertEqual((status, body), (429, {"ok": False, "error": "rate_limited"}))
        self.assertEqual(headers["Retry-After"], "10")
        self.clock[0] += 11
        self.assertEqual(self.request()[0], 202)
        limiter = self.module.RateLimiter(1, 10, 1, lambda: self.clock[0])
        self.assertTrue(limiter.allow("192.0.2.1")[0])
        self.assertFalse(limiter.allow("192.0.2.2")[0])
        self.clock[0] += 11
        self.assertTrue(limiter.allow("192.0.2.2")[0])

    def test_caddy_tls_and_compose_isolate_bridge_exposure(self):
        caddy = (ROOT / "gateway" / "Caddyfile").read_text(encoding="utf-8")
        compose = (ROOT / "compose.web-gateway.local.yaml").read_text(encoding="utf-8")
        for expected in ("tls internal", "skip_install_trust", "method POST OPTIONS", "max_size", "read_header", "read_body", "-X-LeadFlow-Abuse-Token", "X-LeadFlow-Rate-Key"):
            self.assertIn(expected, caddy)
        self.assertNotIn("header_up -X-LeadFlow-Rate-Key", caddy)
        self.assertIn("header_up X-LeadFlow-Rate-Key {http.request.remote.host}", caddy)
        self.assertEqual(compose.count("\n    ports:"), 1)
        self.assertIn('"${WEB_GATEWAY_BIND_ADDRESS:-127.0.0.1}:${WEB_GATEWAY_HTTPS_PORT:', compose)
        caddy_service, rate_service = compose.split("  rate-gate:", 1)
        self.assertIn("- ingress", caddy_service)
        self.assertIn("- edge", caddy_service)
        self.assertNotIn("- bridge", caddy_service)
        self.assertNotIn("- ingress", rate_service.split("networks:", 1)[0])
        self.assertGreaterEqual(compose.count("internal: true"), 1)
        self.assertIn("web-gateway-local-ingress", compose)
        self.assertIn("WEB_BRIDGE_UPSTREAM_NETWORK", compose)

    def test_local_siteverify_override_is_internal_and_cannot_disable_qa_validation(self):
        override = (ROOT / "compose.web-bridge-local-integration.yaml").read_text(encoding="utf-8")
        fixture = (ROOT / "scripts" / "test" / "fixtures" / "siteverify.Caddyfile").read_text(encoding="utf-8")
        self.assertIn("internal: true", override)
        self.assertIn("challenges.cloudflare.com", override)
        self.assertIn("https://challenges.cloudflare.com/healthz", override)
        self.assertNotIn("https://127.0.0.1/healthz", override)
        self.assertIn("SSL_CERT_FILE: /siteverify-ca/root.crt", override)
        self.assertIn("siteverify_public_ca:/public-ca", override)
        self.assertIn("siteverify_public_ca:/siteverify-ca:ro", override)
        self.assertNotIn("siteverify_data:/siteverify-ca", override)
        self.assertIn("chmod 644 /public-ca/root.crt", override)
        self.assertIn('WEB_BRIDGE_TURNSTILE_PROXY_URL: ""', override)
        self.assertNotIn("WEB_BRIDGE_TURNSTILE_MODE", override)
        self.assertNotIn("ports:", override)
        self.assertIn("/turnstile/v0/siteverify", fixture)
        self.assertIn('"success":true', fixture)


if __name__ == "__main__":
    unittest.main(verbosity=2)
