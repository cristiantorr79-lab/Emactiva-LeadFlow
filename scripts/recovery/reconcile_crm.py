"""Reconcile a leased recovery execution through the canonical CRM Adapter."""
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import argparse, json, os, re, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def adapter_base(explicit=None):
 value=explicit or os.environ.get('RECOVERY_ADAPTER_URL','')
 if not value.startswith(('http://','https://')): raise RuntimeError('RECOVERY_ADAPTER_URL is missing or invalid')
 return value.rstrip('/')

def http(url,payload,method='POST'):
 data=json.dumps(payload,separators=(',',':')).encode()
 timeout=max(1,int(os.environ.get('ADAPTER_CALL_TIMEOUT_MS','30000')))/1000
 try:
  with urlopen(Request(url,data=data,method=method,headers={'Content-Type':'application/json'}),timeout=timeout) as response:
   raw=response.read(); return response.status,json.loads(raw) if raw else {}
 except HTTPError as error:
  raw=error.read(); return error.code,json.loads(raw) if raw else {}
 except (URLError,TimeoutError): return 0,{}

def psql(sql):
 password=os.environ['POSTGRES_PASSWORD']; app=os.environ['POSTGRES_USER']; database=os.environ['POSTGRES_DB']
 command=['docker','compose','exec','-T','-e',f'PGPASSWORD={password}','postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-U',app,'-d',database,'-c',sql]
 result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
 if result.returncode: raise RuntimeError(result.stderr.strip() or 'database operation failed')
 return result.stdout.strip()

def sql_text(value): return "'"+value.replace("'","''")+"'"

def reconcile(execution_id,worker_id,adapter_url=None):
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',execution_id) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',worker_id): raise ValueError('invalid recovery identifier')
 secret=os.environ.get('RECOVERY_CONTEXT_KEY','')
 if len(secret)<32: raise RuntimeError('RECOVERY_CONTEXT_KEY is missing or too short')
 context=psql("SELECT execution_id||'|'||idempotency_key||'|'||coalesce(crm_contact_id,'')||'|'||retry_count||'|'||normalized_email FROM leadflow.get_recovery_crm_context('%s','%s','%s');"%(execution_id,worker_id,secret))
 if not context: raise RuntimeError('encrypted recovery context is unavailable or lease is invalid')
 _,idempotency_key,previous_contact,retry_text,normalized=context.split('|',4)
 status,body=http(adapter_base(adapter_url)+'/crm/process',{'email':normalized,'lead':{'email':normalized},'present_fields':{},'operation_key':idempotency_key+':crm_create'})
 adapter_retries=body.get('retry_count',0) if isinstance(body,dict) else 0
 total_retry=int(retry_text)+(adapter_retries if isinstance(adapter_retries,int) else 0)
 if status!=200 or not body.get('success'):
  error_type=body.get('error_type','upstream_error') if isinstance(body,dict) else 'upstream_error'
  error_code=body.get('error_code','adapter_unavailable') if isinstance(body,dict) else 'adapter_unavailable'
  psql("SELECT * FROM leadflow.fail_recovery_crm(%s,%s,%d,%s,%s);"%(sql_text(execution_id),sql_text(worker_id),total_retry,sql_text(error_type),sql_text(error_code)))
  return {'execution_id':execution_id,'status':'failed','error_type':error_type,'error_code':error_code,'retry_count':total_retry}
 contact_id=body.get('contact_id'); action=body.get('crm_action')
 if not isinstance(contact_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',contact_id): raise RuntimeError('CRM Adapter returned an invalid contact identifier')
 resolution='created' if action=='created' else 'reused'
 persisted=psql("SELECT execution_id||'|'||status||'|'||crm_contact_id||'|'||resolution||'|'||retry_count FROM leadflow.record_recovery_crm_adapter_reconciliation(%s,%s,%s,%s,%d);"%(sql_text(execution_id),sql_text(worker_id),sql_text(contact_id),sql_text(resolution),total_retry))
 return {'execution_id':execution_id,'status':'processing','contact_id':contact_id,'resolution':resolution,'retry_count':total_retry,'persisted':persisted,'previous_contact_id':previous_contact or None}

if __name__=='__main__':
 parser=argparse.ArgumentParser(); parser.add_argument('execution_id'); parser.add_argument('worker_id')
 args=parser.parse_args(); print(json.dumps(reconcile(args.execution_id,args.worker_id),separators=(',',':')))
