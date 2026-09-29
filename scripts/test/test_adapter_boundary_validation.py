"""Focused REM-11 validation and sanitization checks."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import importlib.util
import json
import os
import sys


ROOT=Path(__file__).resolve().parents[2]
os.environ.update({
 "APP_ENV":"development",
 "CRM_PROVIDER":"mock",
 "ENRICHMENT_PROVIDER":"mock",
 "CRM_UPSTREAM_URL":"http://crm.synthetic",
 "ENRICHMENT_UPSTREAM_URL":"http://enrichment.synthetic",
 "ALERT_UPSTREAM_URL":"http://alert.synthetic",
 "ADAPTER_SERVICE_KEY":"synthetic-adapter-key-at-least-32-chars",
 "ADAPTER_ALLOWED_OPERATIONS":"crm.process,crm.update_enrichment,enrichment.enrich,alert.send,crm.capabilities",
})
spec=importlib.util.spec_from_file_location("adapter_rem11",ROOT/"adapters"/"server.py")
adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
checks={}
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)

valid_error=adapter.canonical_error(502,"provider_timeout")
check("REM11-1 valid error code",valid_error["code"]=="provider_timeout")
canary=("provider-raw-failure-with-token-synthetic-secret-"*6)
unknown_error=adapter.canonical_error(502,canary)
check("REM11-2 anomalous error canonicalized",unknown_error["code"]=="http_502" and canary not in json.dumps(unknown_error))
check("REM11-3 valid opaque id",adapter.opaque_id("crm-contact_123:revision.2")=="crm-contact_123:revision.2")
check("REM11-4 invalid opaque id controlled",adapter.opaque_id("x"*201) is None and adapter.opaque_id("id/../../secret") is None)
check("REM11-5 valid HTTPS website",adapter.normalize_website("HTTPS://Example.TEST/company?token=drop#fragment")=="https://example.test/company")
check("REM11-6 dangerous website rejected",adapter.normalize_website("javascript:alert(1)") is None and adapter.normalize_website("https://user:pass@example.test/") is None)
allowed=adapter.filter_enrichment_fields({"industry":" Software ","company_size":"Small","website":"https://Example.test/about"})
check("REM11-7 enrichment allowlist",allowed=={"industry":"Software","company_size":"Small","website":"https://example.test/about"})
extra=adapter.filter_enrichment_fields({"industry":"software","email":"leak@example.test","phone":"+56900000000","provider_payload":{"secret":"x"}})
check("REM11-8 provider extras removed",extra=={"industry":"software"})
invalid=adapter.filter_enrichment_fields({"industry":"x"*201,"company_size":9,"website":"file:///etc/passwd"})
check("REM11-9 long and invalid types controlled",invalid=={})
captured_out,captured_err=StringIO(),StringIO()
with redirect_stdout(captured_out),redirect_stderr(captured_err):
 anomalous=adapter.hunter_data({"data":{"company":{"industry":canary,"website":"data:text/plain,"+canary,"unknown":{"payload":canary}}}})
 safe_failure=adapter.failure("enrichment",599,0,code=canary)
serialized=json.dumps({"anomalous":anomalous,"failure":safe_failure})
check("REM11-10 anomalous payload not exposed",canary not in serialized+captured_out.getvalue()+captured_err.getvalue() and anomalous=={})

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
