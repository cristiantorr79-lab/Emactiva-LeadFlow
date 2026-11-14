"""Focused synthetic tests for separated PostgreSQL initialization."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASH = next(
    (str(path) for path in (Path(r"C:\Program Files\Git\bin\bash.exe"), Path(r"C:\Program Files\Git\usr\bin\bash.exe")) if path.exists()),
    shutil.which("bash"),
)


def load_validator():
    path = ROOT / "scripts/validation/validate_deployment_config.py"
    spec = importlib.util.spec_from_file_location("deployment_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PostgresBootstrapTests(unittest.TestCase):
    def setUp(self):
        if not BASH:
            self.skipTest("bash unavailable")
        self.secrets = {
            "POSTGRES_BOOTSTRAP_PASSWORD": "bootstrap-" + "a" * 40,
            "POSTGRES_MIGRATOR_PASSWORD": "migrator-" + "b" * 40,
            "POSTGRES_APP_PASSWORD": "application-" + "c" * 40,
        }
        self.base_env = {
            **os.environ,
            "LEADFLOW_POSTGRES_BOOTSTRAP_AUTHORIZED": "true",
            "COMPOSE_PROJECT_NAME": "lf015_synthetic",
            "POSTGRES_DB": "leadflow_synthetic",
            "POSTGRES_BOOTSTRAP_USER": "bootstrap",
            "POSTGRES_MIGRATOR_USER": "migrator",
            "POSTGRES_APP_USER": "application",
            **self.secrets,
        }

    def fixture(self, temporary: str) -> tuple[Path, Path, Path]:
        fixture = Path(temporary) / "repo"
        scripts = fixture / "scripts/database"
        validation = fixture / "scripts/validation"
        binary = fixture / "bin"
        scripts.mkdir(parents=True)
        validation.mkdir(parents=True)
        binary.mkdir()
        shutil.copy2(ROOT / "scripts/database/bootstrap_postgres.sh", scripts)
        shutil.copy2(ROOT / "scripts/validation/validate_deployment_config.py", validation)
        shutil.copy2(ROOT / "compose.postgres-bootstrap.yaml", fixture)
        (scripts / "apply_migrations.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            "[ \"${POSTGRES_ADMIN_COMPOSE_MODE:-}\" = bootstrap ]\n"
            "printf 'migrations-called\\n' >>\"$FAKE_DOCKER_LOG\"\n"
            "[ \"${FAKE_MIGRATION_FAILURE:-false}\" != true ]\n",
            encoding="utf-8",
        )
        (scripts / "apply_migrations.sh").chmod(0o755)
        docker = binary / "docker"
        docker.write_text(
            "#!/usr/bin/env bash\nset -eu\n"
            "printf '%s\\n' \"$*\" >>\"$FAKE_DOCKER_LOG\"\n"
            "if [ \"${1:-}\" = inspect ]; then [ \"${FAKE_DOCKER_FAILURE:-}\" != health ] || exit 50; echo healthy; exit 0; fi\n"
            "case \" $* \" in\n"
            "  *' run --rm --no-deps --entrypoint sh postgres-bootstrap '*)\n"
            "    case \"${FAKE_VOLUME_STATE:-}\" in empty) exit 10;; initialized) exit 11;; ambiguous) exit 12;; *) exit 99;; esac;;\n"
            "  *' up -d postgres-bootstrap '*) [ \"${FAKE_DOCKER_FAILURE:-}\" != start ] || exit 48;;\n"
            "  *' ps -q postgres-bootstrap '*) echo synthetic-container; exit 0;;\n"
            "  *' stop postgres-bootstrap '*) [ \"${FAKE_DOCKER_FAILURE:-}\" != cleanup ] || exit 51;;\n"
            "  *) exit 0;;\n"
            "esac\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        python3 = binary / "python3"
        python3.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        python3.chmod(0o755)
        return scripts / "bootstrap_postgres.sh", binary, fixture / "docker.log"

    def invoke(self, state="empty", mutate=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        script, binary, log = self.fixture(temporary.name)
        environment = {**self.base_env, "PATH": str(binary) + os.pathsep + os.environ.get("PATH", ""), "FAKE_VOLUME_STATE": state, "FAKE_DOCKER_LOG": str(log)}
        if mutate:
            mutate(environment)
        result = subprocess.run([BASH, str(script)], text=True, capture_output=True, check=False, env=environment)
        return result, log.read_text(encoding="utf-8") if log.exists() else ""

    def test_empty_volume_initializes_then_cleans_up_without_secret_arguments(self):
        result, log = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "PostgreSQL bootstrap: PASS\n")
        self.assertIn("up -d postgres-bootstrap", log)
        self.assertIn("migrations-called", log)
        self.assertIn("stop postgres-bootstrap", log)
        self.assertIn("rm -f postgres-bootstrap", log)
        for secret in self.secrets.values():
            self.assertNotIn(secret, result.stdout + result.stderr + log)

    def test_initialized_or_ambiguous_volume_fails_before_start(self):
        for state, reason in (("initialized", "volume_already_initialized"), ("ambiguous", "ambiguous_volume_state")):
            with self.subTest(state=state):
                result, log = self.invoke(state)
                self.assertNotEqual(result.returncode, 0)
                expected_id = "LF015-PG-VOLUME-INITIALIZED" if state == "initialized" else "LF015-PG-VOLUME-AMBIGUOUS"
                self.assertIn(expected_id, result.stderr)
                self.assertNotIn("up -d", log)
                self.assertNotIn("migrations-called", log)

    def test_missing_authorization_or_credential_fails_before_docker(self):
        cases = (
            lambda env: env.pop("LEADFLOW_POSTGRES_BOOTSTRAP_AUTHORIZED"),
            lambda env: env.pop("POSTGRES_BOOTSTRAP_PASSWORD"),
        )
        for mutate in cases:
            result, log = self.invoke(mutate=mutate)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(log, "")

    def test_migration_failure_does_not_report_pass_and_removes_bootstrap_container(self):
        result, log = self.invoke(mutate=lambda env: env.update(FAKE_MIGRATION_FAILURE="true"))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PASS", result.stdout)
        self.assertIn("migrations-called", log)
        self.assertIn("stop postgres-bootstrap", log)
        self.assertIn("rm -f postgres-bootstrap", log)
        self.assertIn("phase=migrations operation=apply", result.stderr)
        self.assertIn("exit_code=1 error_id=LF015-PG-MIGRATIONS", result.stderr)

    def test_phase_codes_are_preserved_for_start_health_and_cleanup(self):
        cases = (
            ("start", "48", "phase=postgres_start operation=compose_up", "LF015-PG-START"),
            ("health", "50", "phase=postgres_health operation=inspect", "LF015-PG-HEALTH-INSPECT"),
            ("cleanup", "51", "phase=cleanup operation=stop_container", "LF015-PG-CLEANUP-STOP"),
        )
        for failure, code, phase, error_id in cases:
            with self.subTest(failure=failure):
                result, _ = self.invoke(mutate=lambda env, value=failure: env.update(FAKE_DOCKER_FAILURE=value))
                self.assertEqual(result.returncode, int(code))
                self.assertIn(phase, result.stderr)
                self.assertIn("exit_code=" + code, result.stderr)
                self.assertIn("error_id=" + error_id, result.stderr)

    def test_admin_validator_requires_distinct_strong_credentials(self):
        validator = load_validator()
        environment = {**self.base_env, "APP_ENV": "production"}
        self.assertEqual(validator.validate_config(environment, "postgres-admin"), [])
        errors = validator.validate_config({**environment, "POSTGRES_MIGRATOR_PASSWORD": self.secrets["POSTGRES_APP_PASSWORD"]}, "postgres-admin")
        self.assertIn("shared_postgres_password", errors)

    def test_runtime_compose_keeps_admin_credentials_absent(self):
        production = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
        bootstrap = (ROOT / "compose.postgres-bootstrap.yaml").read_text(encoding="utf-8")
        self.assertIn("POSTGRES_PASSWORD: !reset null", production)
        self.assertIn("POSTGRES_BOOTSTRAP_PASSWORD: !reset null", production)
        self.assertIn("POSTGRES_MIGRATOR_PASSWORD: !reset null", production)
        self.assertNotIn("ports:", bootstrap)
        self.assertNotIn("POSTGRES_HOST_AUTH_METHOD", bootstrap)
        self.assertIn('restart: "no"', bootstrap)


if __name__ == "__main__":
    unittest.main(verbosity=2)
