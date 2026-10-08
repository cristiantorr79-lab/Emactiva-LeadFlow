"""Focused sanitized phase diagnostics for the LF012 real-runner interaction setup."""
from pathlib import Path
import importlib.util,sys

ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
adapter=load("lf012_diag_adapter",Path("adapters/server.py")); runner=load("lf012_diag_runner",Path("scripts/test/test_lf012_real_hubspot_delete_opt_in.py"))
SECRET="synthetic-provider-secret"; MESSAGE="private-message"; INTEREST="private-interest"; KEY="technical-operation-key"; checks={}; calls=[]
adapter.CONFIG={"attempts":1,"delay1":1,"delay2":1,"timeout_ms":100,"crm_provider":"hubspot","crm":"https://hub.test","crm_api_key":SECRET,"capabilities":adapter.HUBSPOT_CAPABILITIES.copy(),"hubspot_interaction_properties":{"key":"leadflow_interaction_key","message":"content","interest":"leadflow_interest"},"hubspot_ticket_pipeline_id":"pipeline","hubspot_ticket_stage_id":"stage"}
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
def scripted(items):
 sequence=list(items); calls.clear()
 def fake(method,url,body=None,headers=None): calls.append((method,url,body,headers or {})); return sequence.pop(0)
 adapter.call=fake
def ok(body=None,status=200): return status,{},body or {}
def err(status): return status,{},{}
def search(ticket=None): return ok({"results":[] if ticket is None else [{"id":ticket,"properties":{"leadflow_interaction_key":KEY}}]})
def payload(): return {"contact_id":"contact-technical","operation_key":KEY,"interaction":{"message":MESSAGE,"interest":INTEREST}}

scripted([err(401)]); lookup=adapter.record_interaction(payload())
check("LF012-I lookup failure phase",lookup.get("diagnostic_phase")=="interaction_lookup" and lookup.get("http_status")==401)

scripted([search(),err(400)]); create=adapter.record_interaction(payload())
check("LF012-I create failure phase",create.get("diagnostic_phase")=="interaction_create" and create.get("http_status")==400)

scripted([search("ticket-1"),err(400)]); association=adapter.record_interaction(payload())
check("LF012-I association failure phase",association.get("diagnostic_phase")=="interaction_association" and association.get("http_status")==400)

scripted([ok({"results":"invalid"})]); invalid=adapter.record_interaction(payload())
check("LF012-I invalid response phase",invalid.get("diagnostic_phase")=="interaction_invalid_response" and invalid.get("error_code")=="invalid_response")

scripted([search(),ok({"id":"ticket-1"},201),ok(status=204)]); success=adapter.record_interaction(payload())
check("LF012-I success contract unchanged",success=={"success":True,"interaction_id":"ticket-1","resolution":"created","retry_count":0})

diagnostic=runner.sanitized_interaction_diagnostic({**association,"contact_id":"contact-private","payload":{"message":MESSAGE},"error_message":MESSAGE,"secret":SECRET})
serialized=str(diagnostic)
check("LF012-I runner diagnostic is allowlisted",set(diagnostic)=={"phase","http_status","error_code","retry_count","ambiguous","result_code"})
check("LF012-I diagnostic excludes PII and secrets",all(value not in serialized for value in (MESSAGE,INTEREST,SECRET,"contact-private",KEY)))

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
