"""Focused migration 021 contract for CRM failure persistence."""
from pathlib import Path
import hashlib,os,secrets,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
DB=os.environ['POSTGRES_DB']; APP=os.environ['POSTGRES_APP_USER']; PASSWORD=os.environ['POSTGRES_APP_PASSWORD']
prefix='lf021_'+secrets.token_hex(5); created=[]; checks={}

def psql(sql,app=False,allow_failure=False):
 command=['docker','compose','exec','-T']+(['-e',f'PGPASSWORD={PASSWORD}'] if app else [])+['postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1']
 command+=(['-h','127.0.0.1','-U',APP] if app else ['-U','leadflow_migrator'])+['-d',DB,'-c',sql]
 result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=False)
 if not allow_failure and result.returncode: raise AssertionError('database operation failed')
 return result
def scalar(sql,app=False): return psql(sql,app).stdout.strip()
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)
def fixture(label,checkpoint=False):
 execution='lf_exec_'+secrets.token_hex(16); created.append(execution)
 idem=hashlib.sha256(f'website:{prefix}_{label}'.encode()).hexdigest()
 crm=",crm_action,crm_contact_id" if checkpoint else ""; values=",'created','crm_checkpoint'" if checkpoint else ""
 psql(f"INSERT INTO leadflow.executions(execution_id,idempotency_key,source,lead_identifier,status,stage{crm}) VALUES('{execution}','{idem}','website','{'a'*64}','processing','idempotency'{values});")
 return execution
def record(execution,stage,error_type,retries=0,action='NULL',contact='NULL',allow_failure=False):
 return psql(f"SELECT * FROM leadflow.record_crm_failure('{execution}','{stage}',{retries},'{error_type}','synthetic_code',{action},{contact});",True,allow_failure)

try:
 for label,stage,error in (('lookup','crm_lookup','upstream_error'),('create','crm_create','ambiguous_create'),('update','crm_update','validation_error')):
  execution=fixture(label); result=record(execution,stage,error)
  check('LF021-'+stage+'-historical',result.returncode==0 and scalar(f"SELECT status||'|'||stage FROM leadflow.executions WHERE execution_id='{execution}';")==f'failed|{stage}')

 authorization=fixture('authorization',True); record(authorization,'crm_interaction','authorization_error',0)
 auth_row=scalar(f"SELECT status||'|'||stage||'|'||retry_count||'|'||error_type||'|'||crm_action||'|'||crm_contact_id FROM leadflow.executions WHERE execution_id='{authorization}';")
 check('LF021-interaction-authorization',auth_row=='failed|crm_interaction|0|authorization_error|created|crm_checkpoint')

 ambiguous=fixture('ambiguous',True); record(ambiguous,'crm_interaction','ambiguous_interaction',0)
 check('LF021-interaction-ambiguous',scalar(f"SELECT error_type FROM leadflow.executions WHERE execution_id='{ambiguous}';")=='ambiguous_interaction')

 invalid=fixture('null_retry',True); rejected=record(invalid,'crm_interaction','authorization_error','NULL',allow_failure=True)
 diagnostic=(rejected.stdout+rejected.stderr).lower()
 check('LF021-null-retry-controlled',rejected.returncode!=0 and 'invalid crm failure' in diagnostic and 'upper bound of for loop' not in diagnostic)
 check('LF021-invalid-remains-processing',scalar(f"SELECT status||'|'||crm_contact_id FROM leadflow.executions WHERE execution_id='{invalid}';")=='processing|crm_checkpoint')

 event=scalar(f"SELECT status||'|'||stage||'|'||attempt_number||'|'||error_type||'|'||error_code||'|'||error_message FROM leadflow.execution_events WHERE execution_id='{authorization}' ORDER BY log_id DESC LIMIT 1;")
 check('LF021-audit-event',event=='failed|crm_interaction|1|authorization_error|synthetic_code|CRM request failed')
 evidence=scalar("SELECT coalesce(string_agg(to_jsonb(ev)::text,' '),'') FROM leadflow.execution_events ev WHERE execution_id IN (%s);"%','.join("'"+value+"'" for value in created))
 check('LF021-no-pii-evidence',all(value not in evidence for value in ('synthetic-person@example.test','private interaction content','+56900000000')))
finally:
 if created:
  values=','.join("'"+value+"'" for value in created)
  psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({values}); DELETE FROM leadflow.executions WHERE execution_id IN ({values});")
 remaining=scalar("SELECT count(*) FROM leadflow.executions WHERE execution_id LIKE 'lf_exec_%%' AND idempotency_key IN (%s);"%','.join("'"+hashlib.sha256(f'website:{prefix}_{label}'.encode()).hexdigest()+"'" for label in ('lookup','create','update','authorization','ambiguous','null_retry')))
 check('LF021-cleanup',remaining=='0')

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
