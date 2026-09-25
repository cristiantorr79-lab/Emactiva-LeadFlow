"""Continue a leased, CRM-reconciled execution through enrichment to a terminal state."""
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
import json,os,re,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def http(url,payload,method='POST',timeout=2):
 data=json.dumps(payload,separators=(',',':')).encode()
 try:
  with urlopen(Request(url,data=data,method=method,headers={'Content-Type':'application/json'}),timeout=timeout) as response:
   raw=response.read(); return response.status,dict(response.headers),json.loads(raw) if raw else {}
 except HTTPError as error:
  raw=error.read(); return error.code,dict(error.headers),json.loads(raw) if raw else {}
 except (URLError,TimeoutError): return 0,{},{}

def psql(sql):
 command=['docker','compose','exec','-T','-e',f"PGPASSWORD={os.environ['POSTGRES_PASSWORD']}",'postgres','psql','-X','-q','-At','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-U',os.environ['POSTGRES_USER'],'-d',os.environ['POSTGRES_DB'],'-c',sql]
 result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
 if result.returncode: raise RuntimeError(result.stderr.strip() or 'database operation failed')
 return result.stdout.strip()

def continue_recovery(execution_id,worker_id,enrichment_base=None,crm_base=None,slack_url=None):
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',execution_id) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',worker_id): raise ValueError('invalid recovery identifier')
 secret=os.environ.get('RECOVERY_CONTEXT_KEY','');
 if len(secret)<32: raise RuntimeError('RECOVERY_CONTEXT_KEY is missing or too short')
 context=psql("SELECT execution_id||'|'||coalesce(crm_contact_id,'')||'|'||retry_count||'|'||normalized_email FROM leadflow.get_recovery_crm_context('%s','%s','%s');"%(execution_id,worker_id,secret))
 if not context: raise RuntimeError('recovery context is unavailable or execution is terminal')
 _,contact_id,retry_text,email=context.split('|',3)
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',contact_id): raise RuntimeError('CRM reconciliation is incomplete')
 base_retry=int(retry_text); enrich=enrichment_base or os.environ.get('ENRICHMENT_BASE_URL') or 'http://127.0.0.1:5682'; crm=crm_base or os.environ.get('CRM_BASE_URL') or 'http://127.0.0.1:5683'
 delays=(5,15); last_type='upstream_error'; last_code='unknown'; data=None; attempts=0
 for attempt in range(1,4):
  attempts=attempt; status,headers,body=http(enrich+'/enrich',{'email':email})
  if 200<=status<300 and body.get('enrichment_status')=='success': data=body.get('data') or {}; break
  last_type='validation_error' if status==400 else 'authentication_error' if status==401 else 'rate_limit' if status==429 else 'timeout' if status==0 else 'upstream_error'
  last_code='timeout' if status==0 else 'http_'+str(status)
  retryable=status==0 or status==429 or status>=500
  if not retryable or attempt==3: break
  retry_after=float(headers.get('Retry-After',headers.get('retry-after',0)) or 0); time.sleep(max(delays[attempt-1],retry_after) if status==429 else delays[attempt-1])
 total_retry=base_retry+attempts-1
 if data is not None:
  allowed={name:data[name] for name in ('industry','company_size','website') if name in data}
  status,_,_=http(crm+'/crm/contacts/'+contact_id+'/enrichment',{'fields':allowed},'PATCH')
  if not 200<=status<300: data=None; last_type='upstream_error'; last_code='crm_enrichment_update'
 success=data is not None
 outcome=psql("SELECT execution_id||'|'||status||'|'||retry_count||'|'||coalesce(error_type,'') FROM leadflow.complete_recovery_enrichment('%s','%s',%d,%s,%s,%s);"%(execution_id,worker_id,total_retry,'true' if success else 'false','NULL' if success else "'%s'"%last_type,'NULL' if success else "'%s'"%last_code))
 alert_sent=None
 if not success:
  target=slack_url or os.environ.get('SLACK_WEBHOOK_URL') or 'http://127.0.0.1:5684/webhook'; status,_,_=http(target,{'execution_id':execution_id,'stage':'enrichment','error_code':last_code})
  alert_sent=200<=status<300
  psql("SELECT leadflow.record_alert_result('%s',%s,%s);"%(execution_id,'true' if alert_sent else 'false','NULL' if alert_sent else "'slack_delivery_failed'"))
 return {'execution_id':execution_id,'status':'success' if success else 'failed','retry_count':total_retry,'alert_sent':alert_sent,'outcome':outcome}
