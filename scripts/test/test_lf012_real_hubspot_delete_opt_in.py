"""Explicitly gated real HubSpot DSR DELETE E2E runner. Destructive; never run by default."""
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
import json,os,re,subprocess,sys,uuid

ROOT=Path(__file__).resolve().parents[2]
REQUIRED=("REAL_PROVIDER_ADAPTER_URL","REAL_DSR_DELETE_TEST_EMAIL","ADAPTER_SERVICE_KEY","DSR_ADAPTER_SERVICE_KEY","DSR_SUBJECT_KEY","POSTGRES_MIGRATOR_USER","POSTGRES_MIGRATOR_PASSWORD","POSTGRES_DB")
INTERACTION_PHASES={"interaction_lookup","interaction_create","interaction_association","interaction_invalid_response"}

def sanitized_interaction_diagnostic(result):
 phase=result.get("diagnostic_phase") if isinstance(result,dict) else None
 if phase not in INTERACTION_PHASES: phase="interaction_invalid_response"
 code=result.get("error_code") if isinstance(result,dict) else None
 if not isinstance(code,str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}",code): code="external_error"
 status=result.get("http_status") if isinstance(result,dict) else None
 status=status if isinstance(status,int) and 0<=status<=599 else None
 retries=result.get("retry_count") if isinstance(result,dict) else None
 retries=retries if isinstance(retries,int) and 0<=retries<=99 else 0
 ambiguous=result.get("ambiguous") is True if isinstance(result,dict) else False
 result_code=phase+"_failed" if phase!="interaction_invalid_response" else "interaction_invalid_response"
 return {"phase":phase,"http_status":status,"error_code":code,"retry_count":retries,"ambiguous":ambiguous,"result_code":result_code}

def preflight_absent(post,request_id,email):
 status,result=post("/crm/dsr-locate",{"request_id":request_id,"verified_email":email})
 conclusive=status==200 and result.get("success") is True and result.get("found") is False and result.get("contact_count")==0 and result.get("interaction_count")==0
 return conclusive,"preflight_absent" if conclusive else "preflight_subject_not_conclusively_absent"

def valid_predelete_inventory(status,inventory):
 return status==200 and isinstance(inventory,dict) and inventory.get("success") is True and inventory.get("found") is True and inventory.get("interaction_count")==1

def valid_admin_delete_result(admin_status,admin):
 if admin_status!=0 or not isinstance(admin,dict) or admin.get("provider_status")!="completed": return False
 resolution=admin.get("resolution")
 if resolution=="deleted": return admin.get("interaction_count")==1
 if resolution=="already_absent": return admin.get("found") is False and admin.get("interaction_count")==0
 if resolution=="reconciled_absent":
  return admin.get("provider_result_code")=="reconciled_absent" and admin.get("reconciled") is True and admin.get("found") is False and admin.get("interaction_count")==0
 return False

def run_admin_to_safe_terminal(run_admin):
 admin_status,admin=run_admin()
 if valid_admin_delete_result(admin_status,admin): return True,admin_status,admin
 reconciliable=isinstance(admin,dict) and admin.get("provider_status")=="failed" and admin.get("provider_result_code")=="contact_deletion_ambiguous"
 if not reconciliable: return False,admin_status,admin
 reconciled_status,reconciled=run_admin()
 return valid_admin_delete_result(reconciled_status,reconciled),reconciled_status,reconciled

