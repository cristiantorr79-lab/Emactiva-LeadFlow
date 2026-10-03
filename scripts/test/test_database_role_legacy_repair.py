"""Focused PostgreSQL 17 integration test for the inherited OID 10 repair."""
from pathlib import Path
import os
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
IMAGE = "postgres:17.6-bookworm"
CONTAINER = "leadflow-role-repair-" + uuid.uuid4().hex[:10]
ENVIRONMENT = {
    "POSTGRES_DB": "leadflow",
    "POSTGRES_BOOTSTRAP_USER": "leadflow_bootstrap",
    "POSTGRES_BOOTSTRAP_PASSWORD": "CANARY_BOOTSTRAP_PASSWORD_MUST_NOT_APPEAR_0001",
    "POSTGRES_MIGRATOR_USER": "leadflow_migrator",
    "POSTGRES_MIGRATOR_PASSWORD": "synthetic-migrator-password-0002",
    "POSTGRES_APP_USER": "leadflow_app",
    "POSTGRES_APP_PASSWORD": "synthetic-app-password-000000003",
    "POSTGRES_TRANSITION_USER": "leadflow_bootstrap_transition",
}
CAPTURED_OUTPUT: list[str] = []


def run(command: list[str], *, stdin: str | None = None, expected: int = 0, label: str = "command") -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, input=stdin, text=True, capture_output=True, check=False)
    CAPTURED_OUTPUT.append(result.stdout + result.stderr)
    if result.returncode != expected:
        detail = result.stderr[-1000:]
        for value in ENVIRONMENT.values():
            detail = detail.replace(value, "[synthetic-value]")
        raise AssertionError(f"{label} failed with exit {result.returncode}: {detail.strip()}")
    return result


