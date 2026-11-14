#!/usr/bin/env python3
"""Non-destructive validation of an already running isolated Web Bridge."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit


PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
NETWORK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
PATH_RE = re.compile(r"/[A-Za-z0-9/_-]{1,100}")
CONTAINER_CODE = r'''
import json, os, sys, urllib.request, uuid
request = json.loads(sys.stdin.read())
if request["operation"] == "health":
    response = urllib.request.urlopen(request["url"], timeout=5)
    raise SystemExit(0 if response.status == 200 else 4)
token = request["turnstile_token"]
abuse = os.environ.get("WEB_BRIDGE_ABUSE_TOKEN", "")
if not token or not abuse:
    raise SystemExit(5)
payload = {
    "nombre": "Nombre Sintetico", "apellido": "Apellido Sintetico",
    "email": "lead.synthetic@example.test", "negocio": "Empresa Sintetica",
    "telefono": "+15550100000", "interes": request["interest"],
    "mensaje": "Validacion sintetica controlada.",
}
body = json.dumps(payload, separators=(",", ":")).encode()
headers = {
    "Content-Type": "application/json", "Origin": request["origin"],
    "X-LeadFlow-Submission-Id": str(uuid.uuid4()),
    "X-LeadFlow-Abuse-Token": abuse, "X-Turnstile-Token": token,
}
http_request = urllib.request.Request("http://127.0.0.1:8080" + request["path"], body, headers, method="POST")
response = urllib.request.urlopen(http_request, timeout=15)
raise SystemExit(0 if response.status == 202 else 6)
'''


class ValidationError(RuntimeError):
    def __init__(self, error_id: str):
        self.error_id = error_id
        super().__init__(error_id)


def run(command: list[str], *, input_data: str | None = None, timeout: int = 15, runner=subprocess.run):
    try:
        result = runner(
            command, input=input_data, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValidationError("command_failed") from error
    if result.returncode != 0:
        raise ValidationError("command_failed")
    return result.stdout.strip()


def required_config(env: dict[str, str]) -> tuple[str, str, str, str, str]:
    project = env.get("WEB_BRIDGE_COMPOSE_PROJECT", "").strip()
    main_project = env.get("LEADFLOW_COMPOSE_PROJECT", "").strip()
    network = env.get("WEB_BRIDGE_UPSTREAM_NETWORK", "").strip()
    health_url = env.get("WEB_BRIDGE_N8N_HEALTH_URL", "").strip()
    public_path = env.get("WEB_BRIDGE_PUBLIC_PATH", "").strip()
    origin = env.get("WEB_BRIDGE_ALLOWED_ORIGIN", "").strip()
    if not PROJECT_RE.fullmatch(project) or not PROJECT_RE.fullmatch(main_project) or project == main_project:
        raise ValidationError("project_configuration")
    if not NETWORK_RE.fullmatch(network):
        raise ValidationError("network_configuration")
    health = urlsplit(health_url)
    allowed_origin = urlsplit(origin)
    if (
        health.scheme not in {"http", "https"} or not health.hostname or health.username or health.password or health.fragment
        or allowed_origin.scheme != "https" or not allowed_origin.hostname or allowed_origin.username or allowed_origin.password
        or allowed_origin.path.strip("/") or allowed_origin.query or allowed_origin.fragment
        or not PATH_RE.fullmatch(public_path)
    ):
        raise ValidationError("endpoint_configuration")
    return project, network, health_url, public_path, origin


def locate_bridge(project: str, runner=subprocess.run) -> str:
    output = run([
        "docker", "ps", "--filter", f"label=com.docker.compose.project={project}",
        "--filter", "label=com.docker.compose.service=web-bridge", "--format", "{{.ID}}",
    ], runner=runner)
    identifiers = [item for item in output.splitlines() if item]
    if len(identifiers) != 1:
        raise ValidationError("bridge_container")
    return identifiers[0]


def validate_container(container: str, network: str, runner=subprocess.run) -> None:
    running = run(["docker", "inspect", "--format", "{{.State.Running}}", container], runner=runner)
    ports_raw = run(["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container], runner=runner)
    networks = run([
        "docker", "inspect", "--format",
        "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{\"\\n\"}}{{end}}", container,
    ], runner=runner)
    try:
        ports = json.loads(ports_raw)
    except json.JSONDecodeError as error:
        raise ValidationError("bridge_inspection") from error
    if running != "true" or network not in networks.splitlines() or any(value for value in ports.values()):
        raise ValidationError("bridge_isolation")


def exec_probe(container: str, request: dict, runner=subprocess.run) -> None:
    run(["docker", "exec", "-i", container, "python", "-c", CONTAINER_CODE],
        input_data=json.dumps(request), timeout=20, runner=runner)


def main(argv=None, *, env=None, runner=subprocess.run, token_reader=getpass.getpass) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--functional", action="store_true")
    args = parser.parse_args(argv)
    values = os.environ if env is None else env
    phase = "functional" if args.functional else "preflight"
    try:
        project, network, health_url, public_path, origin = required_config(values)
        container = locate_bridge(project, runner)
        validate_container(container, network, runner)
        exec_probe(container, {"operation": "health", "url": health_url}, runner)
        print("web_bridge_gcp phase=preflight status=PASS")
        if not args.functional:
            print("web_bridge_gcp phase=functional status=NOT_VERIFIED")
            return 0
        if values.get("WEB_BRIDGE_QA_EXTERNAL_EFFECTS_DISABLED") != "true":
            raise ValidationError("functional_safety_gate")
        interest = values.get("WEB_BRIDGE_SYNTHETIC_INTEREST", "").strip()
        if not interest or len(interest) > 100:
            raise ValidationError("functional_configuration")
        token = token_reader("Turnstile token efimero: ")
        try:
            exec_probe(container, {
                "operation": "functional", "turnstile_token": token, "origin": origin,
                "path": public_path, "interest": interest,
            }, runner)
        finally:
            token = ""
        print("web_bridge_gcp phase=functional status=PASS")
        print("web_bridge_gcp phase=cleanup status=NOT_APPLICABLE policy=retention")
        return 0
    except ValidationError as error:
        print(f"web_bridge_gcp phase={phase} status=FAIL error_id={error.error_id}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
