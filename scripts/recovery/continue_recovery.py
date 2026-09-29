"""Continue leased recovery through canonical enrichment, CRM and alert adapters."""
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
import argparse,json,os,re,sys
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
 data=json.dumps(payload,separators=(',',':')).encode(); timeout=max(1,int(os.environ.get('ADAPTER_CALL_TIMEOUT_MS','30000')))/1000
 key=os.environ.get('ADAPTER_SERVICE_KEY','')
 if len(key)<32: raise RuntimeError('ADAPTER_SERVICE_KEY is missing or too short')
 try:
  with urlopen(Request(url,data=data,method=method,headers={'Content-Type':'application/json','X-LeadFlow-Adapter-Key':key}),timeout=timeout) as response:
   raw=response.read(); return response.status,json.loads(raw) if raw else {}
 except HTTPError as error:
  raw=error.read(); return error.code,json.loads(raw) if raw else {}
 except (URLError,TimeoutError): return 0,{}

def terminal_failure(execution_id,worker_id,retry_count):
 psql("SELECT execution_id||'|'||status FROM leadflow.complete_recovery_adapter(%s,%s,%d,false,'upstream_error','recovery_unexpected_error','enrichment');"%(sql_text(execution_id),sql_text(worker_id),retry_count))
 return {'execution_id':execution_id,'status':'failed','retry_count':retry_count,'alert_sent':None,'error_type':'upstream_error','error_code':'recovery_unexpected_error'}

def continue_recovery(execution_id,worker_id,adapter_url=None):
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',execution_id) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',worker_id): raise ValueError('invalid recovery identifier')
 secret=os.environ.get('RECOVERY_CONTEXT_KEY','')
 if len(secret)<32: raise RuntimeError('RECOVERY_CONTEXT_KEY is missing or too short')
 expired=psql("SELECT leadflow.expire_stale_recovery(%s,%s,%d);"%(sql_text(execution_id),sql_text(worker_id),processing_max_age_seconds()))
 if expired=='t':
  return {'execution_id':execution_id,'status':'failed','retry_count':0,'alert_sent':None,'error_type':'timeout','error_code':'recovery_expired'}
 total_retry=0
 try:
  context=psql("SELECT execution_id||'|'||coalesce(crm_contact_id,'')||'|'||retry_count||'|'||normalized_email FROM leadflow.get_recovery_crm_context(%s,%s,%s);"%(sql_text(execution_id),sql_text(worker_id),sql_text(secret)))
  if not context: raise RuntimeError('recovery_context_unavailable')
  _,contact_id,retry_text,email=context.split('|',3)
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',contact_id): raise RuntimeError('recovery_reconciliation_incomplete')
  base=adapter_base(adapter_url); base_retry=int(retry_text)
  status,enriched=http(base+'/enrichment/enrich',{'email':email})
  success=status==200 and enriched.get('success') is True
  adapter_retries=enriched.get('retry_count',0) if isinstance(enriched,dict) else 0
  total_retry=base_retry+(adapter_retries if isinstance(adapter_retries,int) else 0)
  allowed={'validation_error','authentication_error','authorization_error','technical_not_found','conflict_error','rate_limit','timeout','network_error','upstream_error'}
  candidate=enriched.get('error_type','upstream_error') if isinstance(enriched,dict) else 'upstream_error'
  error_type=candidate if candidate in allowed else 'upstream_error'
  candidate=enriched.get('error_code','adapter_unavailable') if isinstance(enriched,dict) else 'adapter_unavailable'
  error_code=candidate if isinstance(candidate,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',candidate) else 'adapter_unavailable'
  failure_stage='enrichment'
  if success:
   status,applied=http(base+'/crm/update-enrichment/'+contact_id,{'fields':enriched.get('data') or {}},'PATCH')
   if status!=200:
    success=False; failure_stage='crm_enrichment_update'; error_type='upstream_error'; error_code='crm_enrichment_update'
  outcome=psql("SELECT execution_id||'|'||status||'|'||retry_count||'|'||coalesce(error_type,'') FROM leadflow.complete_recovery_adapter(%s,%s,%d,%s,%s,%s,%s);"%(sql_text(execution_id),sql_text(worker_id),total_retry,'true' if success else 'false','NULL' if success else sql_text(error_type),'NULL' if success else sql_text(error_code),sql_text(failure_stage)))
  alert_sent=None
  if not success:
   alert_status,alert=http(base+'/alert',{'execution_id':execution_id,'stage':failure_stage,'error_code':error_code})
   alert_sent=alert_status==200 and alert.get('delivered') is True
   psql("SELECT leadflow.record_alert_result(%s,%s,%s);"%(sql_text(execution_id),'true' if alert_sent else 'false','NULL' if alert_sent else "'slack_delivery_failed'"))
  return {'execution_id':execution_id,'status':'success' if success else 'failed','retry_count':total_retry,'alert_sent':alert_sent,'outcome':outcome}
 except RecoveryOperationalError:
  raise
 except Exception:
  return terminal_failure(execution_id,worker_id,total_retry)

if __name__=='__main__':
 parser=argparse.ArgumentParser(); parser.add_argument('execution_id'); parser.add_argument('worker_id')
 args=parser.parse_args()
 try:
  result=continue_recovery(args.execution_id,args.worker_id)
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
