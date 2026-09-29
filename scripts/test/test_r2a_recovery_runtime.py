"""Runtime evidence for migration 012 and REM-10 using only synthetic local data."""
from pathlib import Path
import hashlib
import json
import os
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "recovery"))
import reconcile_crm
from recovery_runtime import psql as app_psql

DB = os.environ["POSTGRES_DB"]
SECRET = os.environ["RECOVERY_CONTEXT_KEY"]
ADAPTER = os.environ["RECOVERY_ADAPTER_URL"]
prefix = "r2a_runtime_" + secrets.token_hex(5)
created = []
checks = {}


def migrator_psql(sql):
    command = [
        "docker", "compose", "exec", "-T", "postgres", "sh", "-c",
        'exec psql -X -q -At -v ON_ERROR_STOP=1 -U leadflow_migrator -d "$POSTGRES_DB"',
    ]
    result = subprocess.run(command, cwd=ROOT, input=sql + "\n", capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("synthetic_database_fixture_error")
    return result.stdout.strip()


def check(name, value):
    checks[name] = bool(value)
    print(("PASS" if value else "FAIL") + " " + name)


def fixture(label, age, worker, leased=True):
    execution = "lf_exec_" + secrets.token_hex(16)
    event_id = prefix + "_" + label
    email = prefix + "-" + label + "@example.invalid"
    idem = hashlib.sha256(("website:" + event_id).encode()).hexdigest()
    lead = hashlib.sha256(email.encode()).hexdigest()
    owner = f"'{worker}'" if leased else "NULL"
    lease = "clock_timestamp()+interval '30 minutes'" if leased else "NULL"
    migrator_psql(
        "INSERT INTO leadflow.executions"
        "(execution_id,idempotency_key,source,lead_identifier,status,stage,updated_at,recovery_owner,recovery_lease_until) "
        f"VALUES('{execution}','{idem}','website','{lead}','processing','idempotency',"
        f"clock_timestamp()-interval '{age}',{owner},{lease});"
    )
    app_psql(f"SELECT leadflow.store_recovery_context('{execution}','{email}','{SECRET.replace(chr(39), chr(39)*2)}');")
    created.append(execution)
    return execution, idem, email


try:
    registry = migrator_psql(
        "SELECT (SELECT count(*) FROM leadflow.schema_migrations WHERE version='012_recovery_expiration')||'|'||"
        "(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='leadflow' AND p.proname='expire_stale_recovery');"
    )
    check("REM10-migration-present-once", registry == "1|1")

    sentinel, _, _ = fixture("sentinel", "1 hour", "unused_worker", leased=False)
    expired_id, expired_key, _ = fixture("expired", "8 days", "worker_expired")
    expired = reconcile_crm.reconcile(expired_id, "worker_expired", ADAPTER)
    expired_row = migrator_psql(
        f"SELECT status||'|'||error_type||'|'||error_code||'|'||(idempotency_key='{expired_key}')::text "
        f"FROM leadflow.executions WHERE execution_id='{expired_id}';"
    )
    sentinel_row = migrator_psql(f"SELECT status FROM leadflow.executions WHERE execution_id='{sentinel}';")
    check("REM10-expired-runtime-terminal", expired["status"] == "failed" and expired_row == "failed|timeout|recovery_expired|true")
    check("REM10-no-global-purge-runtime", sentinel_row == "processing")

    unexpected_id, unexpected_key, email = fixture("unexpected", "1 hour", "worker_unexpected")
    original_http = reconcile_crm.http
    reconcile_crm.http = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic upstream exception"))
    try:
        unexpected = reconcile_crm.reconcile(unexpected_id, "worker_unexpected", ADAPTER)
    finally:
        reconcile_crm.http = original_http
    unexpected_row = migrator_psql(
        f"SELECT status||'|'||error_type||'|'||error_code||'|'||(idempotency_key='{unexpected_key}')::text "
        f"FROM leadflow.executions WHERE execution_id='{unexpected_id}';"
    )
    visible = json.dumps(unexpected)
    check("REM10-unexpected-runtime-terminal", unexpected["status"] == "failed" and unexpected_row == "failed|upstream_error|recovery_unexpected_error|true")
    check("REM10-runtime-output-sanitized", email not in visible and SECRET not in visible and "SELECT " not in visible)

    migration = (ROOT / "database" / "migrations" / "012_recovery_expiration.sql").read_text(encoding="utf-8")
    check("REM10-no-purge-sql", "DELETE FROM" not in migration.upper())
finally:
    if created:
        values = ",".join("'" + value + "'" for value in created)
        migrator_psql(
            f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({values}); "
            f"DELETE FROM leadflow.executions WHERE execution_id IN ({values});"
        )
        remaining = migrator_psql(f"SELECT count(*) FROM leadflow.executions WHERE execution_id IN ({values});")
        check("REM10-runtime-cleanup", remaining == "0")

passed = sum(checks.values())
print(f"RESULT: {'PASS' if passed == len(checks) else 'FAIL'}; passed={passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
