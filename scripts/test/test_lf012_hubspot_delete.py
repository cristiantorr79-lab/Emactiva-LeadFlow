"""Mock-only destructive Adapter regression for LAB-LF-012 ticket #7."""
from contextlib import redirect_stderr,redirect_stdout
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import importlib.util,json,sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("lf012_delete_adapter",ROOT/"adapters"/"server.py")
adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
NORMAL="normal-service-key-with-at-least-32-chars"
DESTRUCTIVE="destructive-service-key-at-least-32-chars"
EMAIL="delete-private@example.test"; MESSAGE="private-message"; INTEREST="private-interest"
checks={}; calls=[]
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
def configure():
 adapter.CONFIG={"attempts":1,"delay1":1,"delay2":1,"timeout_ms":100,"crm_provider":"hubspot","crm":"https://hub.test","crm_api_key":"provider-secret","service_key":NORMAL,"destructive_service_key":DESTRUCTIVE,"allowed_operations":set(),"hubspot_enrichment_properties":{"industry":"industry","company_size":"leadflow_company_size","website":"website"},"hubspot_interaction_properties":{"key":"leadflow_interaction_key","message":"content","interest":"leadflow_interest"}}
 calls.clear()
def scripted(items):
 sequence=list(items); calls.clear()
 def fake(method,url,body=None,headers=None): calls.append((method,url,body,headers or {})); return sequence.pop(0)
 adapter.call=fake
def ok(body=None,status=200): return status,{},body or {}
def contact(count=1): return ok({"results":[{"id":"contact-7","properties":{"email":EMAIL}} for _ in range(count)]})
def associations(paging=False): return ok({"results":[{"toObjectId":"ticket-lf"},{"toObjectId":"ticket-other"}],**({"paging":{"next":{"after":"2"}}} if paging else {})})
def tickets(): return ok({"results":[{"id":"ticket-lf","properties":{"leadflow_interaction_key":"key-1","content":MESSAGE,"leadflow_interest":INTEREST}},{"id":"ticket-other","properties":{"leadflow_interaction_key":"","content":"unowned"}}]})
payload={"request_id":"dsr-delete-7","verified_email":EMAIL}

configure(); scripted([contact(),associations(),tickets(),ok(status=204),ok(status=404),ok(status=204),ok({"results":[]})]); deleted=adapter.dsr_delete(payload)
check("LF012-D delete present contact",deleted.get("success") and deleted.get("resolution")=="deleted" and deleted.get("reconciled"))
check("LF012-D only LeadFlow ticket archived",len([c for c in calls if c[0]=="DELETE"] )==1 and calls[3][1].endswith("/tickets/ticket-lf") and all("ticket-other" not in c[1] for c in calls if c[0]=="DELETE"))
check("LF012-D privacy delete uses contact id",calls[5][0]=="POST" and calls[5][1].endswith("/contact/gdpr-delete") and calls[5][2]=={"objectId":"contact-7"} and EMAIL not in calls[5][1]+str(calls[5][2]))
check("LF012-D conclusive post-delete reads",calls[4][0]=="GET" and calls[6][0]=="POST" and deleted.get("interaction_count")==1)

scripted([ok({"results":[]})]); absent=adapter.dsr_delete(payload)
check("LF012-D already absent idempotent",absent.get("success") and absent.get("resolution")=="already_absent" and len(calls)==1)
scripted([contact(2)]); ambiguous=adapter.dsr_delete(payload)
check("LF012-D duplicate contacts fail closed",ambiguous.get("error_code")=="subject_ambiguous" and len(calls)==1)
invalid=adapter.dsr_delete({"request_id":"bad id","verified_email":EMAIL})
check("LF012-D invalid request rejected",invalid.get("error_code")=="dsr_request_invalid")
scripted([contact(),associations(True)]); paged=adapter.dsr_delete(payload)
check("LF012-D paging fail closed before writes",paged.get("error_code")=="ticket_inventory_incomplete" and not any(c[0] in {"DELETE","PATCH"} or c[1].endswith("gdpr-delete") for c in calls))

scripted([contact(),associations(),tickets(),(0,{},{}),ok(status=404),ok(status=204),ok({"results":[]})]); timeout_ticket=adapter.dsr_delete(payload)
check("LF012-D ambiguous ticket reconciled before any repeat",timeout_ticket.get("success") and len([c for c in calls if c[0]=="DELETE" and c[1].endswith("ticket-lf")])==1 and calls[4][0]=="GET")
scripted([contact(),associations(),tickets(),ok(status=204),ok(status=404),(0,{},{}),ok({"results":[]})]); timeout_contact=adapter.dsr_delete(payload)
check("LF012-D ambiguous contact reconciled before repeat",timeout_contact.get("success") and len([c for c in calls if c[1].endswith("gdpr-delete")])==1)

def post(base,key_header,key):
 headers={"Content-Type":"application/json"}
 if key_header: headers[key_header]=key
 try:
  with urlopen(Request(base+"/crm/dsr-delete",data=json.dumps(payload).encode(),method="POST",headers=headers),timeout=3) as response: return response.status,json.loads(response.read())
 except HTTPError as error: return error.code,json.loads(error.read())
configure(); adapter.call=lambda *args,**kwargs: ok({"results":[]})
server=ThreadingHTTPServer(("127.0.0.1",0),adapter.Handler); thread=Thread(target=server.serve_forever,daemon=True); out,err=StringIO(),StringIO()
try:
 with redirect_stdout(out),redirect_stderr(err):
  thread.start(); base=f"http://127.0.0.1:{server.server_port}"
  missing=post(base,None,None); normal=post(base,"X-LeadFlow-Adapter-Key",NORMAL); wrong=post(base,"X-LeadFlow-DSR-Adapter-Key","wrong"); valid=post(base,"X-LeadFlow-DSR-Adapter-Key",DESTRUCTIVE)
  adapter.CONFIG["destructive_service_key"]=""; unconfigured=post(base,"X-LeadFlow-DSR-Adapter-Key",DESTRUCTIVE)
finally: server.shutdown(); server.server_close(); thread.join(timeout=3)
check("LF012-D destructive key missing rejected",missing[0]==401)
check("LF012-D normal key cannot delete",normal[0]==401)
check("LF012-D invalid destructive key rejected",wrong[0]==401)
check("LF012-D valid destructive key allowed",valid[0]==200 and valid[1].get("resolution")=="already_absent")
check("LF012-D unconfigured destructive identity fails closed",unconfigured[0]==401)
captured=out.getvalue()+err.getvalue()+str((ambiguous,invalid,missing,normal,wrong))
check("LF012-D secrets and PII absent from logs/errors",all(value not in captured for value in (EMAIL,NORMAL,DESTRUCTIVE,"provider-secret",MESSAGE,INTEREST)))
check("LF012-D no fictitious restrict operation","crm.dsr_restrict" not in adapter.ADAPTER_OPERATIONS)
base_config={"APP_ENV":"development","ADAPTER_SERVICE_KEY":"a"*32,"ADAPTER_ALLOWED_OPERATIONS":"crm.process"}
try: adapter.load_config({**base_config,"DSR_ADAPTER_SERVICE_KEY":"a"*32}); equal_closed=False
except ValueError as error: equal_closed=str(error)=="adapter identities must be distinct"
check("LF012-D equal normal and destructive keys fail closed",equal_closed)
distinct=adapter.load_config({**base_config,"DSR_ADAPTER_SERVICE_KEY":"d"*32})
check("LF012-D distinct adapter identities accepted",distinct.get("destructive_service_key")=="d"*32)

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
