"""F2a CRM reconciliation tests; enrichment must remain untouched."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
import hashlib,json,os,secrets,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'/'recovery'))
from reconcile_crm import reconcile
DB=os.environ['POSTGRES_DB']; APP=os.environ['POSTGRES_USER']; PASSWORD=os.environ['POSTGRES_PASSWORD']
CRM=os.environ.get('CRM_BASE_URL') or 'http://127.0.0.1:5683'; ENRICH=os.environ.get('ENRICHMENT_BASE_URL') or 'http://127.0.0.1:5682'
prefix='reconcile_'+secrets.token_hex(5); created=[]; checks={}

def psql(sql,app=False):
 cmd=['docker','compose','exec','-T']+(['-e',f'PGPASSWORD={PASSWORD}'] if app else [])+['postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1']
 cmd+=(['-h','127.0.0.1','-U',APP] if app else ['-U','leadflow_migrator'])+['-d',DB,'-c',sql]
 result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True); assert result.returncode==0,result.stderr; return result.stdout.strip()
def http(path,payload=None,method='GET'):
 data=None if payload is None else json.dumps(payload,separators=(',',':')).encode(); req=Request(CRM+path,data=data,method=method,headers={'Content-Type':'application/json'})
 with urlopen(req,timeout=5) as response: return json.loads(response.read())
def fixture(label,email,stage='idempotency',lease_worker=None,lease_expired=False):
 execution='lf_exec_'+secrets.token_hex(16); idem=hashlib.sha256(f'website:{prefix}_{label}'.encode()).hexdigest(); lead=hashlib.sha256(email.encode()).hexdigest(); created.append(execution)
 owner='NULL' if lease_worker is None else "'%s'"%lease_worker; lease='NULL' if lease_worker is None else ("clock_timestamp()-interval '1 second'" if lease_expired else "clock_timestamp()+interval '5 minutes'")
 psql(f"INSERT INTO leadflow.executions(execution_id,idempotency_key,event_id,source,lead_identifier,status,stage,updated_at,recovery_owner,recovery_lease_until) VALUES('{execution}','{idem}','{prefix}_{label}','website','{lead}','processing','{stage}',clock_timestamp()-interval '8 days',{owner},{lease});")
 psql(f"SELECT leadflow.store_recovery_context('{execution}','{email}','{os.environ['RECOVERY_CONTEXT_KEY']}');",True)
 return execution,idem
def claim(worker): return psql(f"SELECT execution_id FROM leadflow.claim_stale_processing_executions('{worker}',604800,300,1);",True)
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)
def stats(): return http('/stats')

try:
 enrich_before=json.load(urlopen(ENRICH+'/stats',timeout=3))['calls']
 email=f'{prefix}-existing@example.com'; seeded=http('/crm/contacts',{'lead':{'email':email},'operation_key':prefix+':seed'},'POST')['contact_id']
 execution,idem=fixture('existing',email,lease_worker='worker_existing'); result=reconcile(execution,'worker_existing',CRM)
 check('RECOVERY-CRM-existing-reused',result['contact_id']==seeded and result['resolution']=='reused')
 email2=f'{prefix}-safe@example.com'; execution2,idem2=fixture('safe',email2,lease_worker='worker_safe'); before=stats()['contacts']; result2=reconcile(execution2,'worker_safe',CRM); after=stats()['contacts']
 check('RECOVERY-CRM-safe-create',result2['resolution']=='created' and after==before+1)
 email3=f'{prefix}-ambiguous@example.com'; execution3,idem3=fixture('ambiguous',email3,'crm_create',lease_worker='worker_ambiguous')
 http('/control/failure',{'mode':'ambiguous_create','operation':'create','failures':1,'delay_seconds':3},'POST'); result3=reconcile(execution3,'worker_ambiguous',CRM); http('/control/failure',method='DELETE')
 before_repeat=stats()['contacts']; psql(f"UPDATE leadflow.executions SET recovery_owner='worker_repeat',recovery_lease_until=clock_timestamp()+interval '5 minutes' WHERE execution_id='{execution3}';"); repeated=reconcile(execution3,'worker_repeat',CRM)
 check('RECOVERY-CRM-ambiguous-lookup',result3['contact_id']==repeated['contact_id'])
 check('RECOVERY-CRM-operation-key-idempotent',stats()['contacts']==before_repeat and repeated['resolution']=='reused')
 email4=f'{prefix}-concurrent@example.com'; execution4,idem4=fixture('concurrent',email4)
 with ThreadPoolExecutor(max_workers=2) as pool: claims=list(pool.map(claim,['worker_a','worker_b']))
 winners=[('worker_a','worker_b')[index] for index,value in enumerate(claims) if value==execution4]
 if winners: reconcile(execution4,winners[0],CRM)
 check('RECOVERY-CRM-exclusive-worker',len(winners)==1)
 email5=f'{prefix}-expired@example.com'; execution5,idem5=fixture('expired',email5,lease_worker='old_worker',lease_expired=True); reclaimed=claim('new_worker')
 check('RECOVERY-CRM-expired-lease',reclaimed==execution5)
 intact=psql("SELECT count(*) FROM leadflow.executions WHERE event_id LIKE '%s%%' AND idempotency_key IS NOT NULL;"%prefix)
 check('RECOVERY-CRM-keys-intact',intact=='5')
 check('RECOVERY-CRM-no-enrichment',json.load(urlopen(ENRICH+'/stats',timeout=3))['calls']==enrich_before)
 audit=psql("SELECT count(*) FROM leadflow.execution_events WHERE execution_id IN (%s) AND error_code LIKE 'recovery_%%';"%','.join("'"+value+"'" for value in created))
 check('RECOVERY-CRM-audited',int(audit)>=4)
finally:
 try: http('/control/failure',method='DELETE')
 except Exception: pass
 if created:
  values=','.join("'"+value+"'" for value in created); psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({values}); DELETE FROM leadflow.executions WHERE execution_id IN ({values});")
print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(0 if all(checks.values()) else 1)
