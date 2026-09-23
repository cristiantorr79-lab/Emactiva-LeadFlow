"""Validación estática LAB-LF-000; biblioteca estándar, sin servicios externos."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
failures = 0


def check(name, condition):
    global failures
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    failures += not condition


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True)


def read(name):
    path = ROOT / name
    return path.read_text(encoding='utf-8') if path.is_file() else ''


required = [
    'README.md', '.gitignore', '.env.example',
    'docs/architecture/ARCHITECTURE.md', 'docs/architecture/CONTRACTS.md',
    'docs/testing/TEST_PLAN_LF_V1.md', 'docs/setup/SETUP.md',
    'database/migrations/001_initial.sql',
    'labs/LAB-LF-000/HANDOFF_LAB-LF-000.md',
    'scripts/validation/validate_lab.py',
]
check('archivos obligatorios', all((ROOT / f).is_file() for f in required))
check('repositorio Git', git('rev-parse', '--show-toplevel').returncode == 0)
check('.env y variantes ignoradas', all(
    git('check-ignore', '--no-index', '-q', f).returncode == 0
    for f in ['.env', '.env.local', '.env.production', 'mocks/crm/.env']))
check('.env.example no ignorado', git('check-ignore', '--no-index', '-q', '.env.example').returncode == 1)

config = {}
malformed = False
for line in read('.env.example').splitlines():
    if not line.strip() or line.lstrip().startswith('#'):
        continue
    if '=' not in line:
        malformed = True
        continue
    key, value = line.split('=', 1)
    if key in config:
        malformed = True
    config[key] = value
expected = dict.fromkeys([
    'POSTGRES_HOST', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD',
    'CRM_BASE_URL', 'CRM_API_KEY', 'ENRICHMENT_BASE_URL',
    'ENRICHMENT_API_KEY', 'SLACK_WEBHOOK_URL'], '')
expected.update(APP_ENV='development', POSTGRES_PORT='5432', RETRY_MAX_ATTEMPTS='3',
                RETRY_DELAY_FIRST_SECONDS='5', RETRY_DELAY_SECOND_SECONDS='15')
check('ejemplo completo sin credenciales ni URLs reales', not malformed and config == expected)

states = ['received', 'processing', 'duplicate', 'retrying', 'success', 'failed']
stages = ['validation', 'idempotency', 'crm_lookup', 'crm_create', 'crm_update',
          'enrichment', 'crm_enrichment_update', 'alert']
contracts = read('docs/architecture/CONTRACTS.md')
check('estados y etapas documentados', all(f'`{s}`' in contracts for s in states + stages))
plan = read('docs/testing/TEST_PLAN_LF_V1.md')
check('20 casos con objetivo/precondición/entrada/resultado/PASS', all(
    re.search(rf'^\| LF-T{i:02d} \|(?:[^\n|]*\|){{5}}\s*$', plan, re.M)
    for i in range(1, 21)))
sql = read('database/migrations/001_initial.sql')
check('idempotency_key UNIQUE', bool(re.search(r'\bidempotency_key\s+text\s+UNIQUE\b', sql, re.I)))
fields = ['execution_id', 'idempotency_key', 'event_id', 'source', 'lead_identifier',
          'status', 'stage', 'crm_action', 'crm_contact_id', 'enrichment_status',
          'retry_count', 'error_type', 'error_code', 'error_message',
          'started_at', 'finished_at', 'created_at', 'updated_at']
check('campos mínimos SQL', all(re.search(rf'^\s+{f}\s+', sql, re.M) for f in fields))
check('migración transaccional con ledger', all(s in sql for s in [
    'BEGIN;', 'COMMIT;', 'INSERT INTO leadflow.schema_migrations', 'version text PRIMARY KEY']))
# Balance léxico, no parser SQL. Se eliminan comentarios y literales antes de contar.
stripped = re.sub(r'--[^\n]*', '', sql)
stripped = re.sub(r"'(?:''|[^'])*'", "''", stripped)
depth = 0
balanced = True
for char in stripped:
    depth += (char == '(') - (char == ')')
    if depth < 0:
        balanced = False
check('SQL léxico básico (no ejecución PostgreSQL)', balanced and depth == 0 and stripped.count("'") % 2 == 0 and stripped.rstrip().endswith('COMMIT;'))

tracked_result = git('ls-files', '-z')
new_result = git('ls-files', '--others', '--exclude-standard', '-z')
check('inventario Git legible', tracked_result.returncode == new_result.returncode == 0)
tracked = [s for s in tracked_result.stdout.decode('utf-8').split('\0') if s]
new = [s for s in new_result.stdout.decode('utf-8').split('\0') if s]


def real_env(name):
    base = Path(name).name
    return (base == '.env' or base.startswith('.env.')) and not base.endswith('.example')


check('sin .env reales versionados', not any(real_env(f) for f in tracked))
# Heurísticas acotadas; no se imprimen coincidencias ni valores sensibles.
patterns = [
    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    r'\bAKIA[A-Z0-9]{16}\b', r'\bgh[pousr]_[A-Za-z0-9]{20,}\b',
    r'\bxox[baprs]-[A-Za-z0-9-]{15,}\b',
    r'https://hooks\.slack\.com/services/[A-Za-z0-9/]+',
    r'(?im)^[ \t]*[\"\x27]?(?:\w*(?:password|api_key|token|secret)|SLACK_WEBHOOK_URL)[\"\x27]?[ \t]*[:=][ \t]*[\"\x27]?[A-Za-z0-9_+/.-]{16,}',
    r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
]
suspects = []
unreadable = []
for name in sorted(set(tracked + new)):
    path = ROOT / name
    try:
        content = path.read_bytes().decode('utf-8', errors='replace')
    except OSError:
        unreadable.append(name)
        continue
    if any(re.search(pattern, content) for pattern in patterns):
        suspects.append(name)
check('archivos auditables', not unreadable)
check('sin secretos obvios en versionados y nuevos', not suspects)
for name in suspects:
    print(f'  Revisar archivo: {name} (valor oculto)')
check('git diff --check', git('diff', '--check').returncode == 0)
check('git diff --cached --check', git('diff', '--cached', '--check').returncode == 0)
new_checks = [git('diff', '--no-index', '--check', '--', '/dev/null', f) for f in new]
# --no-index puede devolver 1 por diferencias normales entre vacío y archivo nuevo.
check('espacios y conflictos en archivos nuevos', all(
    result.returncode in (0, 1) and not result.stdout.strip() for result in new_checks))
print(f'RESULTADO: {"FAIL" if failures else "PASS"}; fallos={failures}')
sys.exit(1 if failures else 0)
