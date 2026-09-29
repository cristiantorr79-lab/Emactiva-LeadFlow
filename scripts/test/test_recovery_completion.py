"""F2b-2 controlled enrichment continuation and terminal recovery tests."""
from pathlib import Path
from urllib.request import Request,urlopen
import hashlib,json,os,secrets,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'/'recovery'))
from reconcile_crm import reconcile
from continue_recovery import continue_recovery
DB=os.environ['POSTGRES_DB']; APP=os.environ['POSTGRES_APP_USER']; PASSWORD=os.environ['POSTGRES_APP_PASSWORD']; SECRET=os.environ['RECOVERY_CONTEXT_KEY']
CRM=os.environ['CRM_BASE_URL']; ENRICH=os.environ['ENRICHMENT_BASE_URL']; SLACK='http://127.0.0.1:5684'; ADAPTER=os.environ['RECOVERY_ADAPTER_URL']
prefix='completion_'+secrets.token_hex(5); created=[]; checks={}

def psql(sql,app=False):
 cmd=['docker','compose','exec','-T']+(['-e',f'PGPASSWORD={PASSWORD}'] if app else [])+['postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1']
 cmd+=(['-h','127.0.0.1','-U',APP] if app else ['-U','leadflow_migrator'])+['-d',DB,'-c',sql]
 result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True); assert result.returncode==0,result.stderr; return result.stdout.strip()
def request(base,path,payload=None,method='GET'):
 data=None if payload is None else json.dumps(payload,separators=(',',':')).encode(); req=Request(base+path,data=data,method=method,headers={'Content-Type':'application/json'})
 with urlopen(req,timeout=5) as response: raw=response.read(); return json.loads(raw) if raw else {}
def fixture(label,email,worker,existing=False):
 execution='lf_exec_'+secrets.token_hex(16); created.append(execution); idem=hashlib.sha256(f'website:{prefix}_{label}'.encode()).hexdigest(); lead=hashlib.sha256(email.encode()).hexdigest()
 psql(f"INSERT INTO leadflow.executions(execution_id,idempotency_key,source,lead_identifier,status,stage,updated_at,recovery_owner,recovery_lease_until) VALUES('{execution}','{idem}','website','{lead}','processing','idempotency',clock_timestamp()-interval '1 hour','{worker}',clock_timestamp()+interval '30 minutes');")
 psql(f"SELECT leadflow.store_recovery_context('{execution}','{email}','{SECRET}');",True)
 if existing: request(CRM,'/crm/contacts',{'lead':{'email':email},'operation_key':prefix+':seed:'+label},'POST')
 reconciled=reconcile(execution,worker,ADAPTER)
 return execution,idem,reconciled
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)

try:
 request(ENRICH,'/control/failure',method='DELETE'); request(SLACK,'/control/failure',method='DELETE'); request(SLACK,'/alerts',method='DELETE')
 e1,k1,r1=fixture('existing',f'{prefix}-existing@example.com','worker_existing',True)
 e2,k2,r2=fixture('created',f'{prefix}-created@example.com','worker_created',False)
 e3,k3,r3=fixture('temporary',f'{prefix}-temporary@example.com','worker_temporary',True)
 e4,k4,r4=fixture('terminal',f'{prefix}-terminal@example.com','worker_terminal',True)
 crm_before=request(CRM,'/stats'); contacts_before=crm_before['contacts']; creates_before=crm_before['calls']['create']

 success_existing=continue_recovery(e1,'worker_existing',ADAPTER)
 check('RECOVERY-COMPLETE-existing-success',success_existing['status']=='success' and r1['resolution']=='reused')
 success_created=continue_recovery(e2,'worker_created',ADAPTER)
 check('RECOVERY-COMPLETE-created-success',success_created['status']=='success' and r2['resolution']=='created')

 request(ENRICH,'/control/failure',{'mode':'http_500','operation':'enrich','failures':1},'POST')
 temporary=continue_recovery(e3,'worker_temporary',ADAPTER); request(ENRICH,'/control/failure',method='DELETE')
 check('RECOVERY-COMPLETE-temporary-retry',temporary['status']=='success' and temporary['retry_count']==1)

 request(ENRICH,'/control/failure',{'mode':'http_400','operation':'enrich'},'POST')
 terminal=continue_recovery(e4,'worker_terminal',ADAPTER); request(ENRICH,'/control/failure',method='DELETE')
 row=psql(f"SELECT status||'|'||error_type||'|'||error_code FROM leadflow.executions WHERE execution_id='{e4}';")
 alerts=request(SLACK,'/stats')
 check('RECOVERY-COMPLETE-terminal-alert',terminal['status']=='failed' and terminal['alert_sent'] and row=='failed|validation_error|http_400' and alerts['alert_count']==1)

 crm_after=request(CRM,'/stats')
 check('RECOVERY-COMPLETE-no-create',crm_after['calls']['create']==creates_before and crm_after['contacts']==contacts_before)
 check('RECOVERY-COMPLETE-no-duplicates',len({r1['contact_id'],r2['contact_id'],r3['contact_id'],r4['contact_id']})==4)
 values=','.join("'"+value+"'" for value in created)
 check('RECOVERY-COMPLETE-context-cleaned',psql(f"SELECT count(*) FROM leadflow.recovery_contexts WHERE execution_id IN ({values});")=='0')
 keys=psql(f"SELECT count(*) FROM leadflow.executions WHERE execution_id IN ({values}) AND idempotency_key IS NOT NULL;")
 check('RECOVERY-COMPLETE-keys-intact',keys=='4')
 leases=psql(f"SELECT count(*) FROM leadflow.executions WHERE execution_id IN ({values}) AND (recovery_owner IS NOT NULL OR recovery_lease_until IS NOT NULL);")
 check('RECOVERY-COMPLETE-leases-invalidated',leases=='0')
 try: continue_recovery(e1,'worker_existing',ADAPTER); second=False
 except RuntimeError: second=True
 check('RECOVERY-COMPLETE-terminal-no-second-run',second)
finally:
 try: request(ENRICH,'/control/failure',method='DELETE'); request(SLACK,'/control/failure',method='DELETE'); request(SLACK,'/alerts',method='DELETE')
 except Exception: pass
 if created:
  values=','.join("'"+value+"'" for value in created); psql(f"DELETE FROM leadflow.execution_events WHERE execution_id IN ({values}); DELETE FROM leadflow.executions WHERE execution_id IN ({values});")
print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(0 if all(checks.values()) else 1)
