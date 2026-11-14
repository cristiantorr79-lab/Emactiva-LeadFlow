#!/usr/bin/env python3
"""Restricted CONNECT proxy for the isolated QA Turnstile gate."""
from __future__ import annotations

import ipaddress
import os
import select
import socket
import socketserver
import sys
from dataclasses import dataclass


ALLOWED_AUTHORITY = "challenges.cloudflare.com:443"
MAX_REQUEST_BYTES = 4096


class EgressError(RuntimeError):
    pass


@dataclass(frozen=True)
class EgressConfig:
    bind_host: str
    bind_port: int
    timeout: float
    max_tunnel_bytes: int

    @classmethod
    def from_env(cls, env=None):
        values = os.environ if env is None else env
        host = values.get("QA_EGRESS_BIND_HOST", "127.0.0.1").strip()
        try:
            port = int(values.get("QA_EGRESS_BIND_PORT", ""))
            timeout = float(values.get("QA_EGRESS_TIMEOUT_SECONDS", "15"))
            maximum = int(values.get("QA_EGRESS_MAX_TUNNEL_BYTES", "131072"))
        except ValueError as error:
            raise EgressError("configuration_numeric") from error
        if not host or not 1024 <= port <= 65535 or not 1 <= timeout <= 30 or not 16384 <= maximum <= 1048576:
            raise EgressError("configuration_bounds")
        return cls(host, port, timeout, maximum)


def public_addresses(host: str, port: int):
    try:
        candidates = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise EgressError("dns_unavailable") from error
    allowed = []
    for family, socktype, proto, _canonname, address in candidates:
        ip = ipaddress.ip_address(address[0])
        if not ip.is_global:
            raise EgressError("destination_forbidden")
        allowed.append((family, socktype, proto, address))
    if not allowed:
        raise EgressError("destination_unavailable")
    return allowed


def connect_allowed(timeout: float):
    last_error = None
    for family, socktype, proto, address in public_addresses("challenges.cloudflare.com", 443):
        target = socket.socket(family, socktype, proto)
        target.settimeout(timeout)
        try:
            target.connect(address)
            return target
        except OSError as error:
            last_error = error
            target.close()
    raise EgressError("destination_unavailable") from last_error


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        target = None
        try:
            self.request.settimeout(self.server.egress_config.timeout)
            raw = b""
            while b"\r\n\r\n" not in raw and len(raw) <= MAX_REQUEST_BYTES:
                chunk = self.request.recv(1024)
                if not chunk:
                    raise EgressError("request_incomplete")
                raw += chunk
            if len(raw) > MAX_REQUEST_BYTES:
                raise EgressError("request_too_large")
            try:
                line = raw.split(b"\r\n", 1)[0].decode("ascii")
            except UnicodeDecodeError as error:
                raise EgressError("request_invalid") from error
            parts = line.split(" ")
            if len(parts) != 3 or parts[0] != "CONNECT" or parts[1].lower() != ALLOWED_AUTHORITY or parts[2] != "HTTP/1.1":
                raise EgressError("destination_forbidden")
            target = connect_allowed(self.server.egress_config.timeout)
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            transferred = 0
            sockets = (self.request, target)
            while transferred <= self.server.egress_config.max_tunnel_bytes:
                readable, _, _ = select.select(sockets, (), (), self.server.egress_config.timeout)
                if not readable:
                    raise EgressError("tunnel_timeout")
                for source in readable:
                    data = source.recv(16384)
                    if not data:
                        return
                    transferred += len(data)
                    if transferred > self.server.egress_config.max_tunnel_bytes:
                        raise EgressError("tunnel_limit")
                    (target if source is self.request else self.request).sendall(data)
        except (EgressError, OSError):
            try:
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
        finally:
            if target is not None:
                target.close()


class ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, config):
        self.egress_config = config
        super().__init__(address, ProxyHandler)


def main():
    try:
        config = EgressConfig.from_env()
        server = ProxyServer((config.bind_host, config.bind_port), config)
    except Exception:
        print("qa_egress phase=start status=FAIL error_id=configuration", file=sys.stderr)
        return 1
    print("qa_egress phase=start status=PASS", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
