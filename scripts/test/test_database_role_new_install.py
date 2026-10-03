"""Focused PostgreSQL 17 new-install test for restricted migration roles."""
from pathlib import Path
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
CONTAINER = "leadflow-role-new-" + uuid.uuid4().hex[:10]
ENVIRONMENT = {
    "POSTGRES_DB": "leadflow",
    "POSTGRES_BOOTSTRAP_USER": "leadflow_bootstrap",
    "POSTGRES_BOOTSTRAP_PASSWORD": "synthetic-bootstrap-password-1001",
    "POSTGRES_MIGRATOR_USER": "leadflow_migrator",
    "POSTGRES_MIGRATOR_PASSWORD": "synthetic-migrator-password-1002",
    "POSTGRES_APP_USER": "leadflow_app",
    "POSTGRES_APP_PASSWORD": "synthetic-app-password-000000103",
}


def run(command: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, input=stdin, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr[-1000:]
        for value in ENVIRONMENT.values():
            detail = detail.replace(value, "[synthetic-value]")
        raise AssertionError(f"command failed with exit {result.returncode}: {detail.strip()}")
    return result


def psql(user: str, sql: str) -> subprocess.CompletedProcess[str]:
    command = ["docker", "exec", "-i"]
    for name, value in ENVIRONMENT.items():
        command.extend(["-e", f"{name}={value}"])
    command.extend([CONTAINER, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", "leadflow", "-At"])
    return run(command, sql)


def main() -> int:
    run([
        "docker", "run", "-d", "--name", CONTAINER, "--tmpfs", "/var/lib/postgresql/data",
        "-e", "POSTGRES_DB=leadflow", "-e", "POSTGRES_USER=leadflow_bootstrap",
        "-e", "POSTGRES_PASSWORD=" + ENVIRONMENT["POSTGRES_BOOTSTRAP_PASSWORD"], "postgres:17.6-bookworm",
    ])
    try:
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", CONTAINER, "psql", "-X", "-q", "-U", "leadflow_bootstrap", "-d", "leadflow", "-c", "SELECT 1"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise AssertionError("isolated PostgreSQL did not become ready")

        psql("leadflow_bootstrap", (ROOT / "scripts/database/sync_database_roles.sql").read_text(encoding="utf-8"))
        migrations = sorted((ROOT / "database/migrations").glob("*.sql"))
        psql("leadflow_bootstrap", migrations[0].read_text(encoding="utf-8"))
        psql("leadflow_bootstrap", (ROOT / "scripts/database/transfer_leadflow_ownership.sql").read_text(encoding="utf-8"))
        for migration in migrations[1:]:
            psql("leadflow_migrator", migration.read_text(encoding="utf-8"))

        result = psql("leadflow_bootstrap", """
SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles
 WHERE rolname IN ('leadflow_migrator','leadflow_app') ORDER BY rolname;
SELECT has_schema_privilege('leadflow_migrator','leadflow','USAGE'),has_schema_privilege('leadflow_migrator','leadflow','CREATE');
SELECT has_schema_privilege('leadflow_app','leadflow','USAGE'),has_schema_privilege('leadflow_app','leadflow','CREATE');
SELECT has_database_privilege('leadflow_migrator','leadflow','CREATE');
SELECT extname||'|'||r.rolname FROM pg_extension e JOIN pg_roles r ON r.oid=e.extowner WHERE extname='pgcrypto';
SELECT count(*) FROM leadflow.schema_migrations;
""").stdout.splitlines()
        required = {
            "leadflow_app|f|f|f|f", "leadflow_migrator|f|f|f|f",
            "t|t", "t|f", "f", "pgcrypto|leadflow_bootstrap", "17",
        }
        if not required.issubset(set(result)):
            raise AssertionError("new-install verification mismatch")
        psql("leadflow_migrator", "BEGIN; CREATE TABLE leadflow.ddl_probe(id integer); ROLLBACK;")
        print("NEW_INSTALL_ROLE_SEPARATION=PASS")
        print("MIGRATIONS_001_017_AS_RESTRICTED_MIGRATOR=PASS")
        print("PGCRYPTO_OWNED_BY_BOOTSTRAP=PASS")
        print("APP_SCHEMA_CREATE_DENIED=PASS")
        return 0
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"NEW_INSTALL_ROLE_TEST=FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
