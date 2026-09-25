"""Manual F2a CRM reconciliation for one execution already claimed by recovery."""
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import argparse, json, os, re, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def http(url,payload,timeout=2):
 data=json.dumps(payload,separators=(',',':')).encode()
 try:
  with urlopen(Request(url,data=data,method='POST',headers={'Content-Type':'application/json'}),timeout=timeout) as response:
   return response.status,json.loads(response.read())
 except HTTPError as error:
  return error.code,json.loads(error.read())
 except (URLError,TimeoutError):
  return 0,{}

def psql(sql):
 password=os.environ['POSTGRES_PASSWORD']; app=os.environ['POSTGRES_USER']; database=os.environ['POSTGRES_DB']
 command=['docker','compose','exec','-T','-e',f'PGPASSWORD={password}','postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-U',app,'-d',database,'-c',sql]
 result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
 if result.returncode: raise RuntimeError(result.stderr.strip() or 'database operation failed')
 return result.stdout.strip()

def reconcile(execution_id,worker_id,crm_base=None):
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',execution_id) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',worker_id):
  raise ValueError('invalid recovery identifier')
 secret=os.environ.get('RECOVERY_CONTEXT_KEY','')
 if len(secret)<32: raise RuntimeError('RECOVERY_CONTEXT_KEY is missing or too short')
 context=psql("SELECT execution_id||'|'||idempotency_key||'|'||coalesce(crm_contact_id,'')||'|'||retry_count||'|'||normalized_email FROM leadflow.get_recovery_crm_context('%s','%s','%s');"%(execution_id,worker_id,secret))
 if not context: raise RuntimeError('encrypted recovery context is unavailable or lease is invalid')
 _,idempotency_key,previous_contact,retry_count,normalized=context.split('|',4)
 base=crm_base or os.environ.get('CRM_BASE_URL') or 'http://127.0.0.1:5683'
 status,body=http(base+'/crm/lookup',{'email':normalized})
 if status!=200: raise RuntimeError('CRM lookup failed')
 resolution='reused'; contact_id=body.get('contact',{}).get('id') if body.get('found') else None
 if not contact_id:
  operation_key=idempotency_key+':crm_create'
  status,body=http(base+'/crm/contacts',{'lead':{'email':normalized},'operation_key':operation_key})
  contact_id=body.get('contact_id') if status in (200,201) else None; resolution='created'
  if not contact_id:
   status,body=http(base+'/crm/lookup',{'email':normalized})
   contact_id=body.get('contact',{}).get('id') if status==200 and body.get('found') else None
  if not contact_id: raise RuntimeError('CRM CREATE outcome remains ambiguous')
 if not isinstance(contact_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',contact_id):
  raise RuntimeError('CRM returned an invalid contact identifier')
 persisted=psql("SELECT execution_id||'|'||status||'|'||crm_contact_id||'|'||resolution||'|'||retry_count FROM leadflow.record_recovery_crm_reconciliation('%s','%s','%s','%s');"%(execution_id,worker_id,contact_id,resolution))
 return {'execution_id':execution_id,'contact_id':contact_id,'resolution':resolution,'retry_count':int(retry_count),'persisted':persisted}

if __name__=='__main__':
 parser=argparse.ArgumentParser(); parser.add_argument('execution_id'); parser.add_argument('worker_id')
 args=parser.parse_args(); print(json.dumps(reconcile(args.execution_id,args.worker_id),separators=(',',':')))
