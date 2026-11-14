"""Isolated HTTP tests for the Emactiva form bridge."""
from __future__ import annotations

import http.client
import hashlib
import hmac
import importlib.util
import io
import json
import socket
import sys
import threading
import time
import unittest
from unittest import mock
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_bridge():
    path = ROOT / "bridge/server.py"
    spec = importlib.util.spec_from_file_location("leadflow_web_bridge", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UpstreamHandler(BaseHTTPRequestHandler):
    requests = []
    response_status = 200
    delay = 0.0

    def log_message(self, *_args):
        return

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        type(self).requests.append((self.path, dict(self.headers), json.loads(self.rfile.read(length))))
        if type(self).delay:
            time.sleep(type(self).delay)
        try:
            self.send_response(type(self).response_status)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
        except (BrokenPipeError, ConnectionResetError):
            pass


class WebBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = load_bridge()
        UpstreamHandler.requests = []
        UpstreamHandler.response_status = 200
        UpstreamHandler.delay = 0.0
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        self.upstream_thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
        self.upstream_thread.start()
        self.addCleanup(self.stop_upstream)
        self.env = {
            "WEB_BRIDGE_ENV": "production",
            "WEB_BRIDGE_BIND_HOST": "127.0.0.1",
            "WEB_BRIDGE_BIND_PORT": "8080",
            "WEB_BRIDGE_PUBLIC_PATH": "/contacto",
            "WEB_BRIDGE_UPSTREAM_URL": f"http://127.0.0.1:{self.upstream.server_port}/webhook/leadflow",
            "WEB_BRIDGE_SOURCE": "emactiva_web",
            "WEB_BRIDGE_EVENT_ID_KEY": "event-id-" + "i" * 40,
            "WEB_BRIDGE_ALLOWED_ORIGINS": "https://form.example.invalid",
            "WEB_BRIDGE_ABUSE_CONTROL": "external",
            "WEB_BRIDGE_ABUSE_TOKEN": "abuse-" + "a" * 40,
            "WEB_BRIDGE_MAX_BODY_BYTES": "4096",
            "WEB_BRIDGE_REQUEST_TIMEOUT_SECONDS": "1",
            "WEB_BRIDGE_UPSTREAM_TIMEOUT_SECONDS": "1",
            "WEB_BRIDGE_TURNSTILE_MODE": "siteverify",
            "WEB_BRIDGE_TURNSTILE_SECRET_KEY": "turnstile-" + "t" * 32,
            "WEB_BRIDGE_TURNSTILE_HOSTNAMES": "form.example.invalid",
            "WEB_BRIDGE_TURNSTILE_ACTION": "lead_submit",
            "WEB_BRIDGE_TURNSTILE_TIMEOUT_SECONDS": "1",
            "LEADFLOW_WEBHOOK_KEY": "webhook-" + "w" * 40,
            "LEADFLOW_ALLOWED_SOURCES": "emactiva_web,other",
            "LEADFLOW_ALLOWED_INTERESTS": "automatizacion,consultoria",
        }
        self.config = self.bridge.BridgeConfig.from_env(self.env)
        self.real_verify_turnstile = self.bridge.verify_turnstile
        self.turnstile_verifier = mock.patch.object(self.bridge, "verify_turnstile", autospec=True).start()
        self.addCleanup(mock.patch.stopall)
        self.server = self.bridge.BridgeServer(("127.0.0.1", 0), self.config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_bridge)

    def stop_bridge(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.server = None

    def stop_upstream(self):
        if self.upstream:
            self.upstream.shutdown()
            self.upstream.server_close()
            self.upstream_thread.join(timeout=2)
            self.upstream = None

    def request(self, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode()
        request_headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "Origin": "https://form.example.invalid",
            "X-LeadFlow-Abuse-Token": self.env["WEB_BRIDGE_ABUSE_TOKEN"],
            "X-LeadFlow-Submission-Id": "018f47a2-4e12-4d85-8a61-ec9ce6ad3d70",
            "X-Turnstile-Token": "synthetic-turnstile-token",
        }
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request("POST", "/contacto", body, request_headers)
        response = connection.getresponse()
        value = json.loads(response.read())
        connection.close()
        return response.status, value

    def valid_payload(self):
        return {
            "nombre": "Nombre Sintetico", "apellido": "Apellido Sintetico",
            "email": "synthetic@example.test", "negocio": "Empresa Sintetica",
            "telefono": "+15550100000", "interes": "automatizacion",
            "mensaje": "Consulta sintetica.",
        }

    def test_valid_request_maps_contract_and_uses_server_key(self):
        status, response = self.request(self.valid_payload())
        self.assertEqual((status, response), (202, {"ok": True, "status": "accepted"}))
        path, headers, payload = UpstreamHandler.requests[0]
        self.assertEqual(path, "/webhook/leadflow")
        self.assertEqual(headers["X-LeadFlow-Key"], self.env["LEADFLOW_WEBHOOK_KEY"])
        self.assertEqual(set(payload), {"event_id", "source", "lead", "interaction"})
        self.assertEqual(payload["source"], "emactiva_web")
        self.assertEqual(payload["lead"]["email"], "synthetic@example.test")
        self.assertNotIn("nombre", payload)

    def test_same_submission_id_and_request_has_stable_purpose_separated_identity(self):
        first = self.valid_payload()
        second = {**first, "email": "  SYNTHETIC@example.test ", "mensaje": " Consulta sintetica. "}
        self.request(first)
        self.request(second)
        event_ids = [request[2]["event_id"] for request in UpstreamHandler.requests]
        self.assertEqual(event_ids[0], event_ids[1])
        self.assertRegex(event_ids[0], r"^web_[0-9a-f]{64}$")
        self.assertNotIn("synthetic", event_ids[0])
        expected = hmac.new(
            self.env["WEB_BRIDGE_EVENT_ID_KEY"].encode(),
            b"LF015-WEB-EVENT-ID-V1\x00" + b"018f47a2-4e12-4d85-8a61-ec9ce6ad3d70",
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(event_ids[0], "web_" + expected)

    def test_different_submission_ids_create_distinct_events_for_identical_content(self):
        payload = self.valid_payload()
        self.request(payload)
        self.request(payload, {"X-LeadFlow-Submission-Id": "018f47a2-4e12-4d85-9b72-fda8c7be4e81"})
        event_ids = [request[2]["event_id"] for request in UpstreamHandler.requests]
        self.assertNotEqual(event_ids[0], event_ids[1])

    def test_invalid_submission_id_is_rejected_before_forwarding(self):
        for value in ("", "not-a-uuid", "018f47a2-4e12-1d85-8a61-ec9ce6ad3d70", "018F47A2-4E12-4D85-8A61-EC9CE6AD3D70"):
            with self.subTest(value=value):
                status, response = self.request(self.valid_payload(), {"X-LeadFlow-Submission-Id": value})
                self.assertEqual((status, response), (400, {"ok": False, "error": "invalid_request"}))
        self.assertEqual(UpstreamHandler.requests, [])

    def test_preflight_allows_only_client_visible_submission_header(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request("OPTIONS", "/contacto", headers={"Origin": "https://form.example.invalid"})
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)
        self.assertEqual(response.getheader("Access-Control-Allow-Headers"), "Content-Type, X-LeadFlow-Submission-Id, X-Turnstile-Token")
        self.assertNotIn("Abuse", response.getheader("Access-Control-Allow-Headers"))
        connection.close()

    def test_reused_submission_id_with_changed_content_cannot_create_a_new_event(self):
        self.request(self.valid_payload())
        self.request({**self.valid_payload(), "mensaje": "Contenido diferente."})
        event_ids = [request[2]["event_id"] for request in UpstreamHandler.requests]
        self.assertEqual(event_ids[0], event_ids[1])

    def test_invalid_types_unknown_fields_and_disallowed_interest_are_rejected(self):
        cases = (
            {**self.valid_payload(), "telefono": 123},
            {**self.valid_payload(), "source": "attacker"},
            {**self.valid_payload(), "interes": "otro"},
            {key: value for key, value in self.valid_payload().items() if key != "email"},
        )
        for payload in cases:
            with self.subTest(payload=set(payload)):
                status, response = self.request(payload)
                self.assertEqual((status, response), (400, {"ok": False, "error": "invalid_request"}))
        self.assertEqual(UpstreamHandler.requests, [])

    def test_missing_keys_or_abuse_controls_fail_closed_at_configuration(self):
        for name in ("LEADFLOW_WEBHOOK_KEY", "WEB_BRIDGE_EVENT_ID_KEY", "WEB_BRIDGE_ABUSE_TOKEN", "WEB_BRIDGE_TURNSTILE_SECRET_KEY"):
            with self.subTest(name=name):
                environment = {**self.env, name: ""}
                with self.assertRaises(self.bridge.BridgeError):
                    self.bridge.BridgeConfig.from_env(environment)
        with self.assertRaises(self.bridge.BridgeError):
            self.bridge.BridgeConfig.from_env({**self.env, "WEB_BRIDGE_ABUSE_CONTROL": "disabled"})

    def test_origin_and_abuse_attestation_are_not_optional(self):
        for headers in ({"Origin": "https://evil.example.invalid"}, {"X-LeadFlow-Abuse-Token": "wrong"}):
            status, response = self.request(self.valid_payload(), headers)
            self.assertEqual((status, response), (403, {"ok": False, "error": "request_rejected"}))
        self.assertEqual(UpstreamHandler.requests, [])

    def test_body_limit_is_enforced_before_forwarding(self):
        status, response = self.request(self.valid_payload(), {"Content-Length": "5000"})
        self.assertEqual((status, response), (400, {"ok": False, "error": "invalid_request"}))
        self.assertEqual(UpstreamHandler.requests, [])

    def test_compose_is_opt_in_and_does_not_publish_ports(self):
        compose = (ROOT / "compose.web-bridge.yaml").read_text(encoding="utf-8")
        self.assertIn("profiles: [web-bridge]", compose)
        self.assertNotIn("\n    ports:", compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("cap_drop: [ALL]", compose)
        self.assertIn("WEB_BRIDGE_TURNSTILE_SECRET_KEY", compose)

    def test_turnstile_valid_token_is_verified_before_forwarding(self):
        status, response = self.request(self.valid_payload(), {"X-Turnstile-Token": "valid-synthetic-token"})
        self.assertEqual((status, response), (202, {"ok": True, "status": "accepted"}))
        self.turnstile_verifier.assert_called_once_with(self.config, "valid-synthetic-token")
        self.assertEqual(len(UpstreamHandler.requests), 1)

    def test_turnstile_missing_or_rejected_token_never_reaches_upstream(self):
        for token in ("", "invalid token", "x" * 2049):
            with self.subTest(token_length=len(token)):
                status, response = self.request(self.valid_payload(), {"X-Turnstile-Token": token})
                self.assertEqual((status, response), (400, {"ok": False, "error": "invalid_request"}))
        self.turnstile_verifier.side_effect = self.bridge.BridgeError(403, "turnstile_rejected")
        status, response = self.request(self.valid_payload(), {"X-Turnstile-Token": "invalid-synthetic-token"})
        self.assertEqual((status, response), (403, {"ok": False, "error": "request_rejected"}))
        self.assertEqual(UpstreamHandler.requests, [])

    def test_turnstile_hostname_action_and_incomplete_response_fail_closed(self):
        for result, error_id in (
            ({"success": True, "hostname": "other.example.invalid", "action": "lead_submit"}, "turnstile_hostname"),
            ({"success": True, "hostname": "form.example.invalid", "action": "other"}, "turnstile_action"),
            ({"hostname": "form.example.invalid", "action": "lead_submit"}, "turnstile_rejected"),
        ):
            response = mock.Mock(status=200)
            response.read.return_value = json.dumps(result).encode()
            connection = mock.Mock()
            connection.getresponse.return_value = response
            with self.subTest(error_id=error_id), mock.patch.object(self.bridge.http.client, "HTTPSConnection", return_value=connection):
                with self.assertRaises(self.bridge.BridgeError) as raised:
                    self.real_verify_turnstile(self.config, "synthetic-token")
                self.assertEqual(raised.exception.error_id, error_id)
        self.assertEqual(UpstreamHandler.requests, [])

    def test_turnstile_siteverify_accepts_complete_authorized_response(self):
        response = mock.Mock(status=200)
        response.read.return_value = json.dumps({
            "success": True,
            "hostname": "form.example.invalid",
            "action": "lead_submit",
        }).encode()
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch.object(self.bridge.http.client, "HTTPSConnection", return_value=connection):
            self.real_verify_turnstile(self.config, "valid-synthetic-token")
        request = connection.request.call_args
        self.assertEqual(request.args[:2], ("POST", "/turnstile/v0/siteverify"))
        self.assertNotIn("valid-synthetic-token", str(request.kwargs.get("headers")))

    def test_turnstile_proxy_tunnels_only_to_siteverify_authority(self):
        config = self.bridge.BridgeConfig.from_env({
            **self.env, "WEB_BRIDGE_TURNSTILE_PROXY_URL": "http://qa-egress:8899",
        })
        response = mock.Mock(status=200)
        response.read.return_value = json.dumps({
            "success": True, "hostname": "form.example.invalid", "action": "lead_submit",
        }).encode()
        connection = mock.Mock(); connection.getresponse.return_value = response
        with mock.patch.object(self.bridge.http.client, "HTTPSConnection", return_value=connection) as constructor:
            self.real_verify_turnstile(config, "valid-synthetic-token")
        constructor.assert_called_once_with("qa-egress", 8899, timeout=config.turnstile_timeout)
        connection.set_tunnel.assert_called_once_with("challenges.cloudflare.com", 443)
        for invalid in ("https://qa-egress:8899", "http://qa-egress", "http://user@qa-egress:8899/path"):
            with self.subTest(invalid=invalid), self.assertRaises(self.bridge.BridgeError):
                self.bridge.BridgeConfig.from_env({**self.env, "WEB_BRIDGE_TURNSTILE_PROXY_URL": invalid})

    def test_turnstile_timeout_and_service_error_are_generic_and_do_not_forward(self):
        for failure, error_id in ((socket.timeout(), "turnstile_timeout"), (OSError("synthetic"), "turnstile_unavailable")):
            self.turnstile_verifier.reset_mock()
            self.turnstile_verifier.side_effect = None
            self.turnstile_verifier.side_effect = failure
            output = io.StringIO()
            with self.subTest(error_id=error_id), redirect_stderr(output):
                status, response = self.request(self.valid_payload())
            self.assertEqual((status, response), (503, {"ok": False, "error": "request_rejected"}))
            self.assertIn("error_id=" + error_id, output.getvalue())
        self.assertEqual(UpstreamHandler.requests, [])

    def test_turnstile_production_configuration_is_mandatory(self):
        for changes in (
            {"WEB_BRIDGE_TURNSTILE_MODE": "disabled"},
            {"WEB_BRIDGE_TURNSTILE_SECRET_KEY": ""},
            {"WEB_BRIDGE_TURNSTILE_HOSTNAMES": ""},
            {"WEB_BRIDGE_TURNSTILE_ACTION": "not allowed"},
        ):
            with self.subTest(changes=tuple(changes)):
                with self.assertRaises(self.bridge.BridgeError):
                    self.bridge.BridgeConfig.from_env({**self.env, **changes})

    def test_retry_can_renew_turnstile_token_without_changing_event_identity(self):
        payload = self.valid_payload()
        self.request(payload, {"X-Turnstile-Token": "first-synthetic-token"})
        self.request(payload, {"X-Turnstile-Token": "renewed-synthetic-token"})
        self.assertEqual(
            [call.args[1] for call in self.turnstile_verifier.call_args_list],
            ["first-synthetic-token", "renewed-synthetic-token"],
        )
        requests = UpstreamHandler.requests
        self.assertEqual(requests[0][2], requests[1][2])
        self.assertNotIn("Turnstile", requests[0][1])

    def test_upstream_unavailable_and_timeout_are_generic(self):
        for failure, error_id in ((OSError("synthetic unavailable"), "upstream_unavailable"), (socket.timeout(), "upstream_timeout")):
            with self.subTest(error_id=error_id), mock.patch.object(self.bridge, "send_upstream", side_effect=failure):
                output = io.StringIO()
                with redirect_stderr(output):
                    status, response = self.request(self.valid_payload())
                self.assertEqual((status, response), (503, {"ok": False, "error": "request_rejected"}))
                self.assertIn("error_id=" + error_id, output.getvalue())

    def test_public_responses_and_diagnostics_do_not_expose_sensitive_values(self):
        output = io.StringIO()
        payload = {**self.valid_payload(), "email": "private@example.test", "interes": "not-allowed"}
        with redirect_stderr(output):
            status, response = self.request(payload)
        rendered = json.dumps(response) + output.getvalue()
        self.assertEqual(status, 400)
        for value in ("private@example.test", self.env["LEADFLOW_WEBHOOK_KEY"], self.env["WEB_BRIDGE_ABUSE_TOKEN"],
                      self.env["WEB_BRIDGE_TURNSTILE_SECRET_KEY"], "synthetic-turnstile-token", "not-allowed"):
            self.assertNotIn(value, rendered)

    def test_unsupported_mutating_methods_are_rejected_explicitly(self):
        for method in ("PUT", "PATCH", "DELETE"):
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
            connection.request(method, "/contacto", headers={"Origin": "https://form.example.invalid"})
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
            with self.subTest(method=method):
                self.assertEqual((response.status, body), (405, {"ok": False, "error": "request_rejected"}))
        self.assertEqual(UpstreamHandler.requests, [])

    def test_disallowed_source_configuration_and_unexpected_upstream_response_fail_closed(self):
        with self.assertRaises(self.bridge.BridgeError):
            self.bridge.BridgeConfig.from_env({**self.env, "WEB_BRIDGE_SOURCE": "not_allowed"})
        for upstream_status in (302, 500):
            UpstreamHandler.response_status = upstream_status
            with self.subTest(upstream_status=upstream_status):
                status, response = self.request(self.valid_payload())
                self.assertEqual((status, response), (503, {"ok": False, "error": "request_rejected"}))

    def test_qa_is_supported_with_the_same_security_floor_as_production(self):
        qa = {**self.env, "WEB_BRIDGE_ENV": "qa"}
        self.assertEqual(self.bridge.BridgeConfig.from_env(qa).environment, "qa")
        for changes in (
            {"WEB_BRIDGE_ALLOWED_ORIGINS": ""},
            {"WEB_BRIDGE_ALLOWED_ORIGINS": "http://form.example.invalid"},
            {"WEB_BRIDGE_ABUSE_CONTROL": "disabled"},
            {"WEB_BRIDGE_ABUSE_TOKEN": ""},
            {"WEB_BRIDGE_TURNSTILE_MODE": "disabled"},
            {"WEB_BRIDGE_TURNSTILE_SECRET_KEY": ""},
            {"WEB_BRIDGE_TURNSTILE_HOSTNAMES": ""},
        ):
            with self.subTest(environment="qa", changes=tuple(changes)):
                with self.assertRaises(self.bridge.BridgeError):
                    self.bridge.BridgeConfig.from_env({**qa, **changes})
        with self.assertRaises(self.bridge.BridgeError):
            self.bridge.BridgeConfig.from_env({**self.env, "WEB_BRIDGE_ENV": "unknown"})
        self.assertEqual(self.bridge.BridgeConfig.from_env(self.env).environment, "production")
        development = {
            **self.env,
            "WEB_BRIDGE_ENV": "development",
            "WEB_BRIDGE_ALLOWED_ORIGINS": "http://localhost:3000",
            "WEB_BRIDGE_ABUSE_CONTROL": "disabled",
            "WEB_BRIDGE_ABUSE_TOKEN": "",
            "WEB_BRIDGE_TURNSTILE_MODE": "disabled",
            "WEB_BRIDGE_TURNSTILE_SECRET_KEY": "",
            "WEB_BRIDGE_TURNSTILE_HOSTNAMES": "",
        }
        self.assertEqual(self.bridge.BridgeConfig.from_env(development).environment, "development")


if __name__ == "__main__":
    unittest.main(verbosity=2)
