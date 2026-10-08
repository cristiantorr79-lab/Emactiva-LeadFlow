"""Separate administrative DSR entrypoint; reads verified requests from stdin."""
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import hashlib, hmac, json, os, re, subprocess, sys
try:
 from dsr_delete_state import coordinate_delete_state
except ModuleNotFoundError:
 sys.path.insert(0,str(Path(__file__).resolve().parent)); from dsr_delete_state import coordinate_delete_state

ROOT=Path(__file__).resolve().parents[2]
TECH=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
def fail(): print(json.dumps({"status":"failed","result_code":"dsr_request_invalid"})); raise SystemExit(1)
try: request=json.load(sys.stdin)
except Exception: fail()
email=str(request.get("verified_email","")).strip().lower(); secret=os.environ.get("DSR_SUBJECT_KEY","")
required=(request.get("request_id"),request.get("action"),request.get("operator_id"))
action=request.get("action"); corrections=request.get("corrections")
if len(secret)<32 or not email or "@" not in email or not all(isinstance(v,str) and TECH.fullmatch(v) for v in required): fail()
if action=="correct" and (not isinstance(corrections,dict) or not corrections): fail()
lead=hashlib.sha256(email.encode()).hexdigest(); token=hmac.new(secret.encode(),email.encode(),hashlib.sha256).hexdigest()
def q(value): return "NULL" if value is None else "'"+str(value).replace("'","''")+"'"
sql=f"SELECT * FROM leadflow.execute_dsr_request({q(request['request_id'])},{q(request['action'])},{q(lead)},{q(token)},{q(request['operator_id'])},{q(request.get('approver_id'))},{q(request.get('annotation_code'))});"
password=os.environ.get("POSTGRES_MIGRATOR_PASSWORD",""); user=os.environ.get("POSTGRES_MIGRATOR_USER",""); database=os.environ.get("POSTGRES_DB","")
if not password or not user or not database: fail()
command=["docker","compose","exec","-T","postgres","sh","-c",'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql -h 127.0.0.1 -X -q -v ON_ERROR_STOP=1 -U "$1" -d "$2" -At',"sh",user,database]
def database(statement):
 result=subprocess.run(command,cwd=ROOT,input=password+"\n"+statement+"\n",text=True,capture_output=True)
 if result.returncode: print(json.dumps({"status":"failed","result_code":"dsr_database_error"})); raise SystemExit(1)
 return result.stdout.strip()

parts=database(sql).split("|")
response={"request_id":parts[0],"status":parts[1],"local_status":parts[2],"result_code":parts[3],"matched_count":int(parts[4]),"deleted_count":int(parts[5])}
if response["local_status"]=="completed" and action=="annotate":
 recorded=database(f"SELECT * FROM leadflow.record_dsr_provider_result({q(request['request_id'])},'hubspot','annotate','not_applicable',{q(request['request_id']+':hubspot')},'administrative_local_only');").split("|")
 response.update(status=recorded[1],provider_status="not_applicable",provider_result_code=recorded[2])
elif response["local_status"] in {"completed","not_found"} and action in {"locate","export","correct"}:
 base=os.environ.get("CRM_ADAPTER_URL","").rstrip("/"); key=os.environ.get("ADAPTER_SERVICE_KEY","")
 if not base.startswith(("http://","https://")) or len(key)<32: fail()
 adapter_payload={"request_id":request["request_id"],"verified_email":email}
 if action=="correct": adapter_payload["corrections"]=corrections
 try:
  raw=json.dumps(adapter_payload,separators=(",",":")).encode()
  with urlopen(Request(base+"/crm/dsr-"+action,data=raw,method="POST",headers={"Content-Type":"application/json","X-LeadFlow-Adapter-Key":key}),timeout=max(1,int(os.environ.get("ADAPTER_CALL_TIMEOUT_MS","30000")))/1000) as upstream:
   adapter_result=json.loads(upstream.read())
 except (HTTPError,URLError,TimeoutError,ValueError,json.JSONDecodeError):
  adapter_result={"success":False,"error_code":"adapter_unavailable"}
 success=adapter_result.get("success") is True
 result_code=("subject_not_found" if success and not adapter_result.get("found") else "provider_completed") if success else str(adapter_result.get("error_code","provider_error"))
 if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}",result_code): result_code="provider_error"
 reference=str(adapter_result.get("technical_reference",request["request_id"]+":hubspot"))
 if not TECH.fullmatch(reference): reference=request["request_id"]+":hubspot"
 recorded=database(f"SELECT * FROM leadflow.record_dsr_provider_result({q(request['request_id'])},'hubspot',{q(action)},{q('completed' if success else 'failed')},{q(reference)},{q(result_code)});").split("|")
 response.update(status=recorded[1],provider_status="completed" if success else "failed",provider_result_code=recorded[2])
 for name in ("found","contact_count","interaction_count","corrected_count","reconciled","export"):
  if name in adapter_result: response[name]=adapter_result[name]
