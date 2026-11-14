#!/usr/bin/env python3
"""One-shot isolated LF015 gateway-to-core QA runner."""
from __future__ import annotations

import json, os, re, shutil, socket, ssl, subprocess, tempfile, time, urllib.request, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_PROJECT, BRIDGE_PROJECT, GATEWAY_PROJECT = "lf015-core-qa", "lf015-core-qa-bridge", "lf015-core-qa-gateway"
CORE_FILES = [ROOT / "compose.yaml", ROOT / "compose.core-qa.yaml"]
BRIDGE_FILES = [ROOT / "compose.web-bridge.yaml", ROOT / "compose.web-bridge-local-integration.yaml"]
GATEWAY_FILES = [ROOT / "compose.web-gateway.local.yaml"]

class GateError(RuntimeError): pass

def safe_diagnostic(output: str) -> str:
    rules = (
        (r"Required environment variable|Missing environment variable", "configuration_missing"),
        (r"role synchronization failed", "role_sync_failed"),
        (r"Could not determine PostgreSQL role topology", "role_topology_failed"),
        (r"Migration failed", "migration_failed"),
        (r"Could not inspect the migration ledger", "migration_ledger_failed"),
        (r"n8n did not become ready", "n8n_health_failed"),
        (r"Could not create protected temporary credential file", "n8n_credential_file_failed"),
        (r"dependency failed|dependency.*unhealthy", "compose_dependency_failed"),
        (r"port is already allocated|address already in use", "compose_port_collision"),
        (r"invalid mount config|bind source path does not exist|mount denied", "compose_mount_failed"),
        (r"pull access denied|unable to get image|no such image", "compose_image_missing"),
        (r"Could not start n8n", "n8n_start_failed"),
        (r"Credential import failed", "n8n_credential_import_failed"),
        (r"Workflow import failed", "n8n_workflow_import_failed"),
        (r"Workflow activation failed", "n8n_workflow_publish_failed"),
        (r"Published LeadFlow webhook did not become ready", "n8n_webhook_failed"),
        (r"not recognized|not found|No such file", "dependency_missing"),
    )
    for pattern, code in rules:
        if re.search(pattern, output, re.IGNORECASE): return code
    return "command_error"

def run(args, env, *, capture=False, input_text=None, check=True):
    result = subprocess.run(args, cwd=ROOT, env=env, text=True, input=input_text,
                            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.PIPE if capture else subprocess.DEVNULL)
    if check and result.returncode:
        raise GateError(f"command_failed:{Path(args[0]).name}:{result.returncode}")
    return result

def run_checked(phase, operation, args, env):
    result=run(args,env,capture=True,check=False)
    if result.returncode:
        diagnostic=safe_diagnostic((result.stdout or "")+"\n"+(result.stderr or ""))
        raise GateError(f"{phase}:{operation}:exit_{result.returncode}:{diagnostic}")
    return result

def compose(project, files, *args):
    cmd = ["docker", "compose", "--project-name", project]
    for item in files: cmd += ["-f", str(item)]
    return cmd + list(args)

def owned_storage(kind, env):
    names=run(["docker",kind,"ls","--format","{{.Name}}"],env,capture=True,check=False).stdout.split()
    return [name for name in names if name.startswith(("lf015-core-qa", "lf015_core_qa"))]

def sanitized_core_state(env):
    result=run(["docker","ps","-a","--filter",f"label=com.docker.compose.project={CORE_PROJECT}","--format",'{{.Label "com.docker.compose.service"}}={{.State}}/{{.Status}}'],env,capture=True,check=False)
    return ",".join(sorted(line.strip() for line in result.stdout.splitlines() if line.strip())) or "none"