def psql(user: str, sql: str, *, expected: int = 0, label: str = "psql") -> subprocess.CompletedProcess[str]:
    command = ["docker", "exec", "-i"]
    for name, value in ENVIRONMENT.items():
        command.extend(["-e", f"{name}={value}"])
    command.extend([CONTAINER, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", "leadflow", "-At"])
    return run(command, stdin=sql, expected=expected, label=label)


def sql_file(name: str) -> str:
    return (ROOT / "scripts/database" / name).read_text(encoding="utf-8")


def main() -> int:
    docker = ["docker", "run", "-d", "--name", CONTAINER, "--tmpfs", "/var/lib/postgresql/data"]
    docker.extend(["-e", "POSTGRES_DB=leadflow", "-e", "POSTGRES_USER=leadflow_migrator"])
    docker.extend(["-e", "POSTGRES_PASSWORD=synthetic-historical-password-0000", IMAGE])
    run(docker, label="docker startup")
    try:
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", CONTAINER, "psql", "-X", "-q", "-U", "leadflow_migrator", "-d", "leadflow", "-c", "SELECT 1"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise AssertionError("isolated PostgreSQL did not become ready")

        seed = f"""
CREATE ROLE {ENVIRONMENT['POSTGRES_BOOTSTRAP_USER']} LOGIN SUPERUSER CREATEDB CREATEROLE NOREPLICATION
 PASSWORD '{ENVIRONMENT['POSTGRES_BOOTSTRAP_PASSWORD']}';
CREATE ROLE {ENVIRONMENT['POSTGRES_APP_USER']} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
 PASSWORD '{ENVIRONMENT['POSTGRES_APP_PASSWORD']}';
CREATE SCHEMA leadflow AUTHORIZATION {ENVIRONMENT['POSTGRES_MIGRATOR_USER']};
CREATE EXTENSION pgcrypto;
CREATE TABLE leadflow.probe(id integer PRIMARY KEY, value text);
INSERT INTO leadflow.probe VALUES (1, 'preserved');
CREATE FUNCTION leadflow.probe_value() RETURNS text LANGUAGE sql AS $$SELECT value FROM leadflow.probe WHERE id=1$$;
CREATE TABLE public.unexpected_bootstrap_object(id integer);
ALTER TABLE public.unexpected_bootstrap_object OWNER TO {ENVIRONMENT['POSTGRES_BOOTSTRAP_USER']};
"""
        psql("leadflow_migrator", seed, label="synthetic legacy seed")

        failed = psql("leadflow_migrator", sql_file("sync_database_roles_legacy_prepare.sql"), expected=3, label="expected guarded preflight")
        if "unexpected ownership" not in failed.stderr:
            raise AssertionError("legacy preflight did not fail closed on bootstrap ownership")
        topology = psql("leadflow_migrator", "SELECT string_agg(rolname,',' ORDER BY rolname) FROM pg_roles WHERE rolname LIKE 'leadflow_%';").stdout.strip()
        if topology != "leadflow_app,leadflow_bootstrap,leadflow_migrator":
            raise AssertionError("failed preflight changed role topology")

        psql("leadflow_migrator", "DROP TABLE public.unexpected_bootstrap_object;")
        psql("leadflow_migrator", sql_file("sync_database_roles_legacy_prepare.sql"), label="legacy prepare")
        psql(ENVIRONMENT["POSTGRES_TRANSITION_USER"], sql_file("sync_database_roles_legacy_transfer.sql"), label="legacy transfer")
        psql(ENVIRONMENT["POSTGRES_BOOTSTRAP_USER"], sql_file("sync_database_roles_legacy_finalize.sql"), label="legacy finalize")

        verification = psql(ENVIRONMENT["POSTGRES_BOOTSTRAP_USER"], """
SELECT rolname,oid,rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles
 WHERE rolname IN ('leadflow_bootstrap','leadflow_migrator','leadflow_app') ORDER BY rolname;
SELECT n.nspname||'|'||r.rolname FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='leadflow';
SELECT c.relname||'|'||r.rolname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='leadflow' AND c.relname='probe';
SELECT p.proname||'|'||r.rolname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner WHERE n.nspname='leadflow' AND p.proname='probe_value';
SELECT extname||'|'||r.rolname FROM pg_extension e JOIN pg_roles r ON r.oid=e.extowner WHERE extname IN ('pgcrypto','plpgsql') ORDER BY extname;
SELECT leadflow.probe_value();
SELECT count(*) FROM pg_roles WHERE rolname='leadflow_bootstrap_transition';
""").stdout.splitlines()
        expected = {
            "leadflow_app|" + next(line.split("|")[1] for line in verification if line.startswith("leadflow_app|")) + "|f|f|f|f",
            "leadflow_migrator|" + next(line.split("|")[1] for line in verification if line.startswith("leadflow_migrator|")) + "|f|f|f|f",
            "leadflow|leadflow_migrator", "probe|leadflow_migrator", "probe_value|leadflow_migrator",
            "pgcrypto|leadflow_bootstrap", "plpgsql|leadflow_bootstrap", "preserved", "0",
        }
        if not expected.issubset(set(verification)):
            raise AssertionError("legacy repair verification mismatch")
        bootstrap = next(line for line in verification if line.startswith("leadflow_bootstrap|"))
        if bootstrap.split("|")[1:6] != ["10", "t", "t", "t", "f"]:
            raise AssertionError("historical OID 10 was not preserved as bootstrap")

        psql("leadflow_migrator", "BEGIN; CREATE TABLE leadflow.ddl_probe(id integer); ROLLBACK;")
        denied = psql("leadflow_app", "CREATE TABLE leadflow.app_forbidden(id integer);", expected=3)
        if "permission denied" not in denied.stderr:
            raise AssertionError("application CREATE was not denied")

        combined_output = "".join(CAPTURED_OUTPUT)
        for name in ("POSTGRES_BOOTSTRAP_PASSWORD", "POSTGRES_MIGRATOR_PASSWORD", "POSTGRES_APP_PASSWORD"):
            if ENVIRONMENT[name] in combined_output:
                raise AssertionError(f"{name} appeared in psql output")

        print("LEGACY_PREFLIGHT_FAIL_CLOSED=PASS")
        print("LEGACY_OID10_RENAMED_TO_BOOTSTRAP=PASS")
        print("RESTRICTED_MIGRATOR_AND_APP=PASS")
        print("LEADFLOW_OWNERSHIP_AND_DATA_PRESERVED=PASS")
        print("EXTENSION_OWNERSHIP_RETAINED_BY_BOOTSTRAP=PASS")
        print("MIGRATOR_DDL_AND_APP_DENIAL=PASS")
        print("PASSWORD_OUTPUT_SANITIZATION=PASS")
        return 0
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"LEGACY_ROLE_REPAIR=FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
