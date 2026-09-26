"""Continue leased recovery through canonical enrichment, CRM and alert adapters."""
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
import json,os,re,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def adapter_base(explicit=None):
 value=explicit or os.environ.get('RECOVERY_ADAPTER_URL','')
 if not value.startswith(('http://','https://')): raise RuntimeError('RECOVERY_ADAPTER_URL is missing or invalid')
 return value.rstrip('/')

def http(url,payload,method='POST'):
 data=json.dumps(payload,separators=(',',':')).encode(); timeout=max(1,int(os.environ.get('ADAPTER_CALL_TIMEOUT_MS','30000')))/1000
 try:
  with urlopen(Request(url,data=data,method=method,headers={'Content-Type':'application/json'}),timeout=timeout) as response:
   raw=response.read(); return response.status,json.loads(raw) if raw else {}
 except HTTPError as error:
  raw=error.read(); return error.code,json.loads(raw) if raw else {}
 except (URLError,TimeoutError): return 0,{}

def psql(sql):
 command=['docker','compose','exec','-T','-e',f"PGPASSWORD={os.environ['POSTGRES_PASSWORD']}",'postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-U',os.environ['POSTGRES_USER'],'-d',os.environ['POSTGRES_DB'],'-c',sql]
 result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
 if result.returncode: raise RuntimeError(result.stderr.strip() or 'database operation failed')
 return result.stdout.strip()

def sql_text(value): return "'"+value.replace("'","''")+"'"

def continue_recovery(execution_id,worker_id,adapter_url=None):
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',execution_id) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',worker_id): raise ValueError('invalid recovery identifier')
 secret=os.environ.get('RECOVERY_CONTEXT_KEY','')
 if len(secret)<32: raise RuntimeError('RECOVERY_CONTEXT_KEY is missing or too short')
 context=psql("SELECT execution_id||'|'||coalesce(crm_contact_id,'')||'|'||retry_count||'|'||normalized_email FROM leadflow.get_recovery_crm_context('%s','%s','%s');"%(execution_id,worker_id,secret))
 if not context: raise RuntimeError('recovery context is unavailable or execution is terminal')
 _,contact_id,retry_text,email=context.split('|',3)
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',contact_id): raise RuntimeError('CRM reconciliation is incomplete')
 base=adapter_base(adapter_url); base_retry=int(retry_text)
 status,enriched=http(base+'/enrichment/enrich',{'email':email})
 success=status==200 and enriched.get('success') is True
 adapter_retries=enriched.get('retry_count',0) if isinstance(enriched,dict) else 0
 total_retry=base_retry+(adapter_retries if isinstance(adapter_retries,int) else 0)
 error_type=enriched.get('error_type','upstream_error') if isinstance(enriched,dict) else 'upstream_error'
 error_code=enriched.get('error_code','adapter_unavailable') if isinstance(enriched,dict) else 'adapter_unavailable'
 failure_stage='enrichment'
 if success:
  status,applied=http(base+'/crm/update-enrichment/'+contact_id,{'fields':enriched.get('data') or {}},'PATCH')
  if status!=200:
   success=False; failure_stage='crm_enrichment_update'; error_type=(applied.get('error') or {}).get('type','upstream_error'); error_code='crm_enrichment_update'
 outcome=psql("SELECT execution_id||'|'||status||'|'||retry_count||'|'||coalesce(error_type,'') FROM leadflow.complete_recovery_adapter(%s,%s,%d,%s,%s,%s,%s);"%(sql_text(execution_id),sql_text(worker_id),total_retry,'true' if success else 'false','NULL' if success else sql_text(error_type),'NULL' if success else sql_text(error_code),sql_text(failure_stage)))
 alert_sent=None
 if not success:
  alert_status,alert=http(base+'/alert',{'execution_id':execution_id,'stage':failure_stage,'error_code':error_code})
  alert_sent=alert_status==200 and alert.get('delivered') is True
  psql("SELECT leadflow.record_alert_result(%s,%s,%s);"%(sql_text(execution_id),'true' if alert_sent else 'false','NULL' if alert_sent else "'slack_delivery_failed'"))
 return {'execution_id':execution_id,'status':'success' if success else 'failed','retry_count':total_retry,'alert_sent':alert_sent,'outcome':outcome}