def main(env=os.environ):
 if env.get("RUN_REAL_DSR_DELETE_TESTS")!="1": print("RESULT: NOT_RUN; code=real_dsr_delete_opt_in_disabled"); return 0
 if env.get("ALLOW_REAL_HUBSPOT_DELETE")!="1" or any(not env.get(name) for name in REQUIRED): print("RESULT: BLOCKED; code=real_dsr_delete_gate_incomplete"); return 2
 base=env["REAL_PROVIDER_ADAPTER_URL"].rstrip("/"); email=env["REAL_DSR_DELETE_TEST_EMAIL"].strip().lower(); normal_key=env["ADAPTER_SERVICE_KEY"]; destructive_key=env["DSR_ADAPTER_SERVICE_KEY"]
 try: parsed=urlsplit(base)
 except ValueError: parsed=None
 invalid=not parsed or parsed.scheme not in {"http","https"} or not parsed.netloc or len(normal_key)<32 or len(destructive_key)<32 or len(env["DSR_SUBJECT_KEY"])<32 or len(email)>320 or email.count("@")!=1 or any(ord(char)<33 or ord(char)>126 for char in email)
 if invalid or normal_key==destructive_key: print("RESULT: BLOCKED; code=real_dsr_delete_configuration_invalid"); return 2

 run_id=uuid.uuid4().hex; request_id="lf012-real-delete-"+run_id; preflight_id="lf012-real-preflight-"+run_id; operation_key="lf012-real-contact-"+run_id; interaction_key="lf012-real-interaction-"+run_id
 message="LF012 synthetic controlled deletion message "+run_id; interest="lf012-synthetic-delete"; operator_id="lf012_real_delete_operator"; approver_id="lf012_real_delete_approver"
 created=False; absence=False
 def adapter_post(path,payload):
  raw=json.dumps(payload,separators=(",",":")).encode(); headers={"Content-Type":"application/json","X-LeadFlow-Adapter-Key":normal_key}
  try:
   with urlopen(Request(base+path,data=raw,method="POST",headers=headers),timeout=60) as response:
    body=json.loads(response.read() or b"{}"); return response.status,body if isinstance(body,dict) else {}
  except HTTPError as error:
   try: body=json.loads(error.read() or b"{}")
   except Exception: body={}
   return error.code,body if isinstance(body,dict) else {}
  except (URLError,TimeoutError,ValueError,json.JSONDecodeError): return 0,{}
 def run_admin():
  payload={"request_id":request_id,"action":"delete","verified_email":email,"operator_id":operator_id,"approver_id":approver_id}; child_env=env.copy(); child_env["CRM_ADAPTER_URL"]=base
  result=subprocess.run([sys.executable,str(ROOT/"scripts"/"admin"/"dsr_admin.py")],cwd=ROOT,input=json.dumps(payload,separators=(",",":")),text=True,capture_output=True,env=child_env,timeout=180)
  try: body=json.loads(result.stdout) if result.stdout else {}
  except json.JSONDecodeError: body={}
  return result.returncode,body if isinstance(body,dict) else {}
 def database(sql):
  command=["docker","compose","exec","-T","postgres","sh","-c",'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql -h 127.0.0.1 -X -q -v ON_ERROR_STOP=1 -U "$1" -d "$2" -At',"sh",env["POSTGRES_MIGRATOR_USER"],env["POSTGRES_DB"]]
  result=subprocess.run(command,cwd=ROOT,input=env["POSTGRES_MIGRATOR_PASSWORD"]+"\n"+sql+"\n",text=True,capture_output=True,timeout=60); return result.returncode,result.stdout.strip()
 def q(value): return "'"+str(value).replace("'","''")+"'"
 def reconcile_absence():
  locate_status,located=adapter_post("/crm/dsr-locate",{"request_id":request_id,"verified_email":email}); ticket_status,ticket=adapter_post("/crm/reconcile-interaction",{"operation_key":interaction_key})
  return locate_status==200 and located.get("success") is True and located.get("found") is False and ticket_status==200 and ticket.get("success") is True and ticket.get("found") is False

 preflight_ok,_=preflight_absent(adapter_post,preflight_id,email)
 if not preflight_ok: print("RESULT: BLOCKED; code=preflight_subject_not_conclusively_absent"); return 2
 passed=False; failure_code="real_dsr_delete_unexpected_failure"; interaction_diagnostic=None
 try:
  status,contact=adapter_post("/crm/process",{"email":email,"lead":{"email":email,"first_name":"LF012","last_name":"Synthetic","company":"LF012 controlled destructive QA"},"present_fields":{"first_name":"LF012","last_name":"Synthetic","company":"LF012 controlled destructive QA"},"operation_key":operation_key})
  if status!=200 or contact.get("success") is not True or not isinstance(contact.get("contact_id"),str): failure_code="synthetic_contact_setup_failed"; raise RuntimeError
  created=True; contact_id=contact["contact_id"]
  status,interaction=adapter_post("/crm/record-interaction",{"contact_id":contact_id,"operation_key":interaction_key,"interaction":{"message":message,"interest":interest}})
  if status!=200 or interaction.get("success") is not True:
   interaction_diagnostic=sanitized_interaction_diagnostic(interaction); failure_code=interaction_diagnostic["result_code"]; raise RuntimeError
  status,reconciled=adapter_post("/crm/reconcile-interaction",{"operation_key":interaction_key})
  if status!=200 or reconciled.get("success") is not True or reconciled.get("found") is not True: failure_code="synthetic_interaction_confirmation_failed"; raise RuntimeError
  status,inventory=adapter_post("/crm/dsr-locate",{"request_id":request_id,"verified_email":email})
  if not valid_predelete_inventory(status,inventory): failure_code="synthetic_scope_not_isolated"; raise RuntimeError
  admin_ok,admin_status,admin=run_admin_to_safe_terminal(run_admin)
  if not admin_ok: failure_code="dsr_admin_delete_failed"; raise RuntimeError
  absence=reconcile_absence()
  if not absence: failure_code="destructive_absence_not_reconciled"; raise RuntimeError
  db_status,provider=database(f"SELECT status||'|'||result_code FROM leadflow.dsr_provider_actions WHERE request_id={q(request_id)} AND provider='hubspot' AND action='delete';")
  if db_status!=0 or not provider.startswith("completed|"): failure_code="provider_action_not_closed"; raise RuntimeError
  admin_repeat_status,admin_repeat=run_admin()
  if admin_repeat_status!=0 or admin_repeat.get("provider_status")!="completed": failure_code="destructive_repetition_not_idempotent"; raise RuntimeError
  db_status,evidence=database(f"SELECT row_to_json(e)::text FROM (SELECT r.*,json_agg(a ORDER BY a.provider) actions FROM leadflow.dsr_requests r JOIN leadflow.dsr_provider_actions a USING(request_id) WHERE r.request_id={q(request_id)} GROUP BY r.request_id) e;")
  forbidden=(email,message,interest,"verified_email","payload",normal_key,destructive_key,env["DSR_SUBJECT_KEY"],env["POSTGRES_MIGRATOR_PASSWORD"])
  if db_status!=0 or any(value and value in evidence for value in forbidden): failure_code="persistent_evidence_not_minimized"; raise RuntimeError
  passed=True
 except Exception: pass
 finally:
  if created and not absence:
   try: run_admin(); absence=reconcile_absence()
   except Exception: absence=False
 if passed and absence: print("REAL-DSR-DELETE: PASS; ticket_archive=warn"); print("RESULT: PASS"); return 0
 if interaction_diagnostic:
  print("INTERACTION-DIAGNOSTIC: phase={phase} http_status={http_status} error_code={error_code} retry_count={retry_count} ambiguous={ambiguous}".format(**interaction_diagnostic))
 if created and not absence: print("RESULT: FAIL; code=synthetic_cleanup_not_verified")
 else: print("RESULT: FAIL; code="+(failure_code if re.fullmatch(r"[a-z][a-z0-9_]{0,99}",failure_code) else "real_dsr_delete_failed"))
 return 1

if __name__=="__main__": sys.exit(main())
