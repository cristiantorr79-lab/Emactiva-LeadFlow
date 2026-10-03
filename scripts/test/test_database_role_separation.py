import os
import subprocess
import sys


REQUIRED = (
    "POSTGRES_DB",
    "POSTGRES_MIGRATOR_USER",
    "POSTGRES_MIGRATOR_PASSWORD",
    "POSTGRES_APP_USER",
    "POSTGRES_APP_PASSWORD",
)


def run_psql(user: str, password: str, sql: str) -> subprocess.CompletedProcess[str]:
    command = [
        "docker", "compose", "exec", "-T", "postgres", "sh", "-c",
        'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql -h 127.0.0.1 -X -v ON_ERROR_STOP=1 -U "$1" -d "$2" -Atc "$3"',
        "sh", user, os.environ["POSTGRES_DB"], sql,
    ]
    if password in command or password in " ".join(command):
        raise AssertionError("credential appeared in process arguments")
    return subprocess.run(
        command,
        input=password + "\n",
        text=True,
        capture_output=True,
        check=False,
    )


def require_success(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        raise AssertionError(f"{label} failed with exit {result.returncode}")


def main() -> int:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise AssertionError("required database configuration is missing")

    migrator_user = os.environ["POSTGRES_MIGRATOR_USER"]
    migrator_password = os.environ["POSTGRES_MIGRATOR_PASSWORD"]
    app_user = os.environ["POSTGRES_APP_USER"]
    app_password = os.environ["POSTGRES_APP_PASSWORD"]
    if migrator_user == app_user or migrator_password == app_password:
        raise AssertionError("migrator and application credentials are not distinct")

    migrator_identity = run_psql(migrator_user, migrator_password, "SELECT current_user")
    app_identity = run_psql(app_user, app_password, "SELECT current_user")
    require_success(migrator_identity, "migrator connection")
    require_success(app_identity, "application connection")
    if migrator_identity.stdout.strip() != migrator_user or app_identity.stdout.strip() != app_user:
        raise AssertionError("database identity did not match configured role")

    attributes_sql = "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=current_user"
    migrator_attributes = run_psql(migrator_user, migrator_password, attributes_sql)
    app_attributes = run_psql(app_user, app_password, attributes_sql)
    require_success(migrator_attributes, "migrator attributes")
    require_success(app_attributes, "application attributes")
    if migrator_attributes.stdout.strip() != "f|f|f|f":
        raise AssertionError("migrator retains administrative role attributes")
    if app_attributes.stdout.strip() != "f|f|f|f":
        raise AssertionError("application retains administrative role attributes")

    schema_privileges = run_psql(
        app_user,
        app_password,
        "SELECT has_schema_privilege(current_user,'leadflow','USAGE'),has_schema_privilege(current_user,'leadflow','CREATE')",
    )
    require_success(schema_privileges, "application schema privileges")
    if schema_privileges.stdout.strip() != "t|f":
        raise AssertionError("application schema privileges are not least-privilege")

    ddl = run_psql(
        migrator_user,
        migrator_password,
        "BEGIN; CREATE TABLE leadflow.rem06_probe(value integer); ROLLBACK;",
    )
    require_success(ddl, "migrator DDL")

    normal = run_psql(
        app_user,
        app_password,
        "SELECT count(*) >= 0 FROM leadflow.executions;",
    )
    require_success(normal, "application read")
    if normal.stdout.strip() != "t":
        raise AssertionError("application read returned an unexpected result")

    forbidden = run_psql(
        app_user,
        app_password,
        "CREATE TABLE leadflow.rem06_forbidden(value integer);",
    )
    if forbidden.returncode == 0:
        run_psql(migrator_user, migrator_password, "DROP TABLE IF EXISTS leadflow.rem06_forbidden;")
        raise AssertionError("application role unexpectedly obtained DDL privileges")

    for secret in (migrator_password, app_password):
        combined = "".join(
            result.stdout + result.stderr
            for result in (migrator_identity, app_identity, migrator_attributes, app_attributes, schema_privileges, ddl, normal, forbidden)
        )
        if secret in combined:
            raise AssertionError("credential appeared in subprocess output")

    print("MIGRATOR_CONNECTION=PASS")
    print("MIGRATOR_DDL=PASS")
    print("MIGRATOR_ATTRIBUTES=PASS")
    print("APP_CONNECTION=PASS")
    print("APP_NORMAL_OPERATION=PASS")
    print("APP_ADMIN_DENIED=PASS")
    print("APP_ATTRIBUTES=PASS")
    print("APP_SCHEMA_USAGE_WITHOUT_CREATE=PASS")
    print("DISTINCT_IDENTITIES_AND_SECRETS=PASS")
    print("SECRET_OUTPUT_CHECK=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"REM06_RUNTIME=FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
