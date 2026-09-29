"""Unit evidence for REM-07 and REM-10; no Docker or external API calls."""
from pathlib import Path
import importlib.util
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
RECOVERY = ROOT / "scripts" / "recovery"
sys.path.insert(0, str(RECOVERY))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, RECOVERY / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load("r2a_runtime", "recovery_runtime.py")
crm = load("r2a_crm", "reconcile_crm.py")
continuation = load("r2a_continue", "continue_recovery.py")
checks = {}


def check(name, value):
    checks[name] = bool(value)
    print(("PASS" if value else "FAIL") + " " + name)


old_env = os.environ.copy()
password = "synthetic-password-canary"
email = "synthetic-person@example.invalid"
token = "synthetic-token-canary"
os.environ.update({
    "POSTGRES_APP_PASSWORD": password,
    "POSTGRES_APP_USER": "leadflow_app",
    "POSTGRES_DB": "leadflow",
    "RECOVERY_CONTEXT_KEY": token * 3,
})

try:
    captured = {}

    class Failed:
        returncode = 1
        stdout = ""
        stderr = f"provider failed for {email} password={password} token={token}"

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs.get("input", "")
        return Failed()

    original_run = runtime.subprocess.run
    runtime.subprocess.run = fake_run
    try:
        runtime.psql(f"SELECT '{email}', '{token}';")
        raised = False
        caught_code = None
        caught_stage = None
    except runtime.RecoveryOperationalError as error:
        raised = True
        visible = str(error)
        caught_code = error.code
        caught_stage = error.stage
    finally:
        runtime.subprocess.run = original_run

    argv = " ".join(captured["command"])
    check("REM07-sensitive-values-not-in-argv", all(value not in argv for value in (password, email, token)))
    check("REM07-sensitive-values-use-stdin", password in captured["input"] and email in captured["input"] and token in captured["input"])
    check("REM07-stderr-sanitized", raised and visible == "recovery_database_error" and all(value not in visible for value in (password, email, token)))
    check("REM07-diagnostic-code-stage", caught_code == "recovery_database_error" and caught_stage == "database")

    crm_calls = []
    crm.psql = lambda sql: (crm_calls.append(sql) or "t")
    crm.http = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("HTTP must not run for expired recovery"))
    expired = crm.reconcile("lf_exec_expired", "worker_expired", "http://adapter:8080")
    check("REM10-expired-terminal", expired["status"] == "failed" and expired["error_code"] == "recovery_expired")
    check("REM10-expired-no-global-purge", len(crm_calls) == 1 and "expire_stale_recovery" in crm_calls[0] and "DELETE" not in crm_calls[0].upper())

    crm_calls.clear()

    def unexpected_psql(sql):
        crm_calls.append(sql)
        if "expire_stale_recovery" in sql:
            return "f"
        if "get_recovery_crm_context" in sql:
            return f"lf_exec_test|idemhash||0|{email}"
        return "lf_exec_test|failed|0|upstream_error"

    crm.psql = unexpected_psql
    crm.http = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(f"{email} {token}"))
    unexpected = crm.reconcile("lf_exec_test", "worker_test", "http://adapter:8080")
    serialized = json.dumps(unexpected)
    check("REM10-unexpected-terminal", unexpected["status"] == "failed" and unexpected["error_code"] == "recovery_unexpected_error")
    check("REM07-unexpected-output-sanitized", email not in serialized and token not in serialized)
    check("REM10-original-execution", unexpected["execution_id"] == "lf_exec_test" and any("fail_recovery_crm" in sql for sql in crm_calls))

    continuation_calls = []

    def continuation_psql(sql):
        continuation_calls.append(sql)
        if "expire_stale_recovery" in sql:
            return "f"
        if "get_recovery_crm_context" in sql:
            return f"lf_exec_continue|contact_1|0|{email}"
        return "lf_exec_continue|failed"

    continuation.psql = continuation_psql
    continuation.http = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(f"{password} {email}"))
    continued = continuation.continue_recovery("lf_exec_continue", "worker_continue", "http://adapter:8080")
    check("REM10-continuation-unexpected-terminal", continued["status"] == "failed" and any("complete_recovery_adapter" in sql for sql in continuation_calls))
    check("REM07-continuation-output-sanitized", all(value not in json.dumps(continued) for value in (password, email, token)))

    os.environ["RECOVERY_MAX_PROCESSING_AGE_SECONDS"] = "604800"
    check("REM10-seven-day-default", runtime.processing_max_age_seconds() == 604800)
    os.environ["RECOVERY_MAX_PROCESSING_AGE_SECONDS"] = "604801"
    try:
        runtime.processing_max_age_seconds()
        rejected = False
    except runtime.RecoveryOperationalError:
        rejected = True
    check("REM10-over-seven-days-rejected", rejected)

    sources = (RECOVERY / "reconcile_crm.py").read_text(encoding="utf-8") + (RECOVERY / "continue_recovery.py").read_text(encoding="utf-8")
    check("REM07-no-password-env-argv", "PGPASSWORD=" not in sources)
    check("REM10-reconciliation-before-repeat", "/crm/process" in sources and "operation_key" in sources and "createContact" not in sources)
finally:
    os.environ.clear()
    os.environ.update(old_env)

passed = sum(checks.values())
print(f"RESULT: {'PASS' if passed == len(checks) else 'FAIL'}; passed={passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
