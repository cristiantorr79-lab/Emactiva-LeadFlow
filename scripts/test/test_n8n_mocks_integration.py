"""Happy-path integration tests for n8n, CRM mock and enrichment mock."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import os
import secrets
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
WEBHOOK = f"http://127.0.0.1:{os.environ.get('N8N_PORT', '5680')}/webhook/leadflow"
CRM = os.environ.get("CRM_BASE_URL") or "http://127.0.0.1:5683"
KEY = os.environ.get("LEADFLOW_WEBHOOK_KEY", "")
DB = os.environ.get("POSTGRES_DB", "")
suffix = secrets.token_hex(6)
email = f"d2-{suffix}@example.com"
event_create = f"d2_{suffix}_create"
event_update = f"d2_{suffix}_update"
execution_ids = []
checks = {}


def http(url, payload=None, method="GET", webhook=False):
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if webhook:
        headers["X-LeadFlow-Key"] = KEY
    request = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            text = response.read().decode()
            return response.status, json.loads(text), text
    except HTTPError as error:
        text = error.read().decode()
        return error.code, json.loads(text), text


def send(event_id, **lead):
    payload = {"event_id": event_id, "source": "website", "lead": {"email": email, **lead}}
    return http(WEBHOOK, payload, "POST", webhook=True)


def psql(sql):
    command = ["docker", "compose", "exec", "-T", "postgres", "psql", "-X", "-q", "-U", "leadflow_migrator", "-d", DB, "-Atc", sql]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("database assertion failed; details redacted")
    return result.stdout.strip()


def check(name, condition):
    checks[name] = bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}")


if not KEY or not DB:
    print("Required local variables are missing", file=sys.stderr)
    sys.exit(2)

try:
    _, stats_before, _ = http(CRM + "/stats")
    status, created, created_text = send(event_create, first_name="Ada", company="Persistent Company")
    execution_ids.append(created.get("execution_id", ""))
    check("D2-001 lead nuevo success", status == 200 and created.get("status") == "success" and created.get("crm_action") == "created")
    created_row = psql(f"SELECT status||'|'||crm_action||'|'||enrichment_status||'|'||crm_contact_id||'|'||interaction_status FROM leadflow.executions WHERE execution_id='{created['execution_id']}';")
    check("D2-002 success persistido", created_row.startswith("success|created|success|crm_") and created_row.endswith("|not_required"))
    contact_id = created_row.split("|")[3]
    _, contact_created, _ = http(CRM + f"/crm/contacts/{contact_id}")
    check("D2-003 contacto y enrichment", contact_created.get("contact", {}).get("company") == "Persistent Company" and contact_created.get("contact", {}).get("industry") == "software")

    status, updated, updated_text = send(event_update, first_name="Grace")
    execution_ids.append(updated.get("execution_id", ""))
    check("D2-004 contacto existente actualizado", status == 200 and updated.get("status") == "success" and updated.get("crm_action") == "updated")
    updated_row = psql(f"SELECT status||'|'||crm_action||'|'||enrichment_status||'|'||crm_contact_id FROM leadflow.executions WHERE execution_id='{updated['execution_id']}';")
    check("D2-005 mismo contacto", updated_row.endswith("|" + contact_id))
    _, contact_updated, _ = http(CRM + f"/crm/contacts/{contact_id}")
    contact = contact_updated.get("contact", {})
    check("D2-006 omitidos conservados", contact.get("first_name") == "Grace" and contact.get("company") == "Persistent Company" and contact.get("website") == "https://example.test")

    _, stats_pre_duplicate, _ = http(CRM + "/stats")
    status, duplicate, duplicate_text = send(event_update, first_name="Ignored")
    execution_ids.append(duplicate.get("execution_id", ""))
    _, stats_post_duplicate, _ = http(CRM + "/stats")
    check("D2-007 duplicate", status == 200 and duplicate.get("duplicate") is True and duplicate.get("original_execution_id") == updated.get("execution_id"))
    check("D2-008 duplicate sin llamadas externas", stats_pre_duplicate == stats_post_duplicate)

    _, stats_after, _ = http(CRM + "/stats")
    check("D2-009 dos eventos un contacto", stats_after.get("contacts") == stats_before.get("contacts", 0) + 1)
    check("D2-009A V1 no crea interactions", stats_after.get("interactions", 0) == stats_before.get("interactions", 0))
    public = " ".join((created_text, updated_text, duplicate_text))
    check("D2-010 respuesta pública sanitizada", all(value not in public for value in (email, "Ada", "Grace", "Persistent Company", KEY)))
finally:
    safe = [value for value in execution_ids if value.startswith("lf_exec_") and value.replace("lf_exec_", "").isalnum()]
    if safe:
        quoted = ",".join("'" + value + "'" for value in safe)
        psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({quoted}); DELETE FROM leadflow.executions WHERE execution_id IN ({quoted});")

failed = [name for name, passed in checks.items() if not passed]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
