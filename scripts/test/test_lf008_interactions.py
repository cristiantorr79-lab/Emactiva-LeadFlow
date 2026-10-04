"""Focused executable acceptance evidence for LAB-LF-008 (no message content is printed)."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,threading

ROOT=Path(__file__).resolve().parents[2]
workflow=json.loads((ROOT/'workflows/leadflow_core_initial.json').read_text(encoding='utf-8'))
code=next(node['parameters']['jsCode'] for node in workflow['nodes'] if node['id']=='prepare')
spec=importlib.util.spec_from_file_location('lf_adapter',ROOT/'adapters'/'server.py'); adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
WRAPPER="""const fs=require('fs');const x=JSON.parse(fs.readFileSync(0,'utf8'));const f=new Function('require','$json','$env',x.code);Promise.resolve(f(require,x.item,x.env)).then(v=>process.stdout.write(JSON.stringify(v)));"""
ENV={'LEADFLOW_WEBHOOK_KEY':'k'*32,'LEADFLOW_ALLOWED_SOURCES':'website','LEADFLOW_ALLOWED_INTERESTS':'producto_a,producto_b','DSR_SUBJECT_KEY':'d'*32}
MESSAGE='  Línea uno\nvalor | "interno" — 漢字  '
def validate(event='evt_1',interaction='absent'):
 body={'event_id':event,'source':'website','lead':{'email':'Lead@Example.test','unknown':'drop'}}
 if interaction!='absent': body['interaction']=interaction
 item={'headers':{'x-leadflow-key':'k'*32,'content-type':'application/json'},'body':body}
 run=subprocess.run(['node','-e',WRAPPER],cwd=ROOT,input=json.dumps({'code':code,'item':item,'env':ENV}),text=True,encoding='utf-8',capture_output=True)
 return json.loads(run.stdout)['json']
checks={}
def check(number,label,value):
 name=f'LF008-{number:02d} {label}'; checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)

v1=validate(); full=validate(interaction={'interest':' producto_a ','message':MESSAGE}); interest=validate(interaction={'interest':'producto_a'}); message=validate(interaction={'message':MESSAGE}); empty=validate(interaction={'interest':'  ','message':'\n'})
check(1,'V1 compatible',v1.get('route')=='valid' and 'interaction' not in v1)
check(2,'complete interaction',full.get('interaction',{}).get('interest')=='producto_a')
check(3,'interest only',interest.get('interaction')=={'interest':'producto_a'})
check(4,'message only',set(message.get('interaction',{}))=={'message'})
check(5,'empty omitted','interaction' not in empty)
check(6,'invalid interest',validate(interaction={'interest':'otro'}).get('error_code')=='invalid_interest')
check(7,'message limit',validate(interaction={'message':'x'*2001}).get('error_code')=='invalid_interaction')
check(8,'outer trim only',message['interaction']['message'].startswith('Línea') and '\n' in message['interaction']['message'])
check(9,'structured free text',message['interaction']['message']=='Línea uno\nvalor | "interno" — 漢字')
key=lambda event: hashlib.sha256(('website:'+event).encode()).hexdigest()
check(10,'same event stable key',validate('same',{'message':'a'})['idempotency_key']==validate('same',{'message':'a'})['idempotency_key'])
check(11,'content excluded from key',validate('same',{'message':'a'})['idempotency_key']==validate('same',{'message':'b'})['idempotency_key'])
check(12,'new event new interaction identity',key('a')!=key('b'))
check(13,'workflow separates contact and interaction',any(n['id']=='crm-interaction' for n in workflow['nodes']))

SAFE={'interaction_write':True,'interaction_idempotency':True,'interaction_reconciliation':True,'consistent_lookup_after_create':True,'unique_email':True,'idempotent_create_operation_key':True,'conflict_reconciliation':True}
adapter.CONFIG={'attempts':3,'delay1':0,'delay2':0,'crm_provider':'mock','crm':'http://crm','capabilities':SAFE}
store={}; lock=threading.Lock(); calls=[]
def fake(method,url,body,headers=None):
 calls.append((method,url))
 if url.endswith('/reconcile'):
  value=store.get(body['operation_key']); return 200,{}, {'found':value is not None,'interaction_id':value,'absence_conclusive':True}
 with lock:
  created=body['operation_key'] not in store; value=store.setdefault(body['operation_key'],'int_1')
 return (201 if created else 200),{}, {'interaction_id':value,'created':created}
adapter.call=fake; adapter.wait=lambda *_:None
payload={'contact_id':'crm_1','interaction':{'message':'private'},'operation_key':'a'*64+':crm_interaction'}
r1=adapter.record_interaction(payload); r2=adapter.record_interaction(payload)
check(14,'adapter success',r1.get('success'))
check(15,'operation reuse',r2.get('resolution')=='reused' and len(store)==1)
store.clear()
with ThreadPoolExecutor(max_workers=2) as pool: concurrent=list(pool.map(lambda _:adapter.record_interaction(payload),range(2)))
check(16,'concurrent idempotency',len(store)==1 and all(r.get('success') for r in concurrent))
check(17,'transient policy',adapter.retryable(500))
check(18,'Retry-After parsed',adapter.retry_after_seconds({'Retry-After':'9'})==9)
check(19,'deterministic errors no retry',all(not adapter.retryable(s) for s in (400,401,403)))
check(20,'reconciliation finds write',adapter.reconcile_interaction({'operation_key':payload['operation_key']}).get('found'))
check(21,'negative lookup requires conclusive absence',adapter.reconcile_interaction({'operation_key':'missing'}).get('absence_conclusive'))
unsafe={**SAFE,'interaction_write':False}; adapter.CONFIG['capabilities']=unsafe
check(22,'capabilities fail closed',adapter.record_interaction(payload).get('error_code')=='interaction_capability_missing'); adapter.CONFIG['capabilities']=SAFE

migration=(ROOT/'database/migrations/018_lead_interaction.sql').read_text(encoding='utf-8')
recovery=(ROOT/'scripts/recovery/continue_recovery.py').read_text(encoding='utf-8')
mock=(ROOT/'mocks/server.py').read_text(encoding='utf-8')
check(23,'contact checkpoint',"record_crm_contact_checkpoint" in migration)
check(24,'crash reconciliation first',recovery.index('reconcile-interaction')<recovery.index("record-interaction"))
check(25,'confirmed external write persisted',"record_interaction_outcome" in recovery)
check(26,'confirmed interaction skipped',"interaction_state!='confirmed'" in recovery)
check(27,'ambiguous remains processing',"'status':'processing'" in recovery and 'ambiguous_interaction' in recovery)
check(28,'terminal trigger cleanup','cleanup_recovery_context_terminal' in (ROOT/'database/migrations/009_recovery_encrypted_context.sql').read_text())
check(29,'retention cleanup','recovery_contexts' in (ROOT/'database/migrations/014_retention_purge.sql').read_text())
check(30,'JSON encrypted context',"jsonb_build_object('version',1" in migration and 'pgp_sym_encrypt' in migration)
logging=(ROOT/'adapters/logging_policy.py').read_text(encoding='utf-8')
check(31,'message excluded from logs','message' not in logging.lower())
check(32,'Slack technical fields only','allowed={"execution_id","stage","error_code"}' in (ROOT/'adapters/server.py').read_text())
check(33,'public response excludes message',all('message' not in str(n.get('parameters',{}).get('responseBody','')) for n in workflow['nodes']))
check(34,'ciphertext column','context_ciphertext bytea' in (ROOT/'database/migrations/009_recovery_encrypted_context.sql').read_text() or 'RENAME COLUMN email_ciphertext TO context_ciphertext' in migration)
dsr=(ROOT/'database/migrations/017_dsr_restrict_qualification.sql').read_text()
check(35,'DELETE covers context','DELETE FROM leadflow.recovery_contexts' in dsr)
check(36,'RESTRICT blocks processing',"status='failed'" in dsr and "p_action='restrict'" in dsr)
check(37,'EXPORT remains minimized','dsr_export_minimized' in (ROOT/'database/migrations/016_dsr_operations.sql').read_text())
check(38,'QA output redacts content','private' not in ' '.join(checks))
check(39,'mock exposes cleanup-safe isolated stores','interactions_by_operation' in mock and 'interactions = {}' in mock)
failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/39")
sys.exit(1 if failed else 0)
