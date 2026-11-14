"""Private HTTP bridge from the Emactiva form to the LeadFlow webhook contract."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlsplit


FIELDS = {"nombre", "apellido", "email", "negocio", "telefono", "interes", "mensaje"}
OPTIONAL_LIMITS = {"nombre": 200, "apellido": 200, "negocio": 200, "telefono": 200, "mensaje": 2000}
SOURCE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SUBMISSION_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
EVENT_ID_PURPOSE = b"LF015-WEB-EVENT-ID-V1\x00"
SECURE_ENVIRONMENTS = frozenset({"qa", "production"})
TURNSTILE_VERIFY_HOST = "challenges.cloudflare.com"
TURNSTILE_VERIFY_PATH = "/turnstile/v0/siteverify"
TURNSTILE_TOKEN_MAX_BYTES = 2048
TURNSTILE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class BridgeError(Exception):
    def __init__(self, status: int, error_id: str):
        self.status = status
        self.error_id = error_id
        super().__init__(error_id)


@dataclass(frozen=True)
class BridgeConfig:
    environment: str
    bind_host: str
    bind_port: int
    public_path: str
    upstream_url: str
    webhook_key: str
    event_id_key: bytes
    source: str
    interests: frozenset[str]
    allowed_origins: frozenset[str]
    abuse_mode: str
    abuse_token: str
    turnstile_mode: str
    turnstile_secret: str
    turnstile_hostnames: frozenset[str]
    turnstile_action: str
    turnstile_timeout: float
    turnstile_proxy_host: str
    turnstile_proxy_port: int
    max_body_bytes: int
    request_timeout: float
    upstream_timeout: float

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "BridgeConfig":
        values = os.environ if env is None else env
        environment = values.get("WEB_BRIDGE_ENV", "development").strip().lower()
        if environment not in {"development", *SECURE_ENVIRONMENTS}:
            raise BridgeError(500, "configuration_environment")
        bind_host = values.get("WEB_BRIDGE_BIND_HOST", "127.0.0.1").strip()
        try:
            bind_port = int(values.get("WEB_BRIDGE_BIND_PORT", "8080"))
            max_body = int(values.get("WEB_BRIDGE_MAX_BODY_BYTES", "16384"))
            request_timeout = float(values.get("WEB_BRIDGE_REQUEST_TIMEOUT_SECONDS", "5"))
            timeout = float(values.get("WEB_BRIDGE_UPSTREAM_TIMEOUT_SECONDS", "10"))
            turnstile_timeout = float(values.get("WEB_BRIDGE_TURNSTILE_TIMEOUT_SECONDS", "5"))
        except ValueError as exc:
            raise BridgeError(500, "configuration_numeric") from exc
        if not bind_host or not 1 <= bind_port <= 65535 or not 1024 <= max_body <= 65536 or not 0.5 <= request_timeout <= 30 or not 0.1 <= timeout <= 30 or not 0.1 <= turnstile_timeout <= 15:
            raise BridgeError(500, "configuration_bounds")
        public_path = values.get("WEB_BRIDGE_PUBLIC_PATH", "/lead").strip()
        if not re.fullmatch(r"/[A-Za-z0-9/_-]{1,100}", public_path):
            raise BridgeError(500, "configuration_path")
        upstream_url = values.get("WEB_BRIDGE_UPSTREAM_URL", "").strip()
        parsed = urlsplit(upstream_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise BridgeError(500, "configuration_upstream")
        webhook_key = values.get("LEADFLOW_WEBHOOK_KEY", "")
        event_id_key = values.get("WEB_BRIDGE_EVENT_ID_KEY", "")
        if len(webhook_key) < 32 or len(event_id_key) < 32 or hmac.compare_digest(webhook_key, event_id_key):
            raise BridgeError(500, "configuration_secret")
        source = values.get("WEB_BRIDGE_SOURCE", "").strip().lower()
        allowed_sources = {item.strip() for item in values.get("LEADFLOW_ALLOWED_SOURCES", "").split(",") if item.strip()}
        if not SOURCE_RE.fullmatch(source) or source not in allowed_sources:
            raise BridgeError(500, "configuration_source")
        interests = frozenset(item.strip() for item in values.get("LEADFLOW_ALLOWED_INTERESTS", "").split(",") if item.strip())
        if not interests or any(len(item) > 100 for item in interests):
            raise BridgeError(500, "configuration_interests")
        origins = frozenset(item.strip() for item in values.get("WEB_BRIDGE_ALLOWED_ORIGINS", "").split(",") if item.strip())
        if any(not _valid_origin(item, environment) for item in origins):
            raise BridgeError(500, "configuration_origin")
        abuse_mode = values.get("WEB_BRIDGE_ABUSE_CONTROL", "disabled").strip().lower()
        abuse_token = values.get("WEB_BRIDGE_ABUSE_TOKEN", "")
        if environment in SECURE_ENVIRONMENTS:
            if not origins or abuse_mode != "external" or len(abuse_token) < 32:
                raise BridgeError(500, "configuration_abuse_control")
        elif abuse_mode not in {"disabled", "external"} or (abuse_mode == "external" and len(abuse_token) < 32):
            raise BridgeError(500, "configuration_abuse_control")
        if abuse_token and (hmac.compare_digest(abuse_token, webhook_key) or hmac.compare_digest(abuse_token, event_id_key)):
            raise BridgeError(500, "configuration_secret_reuse")
        turnstile_mode = values.get("WEB_BRIDGE_TURNSTILE_MODE", "disabled").strip().lower()
        turnstile_secret = values.get("WEB_BRIDGE_TURNSTILE_SECRET_KEY", "")
        turnstile_hostnames = frozenset(item.strip().lower() for item in values.get("WEB_BRIDGE_TURNSTILE_HOSTNAMES", "").split(",") if item.strip())
        turnstile_action = values.get("WEB_BRIDGE_TURNSTILE_ACTION", "").strip()
        turnstile_proxy = values.get("WEB_BRIDGE_TURNSTILE_PROXY_URL", "").strip()
        proxy_host = ""
        proxy_port = 0
        if turnstile_proxy:
            parsed_proxy = urlsplit(turnstile_proxy)
            if (
                parsed_proxy.scheme != "http" or not parsed_proxy.hostname or parsed_proxy.username
                or parsed_proxy.password or parsed_proxy.path not in {"", "/"} or parsed_proxy.query
                or parsed_proxy.fragment or parsed_proxy.port is None
            ):
                raise BridgeError(500, "configuration_turnstile_proxy")
            proxy_host, proxy_port = parsed_proxy.hostname, parsed_proxy.port
        if turnstile_mode not in {"disabled", "siteverify"} or (environment in SECURE_ENVIRONMENTS and turnstile_mode != "siteverify"):
            raise BridgeError(500, "configuration_turnstile_mode")
        if turnstile_mode == "siteverify":
            if len(turnstile_secret) < 20 or not turnstile_hostnames:
                raise BridgeError(500, "configuration_turnstile")
            if any(not _valid_hostname(item) for item in turnstile_hostnames):
                raise BridgeError(500, "configuration_turnstile_hostname")
            if turnstile_action and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", turnstile_action):
                raise BridgeError(500, "configuration_turnstile_action")
            if any(hmac.compare_digest(turnstile_secret, secret) for secret in (webhook_key, event_id_key, abuse_token) if secret):
                raise BridgeError(500, "configuration_secret_reuse")
        return cls(environment, bind_host, bind_port, public_path, upstream_url, webhook_key, event_id_key.encode(), source,
                   interests, origins, abuse_mode, abuse_token, turnstile_mode, turnstile_secret, turnstile_hostnames,
                   turnstile_action, turnstile_timeout, proxy_host, proxy_port, max_body, request_timeout, timeout)


def _valid_origin(value: str, environment: str) -> bool:
    parsed = urlsplit(value)
    if parsed.scheme not in ({"https"} if environment in SECURE_ENVIRONMENTS else {"http", "https"}):
        return False
    return bool(parsed.hostname and not parsed.username and not parsed.password and not parsed.path.strip("/") and not parsed.query and not parsed.fragment)


def _valid_hostname(value: str) -> bool:
    if len(value) > 253 or value.endswith("."):
        return False
    labels = value.split(".")
    return len(labels) >= 2 and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)


def _load_unique_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BridgeError(400, "duplicate_field")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except BridgeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError(400, "invalid_json") from exc


def transform(payload: object, submission_id: str, config: BridgeConfig) -> dict:
    if not isinstance(payload, dict) or set(payload) - FIELDS:
        raise BridgeError(400, "invalid_fields")
    if "email" not in payload or "interes" not in payload:
        raise BridgeError(400, "missing_fields")
    for name, value in payload.items():
        if not isinstance(value, str):
            raise BridgeError(400, "invalid_type")
        if CONTROL_RE.search(value):
            raise BridgeError(400, "invalid_characters")
    email = payload["email"].strip().lower()
    if len(email) > 254 or re.search(r"\s", email) or email.count("@") != 1:
        raise BridgeError(400, "invalid_email")
    local, domain = email.split("@")
    labels = domain.split(".")
    if not local or len(labels) < 2 or any(not label for label in labels):
        raise BridgeError(400, "invalid_email")
    interest = payload["interes"].strip()
    if not interest or len(interest) > 100 or interest not in config.interests:
        raise BridgeError(400, "invalid_interest")
    normalized = {"email": email, "interes": interest}
    for name, limit in OPTIONAL_LIMITS.items():
        if name not in payload:
            continue
        value = payload[name].strip()
        if len(value) > limit:
            raise BridgeError(400, "invalid_length")
        if value:
            normalized[name] = value
    event_id = "web_" + hmac.new(config.event_id_key, EVENT_ID_PURPOSE + submission_id.encode("ascii"), hashlib.sha256).hexdigest()
    lead = {"email": email}
    for public, internal in (("nombre", "first_name"), ("apellido", "last_name"), ("negocio", "company"), ("telefono", "phone")):
        if public in normalized:
            lead[internal] = normalized[public]
    interaction = {"interest": interest}
    if "mensaje" in normalized:
        interaction["message"] = normalized["mensaje"]
    return {"event_id": event_id, "source": config.source, "lead": lead, "interaction": interaction}


def send_upstream(config: BridgeConfig, payload: dict) -> int:
    parsed = urlsplit(config.upstream_url)
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    connection = connection_cls(parsed.hostname, port, timeout=config.upstream_timeout)
    try:
        connection.request("POST", path, body=body, headers={"Content-Type": "application/json", "X-LeadFlow-Key": config.webhook_key})
        response = connection.getresponse()
        response.read(4096)
        return response.status
    finally:
        connection.close()


def verify_turnstile(config: BridgeConfig, token: str) -> None:
    if config.turnstile_mode == "disabled":
        return
    body = urlencode({"secret": config.turnstile_secret, "response": token}).encode("ascii")
    connection = http.client.HTTPSConnection(
        config.turnstile_proxy_host or TURNSTILE_VERIFY_HOST,
        config.turnstile_proxy_port or 443,
        timeout=config.turnstile_timeout,
    )
    if config.turnstile_proxy_host:
        connection.set_tunnel(TURNSTILE_VERIFY_HOST, 443)
    try:
        connection.request("POST", TURNSTILE_VERIFY_PATH, body=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })
        response = connection.getresponse()
        raw = response.read(16385)
        if response.status != 200 or len(raw) > 16384:
            raise BridgeError(503, "turnstile_unavailable")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError(503, "turnstile_invalid_response") from exc
        if not isinstance(result, dict) or result.get("success") is not True:
            raise BridgeError(403, "turnstile_rejected")
        hostname = result.get("hostname")
        if not isinstance(hostname, str) or hostname.lower() not in config.turnstile_hostnames:
            raise BridgeError(403, "turnstile_hostname")
        if config.turnstile_action and result.get("action") != config.turnstile_action:
            raise BridgeError(403, "turnstile_action")
    finally:
        connection.close()


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "LeadFlowBridge"
    sys_version = ""

    @property
    def config(self) -> BridgeConfig:
        return self.server.bridge_config

    def log_message(self, _format, *_args):
        return

    def send_error(self, code, _message=None, _explain=None):
        status = code if 400 <= code < 500 else 500
        self._respond(status, {"ok": False, "error": "invalid_request" if status < 500 else "internal_error"})

    def _respond(self, status: int, body: dict, origin: str | None = None):
        encoded = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if origin and origin in self.config.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(encoded)

    def _reject(self, error: BridgeError, origin: str | None = None):
        sys.stderr.write(f"web_bridge event=request_rejected error_id={error.error_id}\n")
        public_error = "invalid_request" if error.status == 400 else "request_rejected"
        self._respond(error.status, {"ok": False, "error": public_error}, origin)

    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        if self.path != self.config.public_path or origin not in self.config.allowed_origins:
            self._respond(404, {"ok": False, "error": "not_found"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-LeadFlow-Submission-Id, X-Turnstile-Token")
        self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        if self.path == "/healthz":
            self._respond(200, {"ok": True})
        else:
            self._respond(404, {"ok": False, "error": "not_found"})

    def _method_not_allowed(self):
        self._reject(BridgeError(405, "method"), self.headers.get("Origin"))

    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_PUT = _method_not_allowed

    def do_POST(self):
        origin = self.headers.get("Origin")
        try:
            if self.path != self.config.public_path:
                raise BridgeError(404, "path")
            if self.config.allowed_origins and origin not in self.config.allowed_origins:
                raise BridgeError(403, "origin")
            if self.config.abuse_mode == "external":
                supplied = self.headers.get("X-LeadFlow-Abuse-Token", "")
                if not supplied or not hmac.compare_digest(supplied, self.config.abuse_token):
                    raise BridgeError(403, "abuse_control")
            submission_id = self.headers.get("X-LeadFlow-Submission-Id", "")
            if not SUBMISSION_ID_RE.fullmatch(submission_id):
                raise BridgeError(400, "submission_id")
            turnstile_token = self.headers.get("X-Turnstile-Token", "")
            if self.config.turnstile_mode == "siteverify" and (
                not turnstile_token or len(turnstile_token) > TURNSTILE_TOKEN_MAX_BYTES or not TURNSTILE_TOKEN_RE.fullmatch(turnstile_token)
            ):
                raise BridgeError(400, "turnstile_token")
            if self.headers.get("Transfer-Encoding"):
                raise BridgeError(400, "transfer_encoding")
            if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                raise BridgeError(400, "content_type")
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError as exc:
                raise BridgeError(400, "content_length") from exc
            if length < 1 or length > self.config.max_body_bytes:
                raise BridgeError(400, "body_size")
            self.connection.settimeout(self.config.request_timeout)
            try:
                raw = self.rfile.read(length)
            except (TimeoutError, socket.timeout):
                raise BridgeError(408, "request_timeout")
            if len(raw) != length:
                raise BridgeError(400, "incomplete_body")
            internal = transform(_load_unique_json(raw), submission_id, self.config)
            try:
                verify_turnstile(self.config, turnstile_token)
            except (TimeoutError, socket.timeout):
                raise BridgeError(503, "turnstile_timeout")
            except (OSError, http.client.HTTPException):
                raise BridgeError(503, "turnstile_unavailable")
            try:
                status = send_upstream(self.config, internal)
            except (TimeoutError, socket.timeout):
                raise BridgeError(503, "upstream_timeout")
            except (OSError, http.client.HTTPException):
                raise BridgeError(503, "upstream_unavailable")
            if not 200 <= status < 300:
                raise BridgeError(503, "upstream_rejected")
            self._respond(202, {"ok": True, "status": "accepted"}, origin)
        except BridgeError as error:
            self._reject(error, origin)
        except Exception:
            sys.stderr.write("web_bridge event=request_failed error_id=internal\n")
            self._respond(500, {"ok": False, "error": "internal_error"}, origin)


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, config: BridgeConfig):
        self.bridge_config = config
        super().__init__(address, BridgeHandler)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(self.bridge_config.request_timeout)
        return request, address


def main() -> int:
    try:
        config = BridgeConfig.from_env()
    except BridgeError as error:
        sys.stderr.write(f"web_bridge event=startup_failed error_id={error.error_id}\n")
        return 1
    server = BridgeServer((config.bind_host, config.bind_port), config)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
