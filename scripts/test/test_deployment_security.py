"""Focused LF-002.4 development/production security checks."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import importlib.util,json,os,secrets,sys

ROOT=Path(__file__).resolve().parents[2]; checks={}
os.environ.setdefault('ADAPTER_SERVICE_KEY','a'*32)
os.environ.setdefault('ADAPTER_ALLOWED_OPERATIONS','crm.process,crm.update_enrichment,enrichment.enrich,alert.send,crm.capabilities')
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
deployment=load('deployment_config',Path('scripts/validation/validate_deployment_config.py'))
adapter=load('adapter_security',Path('adapters/server.py'))
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)

development={'APP_ENV':'development','ADAPTER_SERVICE_KEY':'a'*32,'ADAPTER_ALLOWED_OPERATIONS':'crm.process,crm.update_enrichment,enrichment.enrich,alert.send,crm.capabilities'}
check('SEC-001 development valid',deployment.validate_config(development)==[])
dev_adapter=adapter.load_config(development)
check('SEC-002 development mocks available',all('-mock' in dev_adapter[name] for name in ('crm','enrichment','alert')))

production={
 'APP_ENV':'production','POSTGRES_DB':'leadflow','POSTGRES_BOOTSTRAP_USER':'leadflow_bootstrap',
 'POSTGRES_BOOTSTRAP_PASSWORD':'b'*32,'POSTGRES_MIGRATOR_USER':'leadflow_migrator',
 'POSTGRES_MIGRATOR_PASSWORD':'m'*32,'POSTGRES_APP_USER':'leadflow_app',
 'POSTGRES_APP_PASSWORD':'p'*32,'LEADFLOW_WEBHOOK_KEY':'w'*32,'N8N_ENCRYPTION_KEY':'n'*32,
 'RECOVERY_CONTEXT_KEY':'r'*32,'RECOVERY_ADAPTER_URL':'http://adapters:8080',
 'ADAPTER_SERVICE_KEY':'a'*32,'DSR_ADAPTER_SERVICE_KEY':'z'*32,'ADAPTER_ALLOWED_OPERATIONS':'crm.process,crm.update_enrichment,enrichment.enrich,alert.send,crm.capabilities','DSR_SUBJECT_KEY':'d'*32,
 'CRM_UPSTREAM_URL':'https://crm.example.invalid','ENRICHMENT_UPSTREAM_URL':'https://enrichment.example.invalid',
 'SLACK_WEBHOOK_URL':'https://hooks.example.invalid/leadflow','PUBLIC_WEBHOOK_HOST':'leadflow.example.invalid',
 'CRM_PROVIDER':'hubspot','ENRICHMENT_PROVIDER':'hunter','CRM_API_KEY':'synthetic-crm','ENRICHMENT_API_KEY':'synthetic-enrichment',
}
check('SEC-003 production explicit valid',deployment.validate_config(production)==[])
check('SEC-004 production missing critical',any(item.startswith('missing_') for item in deployment.validate_config({'APP_ENV':'production'})))
unsafe={**production,'CRM_UPSTREAM_URL':'http://crm-mock:8080'}
check('SEC-005 production rejects mock', 'unsafe_crm_upstream_url' in deployment.validate_config(unsafe))
try: adapter.load_config({'APP_ENV':'production'}); adapter_closed=False
except ValueError as error: adapter_closed='http' not in str(error) and 'secret' not in str(error)
check('SEC-006 adapter production fail closed',adapter_closed)
check('SEC-007 missing webhook config fail closed','missing_leadflow_webhook_key' in deployment.validate_config({key:value for key,value in production.items() if key!='LEADFLOW_WEBHOOK_KEY'}))
weak={**production,'RECOVERY_CONTEXT_KEY':'short'}
check('SEC-008 weak critical secret rejected','weak_recovery_context_key' in deployment.validate_config(weak))
shared={**production,'POSTGRES_APP_PASSWORD':production['POSTGRES_MIGRATOR_PASSWORD']}
check('SEC-008B shared database password rejected','shared_postgres_password' in deployment.validate_config(shared))

compose=(ROOT/'compose.yaml').read_text(encoding='utf-8'); prod=(ROOT/'compose.production.yaml').read_text(encoding='utf-8')
check('SEC-009 development loopback ports',compose.count('127.0.0.1:${')>=6)
check('SEC-010 production internal ports',prod.count('ports: !reset []')==6 and 'profiles: [development]' in prod)
recovery=(ROOT/'scripts/recovery/reconcile_crm.py').read_text(encoding='utf-8')+(ROOT/'scripts/recovery/continue_recovery.py').read_text(encoding='utf-8')
check('SEC-011 recovery adapter only','RECOVERY_ADAPTER_URL' in recovery and all(token not in recovery for token in ('127.0.0.1:5682','127.0.0.1:5683','127.0.0.1:5684')))

key=os.environ.get('LEADFLOW_WEBHOOK_KEY',''); port=os.environ.get('N8N_PORT','5680'); url=f'http://127.0.0.1:{port}/webhook/leadflow'
payload={'event_id':'security_'+secrets.token_hex(6),'source':'website','lead':{'email':'security-'+secrets.token_hex(5)+'@example.com'}}
def webhook(supplied):
 headers={'Content-Type':'application/json'}
 if supplied is not None: headers['X-LeadFlow-Key']=supplied
 try:
  with urlopen(Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST'),timeout=40) as response: return response.status,json.loads(response.read())
 except HTTPError as error: return error.code,json.loads(error.read())
valid_status,valid_body=webhook(key)
wrong_status,wrong_body=webhook(('x' if not key.startswith('x') else 'y')*max(1,len(key)))
missing_status,missing_body=webhook(None)
check('SEC-012 webhook valid continues',bool(key) and valid_status==200 and valid_body.get('status') in {'success','processing'})
check('SEC-013 webhook wrong rejected',wrong_status==401 and key not in str(wrong_body))
check('SEC-014 webhook missing rejected',missing_status==401 and key not in str(missing_body))

print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(0 if all(checks.values()) else 1)
