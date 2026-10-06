"""LF-002.5 HubSpot/Hunter adapter tests with fully synthetic upstream responses."""
from pathlib import Path
import importlib.util,sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('adapter_provider',ROOT/'adapters'/'server.py'); adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
checks={}; calls=[]; waits=[]; HUB_KEY='synthetic-hub-key'; HUNTER_KEY='synthetic-hunter-key'; AUTH={'ADAPTER_SERVICE_KEY':'a'*32,'ADAPTER_ALLOWED_OPERATIONS':'crm.process,crm.update_enrichment,enrichment.enrich,alert.send,crm.capabilities'}
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)
def config(crm='hubspot',enrichment='hunter'):
 env={**AUTH,'APP_ENV':'development','CRM_PROVIDER':crm,'ENRICHMENT_PROVIDER':enrichment,'CRM_UPSTREAM_URL':'http://hub.test','ENRICHMENT_UPSTREAM_URL':'http://hunter.test','CRM_API_KEY':HUB_KEY,'ENRICHMENT_API_KEY':HUNTER_KEY,'HUBSPOT_TICKET_PIPELINE_ID':'pipeline-test','HUBSPOT_TICKET_STAGE_ID':'stage-test','HUBSPOT_TICKET_INTEREST_PROPERTY':'leadflow_interest'}
 adapter.CONFIG=adapter.load_config(env); calls.clear(); waits.clear()
def scripted(items):
 calls.clear(); waits.clear(); sequence=list(items)
 def fake(method,url,body=None,headers=None): calls.append((method,url,body,headers or {})); item=sequence.pop(0); return item(method,url,body,headers or {}) if callable(item) else item
 adapter.call=fake
def no_wait(headers,status,attempt): waits.append((status,adapter.retry_after_seconds(headers)))
adapter.wait=no_wait
def ok(body): return 200,{},body
def err(status,headers=None,body=None): return status,headers or {},body or {}
def lead(): return {'email':'synthetic@example.invalid','lead':{'email':'synthetic@example.invalid','first_name':'Ada','last_name':'Test','phone':'000','company':'Synthetic'},'present_fields':{'first_name':'Ada'},'operation_key':'stable-operation'}

config(); check('HUB-001 provider selected',adapter.CONFIG['crm_provider']=='hubspot')
check('HUB-002 conservative capabilities',adapter.CONFIG['capabilities']==adapter.HUBSPOT_CAPABILITIES and not adapter.safe_ambiguous_create_retry(adapter.CONFIG['capabilities']))
scripted([ok({'results':[{'id':'101','properties':{'email':'synthetic@example.invalid'}}]})]); found=adapter.crm_lookup('synthetic@example.invalid')
check('HUB-003 lookup found',found[2].get('found') and found[2]['contact']['id']=='101')
check('HUB-003b lookup v3 endpoint',calls[0][1]=='http://hub.test/crm/v3/objects/contacts/search')
check('HUB-004 bearer authentication',calls[0][3].get('Authorization')=='Bearer '+HUB_KEY and HUB_KEY not in calls[0][1])
scripted([ok({'results':[]})]); check('HUB-005 lookup not found',adapter.crm_lookup('synthetic@example.invalid')[2]=={'found':False})
scripted([(201,{}, {'id':'102'})]); created=adapter.crm_create(lead()['lead'],'stable-operation')
check('HUB-006 create success',created[2].get('contact_id')=='102' and calls[0][2]['properties']['email']=='synthetic@example.invalid')
check('HUB-006b create v3 endpoint',calls[0][1]=='http://hub.test/crm/v3/objects/contacts')
check('HUB-007 minimized create fields',set(calls[0][2]['properties'])=={'email','firstname','lastname','phone','company'} and 'operation_key' not in str(calls[0][2]))
scripted([ok({'id':'101'})]); adapter.crm_update('101',{'first_name':'Grace'})
check('HUB-008 update success',calls[0][0]=='PATCH' and calls[0][2]=={'properties':{'firstname':'Grace'}})
check('HUB-008b update v3 endpoint',calls[0][1]=='http://hub.test/crm/v3/objects/contacts/101')
scripted([ok({'id':'101'})]); adapter.crm_update('101',{'industry':'software','company_size':'11-50','website':'https://example.invalid'},True)
check('HUB-009 enrichment update',calls[0][2]=={'properties':{'industry':'software','leadflow_company_size':'11-50','website':'https://example.invalid'}})
for name,status,kind in (('HUB-010 401 permanent',401,'authentication_error'),('HUB-011 403 permanent',403,'authorization_error')):
 scripted([err(status)]); result=adapter.crm_process(lead()); check(name,result.get('error_type')==kind and result.get('retry_count')==0)
