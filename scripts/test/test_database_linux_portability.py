"""Focused static checks for the supported Linux migration path."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sync = ROOT / "scripts/database/sync_database_roles.sh"
apply = ROOT / "scripts/database/apply_migrations.sh"
compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
sync_text = sync.read_text(encoding="utf-8")
apply_text = apply.read_text(encoding="utf-8")
BASH = shutil.which("bash")
if os.name == "nt":
    git_bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe"
    if git_bash.exists():
        BASH = str(git_bash)


def missing_config_fails_closed() -> bool:
    with tempfile.TemporaryDirectory() as directory:
        fake_docker = Path(directory) / "docker"
        fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = sh ]; then exec \"$@\"; fi\n"
            "  shift\n"
            "done\n"
            "exit 1\n",
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)
        environment = {**os.environ, "PATH": directory + os.pathsep + os.environ.get("PATH", "")}
        result = subprocess.run([BASH, str(sync)], text=True, capture_output=True, check=False, env=environment)
        return result.returncode == 31 and "error_id=LF015-PG-ROLE-CONFIG" in result.stderr


def migration_fixture(directory: str) -> tuple[Path, Path]:
    fixture = Path(directory) / "repo"
    database = fixture / "database/migrations"
    scripts = fixture / "scripts/database"
    binary = fixture / "bin"
    database.mkdir(parents=True)
    scripts.mkdir(parents=True)
    binary.mkdir()
    shutil.copy2(apply, scripts / "apply_migrations.sh")
    (scripts / "sync_database_roles.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (scripts / "sync_database_roles.sh").chmod(0o755)
    (scripts / "transfer_leadflow_ownership.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (fixture / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    for version in ("001_initial", "002_second", "003_third", "004_fourth"):
        (database / f"{version}.sql").write_text("SELECT 1;\n", encoding="utf-8")
    fake_docker = binary / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "args=\"$*\"\n"
        "if [[ \"$args\" == *'for name in POSTGRES_DB'* ]]; then printf 'testdb\\nbootstrap\\nmigrator\\n'; exit 0; fi\n"
        "if [[ \"$args\" == *\"to_regclass('leadflow.schema_migrations')\"* ]]; then IFS= read -r _ || true; echo t; exit 0; fi\n"
        "if [[ \"$args\" == *\"version='001_initial'\"* ]]; then IFS= read -r _ || true; echo t; exit 0; fi\n"
        "if [[ \"$args\" == *'SELECT EXISTS'* ]]; then IFS= read -r _ || true; echo t; exit 0; fi\n"
        "if [[ \"$args\" == *'SELECT version FROM'* ]]; then exit 0; fi\n"
        "cat >/dev/null\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    return fixture, binary


def run_fixture(scripts: Path, binary: Path, extra_environment=None):
    environment = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ.get("PATH", "")}
    environment.update(extra_environment or {})
    return subprocess.run(
        [BASH, str(scripts / "apply_migrations.sh")], text=True, capture_output=True,
        check=False, env=environment, stdin=subprocess.DEVNULL,
    )


def stdin_consumption_does_not_truncate_migrations() -> bool:
    with tempfile.TemporaryDirectory() as directory:
        fixture, binary = migration_fixture(directory)
        result = run_fixture(fixture / "scripts/database", binary)
        expected = [f"Already applied: {version}" for version in ("002_second", "003_third", "004_fourth")]
        return result.returncode == 0 and all(line in result.stdout.splitlines() for line in expected)


def incomplete_walk_fails_closed() -> bool:
    with tempfile.TemporaryDirectory() as directory:
        fixture, binary = migration_fixture(directory)
        fixture_apply = fixture / "scripts/database/apply_migrations.sh"
        fixture_text = fixture_apply.read_text(encoding="utf-8")
        fixture_apply.write_text(
            fixture_text.replace(
                "  processed=$((processed+1))",
                "  [ \"$version\" = 002_second ] || processed=$((processed+1))",
                1,
            ),
            encoding="utf-8",
        )
        result = run_fixture(fixture / "scripts/database", binary)
        return result.returncode == 34 and "error_id=LF015-PG-MIGRATION-TRAVERSAL" in result.stderr


def producer_failure_is_preserved() -> bool:
    with tempfile.TemporaryDirectory() as directory:
        fixture, binary = migration_fixture(directory)
        docker = binary / "docker"
        docker.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"$*\" == *'for name in POSTGRES_DB'* ]]; then echo synthetic-secret >&2; exit 47; fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        result = run_fixture(fixture / "scripts/database", binary)
        return (
            result.returncode == 47
            and "phase=configuration operation=read" in result.stderr
            and "error_id=LF015-PG-MIGRATION-CONFIG" in result.stderr
            and "synthetic-secret" not in result.stderr
        )

checks = {
    "bash_syntax_sync": bool(BASH) and subprocess.run([BASH, "-n", str(sync)], check=False).returncode == 0,
    "bash_syntax_apply": bool(BASH) and subprocess.run([BASH, "-n", str(apply)], check=False).returncode == 0,
    "strict_shell_mode": all("set -euo pipefail" in text for text in (sync_text, apply_text)),
    "no_pwsh_dependency": all("pwsh" not in text.lower() and ".ps1" not in text.lower() for text in (sync_text, apply_text)),
    "compose_project_is_explicit": all("--project-directory" in text and "compose.yaml" in text for text in (sync_text, apply_text)),
    "critical_config_fail_closed": all(name in sync_text for name in (
        "POSTGRES_DB", "POSTGRES_BOOTSTRAP_USER", "POSTGRES_BOOTSTRAP_PASSWORD",
        "POSTGRES_MIGRATOR_USER", "POSTGRES_MIGRATOR_PASSWORD", "POSTGRES_APP_USER", "POSTGRES_APP_PASSWORD",
    )),
    "missing_config_runtime_denied": missing_config_fails_closed(),
    "sync_user_reaches_runtime": "POSTGRES_ROLE_SYNC_USER: ${POSTGRES_ROLE_SYNC_USER:-}" in compose,
    "validated_sql_reused": all(name in sync_text for name in (
        "sync_database_roles.sql", "sync_database_roles_legacy_prepare.sql",
        "sync_database_roles_legacy_transfer.sql", "sync_database_roles_legacy_finalize.sql",
    )),
    "historical_001_bootstrap_only": "001_initial.sql" in apply_text and "transfer_leadflow_ownership.sql" in apply_text,
    "remaining_migrations_use_migrator": "psql_file \"$migrator_user\" \"$migration\"" in apply_text,
    "stdin_cannot_truncate_migration_walk": bool(BASH) and stdin_consumption_does_not_truncate_migrations(),
    "migration_walk_count_fails_closed": bool(BASH) and incomplete_walk_fails_closed(),
    "producer_failure_code_preserved_and_sanitized": bool(BASH) and producer_failure_is_preserved(),
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
if not all(checks.values()):
    raise SystemExit(1)
print(f"RESULT: PASS; passed={sum(checks.values())}/{len(checks)}")
