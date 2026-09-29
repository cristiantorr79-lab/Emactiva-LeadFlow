"""Focused contract checks for Authenticate Validate Normalize."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = json.loads((ROOT / "workflows" / "leadflow_core_initial.json").read_text(encoding="utf-8"))
VALIDATOR = next(node["parameters"]["jsCode"] for node in WORKFLOW["nodes"] if node["name"] == "Authenticate Validate Normalize")
WEBHOOK_KEY = "synthetic-webhook-key-with-32-chars"
DSR_KEY = "synthetic-dsr-key-at-least-32-characters"
WRAPPER = """
const fs=require('fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const run=new Function('require','$json','$env',input.code);
Promise.resolve(run(require,input.item,input.env)).then(value=>process.stdout.write(JSON.stringify(value)));
"""


def validate(event_id, source, allowed_sources, email="lead@example.test"):
    item = {
        "headers": {"x-leadflow-key": WEBHOOK_KEY, "content-type": "application/json"},
        "body": {"event_id": event_id, "source": source, "lead": {"email": email}},
    }
    result = subprocess.run(
        ["node", "-e", WRAPPER],
        cwd=ROOT,
        input=json.dumps({
            "code": VALIDATOR,
            "item": item,
            "env": {
                "LEADFLOW_WEBHOOK_KEY": WEBHOOK_KEY,
                "LEADFLOW_ALLOWED_SOURCES": allowed_sources,
                "DSR_SUBJECT_KEY": DSR_KEY,
            },
        }),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError("workflow validator execution failed")
    return json.loads(result.stdout)["json"]


checks = {}


def check(name, condition):
    checks[name] = bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}")


upper = validate("CaseEvent", "Website", "Website,website")
lower = validate("CaseEvent", "website", "Website,website")
wrong_case = validate("CaseEvent", "Website", "website")
check("A source preserves case and allowlist is case-sensitive", upper.get("source") == "Website" and lower.get("source") == "website" and upper.get("idempotency_key") != lower.get("idempotency_key") and wrong_case.get("error_code") == "invalid_source")

source_100 = "S" * 100
check("B source up to 100 characters accepted", validate("EventB", source_100, source_100).get("route") == "valid")

numeric_source = "9channel"
check("C source may start with a number", validate("EventC", numeric_source, numeric_source).get("source") == numeric_source)

event_200 = "E" * 200
check("D event_id from 129 to 200 characters accepted", validate(event_200, "website", "website").get("event_id") == event_200)

alphabetic_event = "AlphabeticEvent"
check("E alphabetic event_id accepted", validate(alphabetic_event, "website", "website").get("route") == "valid")

leading_space = validate(" EventF", "website", "website")
trailing_space = validate("EventF ", "website", "website")
check("F event_id with edge whitespace rejected", leading_space.get("error_code") == "invalid_event_id" and trailing_space.get("error_code") == "invalid_event_id")

normalized_email = validate("EventG", "website", "website", "  MiXeD@Example.COM  ")
check("G email remains trim-lowercase normalized", normalized_email.get("email") == "mixed@example.com" and normalized_email.get("lead", {}).get("email") == "mixed@example.com")

expected_key = hashlib.sha256(b"Website:CaseEvent").hexdigest()
check("H idempotency uses the exact preserved source", upper.get("idempotency_key") == expected_key)

failed = [name for name, passed in checks.items() if not passed]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
