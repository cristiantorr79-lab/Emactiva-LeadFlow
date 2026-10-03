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
        return result.returncode != 0 and "Required PostgreSQL container variable is missing" in result.stderr

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
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
if not all(checks.values()):
    raise SystemExit(1)
print(f"RESULT: PASS; passed={sum(checks.values())}/{len(checks)}")
