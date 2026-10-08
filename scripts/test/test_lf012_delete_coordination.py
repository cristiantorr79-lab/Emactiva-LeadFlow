"""Temporary-PostgreSQL coordination regression for LAB-LF-012 ticket #7."""
from pathlib import Path
import hashlib,hmac,os,secrets,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
def setting(name):
 if os.environ.get(name): return os.environ[name]
 for line in (ROOT/".env").read_text(encoding="utf-8").splitlines():
  if line.startswith(name+"="): return line.split("=",1)[1]
 raise RuntimeError("missing test database configuration")
BOOTSTRAP=setting("POSTGRES_BOOTSTRAP_USER"); MIGRATOR=setting("POSTGRES_MIGRATOR_USER"); BASE=setting("POSTGRES_DB")
DB="leadflow_lf012_delete_"+secrets.token_hex(4); PREFIX="lf012d_"+secrets.token_hex(4); SECRET="synthetic-subject-secret-at-least-32"; checks={}
def run(sql,database=DB,user=MIGRATOR,ok=True):
 result=subprocess.run(["docker","compose","exec","-T","postgres","psql","-X","-q","-v","ON_ERROR_STOP=1","-U",user,"-d",database,"-At"],cwd=ROOT,input=sql,text=True,encoding="utf-8",errors="replace",capture_output=True)
 if ok and result.returncode: raise AssertionError("database operation failed: "+result.stderr.strip())
 return result
def scalar(sql): return run(sql).stdout.strip()
def q(value): return "NULL" if value is None else "'"+str(value).replace("'","''")+"'"
def identity(email):
 normalized=email.lower(); return hashlib.sha256(normalized.encode()).hexdigest(),hmac.new(SECRET.encode(),normalized.encode(),hashlib.sha256).hexdigest()
def fixture(label,email):
 lead,token=identity(email); execution=PREFIX+"_"+label; idem=hashlib.sha256(execution.encode()).hexdigest()
 run(f"INSERT INTO leadflow.executions(execution_id,idempotency_key,source,lead_identifier,subject_token,status,stage,crm_action,crm_contact_id,enrichment_status,started_at,finished_at) VALUES({q(execution)},{q(idem)},'website',{q(lead)},{q(token)},'success','crm_enrichment_update','created','synthetic-contact','success',clock_timestamp()-interval '1 hour',clock_timestamp());")
 return lead,token
def execute(request_id,action,lead,token,operator="operator",approver=None,ok=True): return run(f"SELECT * FROM leadflow.execute_dsr_request({q(request_id)},{q(action)},{q(lead)},{q(token)},{q(operator)},{q(approver)},NULL);",ok=ok)
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
cleanup=False
try:
 run(f'CREATE DATABASE "{DB}";',BASE,BOOTSTRAP)
 migrations=sorted((ROOT/"database"/"migrations").glob("*.sql"))
 run(migrations[0].read_text(encoding="utf-8"),user=BOOTSTRAP)
 run((ROOT/"scripts"/"database"/"transfer_leadflow_ownership.sql").read_text(encoding="utf-8"),user=BOOTSTRAP)
 for migration in migrations[1:]: run(migration.read_text(encoding="utf-8"))

 lead,token=identity("approval-test@example.test")
 check("LF012-DB delete without approver rejected",execute(PREFIX+"_no_approval","delete",lead,token,ok=False).returncode!=0)
 check("LF012-DB same operator and approver rejected",execute(PREFIX+"_same_approval","delete",lead,token,approver="operator",ok=False).returncode!=0)

 absent_id=PREFIX+"_absent"; absent=execute(absent_id,"delete",lead,token,approver="approver").stdout.strip().split("|")
 actions=scalar(f"SELECT provider||'|'||action||'|'||status||'|'||result_code FROM leadflow.dsr_provider_actions WHERE request_id={q(absent_id)} ORDER BY provider;")
 check("LF012-DB absent local creates HubSpot delete pending",absent[1]=="partial" and absent[2]=="not_found" and "hubspot|delete|pending|provider_action_pending" in actions)
 check("LF012-DB Slack remains N/A","slack|no_action|not_applicable|no_subject_data" in actions)
 closed=scalar(f"SELECT * FROM leadflow.record_dsr_provider_result({q(absent_id)},'hubspot','delete','completed',{q(absent_id+':hubspot')},'completed_ticket_archive_warn');").split("|")
 check("LF012-DB pending provider action closes",closed[2]=="completed_ticket_archive_warn" and scalar(f"SELECT status FROM leadflow.dsr_provider_actions WHERE request_id={q(absent_id)} AND provider='hubspot';")=="completed")
 repeated=execute(absent_id,"delete",lead,token,approver="approver").stdout.strip().split("|")
 check("LF012-DB repeated request id idempotent",repeated[0]==absent_id and scalar(f"SELECT count(*) FROM leadflow.dsr_requests WHERE request_id={q(absent_id)};")=="1" and scalar(f"SELECT count(*) FROM leadflow.dsr_provider_actions WHERE request_id={q(absent_id)};")=="3")

 present_lead,present_token=fixture("present","present-delete@example.test"); present_id=PREFIX+"_present"; present=execute(present_id,"delete",present_lead,present_token,approver="approver").stdout.strip().split("|")
 check("LF012-DB present local accepted and pending",present[2]=="completed" and scalar(f"SELECT status FROM leadflow.dsr_provider_actions WHERE request_id={q(present_id)} AND provider='hubspot' AND action='delete';")=="pending")

 restrict_lead,restrict_token=fixture("restrict","restrict-local@example.test"); restrict_id=PREFIX+"_restrict"; restricted=execute(restrict_id,"restrict",restrict_lead,restrict_token,approver="approver").stdout.strip().split("|")
 claim=run(f"SELECT * FROM leadflow.claim_event('{PREFIX}_blocked','website','evt_lf012','{hashlib.sha256(b'website:evt_lf012').hexdigest()}','{restrict_lead}','{restrict_token}');",ok=False)
 check("LF012-DB restrict local remains operative",restricted[2]=="completed" and claim.returncode!=0 and scalar(f"SELECT disposition FROM leadflow.dsr_tombstones WHERE subject_token={q(restrict_token)};")=="restricted")
 check("LF012-DB HubSpot restrict unavailable",scalar(f"SELECT status||'|'||result_code FROM leadflow.dsr_provider_actions WHERE request_id={q(restrict_id)} AND provider='hubspot' AND action='restrict';")=="failed|capability_not_available")

 evidence=scalar(f"SELECT row_to_json(e)::text FROM (SELECT r.*,json_agg(a ORDER BY a.provider) actions FROM leadflow.dsr_requests r JOIN leadflow.dsr_provider_actions a USING(request_id) WHERE r.request_id={q(absent_id)} GROUP BY r.request_id) e;")
 check("LF012-DB evidence excludes PII and payload",all(value not in evidence for value in ("approval-test@example.test","present-delete@example.test","restrict-local@example.test","verified_email","message","interest","payload")))
finally:
 cleanup=run(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE);',BASE,BOOTSTRAP,False).returncode==0
check("LF012-DB synthetic cleanup verified",cleanup)
failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
