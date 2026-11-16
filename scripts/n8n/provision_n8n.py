#!/usr/bin/env python3
"""Fail-closed Linux provisioning for the existing LeadFlow n8n workflow."""
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
COMPOSE_FILES = (ROOT / "compose.yaml", ROOT / "compose.production.yaml")
WORKFLOW_FILE = ROOT / "workflows" / "leadflow_core_initial.json"
WORKFLOW_ID = "leadflow-core-initial"
CREDENTIAL_ID = "leadflow-postgres"
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
WORKFLOW_CONTENT_KEYS = ("id", "name", "settings", "nodes", "connections")


class ProvisionError(RuntimeError):
    def __init__(self, phase: str, error_id: str):
        self.phase = phase
        self.error_id = error_id
        super().__init__(error_id)


class InstallState:
    __slots__ = ("credential", "workflow", "active")

    def __init__(self, credential: str, workflow: str, active: bool | None):
        self.credential = credential
        self.workflow = workflow
        self.active = active


def load_secret_runtime():
    path = ROOT / "scripts" / "admin" / "compose_with_secrets.py"
    spec = importlib.util.spec_from_file_location("leadflow_n8n_secret_runtime", path)
    if spec is None or spec.loader is None:
        raise ProvisionError("preflight", "secret_runtime_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command_base(project: str) -> list[str]:
    return ["docker", "compose", "--project-name", project, "-f", str(COMPOSE_FILES[0]), "-f", str(COMPOSE_FILES[1])]


def run_checked(phase: str, operation: str, command: list[str], environment: dict[str, str], runner=subprocess.run, input_bytes: bytes | None = None) -> bytes:
    try:
        result = runner(command, cwd=ROOT, env=environment, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise ProvisionError(phase, f"{operation}_unavailable") from error
    if result.returncode != 0:
        raise ProvisionError(phase, f"{operation}_failed")
    return result.stdout or b""


def listed(output: bytes, expected_id: str) -> bool:
    try:
        lines = output.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise ProvisionError("preflight", "inventory_invalid") from error
    return any(line.split("|", 1)[0].strip() == expected_id for line in lines)


def credential_state(base: list[str], environment: dict[str, str], desired: bytes, runner=subprocess.run, phase="preflight") -> str:
    script = """umask 077
a=''; d=''
cleanup() { [ -z "$a" ] || rm -f -- "$a"; [ -z "$d" ] || rm -f -- "$d"; }
trap cleanup EXIT HUP INT TERM
a=$(mktemp /tmp/leadflow-n8n-actual.XXXXXX)
d=$(mktemp /tmp/leadflow-n8n-desired.XXXXXX)
chmod 600 "$a" "$d"
cat >"$d"
n8n export:credentials --id=leadflow-postgres --decrypted --output="$a" >/dev/null
node - "$a" "$d" <<'NODE'
const fs=require('fs');
const actual=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const desired=JSON.parse(fs.readFileSync(process.argv[3],'utf8'))[0];
const items=(Array.isArray(actual)?actual:[actual]).filter(x=>x!==null&&x!==undefined);
const stable=v=>Array.isArray(v)?v.map(stable):(v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v);
if(items.length===0) process.stdout.write('absent\n');
else if(items.length!==1 || !items[0] || items[0].id!==desired.id) process.stdout.write('ambiguous\n');
else {
 const selected=({id,name,type,data})=>({id,name,type,data});
 process.stdout.write(JSON.stringify(stable(selected(items[0])))===JSON.stringify(stable(selected(desired)))?'equivalent\n':'divergent\n');
}
NODE"""
    output = run_checked(phase, "credential_inventory", base + ["exec", "-T", "n8n", "sh", "-ceu", script], environment, runner, desired)
    value = output.decode("ascii", "strict").strip()
    if value not in {"absent", "equivalent", "divergent", "ambiguous"}:
        raise ProvisionError(phase, "credential_inventory_invalid")
    return value


def workflow_state(base: list[str], environment: dict[str, str], desired: dict, runner=subprocess.run, phase="preflight") -> tuple[str, bool | None]:
    workflows = run_checked(phase, "workflow_inventory", base + ["exec", "-T", "n8n", "n8n", "list:workflow"], environment, runner)
    if not listed(workflows, WORKFLOW_ID):
        return "absent", None
    export_script = "umask 077; p=$(mktemp /tmp/leadflow-n8n-workflow.XXXXXX); trap 'rm -f \"$p\"' EXIT HUP INT TERM; n8n export:workflow --id=leadflow-core-initial --output=\"$p\" >/dev/null; cat \"$p\""
    raw = run_checked(phase, "workflow_export", base + ["exec", "-T", "n8n", "sh", "-ceu", export_script], environment, runner)
    try:
        exported = json.loads(raw)
    except Exception as error:
        raise ProvisionError(phase, "workflow_inventory_invalid") from error
    items = exported if isinstance(exported, list) else [exported]
    items = [item for item in items if isinstance(item, dict) and item.get("id") == WORKFLOW_ID]
    if len(items) != 1 or not isinstance(items[0].get("active"), bool):
        return "ambiguous", None
    actual = {name: items[0].get(name) for name in WORKFLOW_CONTENT_KEYS}
    expected = {name: desired.get(name) for name in WORKFLOW_CONTENT_KEYS}
    return ("equivalent" if actual == expected else "divergent"), items[0]["active"]


def inspect_state(base: list[str], environment: dict[str, str], desired_workflow: dict, desired_credential: bytes, runner=subprocess.run, phase="preflight") -> InstallState:
    services = run_checked(phase, "service_inventory", base + ["ps", "--status", "running", "--services"], environment, runner)
    if "n8n" not in services.decode("utf-8", "strict").splitlines():
        raise ProvisionError(phase, "n8n_not_running")
    credential = credential_state(base, environment, desired_credential, runner, phase)
    workflow, active = workflow_state(base, environment, desired_workflow, runner, phase)
    return InstallState(credential, workflow, active)


def prepare(map_path: Path, provider_factory=None):
    project = os.environ.get("LEADFLOW_COMPOSE_PROJECT", "").strip()
    if not PROJECT_RE.fullmatch(project):
        raise ProvisionError("preflight", "compose_project_invalid")
    try:
        workflow = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
    except Exception as error:
        raise ProvisionError("preflight", "workflow_invalid") from error
    if not isinstance(workflow, dict) or workflow.get("id") != WORKFLOW_ID:
        raise ProvisionError("preflight", "workflow_invalid")
    runtime = load_secret_runtime()
    try:
        environment = runtime.resolved_environment(map_path, provider_factory or runtime.GcpSecretManagerProvider)
    except Exception as error:
        raise ProvisionError("preflight", "secret_resolution_failed") from error
    for name in ("POSTGRES_DB", "POSTGRES_APP_USER", "POSTGRES_APP_PASSWORD"):
        if not environment.get(name) or "\x00" in environment[name]:
            raise ProvisionError("preflight", "postgres_configuration_invalid")
    environment["LEADFLOW_COMPOSE_PROJECT"] = project
    environment["COMPOSE_DISABLE_ENV_FILE"] = "1"
    return environment, command_base(project), workflow


def preflight(map_path: Path, authorize_replace_credential: bool, authorize_replace_workflow: bool, authorize_active_replacement: bool, provider_factory=None, runner=subprocess.run):
    environment, base, workflow = prepare(map_path, provider_factory)
    run_checked("preflight", "compose_config", base + ["config", "-q"], environment, runner)
    credential = credential_payload(environment)
    state = inspect_state(base, environment, workflow, credential, runner)
    if "ambiguous" in {state.credential, state.workflow}:
        raise ProvisionError("preflight", "installation_state_ambiguous")
    if state.credential == "divergent" and not authorize_replace_credential:
        raise ProvisionError("preflight", "credential_divergence_requires_authorization")
    if state.workflow == "divergent" and not authorize_replace_workflow:
        raise ProvisionError("preflight", "workflow_divergence_requires_authorization")
    if state.workflow == "divergent" and state.active and not authorize_active_replacement:
        raise ProvisionError("preflight", "active_workflow_requires_authorization")
    return environment, base, workflow, credential, state


def credential_payload(environment: dict[str, str]) -> bytes:
    value = [{
        "id": CREDENTIAL_ID,
        "name": "LeadFlow PostgreSQL",
        "type": "postgres",
        "data": {
            "host": "postgres", "database": environment["POSTGRES_DB"],
            "user": environment["POSTGRES_APP_USER"], "password": environment["POSTGRES_APP_PASSWORD"],
            "port": 5432, "ssl": "disable",
        },
    }]
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def apply(environment: dict[str, str], base: list[str], desired_workflow: dict, desired_credential: bytes, initial: InstallState, authorize_publish: bool, runner=subprocess.run):
    import_script = "umask 077; p=$(mktemp /tmp/leadflow-n8n-credential.XXXXXX); trap 'rm -f \"$p\"' EXIT HUP INT TERM; cat >\"$p\"; chmod 600 \"$p\"; n8n import:credentials --input=\"$p\" >/dev/null"
    if initial.credential in {"absent", "divergent"}:
        try:
            run_checked("apply", "credential_import", base + ["exec", "-T", "n8n", "sh", "-ceu", import_script], environment, runner, desired_credential)
        except ProvisionError:
            reconciled = inspect_state(base, environment, desired_workflow, desired_credential, runner, "reconcile")
            if reconciled.credential != "equivalent":
                raise ProvisionError("reconcile", "credential_import_ambiguous")
    if initial.workflow in {"absent", "divergent"}:
        try:
            run_checked("apply", "workflow_import", base + ["exec", "-T", "n8n", "n8n", "import:workflow", "--input=/opt/leadflow/workflows/leadflow_core_initial.json"], environment, runner)
        except ProvisionError:
            reconciled = inspect_state(base, environment, desired_workflow, desired_credential, runner, "reconcile")
            if reconciled.workflow != "equivalent":
                raise ProvisionError("reconcile", "workflow_import_ambiguous")
    should_be_active = bool(authorize_publish or initial.active is True)
    current = inspect_state(base, environment, desired_workflow, desired_credential, runner, "verify")
    if current.credential != "equivalent" or current.workflow != "equivalent":
        raise ProvisionError("verify", "content_reconciliation_failed")
    if should_be_active and not current.active:
        try:
            run_checked("apply", "workflow_publish", base + ["exec", "-T", "n8n", "n8n", "publish:workflow", f"--id={WORKFLOW_ID}"], environment, runner)
        except ProvisionError:
            current = inspect_state(base, environment, desired_workflow, desired_credential, runner, "reconcile")
            if not current.active:
                raise ProvisionError("reconcile", "workflow_publish_ambiguous")
    final = inspect_state(base, environment, desired_workflow, desired_credential, runner, "verify")
    if final.credential != "equivalent" or final.workflow != "equivalent" or final.active is not should_be_active:
        raise ProvisionError("verify", "final_state_mismatch")


def main(argv=None, provider_factory=None, runner=subprocess.run) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "apply"))
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--authorize-provision", action="store_true")
    parser.add_argument("--authorize-replace-credential", action="store_true")
    parser.add_argument("--authorize-replace-workflow", action="store_true")
    parser.add_argument("--authorize-active-replacement", action="store_true")
    parser.add_argument("--authorize-publish", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "apply" and not args.authorize_provision:
            raise ProvisionError("authorization", "provision_not_authorized")
        environment, base, workflow, credential, state = preflight(
            args.map, args.authorize_replace_credential, args.authorize_replace_workflow,
            args.authorize_active_replacement, provider_factory, runner,
        )
        if args.action == "apply":
            apply(environment, base, workflow, credential, state, args.authorize_publish, runner)
        print(f"n8n_linux_provision phase={args.action} status=PASS")
        return 0
    except ProvisionError as error:
        print(f"n8n_linux_provision phase={error.phase} status=FAIL error_id={error.error_id}", file=sys.stderr)
        return 1
    except Exception:
        print("n8n_linux_provision phase=internal status=FAIL error_id=unexpected", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