scripted([err(429,{'Retry-After':'8'}),err(429,{'Retry-After':'8'}),err(429,{'Retry-After':'8'})]); rate=adapter.crm_process(lead())
check('HUB-012 429 Retry-After',rate.get('error_type')=='rate_limit' and rate.get('retry_after_seconds')==8 and rate.get('retry_count')==2)
scripted([err(500),ok({'results':[{'id':'101','properties':{'email':'synthetic@example.invalid'}}]}),ok({'id':'101'})]); temporary=adapter.crm_process(lead())
check('HUB-013 5xx retry',temporary.get('success') and temporary.get('retry_count')==1)
scripted([err(0),ok({'results':[{'id':'101','properties':{'email':'synthetic@example.invalid'}}]}),ok({'id':'101'})]); timeout=adapter.crm_process(lead())
check('HUB-014 timeout retry',timeout.get('success') and timeout.get('retry_count')==1)
scripted([ok({'unexpected':[]})]); invalid=adapter.crm_process(lead())
check('HUB-015 invalid response',invalid.get('error_code')=='http_422')
scripted([ok({'results':[]} ),err(0),ok({'results':[]})]); ambiguous=adapter.crm_process(lead())
check('HUB-016 ambiguous no unsafe retry',ambiguous.get('error_type')=='ambiguous_create' and len([c for c in calls if c[1].endswith('/contacts')])==1)
scripted([ok({'results':[]}),err(409),ok({'results':[{'id':'reconciled','properties':{'email':'synthetic@example.invalid'}}]})]); reconciled=adapter.crm_process(lead())
check('HUB-017 conflict reconciliation',reconciled.get('success') and reconciled.get('contact_id')=='reconciled')
check('HUB-018 no key leakage',HUB_KEY not in str(ambiguous)+str(reconciled))

config(); check('HUNTER-001 provider selected',adapter.CONFIG['enrichment_provider']=='hunter')
hunter_response={'data':{'person':{'name':'Discard Me','phone':'secret'},'company':{'domain':'example.invalid','category':{'industry':'Software'},'metrics':{'employeesRange':'11-50'},'socials':['discard']}}}
scripted([ok(hunter_response)]); enriched=adapter.enrich({'email':'synthetic@example.invalid','company':'Synthetic'})
check('HUNTER-002 enrichment success',enriched.get('success') and enriched.get('enrichment_status')=='success')
check('HUNTER-003 secure header',calls[0][3].get('X-API-KEY')==HUNTER_KEY and HUNTER_KEY not in calls[0][1])
check('HUNTER-004 whitelist mapping',enriched.get('data')=={'industry':'Software','company_size':'11-50','website':'https://example.invalid'})
check('HUNTER-005 raw payload discarded',all(token not in str(enriched) for token in ('Discard Me','phone','socials')))
scripted([err(404)]); nodata=adapter.enrich({'email':'synthetic@example.invalid'})
check('HUNTER-006 no data success empty',nodata.get('success') and nodata.get('data')=={})
scripted([err(400,body={'errors':[{'id':'invalid_email','details':'The supplied email address belongs to a webmail.'}]})]); webmail=adapter.enrich({'email':'person@example.invalid'})
check('HUNTER-006A invalid email success empty',webmail.get('success') and webmail.get('data')=={})
check('HUNTER-006B invalid email sanitized',all(token not in str(webmail) for token in ('details','webmail')))
scripted([err(400,body={'errors':[{'id':'invalid_parameter','details':'Synthetic upstream detail'}]})]); other_bad_request=adapter.enrich({'email':'synthetic@example.invalid'})
check('HUNTER-006C other 400 remains failure',not other_bad_request.get('success') and other_bad_request.get('error_type')=='validation_error' and all(token not in str(other_bad_request) for token in ('invalid_parameter','Synthetic upstream detail')))
for name,status,kind in (('HUNTER-007 authentication',401,'authentication_error'),('HUNTER-008 legal privacy',451,'authorization_error')):
 scripted([err(status)]); result=adapter.enrich({'email':'synthetic@example.invalid'}); check(name,result.get('error_type')==kind and result.get('retry_count')==0)
