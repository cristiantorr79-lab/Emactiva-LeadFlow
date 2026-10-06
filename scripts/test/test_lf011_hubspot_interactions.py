"""Focused synthetic evidence for LAB-LF-011 HubSpot Ticket interactions."""
from pathlib import Path
import importlib.util,sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("lf011_adapter",ROOT/"adapters"/"server.py")
adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
KEY="a"*64+":crm_interaction"; MESSAGE="private-message-lf011"; INTEREST="private-interest-lf011"
checks={}; calls=[]; waits=[]

def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
def configure(attempts=3):
 adapter.CONFIG={"attempts":attempts,"delay1":5,"delay2":15,"timeout_ms":100,"crm_provider":"hubspot","crm":"https://hub.test","crm_api_key":"synthetic-secret","capabilities":adapter.HUBSPOT_CAPABILITIES.copy(),"hubspot_interaction_properties":{"key":"leadflow_interaction_key","message":"content","interest":"leadflow_interest"},"hubspot_ticket_pipeline_id":"pipeline-7","hubspot_ticket_stage_id":"stage-9"}
 calls.clear(); waits.clear()
def scripted(items):
 sequence=list(items); calls.clear(); waits.clear()
 def fake(method,url,body=None,headers=None):
  calls.append((method,url,body,headers or {})); item=sequence.pop(0)
  return item(method,url,body,headers or {}) if callable(item) else item
 adapter.call=fake
def ok(body=None,status=200): return status,{},body or {}
def err(status,headers=None): return status,headers or {},{}
def search(ticket_id=None): return ok({"results":[] if ticket_id is None else [{"id":ticket_id,"properties":{"leadflow_interaction_key":KEY}}]})
def payload(): return {"contact_id":"contact-42","operation_key":KEY,"interaction":{"message":MESSAGE,"interest":INTEREST}}
adapter.wait=lambda headers,status,attempt: waits.append((status,attempt))

configure(); check("LF011-A HubSpot interaction capabilities",all(adapter.CONFIG["capabilities"][name] for name in ("interaction_write","interaction_idempotency","interaction_reconciliation")))
scripted([search(),ok({"id":"ticket-1"},201),ok()]); created=adapter.record_interaction(payload())
ticket_create=calls[1]; properties=ticket_create[2]["properties"]
check("LF011-B creates Ticket with operation key",created.get("success") and created.get("interaction_id")=="ticket-1" and properties["leadflow_interaction_key"]==KEY)
check("LF011-C configured pipeline and stage",properties["hs_pipeline"]=="pipeline-7" and properties["hs_pipeline_stage"]=="stage-9")
check("LF011-D associates exact contact id",calls[2][0]=="PUT" and calls[2][1].endswith("/tickets/ticket-1/associations/default/contacts/contact-42"))
check("LF011-E minimized property mapping",set(properties)=={"leadflow_interaction_key","hs_pipeline","hs_pipeline_stage","subject","content","leadflow_interest"} and properties["content"]==MESSAGE and properties["leadflow_interest"]==INTEREST)

scripted([search("ticket-1"),ok()]); reused=adapter.record_interaction(payload())
check("LF011-F same key reused without CREATE",reused.get("resolution")=="reused" and reused.get("interaction_id")=="ticket-1" and not any(method=="POST" and url.endswith("/tickets") for method,url,_,_ in calls))
scripted([search(),err(409),search("ticket-409"),ok()]); conflict=adapter.record_interaction(payload())
check("LF011-G unique conflict reconciled",conflict.get("success") and conflict.get("interaction_id")=="ticket-409" and len([c for c in calls if c[1].endswith("/tickets")])==1)
scripted([search(),err(0),search("ticket-timeout"),ok()]); ambiguous=adapter.record_interaction(payload())
check("LF011-H ambiguous create reconciled before repeat",ambiguous.get("success") and ambiguous.get("interaction_id")=="ticket-timeout" and len([c for c in calls if c[1].endswith("/tickets")])==1)

scripted([search("ticket-r")]); found=adapter.reconcile_interaction({"operation_key":KEY})
check("LF011-I reconciliation found",found=={"success":True,"found":True,"absence_conclusive":True,"interaction_id":"ticket-r","retry_count":0})
scripted([search()]); absent=adapter.reconcile_interaction({"operation_key":KEY})
check("LF011-J conclusive absence",absent.get("success") and not absent["found"] and absent["absence_conclusive"] and absent["interaction_id"] is None)
configure(1); scripted([err(0)]); lookup_failure=adapter.reconcile_interaction({"operation_key":KEY})
check("LF011-K lookup failure not conclusive",not lookup_failure.get("success") and lookup_failure.get("absence_conclusive") is not True)
for label,status,kind in (("401",401,"authentication_error"),("403",403,"authorization_error")):
 scripted([err(status)]); result=adapter.record_interaction(payload()); check("LF011-L "+label+" terminal",result.get("error_type")==kind and result.get("retry_count")==0)
configure(); scripted([err(429,{"Retry-After":"1"}),search("ticket-rate"),ok()]); rate=adapter.record_interaction(payload())
scripted([err(500),search("ticket-5xx"),ok()]); server_error=adapter.record_interaction(payload())
check("LF011-M 429 and 5xx temporary policy",rate.get("success") and rate.get("retry_count")==1 and server_error.get("success") and server_error.get("retry_count")==1)
check("LF011-N canonical output is sanitized",all(secret not in str(created)+str(reused)+str(conflict)+str(lookup_failure) for secret in (MESSAGE,INTEREST,"synthetic-secret")) and set(created)=={"success","interaction_id","resolution","retry_count"})
check("LF011-O neutral contract",set(created)=={"success","interaction_id","resolution","retry_count"} and "ticket_id" not in created)

base={"APP_ENV":"development","CRM_PROVIDER":"hubspot","ENRICHMENT_PROVIDER":"mock","CRM_UPSTREAM_URL":"https://hub.test","ENRICHMENT_UPSTREAM_URL":"http://enrichment.test","ALERT_UPSTREAM_URL":"http://alert.test","CRM_API_KEY":"x","ADAPTER_SERVICE_KEY":"a"*32,"ADAPTER_ALLOWED_OPERATIONS":"crm.process","HUBSPOT_TICKET_PIPELINE_ID":"pipeline","HUBSPOT_TICKET_STAGE_ID":"stage","HUBSPOT_TICKET_INTEREST_PROPERTY":"leadflow_interest"}
for missing in ("HUBSPOT_TICKET_PIPELINE_ID","HUBSPOT_TICKET_STAGE_ID","HUBSPOT_TICKET_INTEREST_PROPERTY"):
 try: adapter.load_config({key:value for key,value in base.items() if key!=missing}); rejected=False
 except ValueError: rejected=True
 check("LF011-CONFIG missing "+missing,rejected)

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
