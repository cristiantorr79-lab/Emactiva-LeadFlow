"""F2b-1 encrypted minimal recovery context tests."""
from pathlib import Path
import hashlib,json,os,secrets,subprocess,sys

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
 email=f'{prefix}@example.com'; execution,lead=fixture('v1',email)
 psql(f"SELECT leadflow.store_recovery_context('{execution}','{email}',NULL,'{SECRET}');",True)
 cipher=psql(f"SELECT encode(context_ciphertext,'hex') FROM leadflow.recovery_contexts WHERE execution_id='{execution}';")[1]
 check('CONTEXT-V1-encrypted-at-rest',email.encode().hex() not in cipher and email not in cipher)
 v1_state=psql(f"SELECT interaction_status FROM leadflow.executions WHERE execution_id='{execution}';")[1]
 check('CONTEXT-V1-not-required',v1_state=='not_required')
 recovered=psql(f"SELECT public.pgp_sym_decrypt(context_ciphertext,'{SECRET}')::jsonb->>'email' FROM leadflow.recovery_contexts WHERE execution_id='{execution}';")[1]
 check('CONTEXT-correct-secret',recovered==email)
 wrong=psql(f"SELECT normalized_email FROM leadflow.get_recovery_crm_context('{execution}','worker_context','{WRONG}');",True)[1]
 check('CONTEXT-wrong-secret-hidden',wrong=='')
 check('CONTEXT-hash-matches',hashlib.sha256(recovered.encode()).hexdigest()==lead)
 direct=psql(f"SELECT context_ciphertext FROM leadflow.recovery_contexts WHERE execution_id='{execution}';",True,True)
 check('CONTEXT-no-direct-read',direct[0]!=0 and email not in direct[1]+direct[2])

 interaction_email=f'{prefix}-interaction@example.com'; interaction_execution,_=fixture('interaction',interaction_email)
 interaction={'interest':'producto_a','message':'synthetic recovery text | line 1\nline 2'}
 interaction_json=json.dumps(interaction,separators=(',',':'),ensure_ascii=False).replace("'","''")
 psql(f"SELECT leadflow.store_recovery_context('{interaction_execution}','{interaction_email}','{interaction_json}'::jsonb,'{SECRET}');",True)
 interaction_cipher=psql(f"SELECT encode(context_ciphertext,'hex') FROM leadflow.recovery_contexts WHERE execution_id='{interaction_execution}';")[1]
 sensitive_hex=[interaction_email.encode().hex(),interaction['message'].encode().hex(),interaction['interest'].encode().hex()]
 check('CONTEXT-interaction-encrypted-at-rest',all(value not in interaction_cipher for value in sensitive_hex))
 interaction_state=psql(f"SELECT interaction_status FROM leadflow.executions WHERE execution_id='{interaction_execution}';")[1]
 check('CONTEXT-interaction-pending',interaction_state=='pending')
 structured=psql(f"SELECT ((public.pgp_sym_decrypt(context_ciphertext,'{SECRET}')::jsonb->>'email') IS NOT NULL AND public.pgp_sym_decrypt(context_ciphertext,'{SECRET}')::jsonb->'interaction'=$${interaction_json}$$::jsonb AND (public.pgp_sym_decrypt(context_ciphertext,'{SECRET}')::jsonb->'interaction')-'interest'-'message'='{{}}'::jsonb)::text FROM leadflow.recovery_contexts WHERE execution_id='{interaction_execution}';")[1]
 check('CONTEXT-interaction-structured-minimal',structured=='true')
 envelope=psql(f"SELECT (public.pgp_sym_decrypt(context_ciphertext,'{SECRET}')::jsonb-'version'-'email'-'interaction'='{{}}'::jsonb)::text FROM leadflow.recovery_contexts WHERE execution_id='{interaction_execution}';")[1]
 check('CONTEXT-envelope-minimal',envelope=='true')
 v1_lookup=psql(f"SELECT (count(*)=1 AND bool_and(interaction IS NULL AND interaction_status='not_required'))::text FROM leadflow.get_recovery_crm_context('{execution}','worker_context','{SECRET}');",True)[1]
 check('CONTEXT-V1-recovery-row',v1_lookup=='true')
 interaction_lookup=psql(f"SELECT (count(*)=1 AND bool_and(interaction=$${interaction_json}$$::jsonb AND interaction_status='pending'))::text FROM leadflow.get_recovery_crm_context('{interaction_execution}','worker_context','{SECRET}');",True)[1]
 check('CONTEXT-interaction-recovery-row',interaction_lookup=='true')
 wrong_worker=psql(f"SELECT count(*) FROM leadflow.get_recovery_crm_context('{execution}','other_worker','{SECRET}');",True)[1]
 check('CONTEXT-wrong-worker-hidden',wrong_worker=='0')
 expired_email=f'{prefix}-expired@example.com'; expired_execution,_=fixture('expired',expired_email)
 psql(f"SELECT leadflow.store_recovery_context('{expired_execution}','{expired_email}',NULL,'{SECRET}');",True)
 psql(f"UPDATE leadflow.executions SET recovery_lease_until=clock_timestamp()-interval '1 second' WHERE execution_id='{expired_execution}';")
 expired=psql(f"SELECT count(*) FROM leadflow.get_recovery_crm_context('{expired_execution}','worker_context','{SECRET}');",True)[1]
 check('CONTEXT-expired-lease-hidden',expired=='0')
 corrupt_email=f'{prefix}-corrupt@example.com'; corrupt_execution,_=fixture('corrupt',corrupt_email)
 psql(f"SELECT leadflow.store_recovery_context('{corrupt_execution}','{corrupt_email}',NULL,'{SECRET}');",True)
 psql(f"UPDATE leadflow.recovery_contexts SET context_ciphertext=decode('00','hex') WHERE execution_id='{corrupt_execution}';")
 corrupt=psql(f"SELECT count(*) FROM leadflow.get_recovery_crm_context('{corrupt_execution}','worker_context','{SECRET}');",True)[1]
 check('CONTEXT-corrupt-hidden',corrupt=='0')
 terminal_email=f'{prefix}-terminal@example.com'; terminal,unused=fixture('terminal',terminal_email)
 psql(f"SELECT leadflow.store_recovery_context('{terminal}','{terminal_email}',NULL,'{SECRET}');",True)
 psql(f"UPDATE leadflow.executions SET status='failed',error_type='internal_error',error_code='test',error_message='test',finished_at=clock_timestamp() WHERE execution_id='{terminal}';")
 remaining=psql(f"SELECT count(*) FROM leadflow.recovery_contexts WHERE execution_id='{terminal}';")[1]
 check('CONTEXT-terminal-cleanup',remaining=='0')
 check('CONTEXT-minimal-columns',psql("SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='leadflow' AND table_name='recovery_contexts';")[1]=='execution_id,context_ciphertext,created_at')
finally:
 if created:
  values=','.join("'"+value+"'" for value in created); psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({values}); DELETE FROM leadflow.executions WHERE execution_id IN ({values});")
  remaining=psql("SELECT count(*) FROM leadflow.executions WHERE execution_id LIKE 'lf_exec_%' AND recovery_owner='worker_context';")[1]
  check('CONTEXT-cleanup',remaining=='0')
print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(0 if all(checks.values()) else 1)
