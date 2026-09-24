import json
import os
import secrets
import socket
import sys
import time
import urllib.error
import urllib.request


CRM_URL = os.environ.get("CRM_BASE_URL") or "http://127.0.0.1:5683"
ENRICHMENT_URL = os.environ.get("ENRICHMENT_BASE_URL") or "http://127.0.0.1:5682"
suffix = secrets.token_hex(6)
email = f"mock-{suffix}@example.com"
checks = {}


def request(base, path, payload=None, method="POST", timeout=10, include_headers=False):
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    req = urllib.request.Request(
        base + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = (response.status, json.loads(response.read()))
            return (*result, dict(response.headers)) if include_headers else result
    except urllib.error.HTTPError as error:
        result = (error.code, json.loads(error.read()))
        return (*result, dict(error.headers)) if include_headers else result
    except (TimeoutError, socket.timeout):
        return ("timeout", {})


def configure(base, mode, operation, **extra):
    return request(base, "/control/failure", {"mode": mode, "operation": operation, **extra})


def clear(base):
    return request(base, "/control/failure", method="DELETE")


def check(name, condition):
    checks[name] = bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}")


status, missing = request(CRM_URL, "/crm/lookup", {"email": email})
check("CRM-001 lookup inexistente", status == 200 and missing == {"found": False})

lead = {"email": email.upper(), "first_name": "Ada", "company": "Original"}
status, created = request(CRM_URL, "/crm/contacts", {"lead": lead, "operation_key": f"create:{suffix}"})
contact_id = created.get("contact_id")
check("CRM-002 create", status == 201 and created.get("created") is True and isinstance(contact_id, str))

status, found = request(CRM_URL, "/crm/lookup", {"email": email})
check("CRM-003 lookup existente", status == 200 and found == {"found": True, "contact": {"id": contact_id, "email": email}})

status, repeated = request(CRM_URL, "/crm/contacts", {"lead": lead, "operation_key": f"create:{suffix}"})
check("CRM-004 create idempotente", status == 200 and repeated.get("contact_id") == contact_id)

status, conflict = request(CRM_URL, "/crm/contacts", {"lead": {"email": email}, "operation_key": f"other:{suffix}"})
check("CRM-005 email único", status == 409 and conflict.get("error", {}).get("type") == "conflict_error")

status, updated = request(CRM_URL, f"/crm/contacts/{contact_id}", {"fields": {"first_name": "Grace"}}, method="PATCH")
check("CRM-006 update campos presentes", status == 200 and updated.get("contact_id") == contact_id)

status, enrichment_update = request(CRM_URL, f"/crm/contacts/{contact_id}/enrichment", {"fields": {"industry": "technology", "website": "https://leadflow.test"}}, method="PATCH")
check("CRM-007 updateEnrichment", status == 200 and enrichment_update.get("contact_id") == contact_id)

status, found_after = request(CRM_URL, f"/crm/contacts/{contact_id}", method="GET")
contact_after = found_after.get("contact", {})
check("CRM-008 campos omitidos no se borran", status == 200 and contact_after.get("company") == "Original" and contact_after.get("first_name") == "Grace")

allowed = {"industry", "company_size", "website"}
status, enriched_email = request(ENRICHMENT_URL, "/enrich", {"email": email})
data_email = enriched_email.get("data", {})
check("ENRICH-001 success", status == 200 and enriched_email.get("enrichment_status") == "success")
check("ENRICH-002 campos permitidos", set(data_email) <= allowed and all(isinstance(value, str) for value in data_email.values()))
check("ENRICH-003 petición email", status == 200 and bool(data_email))

status, enriched_company = request(ENRICHMENT_URL, "/enrich", {"email": email, "company": "LeadFlow"})
check("ENRICH-004 petición email y company", status == 200 and enriched_company.get("enrichment_status") == "success")

configure(ENRICHMENT_URL, "timeout", "enrich", delay_seconds=1)
timeout_result = request(ENRICHMENT_URL, "/enrich", {"email": email}, timeout=0.2)
check("ERROR-001 timeout", timeout_result[0] == "timeout")
clear(ENRICHMENT_URL)

for case, mode, expected in [
    ("ERROR-002 HTTP 400", "http_400", 400),
    ("ERROR-003 HTTP 401", "http_401", 401),
    ("ERROR-005 HTTP 500", "http_500", 500),
]:
    configure(CRM_URL, mode, "lookup")
    simulated_status, _ = request(CRM_URL, "/crm/lookup", {"email": email})
    check(case, simulated_status == expected)

configure(CRM_URL, "http_429", "lookup", retry_after_seconds=7)
rate_status, _, rate_headers = request(CRM_URL, "/crm/lookup", {"email": email}, include_headers=True)
check("ERROR-004 HTTP 429 Retry-After", rate_status == 429 and rate_headers.get("Retry-After") == "7")
clear(CRM_URL)

time.sleep(1)
normal_status, normal_body = request(ENRICHMENT_URL, "/enrich", {"email": email})
check("ERROR-006 recuperación happy path", normal_status == 200 and normal_body.get("enrichment_status") == "success")

failed = [name for name, passed in checks.items() if not passed]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
