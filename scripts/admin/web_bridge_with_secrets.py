#!/usr/bin/env python3
"""Resolve the Web Bridge secrets in memory and run its isolated Compose project."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "compose.web-bridge.yaml"
MAP_VERSION = "LF015-WEB-BRIDGE-SECRET-MAP-1"
PROVIDER_NAME = "gcp-secret-manager"
OPERATION_NAME = "web-bridge-compose"
AUTHORIZED_SECRET_IDS = {
    "WEB_BRIDGE_TURNSTILE_SECRET_KEY": "leadflow-turnstile-secret",
    "WEB_BRIDGE_ABUSE_TOKEN": "leadflow-web-bridge-abuse-token",
    "LEADFLOW_WEBHOOK_KEY": "leadflow-webhook-key",
    "WEB_BRIDGE_EVENT_ID_KEY": "leadflow-web-bridge-event-id-key",
}
SECRET_NAMES = frozenset(AUTHORIZED_SECRET_IDS)
REQUIRED_NONSECRET_NAMES = frozenset({
    "WEB_BRIDGE_ENV", "WEB_BRIDGE_PUBLIC_PATH", "WEB_BRIDGE_UPSTREAM_URL", "WEB_BRIDGE_SOURCE",
    "WEB_BRIDGE_ALLOWED_ORIGINS", "WEB_BRIDGE_ABUSE_CONTROL", "WEB_BRIDGE_TURNSTILE_MODE",
    "WEB_BRIDGE_TURNSTILE_HOSTNAMES", "LEADFLOW_ALLOWED_SOURCES", "LEADFLOW_ALLOWED_INTERESTS",
    "WEB_BRIDGE_UPSTREAM_NETWORK",
})
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
NETWORK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
COMPOSE_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")
OPERATION_ENV = {
    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "DOCKER_HOST", "DOCKER_CONTEXT",
    "DOCKER_CONFIG", "XDG_CONFIG_HOME", "TMPDIR", "TEMP", "TMP",
}


class WebBridgeSecretError(RuntimeError):
    pass


def load_secure_runtime():
    path = ROOT / "scripts" / "admin" / "compose_with_secrets.py"
    spec = importlib.util.spec_from_file_location("leadflow_secure_secret_runtime", path)
    if spec is None or spec.loader is None:
        raise WebBridgeSecretError("secure provider unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_map(path: Path, secure_runtime):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise WebBridgeSecretError("invalid secret map") from error
    if not isinstance(value, dict) or set(value) != {"version", "provider", "operation", "expected_identity", "secrets"}:
        raise WebBridgeSecretError("invalid secret map")
    if value["version"] != MAP_VERSION or value["provider"] != PROVIDER_NAME or value["operation"] != OPERATION_NAME:
        raise WebBridgeSecretError("invalid secret map")
    identity = value["expected_identity"]
    references = value["secrets"]
    if not isinstance(identity, str) or not secure_runtime.SERVICE_ACCOUNT.fullmatch(identity):
        raise WebBridgeSecretError("invalid secret map")
    identity_project = identity.split("@", 1)[1].removesuffix(".iam.gserviceaccount.com")
    if not isinstance(references, dict) or set(references) != SECRET_NAMES:
        raise WebBridgeSecretError("invalid secret map")
    if any(not isinstance(reference, str) or not secure_runtime.SECRET_REFERENCE.fullmatch(reference) for reference in references.values()):
        raise WebBridgeSecretError("invalid secret map")
    if any(reference.split("/")[3] != AUTHORIZED_SECRET_IDS[name] for name, reference in references.items()):
        raise WebBridgeSecretError("invalid secret map")
    if any(reference.split("/")[1] != identity_project for reference in references.values()):
        raise WebBridgeSecretError("invalid secret map")
    if len(set(references.values())) != len(references):
        raise WebBridgeSecretError("invalid secret map")
    return identity, references


def compose_variables() -> set[str]:
    try:
        return set(COMPOSE_VARIABLE.findall(COMPOSE_FILE.read_text(encoding="utf-8")))
    except OSError as error:
        raise WebBridgeSecretError("compose configuration unavailable") from error


def resolve_environment(map_path: Path, provider_factory=None) -> tuple[dict[str, str], str]:
    secure_runtime = load_secure_runtime()
    identity, references = load_map(map_path, secure_runtime)
    try:
        timeout = int(os.environ.get("WEB_BRIDGE_SECRET_FETCH_TIMEOUT_SECONDS", "5"))
    except ValueError as error:
        raise WebBridgeSecretError("invalid timeout") from error
    if not 1 <= timeout <= 30:
        raise WebBridgeSecretError("invalid timeout")
    bridge_project = os.environ.get("WEB_BRIDGE_COMPOSE_PROJECT", "").strip()
    main_project = os.environ.get("LEADFLOW_COMPOSE_PROJECT", "").strip()
    if not PROJECT_RE.fullmatch(bridge_project) or not PROJECT_RE.fullmatch(main_project) or bridge_project == main_project:
        raise WebBridgeSecretError("compose project separation required")
    if any(not os.environ.get(name, "").strip() for name in REQUIRED_NONSECRET_NAMES):
        raise WebBridgeSecretError("nonsecret configuration incomplete")
    if not NETWORK_RE.fullmatch(os.environ["WEB_BRIDGE_UPSTREAM_NETWORK"].strip()):
        raise WebBridgeSecretError("external network invalid")
    factory = provider_factory or secure_runtime.GcpSecretManagerProvider
    try:
        secrets = secure_runtime.resolve_authorized_secrets(references, identity, timeout, factory)
    except Exception as error:
        raise WebBridgeSecretError("secret resolution failed") from error
    if set(secrets) != SECRET_NAMES or any(not isinstance(value, str) or not value or "\x00" in value for value in secrets.values()):
        raise WebBridgeSecretError("secret resolution failed")
    allowed = compose_variables()
    environment = {
        name: value for name, value in os.environ.items()
        if name in OPERATION_ENV or name in allowed and name not in SECRET_NAMES
    }
    environment.update(secrets)
    environment["COMPOSE_DISABLE_ENV_FILE"] = "1"
    return environment, bridge_project


def run_compose(action: str, environment: dict[str, str], project: str, runner=subprocess.run) -> None:
    command = ["docker", "compose", "--project-name", project, "-f", str(COMPOSE_FILE), "--profile", "web-bridge"]
    if action == "preflight":
        command += ["config", "-q"]
    elif action == "build":
        command += ["build", "web-bridge"]
    elif action == "start":
        command += ["up", "-d", "--build", "web-bridge"]
    elif action in {"start-built", "restore"}:
        command += ["up", "-d", "--no-build", "web-bridge"]
    else:
        raise WebBridgeSecretError("compose action invalid")
    try:
        result = runner(
            command, cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=60 if action == "preflight" else 180, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise WebBridgeSecretError("compose failed") from error
    if result.returncode != 0:
        raise WebBridgeSecretError("compose failed")


def main(argv=None, provider_factory=None, runner=subprocess.run) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "start"))
    parser.add_argument("--map", type=Path)
    args = parser.parse_args(argv)
    try:
        map_path = args.map or (Path(os.environ["WEB_BRIDGE_SECRET_MAP_FILE"]) if os.environ.get("WEB_BRIDGE_SECRET_MAP_FILE") else None)
        if map_path is None:
            raise WebBridgeSecretError("secret map required")
        environment, project = resolve_environment(map_path, provider_factory)
        run_compose("preflight", environment, project, runner)
        if args.action == "start":
            run_compose("start", environment, project, runner)
        print(f"web_bridge_secret_runtime phase={args.action} status=PASS")
        return 0
    except Exception:
        print(f"web_bridge_secret_runtime phase={args.action} status=FAIL", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
