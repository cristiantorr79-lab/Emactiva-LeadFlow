"""F1: detect and exclusively lease stale processing executions without resuming them."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen
import hashlib, json, os, secrets, subprocess, sys

ROOT=Path(__file__).resolve().parents[2]
DB=os.environ['POSTGRES_DB']; APP=os.environ['POSTGRES_USER']; PASSWORD=os.environ['POSTGRES_PASSWORD']
CRM=os.environ.get('CRM_BASE_URL') or 'http://127.0.0.1:5683'
ENRICH=os.environ.get('ENRICHMENT_BASE_URL') or 'http://127.0.0.1:5682'
prefix='recovery_'+secrets.token_hex(5); checks={}

def run_psql(sql,app=False):
 cmd=['docker','compose','exec','-T']
 if app: cmd += ['-e',f'PGPASSWORD={PASSWORD}']
 cmd += ['postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1']
 if app: cmd += ['-h','127.0.0.1','-U',APP]
 else: cmd += ['-U','leadflow_migrator']
 cmd += ['-d',DB,'-c',sql]
 result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
 assert result.returncode==0,result.stderr
 return result.stdout.strip()

def key(label): return hashlib.sha256(f'website:{prefix}_{label}'.encode()).hexdigest()
def insert(label,status='processing',old=True,keyed=True,duplicate_of=None):
 execution=f'lf_exec_{secrets.token_hex(16)}'; idem=key(label) if keyed else None
 finished="clock_timestamp()" if status in {'success','failed','duplicate'} else 'NULL'
 values=(f"'{idem}'" if idem else 'NULL',f"'{duplicate_of}'" if duplicate_of else 'NULL')
 stage='crm_enrichment_update' if status=='success' else 'idempotency'
 crm_action="'created'" if status=='success' else 'NULL'; crm_contact="'crm_fixture'" if status=='success' else 'NULL'
 enrichment="'success'" if status=='success' else "'not_started'"
 sql=f"INSERT INTO leadflow.executions(execution_id,idempotency_key,event_id,source,lead_identifier,status,stage,crm_action,crm_contact_id,enrichment_status,finished_at,duplicate_of) VALUES('{execution}',{values[0]},'{prefix}_{label}','website','{'a'*64}','{status}','{stage}',{crm_action},{crm_contact},{enrichment},{finished},{values[1]});"
 if old: sql+=f" UPDATE leadflow.executions SET updated_at=clock_timestamp()-interval '8 days' WHERE execution_id='{execution}';"
 run_psql(sql)
 return execution,idem
def claim(worker,threshold=604800): return run_psql(f"SELECT execution_id||'|'||idempotency_key||'|'||recovery_owner FROM leadflow.claim_stale_processing_executions('{worker}',{threshold},300,1);",True)
def stats():
 return tuple(json.load(urlopen(url+'/stats',timeout=3))['calls'] for url in (CRM,ENRICH))
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)

created=[]
try:
 external_before=stats()
 recent,_=insert('recent',old=False); created.append(recent)
 check('RECOVERY-recent-not-candidate',claim('worker_recent')=='')
 old,old_key=insert('old'); created.append(old)
 success,_=insert('success','success'); failed,_=insert('failed','failed'); created += [success,failed]
 owner,_=insert('owner','failed'); duplicate,_=insert('duplicate','duplicate',keyed=False,duplicate_of=owner); created += [owner,duplicate]
 result=claim('worker_one')
 check('RECOVERY-old-candidate',result.startswith(old+'|'))
 check('RECOVERY-idempotency-preserved',result==f'{old}|{old_key}|worker_one' and run_psql(f"SELECT idempotency_key FROM leadflow.executions WHERE execution_id='{old}';")==old_key)
 check('RECOVERY-terminal-not-candidates',all(claim('worker_terminal')=='' for _ in range(3)))
 concurrent,_=insert('concurrent'); created.append(concurrent)
 with ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(claim,['worker_a','worker_b']))
 owners=[value for value in results if value]
 check('RECOVERY-exclusive-claim',len(owners)==1 and owners[0].startswith(concurrent+'|'))
 check('RECOVERY-no-external-calls',stats()==external_before)
 count=run_psql("SELECT count(*) FROM leadflow.executions WHERE event_id LIKE '%s%%' AND idempotency_key IS NOT NULL;"%prefix)
 check('RECOVERY-keys-not-released',count=='6')
finally:
 if created:
  values=','.join("'"+value+"'" for value in created)
  run_psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({values}); DELETE FROM leadflow.executions WHERE execution_id IN ({values}) AND status='duplicate'; DELETE FROM leadflow.executions WHERE execution_id IN ({values});")
print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(0 if all(checks.values()) else 1)
