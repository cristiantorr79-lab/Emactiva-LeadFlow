"""Focused LF-002.3 recovery-to-adapter boundary tests."""
from pathlib import Path
import importlib.util,os,sys

ROOT=Path(__file__).resolve().parents[2]; checks={}
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
crm=load('recovery_crm',Path('scripts/recovery/reconcile_crm.py'))
continuation=load('recovery_continue',Path('scripts/recovery/continue_recovery.py'))
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)

old_key=os.environ.get('RECOVERY_CONTEXT_KEY'); old_url=os.environ.pop('RECOVERY_ADAPTER_URL',None); os.environ['RECOVERY_CONTEXT_KEY']='k'*32
try:
 for module,label in ((crm,'CRM'),(continuation,'CONTINUE')):
  try: module.adapter_base(); missing=False
  except RuntimeError: missing=True
  check('RECOVERY-CONFIG-'+label,missing)

 crm_sql=[]; crm_http=[]
 def psql_success(sql):
  crm_sql.append(sql)
  return 'lf_exec_test|idemhash||0|lead@example.com' if 'get_recovery_crm_context' in sql else 'lf_exec_test|processing|c1|created|0'
 def http_success(url,payload,method='POST'):
  crm_http.append((url,payload,method)); return 200,{'success':True,'contact_id':'c1','crm_action':'created','retry_count':0}
 crm.psql=psql_success; crm.http=http_success
 result=crm.reconcile('lf_exec_test','worker_test','http://adapter:8080')
 check('RECOVERY-CRM-adapter',crm_http[0][0]=='http://adapter:8080/crm/process' and result['contact_id']=='c1')
 check('RECOVERY-CRM-operation-key',crm_http[0][1]['operation_key']=='idemhash:crm_create')
 check('RECOVERY-CRM-state-persisted',any('record_recovery_crm_adapter_reconciliation' in sql for sql in crm_sql))

 crm_sql.clear(); crm_http.clear()
 crm.psql=lambda sql: (crm_sql.append(sql) or ('lf_exec_test|idemhash||0|lead@example.com' if 'get_recovery_crm_context' in sql else 'lf_exec_test|failed|0|ambiguous_create'))
 crm.http=lambda *args,**kwargs:(crm_http.append(args) or (200,{'success':False,'error_type':'ambiguous_create','error_code':'ambiguous_create','ambiguous':True,'retry_count':0}))
 failed=crm.reconcile('lf_exec_test','worker_test','http://adapter:8080')
 check('RECOVERY-CRM-ambiguous-terminal',failed['status']=='failed' and any('fail_recovery_crm' in sql for sql in crm_sql))
 check('RECOVERY-CRM-no-direct-create',len(crm_http)==1)

 calls=[]; sql=[]
 continuation.psql=lambda query:(sql.append(query) or ('lf_exec_test|c1|0|lead@example.com' if 'get_recovery_crm_context' in query else 'ok'))
 def continue_success(url,payload,method='POST'):
  calls.append((url,payload,method))
  if url.endswith('/enrichment/enrich'): return 200,{'success':True,'data':{'industry':'software'},'retry_count':1}
  return 200,{'contact_id':'c1'}
 continuation.http=continue_success
 completed=continuation.continue_recovery('lf_exec_test','worker_test','http://adapter:8080')
 check('RECOVERY-ENRICH-adapter',calls[0][0].endswith('/enrichment/enrich') and calls[1][0].endswith('/crm/update-enrichment/c1'))
 check('RECOVERY-ENRICH-terminal-success',completed['status']=='success' and completed['retry_count']==1 and any('complete_recovery_adapter' in query for query in sql))

 calls.clear(); sql.clear()
 continuation.psql=lambda query:(sql.append(query) or ('lf_exec_test|c1|0|lead@example.com' if 'get_recovery_crm_context' in query else 'ok'))
 def continue_failure(url,payload,method='POST'):
  calls.append((url,payload,method))
  if url.endswith('/enrichment/enrich'): return 200,{'success':False,'error_type':'validation_error','error_code':'http_400','retry_count':0}
  return 200,{'delivered':True}
 continuation.http=continue_failure
 failed=continuation.continue_recovery('lf_exec_test','worker_test','http://adapter:8080')
 alert=[call for call in calls if call[0].endswith('/alert')][0]
 check('RECOVERY-ALERT-adapter-sanitized',failed['status']=='failed' and set(alert[1])=={'execution_id','stage','error_code'})

 sources=(ROOT/'scripts/recovery/reconcile_crm.py').read_text(encoding='utf-8')+(ROOT/'scripts/recovery/continue_recovery.py').read_text(encoding='utf-8')
 check('RECOVERY-no-local-fallbacks',all(value not in sources for value in ('127.0.0.1:5682','127.0.0.1:5683','127.0.0.1:5684','CRM_BASE_URL','ENRICHMENT_BASE_URL','SLACK_WEBHOOK_URL')))
finally:
 if old_key is None: os.environ.pop('RECOVERY_CONTEXT_KEY',None)
 else: os.environ['RECOVERY_CONTEXT_KEY']=old_key
 if old_url is not None: os.environ['RECOVERY_ADAPTER_URL']=old_url

print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(0 if all(checks.values()) else 1)
