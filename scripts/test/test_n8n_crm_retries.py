"""CRM classification, retry and CREATE reconciliation tests."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json, os, secrets, subprocess, sys

ROOT=Path(__file__).resolve().parents[2]; CRM=os.environ.get('CRM_BASE_URL') or 'http://127.0.0.1:5683'; WEBHOOK=f"http://127.0.0.1:{os.environ.get('N8N_PORT','5680')}/webhook/leadflow"; KEY=os.environ.get('LEADFLOW_WEBHOOK_KEY',''); DB=os.environ.get('POSTGRES_DB',''); prefix='crm_'+secrets.token_hex(5); ids=[]; checks={}
def http(url,p=None,method='GET',webhook=False,timeout=70):
 data=None if p is None else json.dumps(p,separators=(',',':')).encode(); h={'Content-Type':'application/json'}; h.update({'X-LeadFlow-Key':KEY} if webhook else {}); q=Request(url,data=data,method=method,headers=h)
 try:
  with urlopen(q,timeout=timeout) as r: t=r.read().decode(); return r.status,json.loads(t),t
 except HTTPError as e: t=e.read().decode(); return e.code,json.loads(t),t
def cfg(mode,op,failures=None,delay=3):
 p={'mode':mode,'operation':op,'delay_seconds':delay}; p.update({'failures':failures} if failures else {}); return http(CRM+'/control/failure',p,'POST')
def clear(): http(CRM+'/control/failure',method='DELETE')
def send(label,email=None,**fields):
 email=email or f'{prefix}-{label}@example.com'; r=http(WEBHOOK,{'event_id':f'{prefix}_{label}','source':'website','lead':{'email':email,**fields}},'POST',True); ids.append(r[1].get('execution_id','')); return r,email
def psql(sql):
 r=subprocess.run(['docker','compose','exec','-T','postgres','psql','-X','-q','-U','leadflow_migrator','-d',DB,'-Atc',sql],cwd=ROOT,capture_output=True,text=True); assert r.returncode==0; return r.stdout.strip()
def row(i): return psql(f"SELECT status||'|'||retry_count||'|'||coalesce(error_type,'') FROM leadflow.executions WHERE execution_id='{i}';")
def check(n,v): checks[n]=bool(v); print(('PASS' if v else 'FAIL')+' '+n)
try:
 for mode,kind in [('http_400','validation_error'),('http_401','authentication_error')]:
  cfg(mode,'lookup'); (s,b,_),_=send(mode); clear(); check('CRM-'+mode,s==502 and row(b['execution_id'])==f'failed|0|{kind}')
 cfg('http_500','lookup',1); (s,b,_),_=send('lookup_recover'); clear(); check('CRM-lookup-500-retry',s==200 and row(b['execution_id']).startswith('success|1|'))
 _,before,_=http(CRM+'/stats'); cfg('http_500','create',1); (s,b,_),_=send('create_500'); clear(); _,after,_=http(CRM+'/stats'); check('CRM-create-500-retry',s==200 and row(b['execution_id']).startswith('success|1|') and after['contacts']==before['contacts']+1)
 cfg('http_409','create',1); (s,b,_),_=send('create_409'); clear(); check('CRM-create-409-reconcile',s==200 and b.get('status')=='success')
 cfg('ambiguous_create','create',1,3); (s,b,_),_=send('create_ambiguous'); clear(); check('CRM-create-ambiguous-reconcile',s==200 and b.get('status')=='success')
 existing=f'{prefix}-existing@example.com'; http(CRM+'/crm/contacts',{'lead':{'email':existing},'operation_key':prefix+':seed'},'POST'); cfg('http_500','update',1); (s,b,_),_=send('update_500',existing,first_name='Updated'); clear(); check('CRM-update-500-retry',s==200 and row(b['execution_id']).startswith('success|1|'))
 _,enrich_before,_=http((os.environ.get('ENRICHMENT_BASE_URL') or 'http://127.0.0.1:5682')+'/stats'); cfg('http_500','lookup',3); (s,b,text),terminal_email=send('exhaust'); clear(); _,enrich_after,_=http((os.environ.get('ENRICHMENT_BASE_URL') or 'http://127.0.0.1:5682')+'/stats'); check('CRM-three-attempts',s==502 and row(b['execution_id'])=='failed|2|upstream_error'); check('CRM-no-enrichment-on-failure',enrich_before==enrich_after); check('CRM-public-sanitized',all(x not in text for x in [terminal_email,KEY,CRM]))
 _,final,_=http(CRM+'/stats'); check('CRM-no-duplicates',final['contacts']==len(set([prefix+'-create_500@example.com',prefix+'-create_409@example.com',prefix+'-create_ambiguous@example.com',existing]))+before['contacts'])
finally:
 clear(); safe=[i for i in ids if i.startswith('lf_exec_') and i.replace('lf_exec_','').isalnum()]
 if safe:
  q=','.join("'"+i+"'" for i in safe); psql(f'DELETE FROM leadflow.execution_events WHERE execution_id IN ({q}); DELETE FROM leadflow.executions WHERE execution_id IN ({q});')
print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}"); sys.exit(0 if all(checks.values()) else 1)
