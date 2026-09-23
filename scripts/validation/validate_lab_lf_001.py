"""Static, non-destructive checks for the current LAB-LF-001 baseline."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
failures = 0


def check(name: str, condition: bool) -> None:
    global failures
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    failures += not condition


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


required = ["compose.yaml", ".env.example", "database/migrations/001_initial.sql",
            "scripts/database/wait_postgres.ps1", "scripts/database/apply_migrations.ps1",
            "scripts/test/test_persistence.py", "labs/LAB-LF-001/HANDOFF_LAB-LF-001.md"]
check("estructura LF-001", all((ROOT / name).is_file() for name in required))
compose = read("compose.yaml")
check("PostgreSQL fijado y local", "postgres:17.6-bookworm" in compose and "127.0.0.1:${POSTGRES_PORT:-5432}:5432" in compose)
sql = read("database/migrations/001_initial.sql")
check("reclamo oficial", all(token in sql for token in ["claim_event", "unique_violation", "duplicate_of"]))
check("función de hash", "compute_idempotency_key" in sql and "public.digest(convert_to" in sql)
check("sin borrado de ejecución", not re.search(r"DELETE\s+FROM\s+leadflow\.executions", sql, re.I))
tests = read("scripts/test/test_persistence.py")
check("DB-001 a DB-018", all(f'"DB-{number:03d}"' in tests for number in range(1, 19)))
check("prueba concurrente y hash", "ThreadPoolExecutor" in tests and '"HASH-001"' in tests)
tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, check=True).stdout.decode().split("\0")
private_markers = ["-----BEGIN " + prefix + "PRIVATE" + " KEY-----" for prefix in ("", "RSA ", "EC ", "OPENSSH ")]
patterns = [r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+", r"\bAKIA[A-Z0-9]{16}\b", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"]
suspect = False
for name in filter(None, tracked):
    content = (ROOT / name).read_text(encoding="utf-8", errors="replace")
    suspect |= any(marker in content for marker in private_markers)
    suspect |= any(re.search(pattern, content) for pattern in patterns)
check("sin secretos obvios", not suspect)
check(".env ignorado", subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", ".env"]).returncode == 0)
check("documentación actualizada", all(term in read("docs/setup/SETUP.md") for term in ["Docker Compose", "test_persistence.py", "apply_migrations.ps1"]))
print(f"RESULTADO: {'FAIL' if failures else 'PASS'}; fallos={failures}")
sys.exit(1 if failures else 0)
