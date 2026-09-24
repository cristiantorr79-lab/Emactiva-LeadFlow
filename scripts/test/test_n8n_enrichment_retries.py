"""Enrichment classification and retry tests for LF-001.D3b-1."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import os
import secrets
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
WEBHOOK = f"http://127.0.0.1:{os.environ.get('N8N_PORT', '5680')}/webhook/leadflow"
ENRICHMENT = os.environ.get("ENRICHMENT_BASE_URL") or "http://127.0.0.1:5682"
CRM = os.environ.get("CRM_BASE_URL") or "http://127.0.0.1:5683"
KEY = os.environ.get("LEADFLOW_WEBHOOK_KEY", "")
DB = os.environ.get("POSTGRES_DB", "")
prefix = f"d3b_{secrets.token_hex(5)}"
execution_ids = []
checks = {}


def http(url, payload=None, method="GET", webhook=False, timeout=60):
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if webhook:
        headers["X-LeadFlow-Key"] = KEY
    request = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode()
            return response.status, json.loads(text), text
    except HTTPError as error:
        text = error.read().decode()
        return error.code, json.loads(text), text


def configure(mode, *, failures=None, retry_after=3, delay=3):
    payload = {"mode": mode, "operation": "enrich", "retry_after_seconds": retry_after, "delay_seconds": delay}
    if failures is not None:
        payload["failures"] = failures
    status, _, _ = http(ENRICHMENT + "/control/failure", payload, "POST")
    if status != 200:
        raise RuntimeError("could not configure enrichment mock")


def clear():
    http(ENRICHMENT + "/control/failure", method="DELETE")


def send(label):
    payload = {"event_id": f"{prefix}_{label}", "source": "website", "lead": {"email": f"{prefix}-{label}@example.com", "first_name": "Private"}}
    result = http(WEBHOOK, payload, "POST", webhook=True)
    execution_ids.append(result[1].get("execution_id", ""))
    return result, payload["lead"]["email"]


def psql(sql):
    command = ["docker", "compose", "exec", "-T", "postgres", "psql", "-X", "-q", "-U", "leadflow_migrator", "-d", DB, "-Atc", sql]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("database assertion failed; details redacted")
    return result.stdout.strip()


def row(execution_id):
    return psql(f"SELECT status||'|'||retry_count||'|'||enrichment_status||'|'||coalesce(error_type,'') FROM leadflow.executions WHERE execution_id='{execution_id}';")


def check(name, condition):
    checks[name] = bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}")


if not KEY or not DB:
    print("Required local variables are missing", file=sys.stderr)
    sys.exit(2)

try:
    configure("http_400")
    (status, body, text), email_400 = send("400")
    check("D3B-001 400 sin retry", status == 502 and body.get("error", {}).get("type") == "validation_error" and row(body["execution_id"]) == "failed|0|failed|validation_error")
    clear()

    configure("http_401")
    (status, body, text_401), email_401 = send("401")
    check("D3B-002 401 sin retry", status == 502 and body.get("error", {}).get("type") == "authentication_error" and row(body["execution_id"]) == "failed|0|failed|authentication_error")
    clear()

    _, crm_before, _ = http(CRM + "/stats")
    configure("timeout", failures=1, delay=3)
    started = time.monotonic()
    (status, body, _), _ = send("timeout")
    elapsed_timeout = time.monotonic() - started
    clear()
    check("D3B-003 timeout retry", status == 200 and body.get("status") == "success" and row(body["execution_id"]) == "success|1|success|" and elapsed_timeout >= 6.5)
    _, crm_after, _ = http(CRM + "/stats")
    before_calls, after_calls = crm_before["calls"], crm_after["calls"]
    check("D3B-004 CRM no se duplica", crm_after["contacts"] == crm_before["contacts"] + 1 and after_calls["create"] == before_calls["create"] + 1 and after_calls["update_enrichment"] == before_calls["update_enrichment"] + 1)

    configure("http_429", failures=1, retry_after=7)
    started = time.monotonic()
    (status, body, _), _ = send("429")
    elapsed_429 = time.monotonic() - started
    clear()
    check("D3B-005 429 Retry-After", status == 200 and row(body["execution_id"]) == "success|1|success|" and elapsed_429 >= 7)

    configure("http_500", failures=1)
    (status, body, _), _ = send("500_once")
    clear()
    check("D3B-006 500 retry y success", status == 200 and row(body["execution_id"]) == "success|1|success|")

    configure("http_500", failures=3)
    (status, body, terminal_text), terminal_email = send("500_terminal")
    clear()
    check("D3B-007 tres intentos failed", status == 502 and body.get("error", {}).get("type") == "upstream_error" and row(body["execution_id"]) == "failed|2|failed|upstream_error")
    history = psql(f"SELECT string_agg(status||':'||attempt_number,',' ORDER BY log_id) FROM leadflow.execution_events WHERE execution_id='{body['execution_id']}' AND stage='enrichment';")
    check("D3B-008 transiciones y contador", history == "retrying:1,processing:2,retrying:2,processing:3,failed:3")
    check("D3B-009 respuesta sanitizada", all(value not in terminal_text for value in (terminal_email, "Private", KEY, ENRICHMENT)))
finally:
    clear()
    safe = [value for value in execution_ids if value.startswith("lf_exec_") and value.replace("lf_exec_", "").isalnum()]
    if safe:
        quoted = ",".join("'" + value + "'" for value in safe)
        psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({quoted}); DELETE FROM leadflow.executions WHERE execution_id IN ({quoted});")

failed = [name for name, passed in checks.items() if not passed]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
