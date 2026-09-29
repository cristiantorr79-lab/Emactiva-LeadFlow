"""Shared recovery process boundary with sanitized operational failures."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from adapters.logging_policy import StructuredLogger

LOGGER = StructuredLogger("recovery")
MAX_PROCESSING_AGE_SECONDS = 7 * 24 * 60 * 60


class RecoveryOperationalError(RuntimeError):
    def __init__(self, code, stage):
        self.code = code
        self.stage = stage
        super().__init__(code)


def processing_max_age_seconds():
    try:
        value = int(os.environ.get("RECOVERY_MAX_PROCESSING_AGE_SECONDS", str(MAX_PROCESSING_AGE_SECONDS)))
    except ValueError as error:
        raise RecoveryOperationalError("recovery_configuration_error", "configuration") from error
    if value < 60 or value > MAX_PROCESSING_AGE_SECONDS:
        raise RecoveryOperationalError("recovery_configuration_error", "configuration")
    return value


def sql_text(value):
    return "'" + value.replace("'", "''") + "'"


def psql(sql):
    password = os.environ.get("POSTGRES_APP_PASSWORD", "")
    app = os.environ.get("POSTGRES_APP_USER", "")
    database = os.environ.get("POSTGRES_DB", "")
    if not password or not app or not database or any(char in password for char in "\r\n\0"):
        raise RecoveryOperationalError("recovery_configuration_error", "database")

    shell = 'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql "$@"'
    command = [
        "docker", "compose", "exec", "-T", "postgres", "sh", "-c", shell, "sh",
        "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1",
        "-U", app, "-d", database,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            input=password + "\n" + sql + "\n",
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RecoveryOperationalError("recovery_database_error", "database") from error
    if result.returncode:
        raise RecoveryOperationalError("recovery_database_error", "database")
    return result.stdout.strip()


def log_recovery_result(result):
    LOGGER.emit(
        "INFO" if result.get("status") in {"success", "processing"} else "WARNING",
        "recovery_result",
        execution_id=result.get("execution_id"),
        status=result.get("status"),
        stage=result.get("stage"),
        error_type=result.get("error_type"),
        error_code=result.get("error_code"),
        retry_count=result.get("retry_count"),
    )