scripted([err(403),err(403),err(403)]); hunter_rate=adapter.enrich({'email':'synthetic@example.invalid'})
check('HUNTER-009 documented rate limit',hunter_rate.get('error_type')=='rate_limit' and hunter_rate.get('retry_count')==2)
scripted([err(429,{'Retry-After':'12'}),err(429,{'Retry-After':'12'}),err(429,{'Retry-After':'12'})]); rate=adapter.enrich({'email':'synthetic@example.invalid'})
check('HUNTER-010 Retry-After',rate.get('retry_after_seconds')==12 and waits[0]==(429,12.0))
scripted([err(429,body={'errors':[{'id':'usage_limit','details':'Usage limit reached'}]})]); quota=adapter.enrich({'email':'synthetic@example.invalid'})
check('HUNTER-011 quota permanent',quota.get('error_code')=='quota_exhausted' and quota.get('retry_count')==0)
scripted([err(500),ok(hunter_response)]); check('HUNTER-012 5xx retry',adapter.enrich({'email':'synthetic@example.invalid'}).get('retry_count')==1)
scripted([err(0),ok(hunter_response)]); check('HUNTER-013 timeout retry',adapter.enrich({'email':'synthetic@example.invalid'}).get('retry_count')==1)
scripted([ok({'unexpected':{}})]); malformed=adapter.enrich({'email':'synthetic@example.invalid'})
check('HUNTER-014 invalid response',malformed.get('error_code')=='invalid_response')
check('HUNTER-015 no key leakage',HUNTER_KEY not in str(enriched)+str(quota)+str(malformed))

production={**AUTH,'APP_ENV':'production','CRM_PROVIDER':'hubspot','ENRICHMENT_PROVIDER':'hunter','CRM_UPSTREAM_URL':'https://api.hubapi.com','ENRICHMENT_UPSTREAM_URL':'https://api.hunter.io','ALERT_UPSTREAM_URL':'https://hooks.example.invalid','CRM_API_KEY':'synthetic','ENRICHMENT_API_KEY':'synthetic','HUBSPOT_TICKET_PIPELINE_ID':'pipeline-test','HUBSPOT_TICKET_STAGE_ID':'stage-test','HUBSPOT_TICKET_INTEREST_PROPERTY':'leadflow_interest'}
check('CONFIG-001 production providers valid',adapter.load_config(production)['crm_provider']=='hubspot')
for name,key in (('CONFIG-002 missing HubSpot key','CRM_API_KEY'),('CONFIG-003 missing Hunter key','ENRICHMENT_API_KEY')):
 try: adapter.load_config({k:v for k,v in production.items() if k!=key}); failed=False
 except ValueError: failed=True
 check(name,failed)
try: adapter.load_config({**production,'CRM_PROVIDER':'mock'}); mock_fallback=False
except ValueError: mock_fallback=True
check('CONFIG-004 no production mock fallback',mock_fallback)
check('CONFIG-005 validation output sanitized',HUB_KEY not in str(checks) and HUNTER_KEY not in str(checks))

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