elif response["local_status"] in {"completed","not_found"} and action=="delete":
 state=database(f"SELECT a.status||'|'||a.result_code||'|'||a.technical_reference||'|'||(r.action='delete' AND r.approver_id IS NOT NULL AND r.approver_id<>r.operator_id)::text FROM leadflow.dsr_requests r JOIN leadflow.dsr_provider_actions a ON a.request_id=r.request_id AND a.provider='hubspot' AND a.action='delete' WHERE r.request_id={q(request['request_id'])};").split("|")
 status_code=state[0] if len(state)==4 else "invalid"; prior_code=state[1] if len(state)==4 else ""; reference=state[2] if len(state)==4 and TECH.fullmatch(state[2]) else request["request_id"]+":hubspot"; approved=len(state)==4 and state[3]=="true"
 base=os.environ.get("CRM_ADAPTER_URL","").rstrip("/"); normal_key=os.environ.get("ADAPTER_SERVICE_KEY","")
 def locate_for_reconciliation():
  if not base.startswith(("http://","https://")) or len(normal_key)<32: return {"success":False,"error_code":"adapter_identity_invalid"}
  try:
   raw=json.dumps({"request_id":request["request_id"],"verified_email":email},separators=(",",":")).encode()
   with urlopen(Request(base+"/crm/dsr-locate",data=raw,method="POST",headers={"Content-Type":"application/json","X-LeadFlow-Adapter-Key":normal_key}),timeout=max(1,int(os.environ.get("ADAPTER_CALL_TIMEOUT_MS","30000")))/1000) as upstream:
    value=json.loads(upstream.read()); return value if isinstance(value,dict) else {}
  except (HTTPError,URLError,TimeoutError,ValueError,json.JSONDecodeError): return {"success":False,"error_code":"adapter_unavailable"}
 def complete_reconciled_absence(): return database(f"SELECT * FROM leadflow.reconcile_dsr_delete_absent({q(request['request_id'])},{q(reference)});").split("|")
 decision,reconciled_record=coordinate_delete_state(status_code,prior_code,approved,locate_for_reconciliation,complete_reconciled_absence)
 if decision=="completed": response.update(provider_status="completed",provider_result_code=prior_code)
 elif decision=="reconciled_absent":
  response.update(status=reconciled_record[1],provider_status="completed",provider_result_code=reconciled_record[2],found=False,resolution="reconciled_absent",interaction_count=0,reconciled=True)
 elif decision in {"invalid","reconciliation_blocked"}:
  print(json.dumps({"status":"failed","result_code":"destructive_state_invalid" if decision=="invalid" else "destructive_reconciliation_inconclusive"})); raise SystemExit(1)
 elif decision=="delete":
  base=os.environ.get("CRM_ADAPTER_URL","").rstrip("/"); key=os.environ.get("DSR_ADAPTER_SERVICE_KEY","")
  if not base.startswith(("http://","https://")) or len(key)<32: print(json.dumps({"status":"failed","result_code":"destructive_identity_invalid"})); raise SystemExit(1)
  try:
   raw=json.dumps({"request_id":request["request_id"],"verified_email":email},separators=(",",":")).encode()
   with urlopen(Request(base+"/crm/dsr-delete",data=raw,method="POST",headers={"Content-Type":"application/json","X-LeadFlow-DSR-Adapter-Key":key}),timeout=max(1,int(os.environ.get("ADAPTER_CALL_TIMEOUT_MS","30000")))/1000) as upstream:
    adapter_result=json.loads(upstream.read())
  except (HTTPError,URLError,TimeoutError,ValueError,json.JSONDecodeError): adapter_result={"success":False,"error_code":"adapter_unavailable"}
  success=adapter_result.get("success") is True
  result_code=("already_absent" if success and adapter_result.get("resolution")=="already_absent" else "completed_ticket_archive_warn") if success else str(adapter_result.get("error_code","provider_error"))
  if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}",result_code): result_code="provider_error"
  reference=str(adapter_result.get("technical_reference",request["request_id"]+":hubspot"))
  if not TECH.fullmatch(reference): reference=request["request_id"]+":hubspot"
  recorded=database(f"SELECT * FROM leadflow.record_dsr_provider_result({q(request['request_id'])},'hubspot','delete',{q('completed' if success else 'failed')},{q(reference)},{q(result_code)});").split("|")
  response.update(status=recorded[1],provider_status="completed" if success else "failed",provider_result_code=recorded[2])
  for name in ("found","resolution","interaction_count","tickets_resolution","reconciled"):
   if name in adapter_result: response[name]=adapter_result[name]
elif response["local_status"] in {"completed","not_found"} and action=="restrict":
 response.update(provider_status="failed",provider_result_code="capability_not_available")
print(json.dumps(response,separators=(",",":")))
