"""Executable LF-002.2 conformance contract for CRM and enrichment adapters."""
from pathlib import Path
import importlib.util, sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("adapter_server",ROOT/"adapters"/"server.py")
adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
checks={}; calls=[]; waits=[]
SAFE={"consistent_lookup_after_create":True,"unique_email":True,"idempotent_create_operation_key":True,"conflict_reconciliation":True}
UNSAFE={key:False for key in SAFE}
BASE={"app_env":"development","crm_provider":"mock","enrichment_provider":"mock","attempts":3,"delay1":5,"delay2":15,"timeout_ms":2000,"crm":"http://crm","enrichment":"http://enrichment","alert":"http://alert","crm_api_key":"","enrichment_api_key":""}

def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
def configure(profile=SAFE): adapter.CONFIG={**BASE,"capabilities":dict(profile)}; calls.clear(); waits.clear()
def scripted(items):
 calls.clear(); waits.clear()
 sequence=list(items)
 def fake(method,url,body):
  calls.append((method,url,body)); item=sequence.pop(0)
  return item(method,url,body) if callable(item) else item
 adapter.call=fake
def no_wait(headers,status,attempt):
 delay=(adapter.CONFIG["delay1"],adapter.CONFIG["delay2"])[attempt-1]
 retry=adapter.retry_after_seconds(headers) if status==429 else None
 waits.append(max(delay,retry or 0))
adapter.wait=no_wait
def lead(): return {"email":"normalized@example.com","lead":{"email":"normalized@example.com","first_name":"Ada"},"present_fields":{"first_name":"Ada"},"operation_key":"stable:create:key"}
def err(status,headers=None): return status,headers or {},{}
def ok(body): return 200,{},body

configure()
profile=adapter.CONFIG["capabilities"]
check("CRM-001 capability profile fields",set(profile)==set(SAFE))
check("CRM-002 safe ambiguous profile",adapter.safe_ambiguous_create_retry(profile))
check("CRM-003 unsafe profile rejected",not adapter.safe_ambiguous_create_retry(UNSAFE))

scripted([ok({"found":False}),(201,{}, {"contact_id":"c1"})])
created=adapter.crm_process(lead())
check("CRM-004 lookup not found and create",created.get("success") and created.get("contact_id")=="c1")
check("CRM-005 normalized lookup",calls[0][2]=={"email":"normalized@example.com"})

scripted([ok({"found":True,"contact":{"id":"c1","email":"normalized@example.com"}}),ok({"contact_id":"c1"})])
updated=adapter.crm_process(lead())
check("CRM-006 lookup found and stable id",updated.get("crm_action")=="updated" and updated.get("contact_id")=="c1")
check("CRM-007 partial update",calls[1][2]=={"fields":{"first_name":"Ada"}})

operations={}
def idempotent_create(method,url,body):
 contact=operations.setdefault(body["operation_key"],"c-stable"); return 201,{}, {"contact_id":contact}
ids=[]
for _ in range(2):
 scripted([ok({"found":False}),idempotent_create]); ids.append(adapter.crm_process(lead()).get("contact_id"))
check("CRM-008 operation key idempotency",ids==["c-stable","c-stable"] and len(operations)==1)
check("CRM-009 enrichment update whitelist",adapter.filter_enrichment_fields({"industry":"software","website":"https://example.test","email":"leak@example.com","company_size":7})=={"industry":"software","website":"https://example.test"})

scripted([ok({"found":False}),err(409),ok({"found":True,"contact":{"id":"c409"}})])
conflict=adapter.crm_process(lead())
check("CRM-010 conflict reconciled",conflict.get("success") and conflict.get("contact_id")=="c409")

scripted([ok({"found":False}),err(0),ok({"found":False}),(201,{}, {"contact_id":"c-safe"})])
safe=adapter.crm_process(lead())
check("CRM-011 safe ambiguous retry",safe.get("success") and safe.get("contact_id")=="c-safe" and len([c for c in calls if c[1].endswith('/crm/contacts')])==2)

configure(UNSAFE); adapter.wait=no_wait
scripted([ok({"found":False}),err(0),ok({"found":False})])
unsafe=adapter.crm_process(lead())
check("CRM-012 unsafe ambiguous conservative failure",not unsafe.get("success") and unsafe.get("error_type")=="ambiguous_create" and unsafe.get("ambiguous") is True)
check("CRM-013 unsafe profile never repeats create",len([c for c in calls if c[1].endswith('/crm/contacts')])==1)
check("CRM-014 sanitized canonical error",set(unsafe["error"])=={"type","code","http_status","retry_after_seconds","ambiguous","message"} and "normalized@example.com" not in str(unsafe))

configure(); adapter.wait=no_wait
scripted([ok({"enrichment_status":"success","data":{"industry":"software","company_size":"small","website":"https://example.test"}})])
enriched=adapter.enrich({"email":"normalized@example.com","company":"Acme"})
check("ENRICH-001 success",enriched.get("success") and enriched.get("enrichment_status")=="success")
check("ENRICH-002 optional company",calls[0][2]=={"email":"normalized@example.com","company":"Acme"})

scripted([ok({"enrichment_status":"success","data":{}})])
empty=adapter.enrich({"email":"normalized@example.com"})
check("ENRICH-003 optional fields",empty.get("success") and empty.get("data")=={} and calls[0][2]=={"email":"normalized@example.com"})

scripted([ok({"enrichment_status":"success","data":{"industry":"software","email":"leak@example.com","token":"secret","company_size":9}})])
filtered=adapter.enrich({"email":"normalized@example.com"})
check("ENRICH-004 strict whitelist",filtered.get("data")=={"industry":"software"})

scripted([err(429,{"Retry-After":"9"}),ok({"enrichment_status":"success","data":{}})])
rate=adapter.enrich({"email":"normalized@example.com"})
check("ENRICH-005 429 Retry-After",rate.get("success") and waits==[9.0] and rate.get("retry_count")==1)

scripted([err(0),err(0),err(0)])
timeout=adapter.enrich({"email":"normalized@example.com"})
check("ENRICH-006 timeout retry",timeout.get("error_type")=="timeout" and timeout.get("retry_count")==2 and waits==[5,15])

scripted([err(500),ok({"enrichment_status":"success","data":{}})])
temporary=adapter.enrich({"email":"normalized@example.com"})
check("ENRICH-007 5xx temporary",temporary.get("success") and temporary.get("retry_count")==1)

for name,status,error_type in (("ENRICH-008 permanent 400",400,"validation_error"),("ENRICH-009 permanent 401",401,"authentication_error"),("ENRICH-010 permanent 403",403,"authorization_error")):
 scripted([err(status)]); result=adapter.enrich({"email":"normalized@example.com"}); check(name,result.get("error_type")==error_type and result.get("retry_count")==0)

scripted([err(429,{"Retry-After":"7"}),err(429,{"Retry-After":"7"}),err(429,{"Retry-After":"7"})])
rate_failed=adapter.enrich({"email":"normalized@example.com"})
check("ERROR-001 canonical Retry-After",rate_failed["error"]=={"type":"rate_limit","code":"http_429","http_status":429,"retry_after_seconds":7.0,"ambiguous":False,"message":"upstream dependency failed"})
check("ERROR-002 no secrets or PII",all(value not in str(rate_failed) for value in ("normalized@example.com","secret","token")))

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
