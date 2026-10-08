"""Focused mock-only evidence for LAB-LF-012 HubSpot non-destructive DSR."""
from contextlib import redirect_stderr,redirect_stdout
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import importlib.util,json,sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("lf012_adapter",ROOT/"adapters"/"server.py")
adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
KEY="k"*40; EMAIL="private.person@example.test"; SECRET="synthetic-provider-secret"
checks={}; calls=[]
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
def configure(allowed=None):
 adapter.CONFIG={"attempts":1,"delay1":1,"delay2":1,"timeout_ms":100,"crm_provider":"hubspot","crm":"https://hub.test","crm_api_key":SECRET,"allowed_operations":set(allowed or {"crm.dsr_locate","crm.dsr_export","crm.dsr_correct"}),"service_key":KEY,"hubspot_enrichment_properties":{"industry":"industry","company_size":"leadflow_company_size","website":"website"},"hubspot_interaction_properties":{"key":"leadflow_interaction_key","message":"content","interest":"leadflow_interest"}}
 calls.clear()
def scripted(items):
 sequence=list(items); calls.clear()
 def fake(method,url,body=None,headers=None): calls.append((method,url,body,headers or {})); return sequence.pop(0)
 adapter.call=fake
def ok(body=None,status=200): return status,{},body or {}
def contact(properties=None,items=1):
 row={"id":"contact-7","properties":properties or {"email":EMAIL}}
 return ok({"results":([row]*items)})
def assoc(ids=("ticket-lf","ticket-other")): return ok({"results":[{"toObjectId":item} for item in ids]})
def tickets(export=False):
 lead={"id":"ticket-lf","properties":{"leadflow_interaction_key":"key-1","leadflow_interest":"interest-private","content":"message-private"}}
 other={"id":"ticket-other","properties":{"leadflow_interaction_key":""}}
 return ok({"results":[lead,other]})
base={"request_id":"dsr-12","verified_email":EMAIL}

configure(); scripted([contact(),assoc(),tickets()]); located=adapter.dsr_locate(base)
check("LF012 locate existing",located.get("success") and located.get("found") and located.get("contact_count")==1)
check("LF012 locate only LeadFlow interactions",located.get("interaction_count")==1 and set(located)-{"success","request_id","found","contact_count","interaction_count","technical_reference"}==set())
scripted([ok({"results":[]})]); missing=adapter.dsr_locate(base)
check("LF012 locate not found",missing.get("success") and not missing.get("found") and missing.get("interaction_count")==0)
scripted([contact(items=2)]); ambiguous=adapter.dsr_locate(base)
check("LF012 multiple contacts controlled",not ambiguous.get("success") and ambiguous.get("error_code")=="subject_ambiguous" and EMAIL not in str(ambiguous))
invalid=adapter.dsr_locate({"request_id":"bad id","verified_email":EMAIL})
check("LF012 invalid identity rejected",not invalid.get("success") and invalid.get("error_code")=="dsr_request_invalid")

properties={"email":EMAIL,"firstname":"Private","lastname":"Person","phone":"+000","company":"PrivateCo","industry":"software","leadflow_company_size":"10","website":"https://example.test","unapproved":"hidden"}
scripted([contact(properties),assoc(),tickets(True)]); exported=adapter.dsr_locate(base,True)
allowed_contact={"email","first_name","last_name","phone","company","industry","company_size","website"}
check("LF012 export contact allowlist",set(exported["export"]["contact"])==allowed_contact and "unapproved" not in str(exported["export"]))
check("LF012 export LeadFlow interaction allowlist",exported["export"]["interactions"]==[{"reference":"ticket-lf","interest":"interest-private","message":"message-private"}])
check("LF012 export absent from technical evidence",set(exported)-{"export"}=={"success","request_id","found","contact_count","interaction_count","technical_reference"})

correction={**base,"corrections":{"first_name":"Corrected","company":"CorrectedCo"}}
scripted([contact(),ok(),ok({"properties":{"firstname":"Corrected","company":"CorrectedCo"}})]); corrected=adapter.dsr_correct(correction)
patch=calls[1][2]["properties"]
check("LF012 correct allowlist",corrected.get("success") and patch=={"firstname":"Corrected","company":"CorrectedCo"})
check("LF012 correct reconciled",corrected.get("reconciled") is True and calls[2][0]=="GET")
check("LF012 correct rejects email",adapter.dsr_correct({**base,"corrections":{"email":"other@example.test"}}).get("error_code")=="dsr_request_invalid")
scripted([contact(),ok(),ok({"properties":{"firstname":"Corrected","company":"CorrectedCo"}})]); repeated=adapter.dsr_correct(correction)
check("LF012 repeated correction idempotent",repeated.get("success") and repeated.get("corrected_count")==2)
scripted([contact(),(0,{},{}),ok({"properties":{"firstname":"Corrected","company":"CorrectedCo"}})]); reconciled=adapter.dsr_correct(correction)
check("LF012 ambiguous write reconciled by read",reconciled.get("success") and reconciled.get("reconciled"))

def post(base_url,path,key,payload):
 try:
  with urlopen(Request(base_url+path,data=json.dumps(payload).encode(),method="POST",headers={"Content-Type":"application/json",**({"X-LeadFlow-Adapter-Key":key} if key else {})}),timeout=3) as response: return response.status,json.loads(response.read())
 except HTTPError as error: return error.code,json.loads(error.read())
configure({"crm.dsr_locate"}); adapter.call=lambda *args,**kwargs: ok({"results":[]})
server=ThreadingHTTPServer(("127.0.0.1",0),adapter.Handler); thread=Thread(target=server.serve_forever,daemon=True); out,err=StringIO(),StringIO()
try:
 with redirect_stdout(out),redirect_stderr(err):
  thread.start(); url=f"http://127.0.0.1:{server.server_port}"
  absent=post(url,"/crm/dsr-locate",None,base); allowed=post(url,"/crm/dsr-locate",KEY,base); forbidden=post(url,"/crm/dsr-export",KEY,base)
finally: server.shutdown(); server.server_close(); thread.join(timeout=3)
check("LF012 authorization fail closed",absent[0]==401 and absent[1]["error"]["code"]=="adapter_identity_invalid")
check("LF012 three operations in contract",{"crm.dsr_locate","crm.dsr_export","crm.dsr_correct"}<=adapter.ADAPTER_OPERATIONS)
check("LF012 operation forbidden 403",forbidden[0]==403 and forbidden[1]["error"]["code"]=="adapter_operation_forbidden")
check("LF012 allowed operation works",allowed[0]==200 and allowed[1].get("success"))
captured=out.getvalue()+err.getvalue()+str((located,missing,ambiguous,corrected,reconciled,absent,forbidden))
check("LF012 logs and errors sanitized",all(value not in captured for value in (EMAIL,SECRET,"PrivateCo","message-private","interest-private")))

migration=(ROOT/"database/migrations/022_dsr_hubspot_nondestructive.sql").read_text()
admin=(ROOT/"scripts/admin/dsr_admin.py").read_text()
check("LF012 provider action can close",("record_dsr_provider_result" in admin and "'completed' if success else 'failed'" in admin and "'hubspot','correct','pending'" in migration))
check("LF012 annotate external N/A",("administrative_local_only" in admin and "provider_status=\"not_applicable\"" in admin))
check("LF012 export not persisted",("adapter_result[\"export\"]" not in admin and "dsr_provider_actions" not in adapter.__dict__))

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
