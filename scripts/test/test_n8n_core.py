"""HTTP integration tests for the LF-001.C n8n core."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PORT = os.environ.get("N8N_PORT", "5680")
URL = f"http://127.0.0.1:{PORT}/webhook/leadflow"
KEY = os.environ.get("LEADFLOW_WEBHOOK_KEY", "")
DB = os.environ.get("POSTGRES_DB", "")
PREFIX = f"n8n_test_{secrets.token_hex(4)}"
checks: dict[str, bool] = {}
extras: dict[str, bool] = {}
created_ids: list[str] = []


def check(case: str, condition: bool) -> None:
    checks[case] = bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {case}")


def request(payload, *, key=KEY, content_type="application/json", raw=False, timeout=15):
    data = payload if raw else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": content_type}
    if key is not None:
        headers["X-LeadFlow-Key"] = key
    call = Request(URL, data=data, headers=headers, method="POST")
    try:
        with urlopen(call, timeout=timeout) as response:
            text = response.read().decode()
            return response.status, json.loads(text), text
    except HTTPError as error:
        text = error.read().decode()
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {}
        return error.code, body, text


def psql(sql: str) -> str:
    command = ["docker", "compose", "exec", "-T", "postgres", "psql", "-X", "-q", "-U", "leadflow_migrator", "-d", DB, "-Atc", sql]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("database assertion failed; details redacted")
    return result.stdout.strip()


def valid(event: str, email="core@example.com", **lead_extra):
    lead = {"email": email, **lead_extra}
    return {"event_id": event, "source": "website", "lead": lead}


if not KEY or not DB:
    print("Required local variables are missing", file=sys.stderr)
    sys.exit(2)

try:
    event = PREFIX + "_new"
    status, owner_body, owner_text = request(valid(event, first_name="Private", phone="+56900000000"))
    created_ids.append(owner_body.get("execution_id", ""))
    check("N8N-001", status == 200 and owner_body.get("status") == "success" and owner_body.get("duplicate") is False)

    owner_snapshot = psql(f"SELECT status||'|'||source||'|'||retry_count FROM leadflow.executions WHERE execution_id='{owner_body['execution_id']}';")
    status, duplicate_body, duplicate_text = request(valid(event))
    created_ids.append(duplicate_body.get("execution_id", ""))
    check("N8N-002", status == 200 and duplicate_body.get("duplicate") is True)
    check("N8N-003", psql(f"SELECT status FROM leadflow.executions WHERE execution_id='{owner_body['execution_id']}';") == "success")
    check("N8N-004", psql(f"SELECT status FROM leadflow.executions WHERE execution_id='{duplicate_body['execution_id']}';") == "duplicate")
    check("N8N-005", psql(f"SELECT duplicate_of FROM leadflow.executions WHERE execution_id='{duplicate_body['execution_id']}';") == owner_body["execution_id"])

    norm_event = PREFIX + "_norm"
    normalized = "mixed@example.com"
    status, norm_body, _ = request(valid(norm_event, email="  MiXeD@Example.COM  "))
    created_ids.append(norm_body.get("execution_id", ""))
    expected_lead = hashlib.sha256(normalized.encode()).hexdigest()
    check("N8N-006", status == 200)
    check("N8N-007", psql(f"SELECT lead_identifier FROM leadflow.executions WHERE execution_id='{norm_body['execution_id']}';") == expected_lead)
    expected_key = hashlib.sha256(f"website:{norm_event}".encode()).hexdigest()
    check("N8N-008", psql(f"SELECT idempotency_key FROM leadflow.executions WHERE execution_id='{norm_body['execution_id']}';") == expected_key)

    invalid_cases = [
        ("N8N-009", valid(PREFIX + "_badmail", email="bad-email")),
        ("N8N-010", {"source":"website","lead":{"email":"a@example.com"}}),
        ("N8N-011", {"event_id":PREFIX+"_nosource","lead":{"email":"a@example.com"}}),
        ("N8N-012", {"event_id":PREFIX+"_nolead","source":"website"}),
        ("N8N-013", {"event_id":PREFIX+"_noemail","source":"website","lead":{}}),
        ("N8N-014", {"event_id":PREFIX+"_source","source":"bad:source","lead":{"email":"a@example.com"}}),
        ("N8N-015", {"event_id":123,"source":"website","lead":{"email":"a@example.com"}}),
    ]
    for case, payload in invalid_cases:
        invalid_status, invalid_body, _ = request(payload)
        created_ids.append(invalid_body.get("execution_id", ""))
        check(case, invalid_status == 400 and invalid_body.get("error", {}).get("type") == "validation_error")

    wrong_content = request(b'{"event_id":"x"}', content_type="text/plain", raw=True)
    malformed = request(b'{broken-json', raw=True)
    created_ids.append(wrong_content[1].get("execution_id", ""))
    extras["CONTENT-TYPE"] = wrong_content[0] == 400
    extras["MALFORMED-JSON"] = malformed[0] == 422
    print(f"{'PASS' if extras['CONTENT-TYPE'] else 'FAIL'} EXTRA-CONTENT-TYPE")
    print(f"{'PASS' if extras['MALFORMED-JSON'] else 'FAIL'} EXTRA-MALFORMED-JSON")

    missing_auth = request(valid(PREFIX + "_auth_missing"), key=None)
    wrong_auth = request(valid(PREFIX + "_auth_wrong"), key="incorrect-local-key")
    correct_auth = request(valid(PREFIX + "_auth_ok"))
    created_ids.append(correct_auth[1].get("execution_id", ""))
    check("N8N-016", missing_auth[0] == 401)
    check("N8N-017", wrong_auth[0] == 401)
    check("N8N-018", correct_auth[0] == 200)

    unknown = request({**valid(PREFIX + "_unknown"), "unknown": {"ignored": True}})
    empty_optional = request(valid(PREFIX + "_empty", first_name="", company=""))
    created_ids.extend([unknown[1].get("execution_id", ""), empty_optional[1].get("execution_id", "")])
    check("N8N-019", unknown[0] == 200)
    check("N8N-020", empty_optional[0] == 200)

    subprocess.run(["docker", "compose", "stop", "postgres"], cwd=ROOT, check=True, capture_output=True)
    try:
        unavailable = request(valid(PREFIX + "_dbdown"), timeout=20)
        check("N8N-021", unavailable[0] == 503 and unavailable[1].get("error", {}).get("type") == "persistence_error")
    finally:
        subprocess.run(["docker", "compose", "start", "postgres"], cwd=ROOT, check=True, capture_output=True)
        for _ in range(30):
            ready = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "pg_isready", "-U", "leadflow_migrator", "-d", DB], cwd=ROOT, capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(1)

    public_text = " ".join([owner_text, duplicate_text, json.dumps(missing_auth[1]), json.dumps(wrong_auth[1])])
    check("N8N-022", all(value not in public_text for value in [KEY, "core@example.com", "+56900000000", "Private"]))
    stored_ids = ",".join("'" + value + "'" for value in created_ids if value.startswith("lf_exec_"))
    stored = psql(f"SELECT coalesce(string_agg(to_jsonb(e)::text,' '),'') FROM leadflow.executions e WHERE execution_id IN ({stored_ids});")
    check("N8N-023", all(value not in stored for value in ["core@example.com", "+56900000000", "Private"]))

    concurrent_event = PREFIX + "_concurrent"
    with ThreadPoolExecutor(max_workers=2) as pool:
        simultaneous = [future.result() for future in [pool.submit(request, valid(concurrent_event)), pool.submit(request, valid(concurrent_event))]]
    concurrent_bodies = [row[1] for row in simultaneous]
    created_ids.extend(body.get("execution_id", "") for body in concurrent_bodies)
    owners = sum(body.get("duplicate") is False for body in concurrent_bodies)
    duplicates = sum(body.get("duplicate") is True for body in concurrent_bodies)
    check("N8N-024", all(row[0] == 200 for row in simultaneous) and owners == 1 and duplicates == 1)
    check("N8N-025", owner_snapshot == psql(f"SELECT status||'|'||source||'|'||retry_count FROM leadflow.executions WHERE execution_id='{owner_body['execution_id']}';"))
    concurrent_ids = ",".join("'" + body.get("execution_id", "") + "'" for body in concurrent_bodies)
    concurrency_history = psql(f"SELECT count(*) FROM leadflow.execution_events WHERE execution_id IN ({concurrent_ids});")
    check("N8N-026", concurrency_history == "5")
finally:
    safe_ids = [value for value in created_ids if value.startswith("lf_exec_") and value.replace("lf_exec_", "").isalnum()]
    if safe_ids:
        quoted = ",".join("'" + value + "'" for value in safe_ids)
        psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({quoted}); DELETE FROM leadflow.executions WHERE execution_id IN ({quoted});")

failed = [case for case, passed in {**checks, **extras}.items() if not passed]
print(f"CONCURRENCY requests=2 owners={locals().get('owners', 0)} duplicates={locals().get('duplicates', 0)}")
print(f"RESULT: {'PASS' if not failed else 'FAIL'}; passed={sum(checks.values())}/26")
sys.exit(1 if failed or len(checks) != 26 else 0)
