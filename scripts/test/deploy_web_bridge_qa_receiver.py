#!/usr/bin/env python3
"""Supervised, resumable deployment procedure for the isolated QA receiver."""
from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
RECEIVER_COMPOSE = ROOT / "compose.web-bridge-qa-receiver.yaml"
BRIDGE_COMPOSE = ROOT / "compose.web-bridge.yaml"
RECEIVER_SERVICE = "qa-receiver"
EGRESS_SERVICE = "qa-egress"
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
NETWORK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
PATH_RE = re.compile(r"/[A-Za-z0-9/_-]{1,100}")
OPERATION_ENV = frozenset({
    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "DOCKER_HOST", "DOCKER_CONTEXT",
    "DOCKER_CONFIG", "XDG_CONFIG_HOME", "TMPDIR", "TEMP", "TMP",
})
SAFE_INSPECT_CODE = "import os; print(os.environ.get('WEB_BRIDGE_UPSTREAM_URL',''))"
HEALTH_CODE = "import sys,urllib.request; u=sys.stdin.read(); r=urllib.request.urlopen(u,timeout=5); raise SystemExit(0 if r.status==200 else 4)"
PROXY_TLS_CODE = "import http.client,os,urllib.parse; p=urllib.parse.urlsplit(os.environ['WEB_BRIDGE_TURNSTILE_PROXY_URL']); c=http.client.HTTPSConnection(p.hostname,p.port,timeout=5); c.set_tunnel('challenges.cloudflare.com',443); c.connect(); c.close()"


class ProcedureError(RuntimeError):
    def __init__(self, error_id: str):
        self.error_id = error_id
        super().__init__(error_id)


@dataclass(frozen=True)
class Config:
    main_project: str
    expected_main_count: int
    bridge_project: str
    receiver_project: str
    main_network: str
    qa_network: str
    egress_network: str
    receiver_port: int
    egress_port: int
    receiver_path: str
    upstream_url: str
    proxy_url: str


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProcedureError("module_unavailable")
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


def read_config(env) -> Config:
    projects = [env.get(name, "").strip() for name in (
        "LEADFLOW_COMPOSE_PROJECT", "WEB_BRIDGE_COMPOSE_PROJECT", "WEB_BRIDGE_QA_RECEIVER_PROJECT",
    )]
    main_network = env.get("LEADFLOW_MAIN_NETWORK", "").strip()
    qa_network = env.get("WEB_BRIDGE_QA_NETWORK", "").strip()
    egress_network = env.get("WEB_BRIDGE_QA_EGRESS_NETWORK", "").strip()
    path = env.get("QA_RECEIVER_PATH", "").strip()
    upstream = env.get("WEB_BRIDGE_UPSTREAM_URL", "").strip()
    try:
        expected = int(env.get("LEADFLOW_EXPECTED_MAIN_CONTAINERS", ""))
        port = int(env.get("QA_RECEIVER_PORT", ""))
        egress_port = int(env.get("QA_EGRESS_PORT", ""))
    except ValueError as error:
        raise ProcedureError("configuration_numeric") from error
    if any(not PROJECT_RE.fullmatch(item) for item in projects) or len(set(projects)) != 3 or expected <= 0:
        raise ProcedureError("project_configuration")
    if (
        any(not NETWORK_RE.fullmatch(item) for item in (main_network, qa_network, egress_network))
        or len({main_network, qa_network, egress_network}) != 3
    ):
        raise ProcedureError("network_configuration")
    if not 1024 <= port <= 65535 or not 1024 <= egress_port <= 65535 or port == egress_port or not PATH_RE.fullmatch(path):
        raise ProcedureError("receiver_configuration")
    parsed = urlsplit(upstream)
    if parsed.scheme != "http" or parsed.hostname != RECEIVER_SERVICE or parsed.port != port or parsed.path != path or parsed.query or parsed.fragment:
        raise ProcedureError("unsafe_upstream")
    if env.get("WEB_BRIDGE_UPSTREAM_NETWORK", "").strip() != qa_network:
        raise ProcedureError("unsafe_upstream_network")
    proxy_url = env.get("WEB_BRIDGE_TURNSTILE_PROXY_URL", "").strip()
    proxy = urlsplit(proxy_url)
    if (
        proxy.scheme != "http" or proxy.hostname != EGRESS_SERVICE or proxy.port != egress_port
        or proxy.path not in {"", "/"} or proxy.username or proxy.password or proxy.query or proxy.fragment
    ):
        raise ProcedureError("unsafe_turnstile_proxy")
    return Config(projects[0], expected, projects[1], projects[2], main_network, qa_network,
                  egress_network, port, egress_port, path, upstream, proxy_url)