def main() -> int:
    env = os.environ.copy(); temp = Path(tempfile.mkdtemp(prefix="lf015-core-qa-")); ca = temp / "root.crt"
    synthetic = {
        "POSTGRES_DB":"leadflow_core_qa", "POSTGRES_BOOTSTRAP_USER":"lf015_bootstrap", "POSTGRES_BOOTSTRAP_PASSWORD":"synthetic-bootstrap-0000000000000001",
        "POSTGRES_MIGRATOR_USER":"lf015_migrator", "POSTGRES_MIGRATOR_PASSWORD":"synthetic-migrator-0000000000000002", "POSTGRES_APP_USER":"lf015_app", "POSTGRES_APP_PASSWORD":"synthetic-app-00000000000000000003",
        "POSTGRES_ROLE_SYNC_USER":"lf015_bootstrap", "APP_ENV":"development", "CRM_PROVIDER":"mock", "ENRICHMENT_PROVIDER":"mock", "N8N_ENCRYPTION_KEY":"synthetic-n8n-key-0000000000000000000001",
        "LEADFLOW_WEBHOOK_KEY":"synthetic-webhook-key-00000000000000000001", "LEADFLOW_ALLOWED_SOURCES":"emactiva_web", "LEADFLOW_ALLOWED_INTERESTS":"automatizacion", "DSR_SUBJECT_KEY":"synthetic-dsr-key-0000000000000000000001",
        "RECOVERY_CONTEXT_KEY":"synthetic-recovery-key-000000000000000001", "ADAPTER_SERVICE_KEY":"synthetic-adapter-key-0000000000000000001", "DSR_ADAPTER_SERVICE_KEY":"synthetic-dsr-adapter-000000000000000001",
        "ADAPTER_ALLOWED_OPERATIONS":"crm.process,crm.update_enrichment,crm.record_interaction,crm.reconcile_interaction,enrichment.enrich,alert.send,crm.capabilities", "LF015_CORE_QA_NETWORK":"lf015_core_qa_internal", "LEADFLOW_N8N_LOCAL_DIR":str(temp / "n8n"), "LEADFLOW_N8N_PROBE_MODE":"container",
        "WEB_BRIDGE_ENV":"qa", "WEB_BRIDGE_PUBLIC_PATH":"/lead", "WEB_BRIDGE_UPSTREAM_URL":"http://n8n:5678/webhook/leadflow", "WEB_BRIDGE_SOURCE":"emactiva_web", "WEB_BRIDGE_EVENT_ID_KEY":"synthetic-event-key-0000000000000000000001",
        "WEB_BRIDGE_ALLOWED_ORIGINS":"https://form.example.invalid", "WEB_BRIDGE_ABUSE_CONTROL":"external", "WEB_BRIDGE_ABUSE_TOKEN":"synthetic-abuse-key-0000000000000000000001", "WEB_BRIDGE_TURNSTILE_MODE":"siteverify",
        "WEB_BRIDGE_TURNSTILE_SECRET_KEY":"synthetic-turnstile-key-000000000000000001", "WEB_BRIDGE_TURNSTILE_HOSTNAMES":"form.example.invalid", "WEB_BRIDGE_TURNSTILE_ACTION":"lead_submit", "WEB_BRIDGE_UPSTREAM_NETWORK":"lf015_core_qa_internal",
        "WEB_GATEWAY_BIND_ADDRESS":"127.0.0.1", "WEB_GATEWAY_HTTPS_PORT":"18447", "WEB_GATEWAY_HOST":"localhost", "WEB_GATEWAY_PUBLIC_PATH":"/lead", "WEB_GATEWAY_ALLOWED_ORIGINS":"https://form.example.invalid", "WEB_GATEWAY_UPSTREAM_URL":"http://web-bridge:8080/lead",
        "WEB_GATEWAY_MAX_BODY_BYTES":"16384", "WEB_GATEWAY_REQUEST_TIMEOUT_SECONDS":"5", "WEB_GATEWAY_UPSTREAM_TIMEOUT_SECONDS":"15", "WEB_GATEWAY_RATE_REQUESTS":"4", "WEB_GATEWAY_RATE_WINDOW_SECONDS":"30", "WEB_GATEWAY_RATE_MAX_KEYS":"100", "COMPOSE_PROFILES":"web-bridge,web-gateway-local",
    }; env.update(synthetic); env["COMPOSE_PROJECT_NAME"]=CORE_PROJECT; env["COMPOSE_FILE"]=os.pathsep.join(map(str,CORE_FILES)); (temp / "n8n").mkdir()
    main_before = sorted(run(["docker","ps","--filter","label=com.docker.compose.project=emactiva-leadflow","--format","{{.ID}}"],env,capture=True).stdout.split())
    failed = None; owned = False
    try:
        if len(main_before) != 6: raise GateError("main_inventory")
        existing=[]
        for project in (CORE_PROJECT,BRIDGE_PROJECT,GATEWAY_PROJECT):
            existing += run(["docker","ps","-a","--filter",f"label=com.docker.compose.project={project}","--format","{{.ID}}"],env,capture=True).stdout.split()
        existing += owned_storage("network",env)+owned_storage("volume",env)
        if existing: raise GateError("preflight:ownership:qa_resources_preexist")
        for port in (18447,):
            with socket.socket() as probe:
                try: probe.bind(("127.0.0.1",port))
                except OSError as exc: raise GateError("loopback_port_collision") from exc
        for project, files in ((CORE_PROJECT,CORE_FILES),(BRIDGE_PROJECT,BRIDGE_FILES),(GATEWAY_PROJECT,GATEWAY_FILES)):
            run_checked("preflight","compose_config",compose(project,files,"config","--quiet"),env)
        config=json.loads(run(compose(CORE_PROJECT,CORE_FILES,"config","--format","json"),env,capture=True).stdout)
        adapter=config["services"]["adapters"]["environment"]
        if adapter.get("CRM_PROVIDER")!="mock" or adapter.get("ENRICHMENT_PROVIDER")!="mock" or not config["networks"]["default"].get("internal"): raise GateError("unsafe_core_config")
        owned=True
        run_checked("core_start","compose_up",compose(CORE_PROJECT,CORE_FILES,"up","-d","--no-build","postgres","crm-mock","enrichment-mock","slack-mock","adapters"),env)
        run_checked("database","apply_migrations",["pwsh","-NoProfile","-File",str(ROOT/"scripts/database/apply_migrations.ps1")],env)
        run_checked("n8n","provision",["pwsh","-NoProfile","-File",str(ROOT/"scripts/n8n/provision_n8n.ps1")],env)
        run_checked("bridge","compose_up",compose(BRIDGE_PROJECT,BRIDGE_FILES,"up","-d","--no-build","siteverify-mock","web-bridge"),env)
        run_checked("gateway","compose_up",compose(GATEWAY_PROJECT,GATEWAY_FILES,"up","-d","--no-build"),env)
        time.sleep(4)
        caddy=run(compose(GATEWAY_PROJECT,GATEWAY_FILES,"ps","-q","caddy"),env,capture=True).stdout.strip()
        run(["docker","cp",f"{caddy}:/data/caddy/pki/authorities/local/root.crt",str(ca)],env)
        context=ssl.create_default_context(cafile=str(ca))
        def submit(sid, message):
            body=json.dumps({"nombre":"Synthetic","apellido":"QA","email":"lead@example.invalid","negocio":"QA","telefono":"+56900000000","interes":"automatizacion","mensaje":message},separators=(",",":")).encode()
            req=urllib.request.Request("https://localhost:18447/lead",body,method="POST",headers={"Content-Type":"application/json","Origin":"https://form.example.invalid","X-LeadFlow-Submission-Id":sid,"X-Turnstile-Token":"synthetic-token"})
            with urllib.request.urlopen(req,context=context,timeout=20) as response: return response.status
        first=str(uuid.uuid4()); second=str(uuid.uuid4())
        statuses=[submit(first,"Synthetic first"),submit(second,"Synthetic second"),submit(first,"Synthetic first")]
        stats=json.loads(run(compose(CORE_PROJECT,CORE_FILES,"exec","-T","crm-mock","python","-c","import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/stats').read().decode())"),env,capture=True).stdout)
        sql="SELECT count(DISTINCT idempotency_key)||'|'||count(DISTINCT lead_identifier)||'|'||count(*) FILTER (WHERE interaction_status='confirmed')||'|'||count(*) FROM leadflow.executions;"
        db=run(compose(CORE_PROJECT,CORE_FILES,"exec","-T","postgres","psql","-X","-Atq","-U",synthetic["POSTGRES_APP_USER"],"-d",synthetic["POSTGRES_DB"],"-c",sql),env,capture=True).stdout.strip()
        if stats.get("contacts")!=1 or stats.get("interactions")!=2 or db!="2|1|2|3":
            safe_db=db if re.fullmatch(r"\d+\|\d+\|\d+\|\d+",db) else "invalid"
            raise GateError(f"state_mismatch:http_{'-'.join(map(str,statuses))}:db_{safe_db}:crm_{stats.get('contacts')}-{stats.get('interactions')}")
        print(f"core_qa status=PASS http={','.join(map(str,statuses))} db=2|1|2 executions=3 crm=1|2 idempotency=PASS external_effects=0")
    except Exception as exc:
        failed = str(exc) if isinstance(exc,GateError) else "unexpected_failure"
        print(f"core_qa status=FAIL phase={failed}")
        if owned: print(f"core_qa services={sanitized_core_state(env)}")
    finally:
        if owned:
            for project,files in ((GATEWAY_PROJECT,GATEWAY_FILES),(BRIDGE_PROJECT,BRIDGE_FILES),(CORE_PROJECT,CORE_FILES)):
                run(compose(project,files,"down","--volumes","--remove-orphans"),env,check=False)
        shutil.rmtree(temp,ignore_errors=True)
        main_after=sorted(run(["docker","ps","--filter","label=com.docker.compose.project=emactiva-leadflow","--format","{{.ID}}"],env,capture=True,check=False).stdout.split())
        leftovers=[]
        for project in (CORE_PROJECT,BRIDGE_PROJECT,GATEWAY_PROJECT):
            leftovers += run(["docker","ps","-a","--filter",f"label=com.docker.compose.project={project}","--format","{{.ID}}"],env,capture=True,check=False).stdout.split()
        leftovers += owned_storage("network",env)+owned_storage("volume",env)
        cleanup=not leftovers and not temp.exists()
        print(f"core_qa cleanup={'PASS' if cleanup else 'FAIL'} main_unchanged={'PASS' if main_before==main_after else 'FAIL'}")
        if not cleanup or main_before!=main_after: failed=failed or "cleanup_failed"
    return 1 if failed else 0

if __name__ == "__main__": raise SystemExit(main())
