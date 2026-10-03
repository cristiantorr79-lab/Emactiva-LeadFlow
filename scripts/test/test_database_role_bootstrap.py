"""Static checks for PostgreSQL bootstrap/migrator/runtime separation."""
from pathlib import Path
import hashlib


ROOT = Path(__file__).resolve().parents[2]
compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
sync_ps1 = (ROOT / "scripts/database/sync_database_roles.ps1").read_text(encoding="utf-8")
sync_sql = (ROOT / "scripts/database/sync_database_roles.sql").read_text(encoding="utf-8")
apply_ps1 = (ROOT / "scripts/database/apply_migrations.ps1").read_text(encoding="utf-8")
initial_migration = (ROOT / "database/migrations/001_initial.sql").read_text(encoding="utf-8")
initial_migration_bytes = (ROOT / "database/migrations/001_initial.sql").read_bytes()
legacy_prepare = (ROOT / "scripts/database/sync_database_roles_legacy_prepare.sql").read_text(encoding="utf-8")
legacy_transfer = (ROOT / "scripts/database/sync_database_roles_legacy_transfer.sql").read_text(encoding="utf-8")
legacy_finalize = (ROOT / "scripts/database/sync_database_roles_legacy_finalize.sql").read_text(encoding="utf-8")

checks = {
    "bootstrap_is_postgres_user": "POSTGRES_USER: ${POSTGRES_BOOTSTRAP_USER:?POSTGRES_BOOTSTRAP_USER is required}" in compose,
    "bootstrap_password_is_postgres_password": "POSTGRES_PASSWORD: ${POSTGRES_BOOTSTRAP_PASSWORD:?POSTGRES_BOOTSTRAP_PASSWORD is required}" in compose,
    "bootstrap_user_exposed_to_container": "POSTGRES_BOOTSTRAP_USER: ${POSTGRES_BOOTSTRAP_USER:?POSTGRES_BOOTSTRAP_USER is required}" in compose,
    "bootstrap_password_exposed_to_container": "POSTGRES_BOOTSTRAP_PASSWORD: ${POSTGRES_BOOTSTRAP_PASSWORD:?POSTGRES_BOOTSTRAP_PASSWORD is required}" in compose,
    "migrator_and_app_exposed_to_container": all(
        f"{name}: ${{{name}:?{name} is required}}" in compose
        for name in (
            "POSTGRES_MIGRATOR_USER", "POSTGRES_MIGRATOR_PASSWORD",
            "POSTGRES_APP_USER", "POSTGRES_APP_PASSWORD",
        )
    ),
    "migrator_not_postgres_user": "POSTGRES_USER: ${POSTGRES_MIGRATOR_USER" not in compose,
    "three_credentials_required": all(name in sync_ps1 for name in (
        "POSTGRES_BOOTSTRAP_USER", "POSTGRES_BOOTSTRAP_PASSWORD",
        "POSTGRES_MIGRATOR_USER", "POSTGRES_MIGRATOR_PASSWORD",
        "POSTGRES_APP_USER", "POSTGRES_APP_PASSWORD",
    )),
    "legacy_transition_bounded": all(token in sync_ps1 for token in (
        "POSTGRES_ROLE_SYNC_USER", "legacy remediation only", "oid=10",
        "sync_database_roles_legacy_prepare.sql", "sync_database_roles_legacy_transfer.sql",
        "sync_database_roles_legacy_finalize.sql",
    )),
    "legacy_preflight_guards": all(token in legacy_prepare for token in (
        "migrator_oid <> 10", "Destination bootstrap has unexpected ownership",
        "Unexpected role membership", "unsupported user objects outside schema leadflow",
        "Extension objects inside schema leadflow",
    )),
    "legacy_selective_transfer": all(token in legacy_transfer for token in (
        "ALTER SCHEMA leadflow OWNER", "ALTER ROUTINE", "d.deptype = 'e'",
    )) and "REASSIGN OWNED" not in legacy_transfer,
    "legacy_oid10_preserved": "Final bootstrap is not OID 10" not in legacy_finalize and "OID 10 bootstrap" in legacy_finalize,
    "legacy_transition_drop_guarded": "Transition role is not empty" in legacy_finalize and "DROP ROLE" in legacy_finalize,
    "migrator_explicitly_restricted": "ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION" in sync_sql,
    "app_explicitly_restricted": "ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION" in sync_sql,
    "migrator_schema_scope": "GRANT USAGE, CREATE ON SCHEMA leadflow" in sync_sql,
    "app_no_schema_create": "REVOKE CREATE ON SCHEMA leadflow" in sync_sql,
    "migration_runs_as_migrator": "-U $env:POSTGRES_MIGRATOR_USER" in apply_ps1,
    "extension_installed_by_bootstrap": "CREATE EXTENSION IF NOT EXISTS pgcrypto" in sync_sql,
    "historical_migration_001_immutable": hashlib.sha1(b"blob " + str(len(initial_migration_bytes)).encode() + b"\0" + initial_migration_bytes).hexdigest() == "eb6d27e1c77fc8176e6f8e1c58ce4125715bac71",
    "migration_001_bootstrap_special_case": all(token in apply_ps1 for token in (
        "Bootstrap migration failed: 001_initial", "POSTGRES_BOOTSTRAP_USER",
        "transfer_leadflow_ownership.sql", "Where-Object BaseName -ne '001_initial'",
    )),
    "sync_precedes_migrations": apply_ps1.index("sync_database_roles.ps1") < apply_ps1.index("$migrationFiles"),
}

for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
if not all(checks.values()):
    raise SystemExit(1)
print(f"RESULT: PASS; passed={sum(checks.values())}/{len(checks)}")
