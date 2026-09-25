"""Focused LF-002.1 adapter boundary and configuration tests."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import importlib.util,json,secrets,sys
ROOT=Path(__file__).resolve().parents[2]; ADAPTER='http://127.0.0.1:5685'; CRM='http://127.0.0.1:5683'; SLACK='http://127.0.0.1:5684'; checks={}; prefix='adapter_'+secrets.token_hex(5)
def http(base,path,p=None,method='GET',timeout=15):
 data=None if p is None else json.dumps(p,separators=(',',':')).encode()
 try:
  with urlopen(Request(base+path,data=data,method=method,headers={'Content-Type':'application/json'}),timeout=timeout) as r: return r.status,json.loads(r.read())
 except HTTPError as e: return e.code,json.loads(e.read())
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)
def process(label,email=None):
 email=email or f'{prefix}-{label}@example.com'; return http(ADAPTER,'/crm/process',{'email':email,'lead':{'email':email,'first_name':'Test'},'present_fields':{'first_name':'Test'},'operation_key':prefix+':'+label+':crm_create'},'POST')[1]
try:
 check('ADAPTER-health',http(ADAPTER,'/healthz')[0]==200)
 created=process('create'); check('ADAPTER-CRM-create',created.get('success') and created.get('crm_action')=='created')
 existing=process('existing',f'{prefix}-create@example.com'); check('ADAPTER-CRM-existing',existing.get('success') and existing.get('contact_id')==created.get('contact_id'))
 enriched=http(ADAPTER,'/enrichment/enrich',{'email':f'{prefix}-create@example.com'},'POST')[1]; check('ADAPTER-enrichment',enriched.get('success') and set(enriched.get('data',{}))<= {'industry','company_size','website'})
 applied=http(ADAPTER,f"/crm/update-enrichment/{created['contact_id']}",{'fields':enriched['data']},'PATCH')[1]; check('ADAPTER-CRM-enrichment',applied.get('contact_id')==created['contact_id'])
 http(SLACK,'/alerts',method='DELETE'); alert=http(ADAPTER,'/alert',{'execution_id':'lf_exec_adapter','stage':'enrichment','error_code':'http_500'},'POST')[1]; stats=http(SLACK,'/stats')[1]; check('ADAPTER-alert-sanitized',alert.get('delivered') and stats.get('last_alert')=={'execution_id':'lf_exec_adapter','stage':'enrichment','error_code':'http_500'})
 http(CRM,'/control/failure',{'mode':'http_409','operation':'create','failures':1},'POST'); conflict=process('conflict'); http(CRM,'/control/failure',method='DELETE'); check('ADAPTER-CRM-409-reconciled',conflict.get('success'))
 http(CRM,'/control/failure',{'mode':'ambiguous_create','operation':'create','failures':1,'delay_seconds':3},'POST'); ambiguous=process('ambiguous'); http(CRM,'/control/failure',method='DELETE'); check('ADAPTER-CRM-ambiguous-reconciled',ambiguous.get('success'))
 spec=importlib.util.spec_from_file_location('adapter_server',ROOT/'adapters'/'server.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
 invalid=[]
 for env in ({'RETRY_MAX_ATTEMPTS':'4'},{'RETRY_DELAY_FIRST_SECONDS':'0'},{'ADAPTER_HTTP_TIMEOUT_MS':'0'}):
  try: module.load_config(env); invalid.append(False)
  except ValueError: invalid.append(True)
 check('ADAPTER-invalid-config',all(invalid))
 check('ADAPTER-default-config',module.load_config({})['attempts']==3 and module.load_config({})['delay1']==5 and module.load_config({})['delay2']==15 and module.load_config({})['timeout_ms']==2000)
finally:
 try: http(CRM,'/control/failure',method='DELETE'); http(SLACK,'/alerts',method='DELETE')
 except Exception: pass
print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}"); sys.exit(0 if all(checks.values()) else 1)
