"""Focused REM-09 validation, minimization, idempotency and recovery checks."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = json.loads((ROOT / "workflows" / "leadflow_core_initial.json").read_text(encoding="utf-8"))
VALIDATOR = next(node["parameters"]["jsCode"] for node in WORKFLOW["nodes"] if node["name"] == "Authenticate Validate Normalize")
WEBHOOK_KEY = "synthetic-webhook-key-with-32-chars"
PREFIX = "rem09_focus_"
checks = {}


def check(name, value):
    checks[name] = bool(value)
    print(f"{'PASS' if value else 'FAIL'} {name}")


def validate(event_id, source):
    wrapper = """
const fs=require('fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const run=new Function('require','$json','$env',input.code);
Promise.resolve(run(require,input.item,input.env)).then(value=>process.stdout.write(JSON.stringify(value)));
"""
    item = {
        "headers": {"x-leadflow-key": WEBHOOK_KEY, "content-type": "application/json"},
        "body": {"event_id": event_id, "source": source, "lead": {"email": "lead@example.test"}},
    }
    result = subprocess.run(
        ["node", "-e", wrapper],
        cwd=ROOT,
        input=json.dumps({"code": VALIDATOR, "item": item, "env": {"LEADFLOW_WEBHOOK_KEY": WEBHOOK_KEY, "LEADFLOW_ALLOWED_SOURCES": "website,partner_api", "DSR_SUBJECT_KEY": "synthetic-dsr-key-at-least-32-characters"}}),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError("workflow validator execution failed")
    return json.loads(result.stdout), result.stdout + result.stderr


def psql(user, password, sql, check_result=True):
    command = [
        "docker", "compose", "exec", "-T", "postgres", "sh", "-c",
        'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql -h 127.0.0.1 -X -q -v ON_ERROR_STOP=1 -U "$1" -d "$2" -At',
        "sh", user, os.environ["POSTGRES_DB"],
    ]
    result = subprocess.run(command, cwd=ROOT, input=password + "\n" + sql + "\n", text=True, capture_output=True, check=False)
    if check_result and result.returncode:
        raise AssertionError("database operation failed")
    return result


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


valid, _ = validate("evt_2026-09-28_001", "website")
check("REM09-1 source allowlist and exact form", valid["json"].get("route") == "valid" and valid["json"].get("source") == "website")
bad_source, _ = validate("evt_2026-09-28_002", "unknown")
check("REM09-2 source outside allowlist rejected", bad_source["json"] == {"route": "validation_error", "execution_id": bad_source["json"]["execution_id"], "error_code": "invalid_source"})
check("REM09-3 technical event id accepted", valid["json"].get("event_id") == "evt_2026-09-28_001" and len(valid["json"].get("idempotency_key", "")) == 64)
email_event, _ = validate("AlphabeticEvent", "website")
check("REM09-4 alphabetic event id accepted", email_event["json"].get("route") == "valid" and email_event["json"].get("event_id") == "AlphabeticEvent")
oversized, _ = validate("x" * 201, "website")
check("REM09-5 out-of-bounds event id rejected", oversized["json"].get("error_code") == "invalid_event_id")

app_user = os.environ["POSTGRES_APP_USER"]
app_password = os.environ["POSTGRES_APP_PASSWORD"]
migrator_user = os.environ["POSTGRES_MIGRATOR_USER"]
migrator_password = os.environ["POSTGRES_MIGRATOR_PASSWORD"]
event = "evt_2026-09-28_runtime"
event2 = "evt_2026-09-28_distinct"
source = "website"
key = hashlib.sha256(f"{source}:{event}".encode()).hexdigest()
key2 = hashlib.sha256(f"{source}:{event2}".encode()).hexdigest()
lead = hashlib.sha256(b"synthetic-lead@example.test").hexdigest()
subject = hashlib.sha256(b"synthetic-dsr-subject-token").hexdigest()
owner, duplicate, distinct = PREFIX + "owner", PREFIX + "duplicate", PREFIX + "distinct"

try:
    owner_result = psql(app_user, app_password, f"SELECT * FROM leadflow.claim_event({sql_literal(owner)},{sql_literal(source)},{sql_literal(event)},{sql_literal(key)},{sql_literal(lead)},{sql_literal(subject)});")
    duplicate_result = psql(app_user, app_password, f"SELECT * FROM leadflow.claim_event({sql_literal(duplicate)},{sql_literal(source)},{sql_literal(event)},{sql_literal(key)},{sql_literal(lead)},{sql_literal(subject)});")
    distinct_result = psql(app_user, app_password, f"SELECT * FROM leadflow.claim_event({sql_literal(distinct)},{sql_literal(source)},{sql_literal(event2)},{sql_literal(key2)},{sql_literal(lead)},{sql_literal(subject)});")
    column_count = psql(app_user, app_password, "SELECT count(*) FROM information_schema.columns WHERE table_schema='leadflow' AND table_name='executions' AND column_name='event_id';").stdout.strip()
    stored_source = psql(app_user, app_password, f"SELECT source FROM leadflow.executions WHERE execution_id={sql_literal(owner)};").stdout.strip()
    check("REM09-6 raw event id not persisted", column_count == "0" and stored_source == source)
    check("REM09-7 logical duplicate preserved", owner_result.stdout.strip() == f"t|{owner}|" and duplicate_result.stdout.strip() == f"f|{duplicate}|{owner}")
    check("REM09-8 distinct events produce distinct keys", key != key2 and distinct_result.stdout.strip() == f"t|{distinct}|")
    psql(migrator_user, migrator_password, f"UPDATE leadflow.executions SET updated_at=clock_timestamp()-interval '120 seconds' WHERE execution_id={sql_literal(owner)};")
    recovery = psql(app_user, app_password, "SELECT execution_id FROM leadflow.claim_stale_processing_executions('rem09_worker',60,30,10) ORDER BY execution_id;").stdout.splitlines()
    duplicate_of = psql(app_user, app_password, f"SELECT duplicate_of FROM leadflow.executions WHERE execution_id={sql_literal(duplicate)};").stdout.strip()
    check("REM09-9 recovery and original identity preserved", owner in recovery and duplicate_of == owner)
finally:
    psql(migrator_user, migrator_password, f"DELETE FROM leadflow.execution_events WHERE execution_id LIKE {sql_literal(PREFIX + '%')}; DELETE FROM leadflow.executions WHERE execution_id LIKE {sql_literal(PREFIX + '%')};", check_result=False)

failed = [name for name, passed in checks.items() if not passed]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