def run(command, *, runner=subprocess.run, environment=None, input_data=None, timeout=60):
    try:
        result = runner(command, cwd=ROOT, env=environment, input=input_data, text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise ProcedureError("command_failed") from error
    if result.returncode != 0:
        raise ProcedureError("command_failed")
    return result.stdout.strip()


def containers(project: str, service: str | None = None, runner=subprocess.run):
    command = ["docker", "ps", "--filter", f"label=com.docker.compose.project={project}"]
    if service:
        command += ["--filter", f"label=com.docker.compose.service={service}"]
    command += ["--format", "{{.ID}}"]
    return [item for item in run(command, runner=runner).splitlines() if item]


def validate_owned_network(name: str, expected_owner: str, runner=subprocess.run, required=False):
    matches = [item for item in run([
        "docker", "network", "ls", "--filter", f"name=^{name}$", "--format", "{{.Name}}",
    ], runner=runner).splitlines() if item == name]
    if not matches:
        if required:
            raise ProcedureError("network_missing")
        return False
    if len(matches) != 1:
        raise ProcedureError("network_ambiguous")
    owner = run(["docker", "network", "inspect", "--format", '{{index .Labels "com.emactiva.component"}}', name], runner=runner)
    if owner != expected_owner:
        raise ProcedureError("network_ownership")
    return True


def inspect_container(identifier: str, expected_network: str, runner=subprocess.run):
    running = run(["docker", "inspect", "--format", "{{.State.Running}}", identifier], runner=runner)
    ports = json.loads(run(["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", identifier], runner=runner))
    networks = run(["docker", "inspect", "--format", "{{range $n, $_ := .NetworkSettings.Networks}}{{$n}}{{\"\\n\"}}{{end}}", identifier], runner=runner).splitlines()
    if running != "true" or networks != [expected_network] or any(value for value in ports.values()):
        raise ProcedureError("container_isolation")


def inspect_egress(identifier: str, config: Config, runner=subprocess.run):
    running = run(["docker", "inspect", "--format", "{{.State.Running}}", identifier], runner=runner)
    ports = json.loads(run(["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", identifier], runner=runner))
    networks = set(run(["docker", "inspect", "--format", "{{range $n, $_ := .NetworkSettings.Networks}}{{$n}}{{\"\\n\"}}{{end}}", identifier], runner=runner).splitlines())
    owner = run(["docker", "inspect", "--format", '{{index .Config.Labels "com.emactiva.component"}}', identifier], runner=runner)
    if running != "true" or networks != {config.qa_network, config.egress_network} or any(ports.values()) or owner != "web-bridge-qa-egress":
        raise ProcedureError("egress_isolation")


def receiver_environment(base: dict[str, str], config: Config):
    result = {name: value for name, value in base.items() if name in OPERATION_ENV or name == "LEADFLOW_WEBHOOK_KEY"}
    result.update({
        "WEB_BRIDGE_QA_NETWORK": config.qa_network,
        "QA_RECEIVER_PORT": str(config.receiver_port),
        "QA_RECEIVER_PATH": config.receiver_path,
        "WEB_BRIDGE_QA_EGRESS_NETWORK": config.egress_network,
        "QA_EGRESS_PORT": str(config.egress_port),
        "COMPOSE_DISABLE_ENV_FILE": "1",
    })
    return result


def receiver_compose(config: Config, action: str, environment, runner=subprocess.run):
    command = ["docker", "compose", "--project-name", config.receiver_project, "-f", str(RECEIVER_COMPOSE), "--profile", "qa-receiver"]
    if action == "preflight": command += ["config", "-q"]
    elif action == "start": command += ["up", "-d", "--build", RECEIVER_SERVICE, EGRESS_SERVICE]
    elif action == "remove-egress": command += ["rm", "--stop", "--force", EGRESS_SERVICE]
    else: raise ProcedureError("invalid_action")
    run(command, runner=runner, environment=environment, timeout=180 if action == "start" else 60)


def preflight(config: Config, bridge_env, runner=subprocess.run):
    for path in (
        RECEIVER_COMPOSE, BRIDGE_COMPOSE, ROOT / "bridge" / "qa_receiver.py", ROOT / "bridge" / "Dockerfile.qa-receiver",
        ROOT / "bridge" / "qa_egress_proxy.py", ROOT / "bridge" / "Dockerfile.qa-egress",
    ):
        if not path.is_file(): raise ProcedureError("file_missing")
    run(["docker", "version", "--format", "{{.Server.Version}}"], runner=runner)
    run(["docker", "compose", "version", "--short"], runner=runner)
    validate_owned_network(config.qa_network, "web-bridge-qa-network", runner, required=True)
    validate_owned_network(config.egress_network, "web-bridge-qa-egress-network", runner)
    main_snapshot = containers(config.main_project, runner=runner)
    if len(main_snapshot) != config.expected_main_count:
        raise ProcedureError("main_container_count")
    if len(containers(config.bridge_project, "web-bridge", runner)) != 1:
        raise ProcedureError("bridge_container")
    existing = containers(config.receiver_project, RECEIVER_SERVICE, runner)
    existing_egress = containers(config.receiver_project, EGRESS_SERVICE, runner)
    if len(existing) > 1:
        raise ProcedureError("receiver_ambiguous")
    if existing:
        owner = run(["docker", "inspect", "--format", '{{index .Config.Labels "com.emactiva.component"}}', existing[0]], runner=runner)
        if owner != "web-bridge-qa-receiver":
            raise ProcedureError("receiver_ownership")
    if len(existing_egress) > 1:
        raise ProcedureError("egress_ambiguous")
    if existing_egress:
        owner = run(["docker", "inspect", "--format", '{{index .Config.Labels "com.emactiva.component"}}', existing_egress[0]], runner=runner)
        if owner != "web-bridge-qa-egress":
            raise ProcedureError("egress_ownership")
    receiver_compose(config, "preflight", receiver_environment(bridge_env, config), runner)
    return tuple(main_snapshot)


def verify(config: Config, runner=subprocess.run, functional=False, token_reader=getpass.getpass, interest="", origin="", public_path=""):
    if len(containers(config.main_project, runner=runner)) != config.expected_main_count:
        raise ProcedureError("main_container_count")
    bridge = containers(config.bridge_project, "web-bridge", runner)
    receiver = containers(config.receiver_project, RECEIVER_SERVICE, runner)
    egress = containers(config.receiver_project, EGRESS_SERVICE, runner)
    if len(bridge) != 1 or len(receiver) != 1 or len(egress) != 1:
        raise ProcedureError("qa_container_count")
    inspect_container(bridge[0], config.qa_network, runner)
    inspect_container(receiver[0], config.qa_network, runner)
    inspect_egress(egress[0], config, runner)
    effective = run(["docker", "exec", bridge[0], "python", "-c", SAFE_INSPECT_CODE], runner=runner)
    if effective != config.upstream_url:
        raise ProcedureError("upstream_mismatch")
    proxy_effective = run(["docker", "exec", bridge[0], "python", "-c", "import os; print(os.environ.get('WEB_BRIDGE_TURNSTILE_PROXY_URL',''))"], runner=runner)
    if proxy_effective != config.proxy_url:
        raise ProcedureError("turnstile_proxy_mismatch")
    run(["docker", "exec", bridge[0], "python", "-c", PROXY_TLS_CODE], runner=runner)
    health_url = f"http://{RECEIVER_SERVICE}:{config.receiver_port}/healthz"
    run(["docker", "exec", "-i", bridge[0], "python", "-c", HEALTH_CODE], runner=runner, input_data=health_url)
    if functional:
        allowed_origin = urlsplit(origin)
        if (
            not interest or len(interest) > 100 or not PATH_RE.fullmatch(public_path)
            or allowed_origin.scheme != "https" or not allowed_origin.hostname
            or allowed_origin.username or allowed_origin.password or allowed_origin.path.strip("/")
            or allowed_origin.query or allowed_origin.fragment
        ):
            raise ProcedureError("functional_configuration")
        validator = load_module("web_bridge_gcp_validator", ROOT / "scripts" / "test" / "validate_web_bridge_gcp.py")
        token = token_reader("Turnstile token efimero: ")
        try:
            validator.exec_probe(bridge[0], {
                "operation": "functional", "turnstile_token": token,
                "origin": origin, "path": public_path, "interest": interest,
            }, runner)
        finally:
            token = ""


def main(argv=None, *, env=None, runner=subprocess.run, resolver=None, token_reader=getpass.getpass):
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", nargs="?", choices=("preflight", "apply", "verify", "rollback"), default="preflight")
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--authorize-apply", action="store_true")
    parser.add_argument("--functional", action="store_true")
    args = parser.parse_args(argv)
    values = dict(os.environ if env is None else env)
    try:
        config = read_config(values)
        loader = load_module("web_bridge_secret_loader", ROOT / "scripts" / "admin" / "web_bridge_with_secrets.py")
        resolve = resolver or loader.resolve_environment
        bridge_env, project = resolve(args.map)
        if project != config.bridge_project or set(loader.SECRET_NAMES) - set(bridge_env):
            raise ProcedureError("secret_delivery")
        main_snapshot = preflight(config, bridge_env, runner)
        loader.run_compose("preflight", bridge_env, config.bridge_project, runner)
        print("qa_receiver phase=preflight status=PASS")
        if args.phase == "preflight": return 0
        if args.phase in {"apply", "rollback"} and not args.authorize_apply:
            raise ProcedureError("authorization_required")
        if args.phase == "apply":
            loader.run_compose("build", bridge_env, config.bridge_project, runner)
            receiver_compose(config, "start", receiver_environment(bridge_env, config), runner)
            loader.run_compose("start-built", bridge_env, config.bridge_project, runner)
            if tuple(containers(config.main_project, runner=runner)) != main_snapshot:
                raise ProcedureError("main_containers_changed")
            print("qa_receiver phase=apply status=PASS")
            return 0
        if args.phase == "verify":
            verify(
                config, runner, args.functional, token_reader,
                values.get("WEB_BRIDGE_SYNTHETIC_INTEREST", "").strip(),
                values.get("WEB_BRIDGE_ALLOWED_ORIGIN", "").strip(),
                values.get("WEB_BRIDGE_PUBLIC_PATH", "").strip(),
            )
            print("qa_receiver phase=verify status=PASS")
            return 0
        previous_url = values.get("WEB_BRIDGE_PREVIOUS_UPSTREAM_URL", "").strip()
        previous_network = values.get("WEB_BRIDGE_PREVIOUS_UPSTREAM_NETWORK", "").strip()
        previous_proxy = values.get("WEB_BRIDGE_PREVIOUS_TURNSTILE_PROXY_URL", "").strip()
        if not previous_url or not NETWORK_RE.fullmatch(previous_network) or not previous_proxy:
            raise ProcedureError("rollback_configuration")
        restored = dict(bridge_env); restored["WEB_BRIDGE_UPSTREAM_URL"] = previous_url; restored["WEB_BRIDGE_UPSTREAM_NETWORK"] = previous_network
        restored["WEB_BRIDGE_TURNSTILE_PROXY_URL"] = "" if previous_proxy == "DIRECT" else previous_proxy
        loader.run_compose("restore", restored, config.bridge_project, runner)
        receiver_compose(config, "remove-egress", receiver_environment(bridge_env, config), runner)
        if validate_owned_network(config.egress_network, "web-bridge-qa-egress-network", runner):
            run(["docker", "network", "rm", config.egress_network], runner=runner)
        print("qa_receiver phase=rollback status=PASS")
        return 0
    except ProcedureError as error:
        print(f"qa_receiver phase={args.phase} status=FAIL error_id={error.error_id}", file=sys.stderr)
        return 1
    except Exception:
        print(f"qa_receiver phase={args.phase} status=FAIL error_id=unexpected", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
