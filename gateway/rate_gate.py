#!/usr/bin/env python3
"""Internal local gateway policy and bounded in-memory rate limiter."""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


PATH_RE = re.compile(r"/[A-Za-z0-9/_-]{1,100}")
FORWARDED_HEADERS = ("Content-Type", "Origin", "X-LeadFlow-Submission-Id", "X-Turnstile-Token")


class GateError(RuntimeError):
    pass


@dataclass(frozen=True)
class GateConfig:
    bind_host: str
    bind_port: int
    public_path: str
    upstream_host: str
    upstream_port: int
    upstream_path: str
    allowed_origins: frozenset[str]
    abuse_token: str
    max_body_bytes: int
    timeout: float
    rate_requests: int
    rate_window: float
    rate_max_keys: int

    @classmethod
    def from_env(cls, env=None):
        values = os.environ if env is None else env
        try:
            bind_port = int(values.get("WEB_GATEWAY_POLICY_PORT", "8081"))
            max_body = int(values.get("WEB_GATEWAY_MAX_BODY_BYTES", ""))
            timeout = float(values.get("WEB_GATEWAY_UPSTREAM_TIMEOUT_SECONDS", ""))
            rate_requests = int(values.get("WEB_GATEWAY_RATE_REQUESTS", ""))
            rate_window = float(values.get("WEB_GATEWAY_RATE_WINDOW_SECONDS", ""))
            rate_max_keys = int(values.get("WEB_GATEWAY_RATE_MAX_KEYS", ""))
        except ValueError as error:
            raise GateError("configuration_numeric") from error
        bind_host = values.get("WEB_GATEWAY_POLICY_BIND_HOST", "127.0.0.1").strip()
        public_path = values.get("WEB_GATEWAY_PUBLIC_PATH", "").strip()
        origins = frozenset(item.strip() for item in values.get("WEB_GATEWAY_ALLOWED_ORIGINS", "").split(",") if item.strip())
        abuse_token = values.get("WEB_BRIDGE_ABUSE_TOKEN", "")
        parsed = urlsplit(values.get("WEB_GATEWAY_UPSTREAM_URL", "").strip())
        if (
            not bind_host or not 1024 <= bind_port <= 65535 or not 1024 <= max_body <= 65536
            or not 0.1 <= timeout <= 30 or not 1 <= rate_requests <= 100 or not 1 <= rate_window <= 3600
            or not 10 <= rate_max_keys <= 100000 or public_path != "/lead" or len(abuse_token) < 32
        ):
            raise GateError("configuration_bounds")
        if not origins or any(not _valid_origin(item) for item in origins):
            raise GateError("configuration_origin")
        if (
            parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path != public_path
        ):
            raise GateError("configuration_upstream")
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            pass
        else:
            raise GateError("configuration_upstream")
        return cls(bind_host, bind_port, public_path, parsed.hostname, parsed.port or 80, parsed.path,
                   origins, abuse_token, max_body, timeout, rate_requests, rate_window, rate_max_keys)


def _valid_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                and not parsed.path.strip("/") and not parsed.query and not parsed.fragment)


class RateLimiter:
    def __init__(self, maximum: int, window: float, max_keys: int, clock=time.monotonic):
        self.maximum = maximum
        self.window = window
        self.max_keys = max_keys
        self.clock = clock
        self.entries = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = self.clock()
        with self.lock:
            if key not in self.entries and len(self.entries) >= self.max_keys:
                for known in tuple(self.entries):
                    events = self.entries[known]
                    while events and now - events[0] >= self.window:
                        events.popleft()
                    if not events:
                        del self.entries[known]
                if len(self.entries) >= self.max_keys:
                    return False, max(1, int(self.window + 0.999))
            events = self.entries.setdefault(key, deque())
            while events and now - events[0] >= self.window:
                events.popleft()
            if len(events) >= self.maximum:
                retry = max(1, int(self.window - (now - events[0]) + 0.999))
                return False, retry
            events.append(now)
            return True, 0


class GateHandler(BaseHTTPRequestHandler):
    server_version = "LeadFlowLocalGate"
    sys_version = ""

    def log_message(self, _format, *_args):
        return

    def _respond(self, status: int, body: dict, extra=None):
        encoded = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers(); self.wfile.write(encoded)

    def do_POST(self):
        self._handle(True)

    def do_OPTIONS(self):
        self._handle(False)

    def do_GET(self):
        self._respond(405 if self.path == self.server.config.public_path else 404, {"ok": False, "error": "request_rejected"})

    do_PUT = do_GET
    do_PATCH = do_GET
    do_DELETE = do_GET

    def _handle(self, limited: bool):
        config = self.server.config
        if self.path != config.public_path:
            self._respond(404, {"ok": False, "error": "request_rejected"}); return
        origin = self.headers.get("Origin", "")
        if origin not in config.allowed_origins:
            self._respond(403, {"ok": False, "error": "request_rejected"}); return
        key = self.headers.get("X-LeadFlow-Rate-Key", "")
        try:
            key = str(ipaddress.ip_address(key))
        except ValueError:
            self._respond(403, {"ok": False, "error": "request_rejected"}); return
        if limited:
            allowed, retry = self.server.rate_limiter.allow(key)
            if not allowed:
                self._respond(429, {"ok": False, "error": "rate_limited"}, {"Retry-After": str(retry)}); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond(400, {"ok": False, "error": "invalid_request"}); return
        if length < 0 or length > config.max_body_bytes:
            self._respond(413, {"ok": False, "error": "request_rejected"}); return
        body = self.rfile.read(length) if length else b""
        headers = {name: self.headers[name] for name in FORWARDED_HEADERS if self.headers.get(name)}
        headers["X-LeadFlow-Abuse-Token"] = config.abuse_token
        connection = http.client.HTTPConnection(config.upstream_host, config.upstream_port, timeout=config.timeout)
        try:
            connection.request(self.command, config.upstream_path, body=body, headers=headers)
            response = connection.getresponse(); raw = response.read(config.max_body_bytes + 1)
            if len(raw) > config.max_body_bytes:
                raise OSError("upstream response too large")
            safe = {name: value for name in ("Content-Type", "Access-Control-Allow-Origin", "Vary", "Retry-After")
                    if (value := response.getheader(name))}
            self.send_response(response.status)
            for name, value in safe.items(): self.send_header(name, value)
            self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store")
            self.end_headers(); self.wfile.write(raw)
        except (OSError, http.client.HTTPException):
            self._respond(503, {"ok": False, "error": "request_rejected"})
        finally:
            connection.close()


class GateServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, config, clock=time.monotonic):
        self.config = config
        self.rate_limiter = RateLimiter(config.rate_requests, config.rate_window, config.rate_max_keys, clock)
        super().__init__(address, GateHandler)


def main():
    try:
        config = GateConfig.from_env()
        server = GateServer((config.bind_host, config.bind_port), config)
    except Exception:
        print("web_gateway phase=start status=FAIL error_id=configuration", file=sys.stderr)
        return 1
    print("web_gateway phase=start status=PASS", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
