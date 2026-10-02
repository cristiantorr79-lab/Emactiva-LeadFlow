"""Static, focused validation for LAB-LF-006."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAB_DIR = ROOT / "labs" / "LAB-LF-006"
RUNBOOK = LAB_DIR / "LEADFLOW_REMOTE_DEPLOYMENT_RUNBOOK.md"
TEMPLATE = LAB_DIR / "LEADFLOW_CLIENT_IMPLEMENTATION_TEMPLATE.md"
HANDOFF = LAB_DIR / "HANDOFF_LAB-LF-006.md"

TECHNICAL_ARTIFACTS = (
    ROOT / "compose.production.yaml",
    ROOT / ".env.example",
    ROOT / "docs" / "setup" / "SETUP.md",
    ROOT / "docs" / "runbooks" / "BACKUP_RESTORE.md",
    ROOT / "config" / "backup-policy.json",
    ROOT / "scripts" / "validation" / "validate_deployment_config.py",
    ROOT / "scripts" / "database" / "apply_migrations.ps1",
    ROOT / "scripts" / "database" / "sync_database_roles.ps1",
)


class ValidationFailure(Exception):
    """First real validation failure."""


def normalized(text: str) -> str:
    replacements = str.maketrans("áéíóúüñ", "aeiouun")
    return text.lower().translate(replacements)


def require_terms(label: str, text: str, terms: tuple[str, ...]) -> None:
    content = normalized(text)
    for term in terms:
        if normalized(term) not in content:
            raise ValidationFailure(f"{label}: missing reference to {term}")


def load_deployment_validator():
    path = ROOT / "scripts" / "validation" / "validate_deployment_config.py"
    spec = importlib.util.spec_from_file_location("validate_deployment_config", path)
    if spec is None or spec.loader is None:
        raise ValidationFailure("cannot import validate_deployment_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def production_environment() -> dict[str, str]:
    strong = "synthetic-value-with-at-least-32-chars"
    return {
        "APP_ENV": "production",
        "POSTGRES_DB": "leadflow_synthetic",
        "POSTGRES_MIGRATOR_USER": "leadflow_migrator_synthetic",
        "POSTGRES_MIGRATOR_PASSWORD": strong + "-migrator",
        "POSTGRES_APP_USER": "leadflow_app_synthetic",
        "POSTGRES_APP_PASSWORD": strong + "-app",
        "LEADFLOW_WEBHOOK_KEY": strong + "-webhook",
        "N8N_ENCRYPTION_KEY": strong + "-n8n",
        "RECOVERY_CONTEXT_KEY": strong + "-recovery",
        "RECOVERY_ADAPTER_URL": "http://adapters:5685",
        "ADAPTER_SERVICE_KEY": strong + "-adapter",
        "ADAPTER_ALLOWED_OPERATIONS": "crm.process,enrichment.enrich,alert.send",
        "DSR_SUBJECT_KEY": strong + "-dsr",
        "CRM_UPSTREAM_URL": "https://api.hubapi.com",
        "ENRICHMENT_UPSTREAM_URL": "https://api.hunter.io",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/synthetic/not-real/value",
        "PUBLIC_WEBHOOK_HOST": "leadflow.example.test",
        "CRM_PROVIDER": "hubspot",
        "ENRICHMENT_PROVIDER": "hunter",
        "CRM_API_KEY": "synthetic-crm-key",
        "ENRICHMENT_API_KEY": "synthetic-enrichment-key",
    }


def assert_expected_error(validate_config, mutation, expected: str) -> None:
    env = production_environment()
    mutation(env)
    errors = validate_config(env)
    if expected not in errors:
        raise ValidationFailure(f"synthetic config did not report {expected}")


def validate_no_secrets() -> None:
    suspicious_patterns = (
        re.compile(r"\b(?:ghp|github_pat|sk|xox[baprs])-[-A-Za-z0-9_]{12,}\b"),
        re.compile(r"postgres(?:ql)?://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
        re.compile(r"https://hooks\.slack\.com/services/[A-Z0-9]{8,}/[A-Z0-9]{8,}/[A-Za-z0-9]{16,}"),
        re.compile(
            r"(?im)^\s*(?:LEADFLOW_WEBHOOK_KEY|CRM_API_KEY|ENRICHMENT_API_KEY|"
            r"POSTGRES_(?:APP|MIGRATOR)_PASSWORD)\s*[=:]\s*[`\"']?"
            r"(?!\s*(?:$|<|\{|\[|REDACTED|PLACEHOLDER|EXAMPLE))\S+"
        ),
    )
    for path in sorted(LAB_DIR.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in suspicious_patterns:
            if pattern.search(text):
                raise ValidationFailure(f"possible secret in {path.relative_to(ROOT)}")


def run() -> tuple[int, int]:
    checks = 0

    required_files = (RUNBOOK, TEMPLATE, HANDOFF, *TECHNICAL_ARTIFACTS)
    for path in required_files:
        if not path.is_file():
            raise ValidationFailure(f"missing artifact: {path.relative_to(ROOT)}")
        checks += 1

    runbook = RUNBOOK.read_text(encoding="utf-8")
    require_terms(
        "runbook",
        runbook,
        (
            "discovery", "preflight", "deployment", "smoke test",
            "primera ejecución controlada", "duplicado", "idempotencia",
            "rollback", "cleanup", "handoff", "SYSTEM", "HYBRID", "ENVIRONMENT",
        ),
    )
    checks += 1
    runbook_normalized = normalized(runbook)
    if not (
        "nunca almacenar secretos" in runbook_normalized
        or "nunca almacenar secretos en git" in runbook_normalized
        or "secretos no se incluyen" in runbook_normalized
    ):
        raise ValidationFailure("runbook: missing explicit prohibition on storing secrets")
    checks += 1
    if "no existe fail critico" not in runbook_normalized:
        raise ValidationFailure("runbook: missing explicit prohibition on production with critical FAIL")
    checks += 1

    template = TEMPLATE.read_text(encoding="utf-8")
    require_terms(
        "template",
        template,
        (
            "identificación", "discovery", "accesos", "configuración", "preflight",
            "deployment", "smoke test", "primera ejecución controlada", "duplicado",
            "entorno", "producción", "rollback", "cleanup", "handoff",
            "aceptación funcional", "PASS", "WARN", "FAIL", "N/A", "NOT_VERIFIED",
        ),
    )
    checks += 1

    handoff = HANDOFF.read_text(encoding="utf-8")
    require_terms(
        "handoff",
        handoff,
        (
            "objetivo", "alcance", "fuera de alcance", "decisiones", "artefactos",
            "SYSTEM", "HYBRID", "ENVIRONMENT", "PASS", "WARN", "NOT_VERIFIED",
            "criterio de cierre",
        ),
    )
    checks += 1

    validate_no_secrets()
    checks += 1

    deployment = load_deployment_validator()
    validate_config = deployment.validate_config
    if validate_config(production_environment()):
        raise ValidationFailure("synthetic valid production config did not pass")
    checks += 1

    assert_expected_error(
        validate_config,
        lambda env: env.pop("LEADFLOW_WEBHOOK_KEY"),
        "missing_leadflow_webhook_key",
    )
    checks += 1
    assert_expected_error(
        validate_config,
        lambda env: env.__setitem__("CRM_UPSTREAM_URL", "http://localhost:5683"),
        "unsafe_crm_upstream_url",
    )
    checks += 1
    assert_expected_error(
        validate_config,
        lambda env: env.__setitem__("POSTGRES_APP_USER", env["POSTGRES_MIGRATOR_USER"]),
        "shared_postgres_role",
    )
    checks += 1
    assert_expected_error(
        validate_config,
        lambda env: env.__setitem__("POSTGRES_APP_PASSWORD", env["POSTGRES_MIGRATOR_PASSWORD"]),
        "shared_postgres_password",
    )
    checks += 1

    return checks, checks


def main() -> int:
    try:
        passed, total = run()
    except (OSError, UnicodeError, ValidationFailure) as exc:
        print("LAB-LF-006 VALIDATION: FAIL")
        print(f"first_failure={exc}")
        return 1
    print("LAB-LF-006 VALIDATION: PASS")
    print(f"checks={passed}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
