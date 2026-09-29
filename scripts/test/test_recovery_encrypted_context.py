"""F2b-1 encrypted minimal recovery context tests."""
from pathlib import Path
import hashlib,os,secrets,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]; DB=os.environ['POSTGRES_DB']; APP=os.environ['POSTGRES_APP_USER']; PASSWORD=os.environ['POSTGRES_APP_PASSWORD']
SECRET=os.environ['RECOVERY_CONTEXT_KEY']; WRONG='f'*64 if SECRET!='f'*64 else 'e'*64
prefix='context_'+secrets.token_hex(5); created=[]; checks={}

def psql(sql,app=False,allow_failure=False):
 cmd=['docker','compose','exec','-T']+(['-e',f'PGPASSWORD={PASSWORD}'] if app else [])+['postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1']
 cmd+=(['-h','127.0.0.1','-U',APP] if app else ['-U','leadflow_migrator'])+['-d',DB,'-c',sql]
 result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
 if not allow_failure: assert result.returncode==0,result.stderr
 return result.returncode,result.stdout.strip(),result.stderr.strip()
def fixture(label,email,status='processing'):
 execution='lf_exec_'+secrets.token_hex(16); created.append(execution); idem=hashlib.sha256(f'website:{prefix}_{label}'.encode()).hexdigest(); lead=hashlib.sha256(email.encode()).hexdigest()
 psql(f"INSERT INTO leadflow.executions(execution_id,idempotency_key,source,lead_identifier,status,stage,updated_at,recovery_owner,recovery_lease_until) VALUES('{execution}','{idem}','website','{lead}','{status}','idempotency',clock_timestamp()-interval '8 days','worker_context',clock_timestamp()+interval '5 minutes');")
 return execution,lead
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)

try:
 email=f'{prefix}@example.com'; execution,lead=fixture('main',email)
 psql(f"SELECT leadflow.store_recovery_context('{execution}','{email}','{SECRET}');",True)
 cipher=psql(f"SELECT encode(email_ciphertext,'hex') FROM leadflow.recovery_contexts WHERE execution_id='{execution}';")[1]
 check('CONTEXT-encrypted-at-rest',email.encode().hex() not in cipher and email not in cipher)
 recovered=psql(f"SELECT normalized_email FROM leadflow.get_recovery_crm_context('{execution}','worker_context','{SECRET}');",True)[1]
 check('CONTEXT-correct-secret',recovered==email)
 wrong=psql(f"SELECT normalized_email FROM leadflow.get_recovery_crm_context('{execution}','worker_context','{WRONG}');",True)[1]
 check('CONTEXT-wrong-secret-hidden',wrong=='')
 check('CONTEXT-hash-matches',hashlib.sha256(recovered.encode()).hexdigest()==lead)
 direct=psql(f"SELECT email_ciphertext FROM leadflow.recovery_contexts WHERE execution_id='{execution}';",True,True)
 check('CONTEXT-no-direct-read',direct[0]!=0 and email not in direct[1]+direct[2])
 terminal_email=f'{prefix}-terminal@example.com'; terminal,unused=fixture('terminal',terminal_email)
 psql(f"SELECT leadflow.store_recovery_context('{terminal}','{terminal_email}','{SECRET}');",True)
 psql(f"UPDATE leadflow.executions SET status='failed',error_type='internal_error',error_code='test',error_message='test',finished_at=clock_timestamp() WHERE execution_id='{terminal}';")
 remaining=psql(f"SELECT count(*) FROM leadflow.recovery_contexts WHERE execution_id='{terminal}';")[1]
 check('CONTEXT-terminal-cleanup',remaining=='0')
 check('CONTEXT-minimal-columns',psql("SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='leadflow' AND table_name='recovery_contexts';")[1]=='execution_id,email_ciphertext,created_at')
finally:
 if created:
  values=','.join("'"+value+"'" for value in created); psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({values}); DELETE FROM leadflow.executions WHERE execution_id IN ({values});")
print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(0 if all(checks.values()) else 1)
