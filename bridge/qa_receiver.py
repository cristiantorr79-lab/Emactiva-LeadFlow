#!/usr/bin/env python3
"""Stateless QA-only receiver for Web Bridge functional validation."""
from __future__ import annotations

import hmac
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SOURCE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
PATH_RE = re.compile(r"/[A-Za-z0-9/_-]{1,100}")
LEAD_FIELDS = frozenset({"email", "first_name", "last_name", "company", "phone"})
INTERACTION_FIELDS = frozenset({"interest", "message"})


class ReceiverError(Exception):
    def __init__(self, status: int, error_id: str):
        self.status = status
        self.error_id = error_id
        super().__init__(error_id)


@dataclass(frozen=True)
class ReceiverConfig:
    host: str
    port: int
    path: str
    key: str
    max_body_bytes: int
    request_timeout: float

    @classmethod
    def from_env(cls, env=None):
        values = os.environ if env is None else env
        host = values.get("QA_RECEIVER_BIND_HOST", "127.0.0.1").strip()
        path = values.get("QA_RECEIVER_PATH", "").strip()
        key = values.get("LEADFLOW_WEBHOOK_KEY", "")
        try:
            port = int(values.get("QA_RECEIVER_PORT", "8090"))
            maximum = int(values.get("QA_RECEIVER_MAX_BODY_BYTES", "16384"))
            timeout = float(values.get("QA_RECEIVER_TIMEOUT_SECONDS", "5"))
        except ValueError as error:
            raise ReceiverError(500, "configuration_numeric") from error
        if not host or not 1 <= port <= 65535 or not PATH_RE.fullmatch(path):
            raise ReceiverError(500, "configuration_endpoint")
        if len(key) < 32 or not 1024 <= maximum <= 65536 or not 0.5 <= timeout <= 30:
            raise ReceiverError(500, "configuration_security")
        return cls(host, port, path, key, maximum, timeout)


def validate_payload(value) -> None:
    if not isinstance(value, dict) or set(value) != {"event_id", "source", "lead", "interaction"}:
        raise ReceiverError(400, "payload_shape")
    if not isinstance(value["event_id"], str) or not EVENT_ID_RE.fullmatch(value["event_id"]):
        raise ReceiverError(400, "payload_event")
    if not isinstance(value["source"], str) or not SOURCE_RE.fullmatch(value["source"]):
        raise ReceiverError(400, "payload_source")
    lead, interaction = value["lead"], value["interaction"]
    if not isinstance(lead, dict) or "email" not in lead or not set(lead) <= LEAD_FIELDS:
        raise ReceiverError(400, "payload_lead")
    if not isinstance(interaction, dict) or "interest" not in interaction or not set(interaction) <= INTERACTION_FIELDS:
        raise ReceiverError(400, "payload_interaction")
    if any(not isinstance(item, str) or not item or len(item) > 2000 for item in (*lead.values(), *interaction.values())):
        raise ReceiverError(400, "payload_value")


class ReceiverHandler(BaseHTTPRequestHandler):
    server_version = "LeadFlowQAReceiver"
    sys_version = ""

    @property
    def config(self):
        return self.server.receiver_config

    def log_message(self, _format, *_args):
        return

    def _respond(self, status: int, body: dict):
        encoded = json.dumps(body, separators=(",", ":")).encode()
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def _reject(self, error: ReceiverError):
        sys.stderr.write(f"qa_receiver event=request_rejected error_id={error.error_id}\n")
        self._respond(error.status, {"ok": False, "error": "invalid_request" if error.status == 400 else "request_rejected"})

    def do_GET(self):
        if self.path == "/healthz":
            self._respond(200, {"ok": True, "status": "qa_ready"})
        else:
            self._respond(404, {"ok": False, "error": "not_found"})

    def _method_not_allowed(self):
        self._reject(ReceiverError(405, "method"))

    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_PUT = _method_not_allowed

    def do_POST(self):
        try:
            if self.path != self.config.path:
                raise ReceiverError(404, "path")
            supplied = self.headers.get("X-LeadFlow-Key", "")
            if not supplied or not hmac.compare_digest(supplied, self.config.key):
                raise ReceiverError(403, "authentication")
            if self.headers.get("Transfer-Encoding") or not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                raise ReceiverError(400, "request_headers")
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError as error:
                raise ReceiverError(400, "content_length") from error
            if length < 1 or length > self.config.max_body_bytes:
                raise ReceiverError(400, "body_size")
            self.connection.settimeout(self.config.request_timeout)
            try:
                raw = self.rfile.read(length)
            except (TimeoutError, socket.timeout):
                raise ReceiverError(408, "request_timeout")
            if len(raw) != length:
                raise ReceiverError(400, "incomplete_body")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ReceiverError(400, "invalid_json") from error
            validate_payload(payload)
            self._respond(202, {"ok": True, "status": "received_qa"})
        except ReceiverError as error:
            self._reject(error)
        except Exception:
            sys.stderr.write("qa_receiver event=request_failed error_id=internal\n")
            self._respond(500, {"ok": False, "error": "internal_error"})


class ReceiverServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, config: ReceiverConfig):
        self.receiver_config = config
        super().__init__(address, ReceiverHandler)


def main() -> int:
    try:
        config = ReceiverConfig.from_env()
    except ReceiverError as error:
        sys.stderr.write(f"qa_receiver event=startup_failed error_id={error.error_id}\n")
        return 1
    server = ReceiverServer((config.host, config.port), config)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
