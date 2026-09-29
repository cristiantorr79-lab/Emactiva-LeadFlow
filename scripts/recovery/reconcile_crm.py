"""Reconcile a leased recovery execution through the canonical CRM Adapter."""
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import argparse, json, os, re, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RECOVERY_DIR=Path(__file__).resolve().parent
if str(RECOVERY_DIR) not in sys.path: sys.path.insert(0,str(RECOVERY_DIR))
from recovery_runtime import RecoveryOperationalError,log_recovery_result,processing_max_age_seconds,psql,sql_text

def adapter_base(explicit=None):
 value=explicit or os.environ.get('RECOVERY_ADAPTER_URL','')
 if not value.startswith(('http://','https://')): raise RuntimeError('RECOVERY_ADAPTER_URL is missing or invalid')
 return value.rstrip('/')

def http(url,payload,method='POST'):
 data=json.dumps(payload,separators=(',',':')).encode()
 timeout=max(1,int(os.environ.get('ADAPTER_CALL_TIMEOUT_MS','30000')))/1000
 key=os.environ.get('ADAPTER_SERVICE_KEY','')
 if len(key)<32: raise RuntimeError('ADAPTER_SERVICE_KEY is missing or too short')
 try:
  with urlopen(Request(url,data=data,method=method,headers={'Content-Type':'application/json','X-LeadFlow-Adapter-Key':key}),timeout=timeout) as response:
   raw=response.read(); return response.status,json.loads(raw) if raw else {}
 except HTTPError as error:
  raw=error.read(); return error.code,json.loads(raw) if raw else {}
 except (URLError,TimeoutError): return 0,{}

def terminal_failure(execution_id,worker_id,retry_count,error_type='upstream_error',error_code='recovery_unexpected_error'):
 psql("SELECT * FROM leadflow.fail_recovery_crm(%s,%s,%d,%s,%s);"%(sql_text(execution_id),sql_text(worker_id),retry_count,sql_text(error_type),sql_text(error_code)))
 return {'execution_id':execution_id,'status':'failed','error_type':error_type,'error_code':error_code,'retry_count':retry_count}

def reconcile(execution_id,worker_id,adapter_url=None):
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',execution_id) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',worker_id): raise ValueError('invalid recovery identifier')
 secret=os.environ.get('RECOVERY_CONTEXT_KEY','')
 if len(secret)<32: raise RuntimeError('RECOVERY_CONTEXT_KEY is missing or too short')
 expired=psql("SELECT leadflow.expire_stale_recovery(%s,%s,%d);"%(sql_text(execution_id),sql_text(worker_id),processing_max_age_seconds()))
 if expired=='t':
  return {'execution_id':execution_id,'status':'failed','error_type':'timeout','error_code':'recovery_expired','retry_count':0}
 total_retry=0
 try:
  context=psql("SELECT execution_id||'|'||idempotency_key||'|'||coalesce(crm_contact_id,'')||'|'||retry_count||'|'||normalized_email FROM leadflow.get_recovery_crm_context(%s,%s,%s);"%(sql_text(execution_id),sql_text(worker_id),sql_text(secret)))
  if not context: raise RuntimeError('recovery_context_unavailable')
  _,idempotency_key,previous_contact,retry_text,normalized=context.split('|',4)
  total_retry=int(retry_text)
  status,body=http(adapter_base(adapter_url)+'/crm/process',{'email':normalized,'lead':{'email':normalized},'present_fields':{},'operation_key':idempotency_key+':crm_create'})
  adapter_retries=body.get('retry_count',0) if isinstance(body,dict) else 0
  total_retry+=(adapter_retries if isinstance(adapter_retries,int) else 0)
  if status!=200 or not body.get('success'):
   allowed={'validation_error','authentication_error','authorization_error','technical_not_found','conflict_error','rate_limit','timeout','network_error','upstream_error','ambiguous_create'}
   candidate=body.get('error_type','upstream_error') if isinstance(body,dict) else 'upstream_error'
   error_type=candidate if candidate in allowed else 'upstream_error'
   candidate=body.get('error_code','adapter_unavailable') if isinstance(body,dict) else 'adapter_unavailable'
   error_code=candidate if isinstance(candidate,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',candidate) else 'adapter_unavailable'
   return terminal_failure(execution_id,worker_id,total_retry,error_type,error_code)
  contact_id=body.get('contact_id'); action=body.get('crm_action')
  if not isinstance(contact_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',contact_id): raise RuntimeError('invalid_adapter_response')
  resolution='created' if action=='created' else 'reused'
  persisted=psql("SELECT execution_id||'|'||status||'|'||crm_contact_id||'|'||resolution||'|'||retry_count FROM leadflow.record_recovery_crm_adapter_reconciliation(%s,%s,%s,%s,%d);"%(sql_text(execution_id),sql_text(worker_id),sql_text(contact_id),sql_text(resolution),total_retry))
  return {'execution_id':execution_id,'status':'processing','contact_id':contact_id,'resolution':resolution,'retry_count':total_retry,'persisted':persisted,'previous_contact_id':previous_contact or None}
 except RecoveryOperationalError:
  raise
 except Exception:
  return terminal_failure(execution_id,worker_id,total_retry)

if __name__=='__main__':
 parser=argparse.ArgumentParser(); parser.add_argument('execution_id'); parser.add_argument('worker_id')
 args=parser.parse_args()
 try:
  result=reconcile(args.execution_id,args.worker_id)
 except RecoveryOperationalError as error:
  result={'status':'failed','stage':error.stage,'error_code':error.code}
  log_recovery_result(result)
  print(json.dumps(result,separators=(',',':'))); raise SystemExit(1)
 except Exception:
  result={'status':'failed','stage':'recovery','error_code':'recovery_unexpected_error'}
  log_recovery_result(result)
  print(json.dumps(result,separators=(',',':'))); raise SystemExit(1)
 log_recovery_result(result)
 print(json.dumps(result,separators=(',',':')))
