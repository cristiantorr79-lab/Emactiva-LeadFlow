"""Explicitly gated real-provider smoke test. Never runs in normal regression."""
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import json,os,sys,uuid

if os.environ.get('RUN_REAL_PROVIDER_TESTS')!='1':
 print('RESULT: NOT_RUN; real provider tests require explicit opt-in')
 sys.exit(0)

mode=os.environ.get('REAL_PROVIDER_TEST_MODE','all')
if mode not in {'all','hubspot-only','hunter-only'}:
 print('RESULT: BLOCKED; invalid real-provider test mode')
 sys.exit(2)
required=('REAL_PROVIDER_ADAPTER_URL','REAL_PROVIDER_TEST_EMAIL')
missing=[name for name in required if not os.environ.get(name)]
if missing:
 print('RESULT: BLOCKED; missing non-secret real-test configuration')
 sys.exit(2)
if mode in {'all','hubspot-only'} and os.environ.get('ALLOW_REAL_HUBSPOT_WRITE')!='1':
 print('RESULT: BLOCKED; HubSpot write gate is not enabled')
 sys.exit(2)

base=os.environ['REAL_PROVIDER_ADAPTER_URL'].rstrip('/'); email=os.environ['REAL_PROVIDER_TEST_EMAIL']
def post(path,payload):
 data=json.dumps(payload,separators=(',',':')).encode()
 try:
  with urlopen(Request(base+path,data=data,method='POST',headers={'Content-Type':'application/json'}),timeout=60) as response: return response.status,json.loads(response.read())
 except HTTPError as error: return error.code,json.loads(error.read())

results=[]
if mode in {'all','hubspot-only'}:
 operation='real-opt-in:'+uuid.uuid4().hex
 crm_status,crm=post('/crm/process',{'email':email,'lead':{'email':email,'company':'Emactiva controlled test'},'present_fields':{'company':'Emactiva controlled test'},'operation_key':operation})
 crm_ok=crm_status==200 and crm.get('success') is True and isinstance(crm.get('contact_id'),str); results.append(crm_ok)
 print('REAL-HUBSPOT: '+('PASS' if crm_ok else 'FAIL'))
if mode in {'all','hunter-only'}:
 enrich_status,enriched=post('/enrichment/enrich',{'email':email,'company':'Emactiva controlled test'})
 enrich_ok=enrich_status==200 and enriched.get('success') is True and set(enriched.get('data') or {})<={'industry','company_size','website'}; results.append(enrich_ok)
 print('REAL-HUNTER: '+('PASS' if enrich_ok else 'FAIL'))
passed=bool(results) and all(results); print('RESULT: '+('PASS' if passed else 'FAIL'))
sys.exit(0 if passed else 1)
