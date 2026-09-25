"""E1: sanitized alerts after definitive CRM or enrichment failures."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json, os, secrets, subprocess, sys

ROOT=Path(__file__).resolve().parents[2]
WEBHOOK=f"http://127.0.0.1:{os.environ.get('N8N_PORT','5680')}/webhook/leadflow"
CRM=os.environ.get('CRM_BASE_URL') or 'http://127.0.0.1:5683'
ENRICH=os.environ.get('ENRICHMENT_BASE_URL') or 'http://127.0.0.1:5682'
SLACK=os.environ.get('SLACK_MOCK_URL') or 'http://127.0.0.1:5684'
KEY=os.environ.get('LEADFLOW_WEBHOOK_KEY',''); DB=os.environ.get('POSTGRES_DB','')
prefix='alert_'+secrets.token_hex(5); ids=[]; checks={}

def http(url,p=None,method='GET',webhook=False,timeout=70):
 data=None if p is None else json.dumps(p,separators=(',',':')).encode(); headers={'Content-Type':'application/json'}
 if webhook: headers['X-LeadFlow-Key']=KEY
 try:
  with urlopen(Request(url,data=data,method=method,headers=headers),timeout=timeout) as r:
   text=r.read().decode(); return r.status,json.loads(text),text
 except HTTPError as e:
  text=e.read().decode(); return e.code,json.loads(text),text

def cfg(base,mode,operation): return http(base+'/control/failure',{'mode':mode,'operation':operation},'POST')
def clear():
 for base in (CRM,ENRICH,SLACK): http(base+'/control/failure',method='DELETE')
 http(SLACK+'/alerts',method='DELETE')
def send(label):
 email=f'{prefix}-{label}@example.com'; payload={'event_id':f'{prefix}_{label}','source':'website','lead':{'email':email,'first_name':'Private','phone':'+56911111111'}}
 result=http(WEBHOOK,payload,'POST',True); ids.append(result[1].get('execution_id','')); return result,email
def psql(sql):
 r=subprocess.run(['docker','compose','exec','-T','postgres','psql','-X','-q','-U','leadflow_migrator','-d',DB,'-Atc',sql],cwd=ROOT,capture_output=True,text=True)
 assert r.returncode==0,r.stderr; return r.stdout.strip()
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)

try:
 clear(); cfg(CRM,'http_400','lookup'); (status,body,_),email=send('crm'); stats=http(SLACK+'/stats')[1]; clear()
 check('ALERT-CRM',status==502 and body.get('status')=='failed' and stats['alert_count']==1 and stats['last_alert']=={'execution_id':body.get('execution_id'),'stage':'crm_lookup','error_code':'http_400'})
 serialized=json.dumps(stats); check('ALERT-PRIVACY',all(value not in serialized for value in [email,'Private','+56911111111',KEY]))

 cfg(ENRICH,'http_400','enrich'); (status,body,_),_=send('enrichment'); stats=http(SLACK+'/stats')[1]; clear()
 check('ALERT-ENRICHMENT',status==502 and body.get('status')=='failed' and stats['alert_count']==1 and stats['last_alert']['stage']=='enrichment' and stats['last_alert']['error_code']=='http_400')

 (status,body,_),_=send('success'); stats=http(SLACK+'/stats')[1]
 check('ALERT-NONE-SUCCESS',status==200 and body.get('status')=='success' and stats['alert_count']==0)
 duplicate=http(WEBHOOK,{'event_id':f'{prefix}_success','source':'website','lead':{'email':f'{prefix}-success@example.com'}},'POST',True)
 ids.append(duplicate[1].get('execution_id',''))
 stats=http(SLACK+'/stats')[1]; check('ALERT-NONE-DUPLICATE',duplicate[1].get('status')=='duplicate' and stats['alert_count']==0)

 clear(); cfg(CRM,'http_400','lookup'); cfg(SLACK,'http_500','alert'); (status,body,_),_=send('slack_failure'); stats=http(SLACK+'/stats')[1]
 execution_id=body.get('execution_id'); db=psql("SELECT status||'|'||error_type||'|'||error_code FROM leadflow.executions WHERE execution_id='%s';"%execution_id)
 alert_event=psql("SELECT count(*)||'|'||coalesce(max(error_code),'') FROM leadflow.execution_events WHERE execution_id='%s' AND stage='alert';"%execution_id)
 check('ALERT-FAILURE-PRESERVES-MAIN',status==502 and db=='failed|validation_error|http_400' and alert_event=='1|slack_delivery_failed')
 check('ALERT-NO-RECURSION',stats['calls']['alert']==1 and stats['alert_count']==0)
finally:
 clear(); safe=[i for i in ids if i.startswith('lf_exec_') and i.replace('lf_exec_','').isalnum()]
 if safe:
  values=','.join("'"+i+"'" for i in safe); psql(f'DELETE FROM leadflow.execution_events WHERE execution_id IN ({values}); DELETE FROM leadflow.executions WHERE execution_id IN ({values}) AND status=\'duplicate\'; DELETE FROM leadflow.executions WHERE execution_id IN ({values});')
print(f"RESULT: {'PASS' if all(checks.values()) else 'FAIL'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(0 if all(checks.values()) else 1)
