"""Executable PostgreSQL + mocked HubSpot regression for LF012 absent-local CORRECT."""
from pathlib import Path
import hashlib,hmac,importlib.util,os,secrets,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
def setting(name):
 if os.environ.get(name): return os.environ[name]
 for line in (ROOT/".env").read_text(encoding="utf-8").splitlines():
  if line.startswith(name+"="): return line.split("=",1)[1]
 raise RuntimeError("missing test database configuration")
BOOTSTRAP=setting("POSTGRES_BOOTSTRAP_USER")
MIGRATOR=setting("POSTGRES_MIGRATOR_USER")
BASE=setting("POSTGRES_DB")
DB="leadflow_lf012_"+secrets.token_hex(4)
REQUEST="lf012_absent_"+secrets.token_hex(4)
EMAIL="lf012-private-person@example.test"
CORRECTION="Corrected Private Company"
SUBJECT_SECRET="synthetic-lf012-subject-secret-at-least-32"
checks={}

def run(sql,database=DB,user=MIGRATOR,ok=True):
 result=subprocess.run(
  ["docker","compose","exec","-T","postgres","psql","-X","-q","-v","ON_ERROR_STOP=1","-U",user,"-d",database,"-At"],
  cwd=ROOT,input=sql,text=True,encoding="utf-8",errors="replace",capture_output=True
 )
 if ok and result.returncode: raise AssertionError("database operation failed: "+result.stderr.strip())
 return result

def scalar(sql): return run(sql).stdout.strip()
def q(value): return "'"+str(value).replace("'","''")+"'"
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)

lead=hashlib.sha256(EMAIL.encode()).hexdigest()
token=hmac.new(SUBJECT_SECRET.encode(),EMAIL.encode(),hashlib.sha256).hexdigest()
try:
 run(f'CREATE DATABASE "{DB}";',BASE,BOOTSTRAP)
 migrations=sorted((ROOT/"database"/"migrations").glob("*.sql"))
 run(migrations[0].read_text(encoding="utf-8"),user=BOOTSTRAP)
 run((ROOT/"scripts"/"database"/"transfer_leadflow_ownership.sql").read_text(encoding="utf-8"),user=BOOTSTRAP)
 for migration in migrations[1:]: run(migration.read_text(encoding="utf-8"))

 execute=f"SELECT * FROM leadflow.execute_dsr_request({q(REQUEST)},'correct',{q(lead)},{q(token)},'dsr_operator',NULL,NULL);"
 first=scalar(execute).split("|")
 check("LF012-DB absent local remains partial",first[1]=="partial" and first[2]=="not_found" and first[4]=="0")
 actions=scalar(f"SELECT provider||'|'||action||'|'||status||'|'||result_code FROM leadflow.dsr_provider_actions WHERE request_id={q(REQUEST)} ORDER BY provider;")
 check("LF012-DB HubSpot correct pending created","hubspot|correct|pending|provider_action_pending" in actions)
 check("LF012-DB Hunter and Slack remain N/A","hunter|correct|not_applicable|no_correction_contract" in actions and "slack|no_action|not_applicable|no_subject_data" in actions)

 spec=importlib.util.spec_from_file_location("lf012_absent_adapter",ROOT/"adapters"/"server.py")
 adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
 adapter.CONFIG={"attempts":1,"delay1":1,"delay2":1,"timeout_ms":100,"crm_provider":"hubspot","crm":"https://hub.test","crm_api_key":"synthetic-secret","hubspot_enrichment_properties":{"industry":"industry","company_size":"leadflow_company_size","website":"website"},"hubspot_interaction_properties":{"key":"leadflow_interaction_key","message":"content","interest":"leadflow_interest"}}
 sequence=[(200,{}, {"results":[{"id":"contact-12","properties":{"email":EMAIL}}]}),(200,{},{}),(200,{}, {"properties":{"company":CORRECTION}})]
 adapter.call=lambda method,url,body=None,headers=None: sequence.pop(0)
 provider=adapter.dsr_correct({"request_id":REQUEST,"verified_email":EMAIL,"corrections":{"company":CORRECTION}})
 check("LF012-DB mocked HubSpot correction reconciles",provider.get("success") and provider.get("found") and provider.get("reconciled") and provider.get("corrected_count")==1)

 closed=scalar(f"SELECT * FROM leadflow.record_dsr_provider_result({q(REQUEST)},'hubspot','correct','completed',{q(REQUEST+':hubspot')},'provider_completed');").split("|")
 check("LF012-DB provider result closes without missing action",closed[1]=="completed" and scalar(f"SELECT status FROM leadflow.dsr_provider_actions WHERE request_id={q(REQUEST)} AND provider='hubspot' AND action='correct';")=="completed")
 repeated=scalar(execute).split("|")
 check("LF012-DB repeated request id is idempotent",repeated[:4]==[REQUEST,"completed","not_found","subject_not_found"] and scalar(f"SELECT count(*) FROM leadflow.dsr_requests WHERE request_id={q(REQUEST)};")=="1" and scalar(f"SELECT count(*) FROM leadflow.dsr_provider_actions WHERE request_id={q(REQUEST)};")=="3")
 evidence=scalar(f"SELECT row_to_json(e)::text FROM (SELECT r.*,json_agg(a ORDER BY a.provider) actions FROM leadflow.dsr_requests r JOIN leadflow.dsr_provider_actions a USING(request_id) WHERE r.request_id={q(REQUEST)} GROUP BY r.request_id) e;")
 check("LF012-DB persistent evidence excludes PII and payload",EMAIL not in evidence and CORRECTION not in evidence and "corrections" not in evidence and "verified_email" not in evidence and "payload" not in evidence)
finally:
 run(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE);',BASE,BOOTSTRAP,False)

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
