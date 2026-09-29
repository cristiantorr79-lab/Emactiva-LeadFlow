"""Single focused R4 battery for logging, Docker limits and portability."""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.logging_policy import StructuredLogger

results = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    results.append(name)
    print(f"PASS {len(results):02d}/12 {name}")


stream = io.StringIO()
logger = StructuredLogger("r4_test", {"LOG_LEVEL": "DEBUG", "LOG_OUTPUT": "stdout"}, stdout=stream)
logger.emit(
    "ERROR",
    "provider_failure",
    email="r4.email.canary@example.test",
    phone="+56911112222",
    token="r4-secret-token-canary",
    headers="Authorization: Bearer r4-header-canary",
    error_code="r4.email.canary@example.test",
    error_type="upstream_error",
    stage="enrichment",
    status="failed",
    http_status=502,
)
raw = stream.getvalue()
record = json.loads(raw)
check("email_redacted", "r4.email.canary@example.test" not in raw)
check("phone_redacted", "+56911112222" not in raw)
check("secrets_and_headers_redacted", "r4-secret-token-canary" not in raw and "r4-header-canary" not in raw)
check("external_error_canonical", record["error_code"] == "external_error")
check("technical_metadata_preserved", record["stage"] == "enrichment" and record["error_type"] == "upstream_error" and record["http_status"] == 502)

quiet = io.StringIO()
StructuredLogger("r4_test", {"LOG_LEVEL": "ERROR", "LOG_OUTPUT": "stdout"}, stdout=quiet).emit("INFO", "suppressed")
invalid_rejected = False
try:
    StructuredLogger("r4_test", {"LOG_LEVEL": "VERBOSE", "LOG_OUTPUT": "stdout"})
except ValueError:
    invalid_rejected = True
check("logging_configuration_validated", quiet.getvalue() == "" and invalid_rejected)

compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
production = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
architecture = (ROOT / "docs/architecture/ARCHITECTURE.md").read_text(encoding="utf-8")
check("compose_rotation_all_services", compose.count("logging: *log-policy") == 6)
check("rotation_defaults_configurable", all(value in compose for value in ("${DOCKER_LOG_DRIVER:-json-file}", "${DOCKER_LOG_MAX_SIZE:-10m}", "${DOCKER_LOG_MAX_FILE:-3}")))
check("environment_endpoints_externalized", all(value in production for value in ("${PUBLIC_WEBHOOK_HOST:", "${CRM_UPSTREAM_URL:", "${ENRICHMENT_UPSTREAM_URL:", "${SLACK_WEBHOOK_URL:")))
check("production_has_no_local_dependency", all(value not in production for value in ("127.0.0.1", "C:\\\\Users\\\\", "/Users/", "api.hubapi.com", "api.hunter.io")))
check("core_adapter_environment_separation", "CRM_ADAPTER_URL: http://adapters:8080" in compose and "CRM_PROVIDER: ${CRM_PROVIDER:" in production)
check("environment_gaps_classified", all(value in architecture for value in ("HYBRID/ENVIRONMENT", "DNS", "TLS", "firewall", "IAM", "backup/restore", "monitoreo")))

print("R4_FOCUSED=PASS 12/12")
