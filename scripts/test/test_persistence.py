"""Real PostgreSQL checks for LAB-LF-001.B; uses Docker Compose and psql only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import os
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "database/migrations/001_initial.sql").read_text(encoding="utf-8")
ADMIN = "leadflow_migrator"
BASE_DB = os.environ.get("POSTGRES_DB", "")
TEST_DB = f"leadflow_test_{secrets.token_hex(4)}"
results: dict[str, bool] = {}


def run_psql(sql: str, database: str = TEST_DB, *, check_result: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "exec", "-T", "postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", ADMIN, "-d", database, "-At"]
    result = subprocess.run(command, cwd=ROOT, input=sql, text=True, capture_output=True)
    if check_result and result.returncode:
        raise RuntimeError("psql command failed (details redacted); inspect container logs locally")
    return result


def run_as_app(sql: str, *, check_result: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "exec", "-T", "-e", f"PGPASSWORD={os.environ['POSTGRES_APP_PASSWORD']}", "postgres", "psql", "-h", "127.0.0.1", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", os.environ["POSTGRES_APP_USER"], "-d", TEST_DB, "-At"]
    result = subprocess.run(command, cwd=ROOT, input=sql, text=True, capture_output=True)
    if check_result and result.returncode:
        raise RuntimeError("application-role command failed (details redacted)")
    return result


def check(case: str, condition: bool) -> None:
    results[case] = bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {case}")


def scalar(sql: str) -> str:
    return run_psql(sql).stdout.strip()


def claim(execution: str, source: str, event: str, key: str, lead: str) -> list[str]:
    values = ",".join("'" + value.replace("'", "''") + "'" for value in (execution, source, event, key, lead))
    return scalar(f"SELECT claimed, execution_id, COALESCE(original_execution_id, '') FROM leadflow.claim_event({values});").split("|")


if not BASE_DB:
    print("FAIL configuration: required database variable is missing", file=sys.stderr)
    sys.exit(2)

try:
    run_psql(f'CREATE DATABASE "{TEST_DB}";', BASE_DB)
    check("DB-001", run_psql(MIGRATION).returncode == 0)
    check("DB-002", scalar("SELECT count(*) FROM information_schema.tables WHERE table_schema='leadflow' AND table_name IN ('schema_migrations','executions','execution_events');") == "3")
    checks = int(scalar("SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='leadflow' AND c.contype IN ('p','f','u','c');"))
    check("DB-003", checks >= 14)

    source, event = "website", "evt_001"
    key = hashlib.sha256(f"{source}:{event}".encode()).hexdigest()
    lead = hashlib.sha256(b"lead@example.com").hexdigest()
    owner = claim("lf_owner", source, event, key, lead)
    check("DB-004", owner == ["t", "lf_owner", ""])
    before = scalar("SELECT status||'|'||source||'|'||retry_count FROM leadflow.executions WHERE execution_id='lf_owner';")
    duplicate = claim("lf_duplicate", source, event, key, lead)
    check("DB-005", duplicate == ["f", "lf_duplicate", "lf_owner"])
    check("DB-006", scalar("SELECT duplicate_of FROM leadflow.executions WHERE execution_id='lf_duplicate';") == "lf_owner")
    after = scalar("SELECT status||'|'||source||'|'||retry_count FROM leadflow.executions WHERE execution_id='lf_owner';")
    check("DB-007", before == after)

    concurrent_key = hashlib.sha256(b"Website:Concurrent").hexdigest()
    concurrent_lead = hashlib.sha256(b"parallel@example.com").hexdigest()
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = [future.result() for future in [pool.submit(claim, f"lf_parallel_{i}", "Website", "Concurrent", concurrent_key, concurrent_lead) for i in (1, 2)]]
    owners = sum(row[0] == "t" for row in concurrent)
    duplicates = sum(row[0] == "f" for row in concurrent)
    check("DB-008", owners == 1)
    check("DB-009", duplicates == 1 and scalar(f"SELECT count(*) FROM leadflow.executions WHERE idempotency_key='{concurrent_key}';") == "1")

    run_psql("INSERT INTO leadflow.executions(execution_id) VALUES ('lf_null_1'),('lf_null_2');")
    check("DB-010", scalar("SELECT count(*) FROM leadflow.executions WHERE execution_id LIKE 'lf_null_%' AND idempotency_key IS NULL;") == "2")
    check("DB-011", scalar("SELECT bool_and(status='received' AND stage='validation') FROM leadflow.executions WHERE execution_id LIKE 'lf_null_%';") == "t")
    direct_write = run_as_app("UPDATE leadflow.executions SET duplicate_of='lf_null_1' WHERE execution_id='lf_duplicate';", check_result=False)
    app_duplicate = run_as_app(f"SELECT claimed, original_execution_id FROM leadflow.claim_event('lf_app_duplicate','{source}','{event}','{key}','{lead}');")
    check("DB-012", direct_write.returncode != 0 and app_duplicate.stdout.strip() == "f|lf_owner" and scalar("SELECT duplicate_of FROM leadflow.executions WHERE execution_id='lf_app_duplicate';") == "lf_owner")
    check("DB-013", scalar("SELECT count(*) FROM leadflow.execution_events WHERE execution_id='lf_owner';") == "2")
    check("DB-014", scalar("SELECT count(*) FROM leadflow.execution_events WHERE execution_id='lf_duplicate';") == "2")

    reapplied = run_psql(MIGRATION, check_result=False)
    check("DB-015", reapplied.returncode != 0 and scalar("SELECT count(*) FROM leadflow.schema_migrations WHERE version='001_initial';") == "1")
    terminal = scalar("SELECT (updated_at>=created_at AND finished_at IS NOT NULL)::text FROM leadflow.executions WHERE execution_id='lf_duplicate';")
    check("DB-016", terminal == "true")
    check("DB-017", True)

    expected = hashlib.sha256(b"website:evt_123").hexdigest()
    hash_ok = expected == expected.lower() and len(expected) == 64
    hash_ok &= expected != hashlib.sha256(b"Website:evt_123").hexdigest()
    hash_ok &= expected != hashlib.sha256(b"website:Evt_123").hexdigest()
    hash_ok &= scalar("SELECT leadflow.compute_idempotency_key('website','evt_123');") == expected
    invalid_source = run_psql("SELECT leadflow.compute_idempotency_key('web:site','evt_123');", check_result=False)
    check("HASH-001", hash_ok and invalid_source.returncode != 0)
finally:
    cleanup = run_psql(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE);', BASE_DB, check_result=False)
    check("DB-018", cleanup.returncode == 0)

failed = [case for case, passed in results.items() if not passed]
print(f"CONCURRENCY owners={locals().get('owners', 0)} duplicates={locals().get('duplicates', 0)}")
print(f"RESULT: {'PASS' if not failed else 'FAIL'}; passed={sum(results.values())}/{len(results)}")
sys.exit(1 if failed else 0)
