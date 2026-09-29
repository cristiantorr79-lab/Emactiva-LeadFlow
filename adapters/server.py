"""Provider-neutral HTTP adapter boundary for LeadFlow."""
import hmac, json, os, re, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
try:
 from logging_policy import StructuredLogger
except ModuleNotFoundError:
 import sys
 sys.path.insert(0,os.path.dirname(__file__))
 from logging_policy import StructuredLogger

ALLOWED_ENRICHMENT={"industry","company_size","website"}
TEMPORARY_STATUSES={408,429,500,502,503,504}
HUBSPOT_CAPABILITIES={"consistent_lookup_after_create":False,"unique_email":False,"idempotent_create_operation_key":False,"conflict_reconciliation":True}
ADAPTER_OPERATIONS={"crm.process","crm.update_enrichment","enrichment.enrich","alert.send","crm.capabilities"}
TECHNICAL_CODE=re.compile(r"^[a-z][a-z0-9_-]{0,99}$")
OPAQUE_ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
TEXT_LIMITS={"industry":200,"company_size":100}
LOGGER=StructuredLogger("adapter")

def load_config(env=os.environ):
 def integer(name,default,low,high=None):
  try: value=int(env.get(name,str(default)))
  except ValueError as error: raise ValueError(f"invalid {name}") from error
  if value<low or (high is not None and value>high): raise ValueError(f"invalid {name}")
  return value
 def boolean(name,default=True):
  value=str(env.get(name,str(default).lower())).strip().lower()
  if value not in {"true","false"}: raise ValueError(f"invalid {name}")
  return value=="true"
 app_env=str(env.get("APP_ENV","development")).strip().lower()
 if app_env not in {"development","production"}: raise ValueError("invalid APP_ENV")
 crm_provider=str(env.get("CRM_PROVIDER","mock" if app_env=="development" else "")).strip().lower()
 enrichment_provider=str(env.get("ENRICHMENT_PROVIDER","mock" if app_env=="development" else "")).strip().lower()
 if crm_provider not in {"mock","hubspot"}: raise ValueError("invalid CRM_PROVIDER")
 if enrichment_provider not in {"mock","hunter"}: raise ValueError("invalid ENRICHMENT_PROVIDER")
 if app_env=="production" and (crm_provider!="hubspot" or enrichment_provider!="hunter"): raise ValueError("invalid production provider")
 config={
  "app_env":app_env,
  "attempts":integer("RETRY_MAX_ATTEMPTS",3,1,3),
  "delay1":integer("RETRY_DELAY_FIRST_SECONDS",5,1),
  "delay2":integer("RETRY_DELAY_SECOND_SECONDS",15,1),
  "timeout_ms":integer("ADAPTER_HTTP_TIMEOUT_MS",2000,1),
  "crm_provider":crm_provider,"enrichment_provider":enrichment_provider,
  "capabilities":HUBSPOT_CAPABILITIES.copy() if crm_provider=="hubspot" else {
   "consistent_lookup_after_create":boolean("CRM_CAP_CONSISTENT_LOOKUP_AFTER_CREATE"),
   "unique_email":boolean("CRM_CAP_UNIQUE_EMAIL"),
   "idempotent_create_operation_key":boolean("CRM_CAP_IDEMPOTENT_CREATE_OPERATION_KEY"),
   "conflict_reconciliation":boolean("CRM_CAP_CONFLICT_RECONCILIATION"),
  },
 }
 service_key=str(env.get("ADAPTER_SERVICE_KEY", ""))
 if len(service_key)<32 or any(char in service_key for char in "\r\n\0"): raise ValueError("missing or invalid ADAPTER_SERVICE_KEY")
 allowed_operations={item.strip() for item in str(env.get("ADAPTER_ALLOWED_OPERATIONS", "")).split(",") if item.strip()}
 if not allowed_operations or not allowed_operations<=ADAPTER_OPERATIONS: raise ValueError("missing or invalid ADAPTER_ALLOWED_OPERATIONS")
 config.update(service_key=service_key,allowed_operations=allowed_operations)
 defaults={"crm":"http://crm-mock:8080","enrichment":"http://enrichment-mock:8080","alert":"http://slack-mock:8080/webhook"}
 config.update(crm=env.get("CRM_UPSTREAM_URL",defaults["crm"] if app_env=="development" and crm_provider=="mock" else ""),enrichment=env.get("ENRICHMENT_UPSTREAM_URL",defaults["enrichment"] if app_env=="development" and enrichment_provider=="mock" else ""),alert=env.get("ALERT_UPSTREAM_URL",defaults["alert"] if app_env=="development" else ""),crm_api_key=env.get("CRM_API_KEY",""),enrichment_api_key=env.get("ENRICHMENT_API_KEY",""))
 config["hubspot_enrichment_properties"]={"industry":env.get("HUBSPOT_PROPERTY_INDUSTRY","industry"),"company_size":env.get("HUBSPOT_PROPERTY_COMPANY_SIZE","leadflow_company_size"),"website":env.get("HUBSPOT_PROPERTY_WEBSITE","website")}
 if not all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*",value or "") for value in config["hubspot_enrichment_properties"].values()): raise ValueError("invalid HubSpot property mapping")
 if not all(str(config[name]).startswith(("http://","https://")) for name in ("crm","enrichment","alert")): raise ValueError("invalid upstream URL")
 if crm_provider=="hubspot" and not config["crm_api_key"]: raise ValueError("missing CRM_API_KEY")
 if enrichment_provider=="hunter" and not config["enrichment_api_key"]: raise ValueError("missing ENRICHMENT_API_KEY")
 if app_env=="production":
  unsafe=("localhost","127.0.0.1","crm-mock","enrichment-mock","slack-mock")
  if any(not config[name].startswith("https://") or any(token in config[name].lower() for token in unsafe) for name in ("crm","enrichment","alert")): raise ValueError("unsafe production upstream")
 return config

CONFIG=None

def call(method,url,body=None,headers=None):
 data=None if body is None else json.dumps(body,separators=(",",":")).encode(); request_headers={"Content-Type":"application/json",**(headers or {})}
 try:
  with urlopen(Request(url,data=data,method=method,headers=request_headers),timeout=CONFIG["timeout_ms"]/1000) as response:
   raw=response.read(); return response.status,dict(response.headers),json.loads(raw) if raw else {}
 except HTTPError as error:
  raw=error.read()
  try: body=json.loads(raw) if raw else {}
  except (json.JSONDecodeError,UnicodeDecodeError): body={}
  return error.code,dict(error.headers),body
 except (URLError,TimeoutError): return 0,{},{}

def classify(status): return {0:"timeout",400:"validation_error",401:"authentication_error",403:"authorization_error",404:"technical_not_found",409:"conflict_error",422:"validation_error",429:"rate_limit",451:"authorization_error"}.get(status,"upstream_error")
def retryable(status): return status==0 or status in TEMPORARY_STATUSES
def retry_after_seconds(headers):
 try:
  value=float(headers.get("Retry-After",headers.get("retry-after",0))); return value if value>=0 else None
 except (TypeError,ValueError): return None
def wait(headers,status,attempt):
 delay=(CONFIG["delay1"],CONFIG["delay2"])[attempt-1]
 if status==429:
  retry_after=retry_after_seconds(headers)
  if retry_after is not None: delay=max(delay,retry_after)
 time.sleep(delay)

def technical_code(value,fallback):
 return value if isinstance(value,str) and TECHNICAL_CODE.fullmatch(value) else fallback

def opaque_id(value):
 return value if isinstance(value,str) and OPAQUE_ID.fullmatch(value) else None

def normalize_website(value):
 if not isinstance(value,str) or len(value)>2048 or any(ord(char)<32 for char in value): return None
 try: parsed=urlsplit(value.strip())
 except ValueError: return None
 if parsed.scheme.lower() not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password: return None
 try:
  host=parsed.hostname.lower(); port=f":{parsed.port}" if parsed.port else ""
 except ValueError: return None
 return urlunsplit((parsed.scheme.lower(),host+port,parsed.path or "","",""))

def canonical_error(status,code=None,ambiguous=False):
 fallback="timeout" if status==0 else f"http_{status}"
 return {"type":"ambiguous_create" if ambiguous else classify(status),"code":technical_code(code,fallback),"http_status":status or None,"retry_after_seconds":None,"ambiguous":bool(ambiguous),"message":"upstream dependency failed"}

def failure(stage,status,retries,headers=None,code=None,ambiguous=False,**context):
 error=canonical_error(status,code,ambiguous)
 if status==429: error["retry_after_seconds"]=retry_after_seconds(headers or {})
 return {"success":False,"stage":stage,"error_type":error["type"],"error_code":error["code"],"http_status":error["http_status"],"retry_after_seconds":error["retry_after_seconds"],"ambiguous":error["ambiguous"],"error_message":error["message"],"error":error,"retry_count":retries,**context}

def request_with_retry(method,base,path,body,operation=None):
 last=(0,{},{})
 for attempt in range(1,CONFIG["attempts"]+1):
  last=operation() if operation else call(method,base+path,body)
  if 200<=last[0]<300 or not retryable(last[0]) or attempt==CONFIG["attempts"]: return (*last,attempt-1)
  wait(last[1],last[0],attempt)
 return (*last,CONFIG["attempts"]-1)

def safe_ambiguous_create_retry(capabilities):
 return bool(capabilities.get("idempotent_create_operation_key") or (capabilities.get("consistent_lookup_after_create") and capabilities.get("unique_email")))

def filter_enrichment_fields(fields):
 if not isinstance(fields,dict): return {}
 filtered={}
 for key in ALLOWED_ENRICHMENT:
  value=fields.get(key)
  if key=="website":
   normalized=normalize_website(value)
  else:
   normalized=value.strip() if isinstance(value,str) and 0<len(value.strip())<=TEXT_LIMITS[key] and not any(ord(char)<32 for char in value) else None
  if normalized is not None: filtered[key]=normalized
 return filtered

def hubspot_headers(): return {"Authorization":"Bearer "+CONFIG["crm_api_key"]}
def hunter_headers(): return {"X-API-KEY":CONFIG["enrichment_api_key"]}
def hubspot_properties(fields,include_email=False):
 mapping={"first_name":"firstname","last_name":"lastname","phone":"phone","company":"company",**CONFIG["hubspot_enrichment_properties"]}
 properties={mapping[key]:value for key,value in (fields or {}).items() if key in mapping and isinstance(value,str) and value}
 if include_email and isinstance((fields or {}).get("email"),str): properties["email"]=fields["email"]
 return properties

def crm_lookup(email):
 if CONFIG["crm_provider"]=="mock": return call("POST",CONFIG["crm"]+"/crm/lookup",{"email":email})
 payload={"filterGroups":[{"filters":[{"propertyName":"email","operator":"EQ","value":email}]}],"properties":["email"],"limit":2}
 status,headers,body=call("POST",CONFIG["crm"]+"/crm/v3/objects/contacts/search",payload,hubspot_headers())
 if status!=200: return status,headers,{}
 results=body.get("results") if isinstance(body,dict) else None
 if not isinstance(results,list) or len(results)>1: return 422,headers,{}
 if not results: return 200,headers,{"found":False}
 contact=results[0]; contact_id=opaque_id(contact.get("id")) if isinstance(contact,dict) else None
 return (200,headers,{"found":True,"contact":{"id":contact_id,"email":((contact.get("properties") or {}).get("email"))}}) if isinstance(contact_id,str) else (422,headers,{})

def crm_create(lead,operation_key):
 if CONFIG["crm_provider"]=="mock":
  status,headers,body=call("POST",CONFIG["crm"]+"/crm/contacts",{"lead":lead,"operation_key":operation_key})
  if not 200<=status<300: return status,headers,{}
  return (status,headers,{"contact_id":opaque_id(body.get("contact_id"))}) if isinstance(body,dict) and opaque_id(body.get("contact_id")) else (422,headers,{})
 status,headers,body=call("POST",CONFIG["crm"]+"/crm/v3/objects/contacts",{"properties":hubspot_properties(lead,True)},hubspot_headers())
 if not 200<=status<300: return status,headers,{}
 contact_id=opaque_id(body.get("id")) if isinstance(body,dict) else None
 return (status,headers,{"contact_id":contact_id}) if contact_id else (422,headers,{})

def crm_update(contact_id,fields,enrichment=False):
 if CONFIG["crm_provider"]=="mock":
  suffix="/enrichment" if enrichment else ""; return call("PATCH",CONFIG["crm"]+f"/crm/contacts/{contact_id}{suffix}",{"fields":fields})
 return call("PATCH",CONFIG["crm"]+f"/crm/v3/objects/contacts/{contact_id}",{"properties":hubspot_properties(fields)},hubspot_headers())

def hunter_data(body):
 data=body.get("data") if isinstance(body,dict) else None
 if not isinstance(data,dict): return None
 company=data.get("company") if isinstance(data.get("company"),dict) else {}
 category=company.get("category") if isinstance(company.get("category"),dict) else {}
 metrics=company.get("metrics") if isinstance(company.get("metrics"),dict) else {}
 site=company.get("site") if isinstance(company.get("site"),dict) else {}
 industry=company.get("industry") or category.get("industry")
 size=company.get("company_size") or company.get("employees") or metrics.get("employeesRange")
 website=company.get("website") or site.get("url") or company.get("domain")
 if isinstance(website,str) and website and "://" not in website: website="https://"+website
 return filter_enrichment_fields({"industry":industry,"company_size":str(size) if isinstance(size,(int,float)) else size,"website":website})

def hunter_invalid_email(body):
 errors=body.get("errors") if isinstance(body,dict) else None
 return isinstance(errors,list) and any(isinstance(error,dict) and error.get("id")=="invalid_email" for error in errors)

def provider_enrich(payload):
 if CONFIG["enrichment_provider"]=="mock": return call("POST",CONFIG["enrichment"]+"/enrich",{key:payload[key] for key in ("email","company") if payload.get(key)})
 url=CONFIG["enrichment"]+"/v2/combined/find?"+urlencode({"email":payload.get("email","")})
 status,headers,body=call("GET",url,None,hunter_headers())
 if status==404: return 200,headers,{"enrichment_status":"success","data":{}}
 if status==400 and hunter_invalid_email(body): return 200,headers,{"enrichment_status":"success","data":{}}
 if status==403: return 429,headers,body
 if status==200:
  mapped=hunter_data(body); return (200,headers,{"enrichment_status":"success","data":mapped}) if mapped is not None else (422,headers,{})
 return status,headers,body

def hunter_quota_error(status,body):
 if CONFIG["enrichment_provider"]!="hunter" or status!=429: return False
 text=json.dumps(body,separators=(",",":")).lower() if isinstance(body,(dict,list)) else ""
 return any(token in text for token in ("usage","quota","plan"))

def crm_process(payload):
 email=payload.get("email"); lead=payload.get("lead"); fields=payload.get("present_fields"); operation_key=payload.get("operation_key"); capabilities=CONFIG["capabilities"]
 status,headers,body,retries=request_with_retry("POST","","",{"email":email},operation=lambda:crm_lookup(email))
 if status!=200: return failure("crm_lookup",status,retries,headers)
 if body.get("found"):
  contact_id=(body.get("contact") or {}).get("id")
  status,headers,body,used=request_with_retry("PATCH","","",{"fields":fields or {}},operation=lambda:crm_update(contact_id,fields or {})); retries+=used
  if 200<=status<300: return {"success":True,"contact_id":contact_id,"crm_action":"updated","retry_count":retries}
  return failure("crm_update",status,retries,headers,contact_id=contact_id,crm_action="updated")
 for attempt in range(1,CONFIG["attempts"]+1):
  status,headers,body=crm_create(lead,operation_key)
  if 200<=status<300: return {"success":True,"contact_id":body.get("contact_id"),"crm_action":"created","retry_count":retries+attempt-1}
  if status in (0,409) and (status==0 or capabilities.get("conflict_reconciliation")):
   lookup,_,found=crm_lookup(email)
   if lookup==200 and found.get("found"): return {"success":True,"contact_id":found["contact"]["id"],"crm_action":"created","retry_count":retries+attempt-1}
   if status==409: return failure("crm_create",409,retries+attempt-1,headers)
   if not safe_ambiguous_create_retry(capabilities): return failure("crm_create",0,retries+attempt-1,headers,code="ambiguous_create",ambiguous=True)
  if not retryable(status) or attempt==CONFIG["attempts"]: return failure("crm_create",status,retries+attempt-1,headers,code="ambiguous_create" if status==0 else None,ambiguous=status==0)
  wait(headers,status,attempt)

def enrich(payload):
 last=(0,{},{}); request_body={key:payload[key] for key in ("email","company") if payload.get(key)}
 for attempt in range(1,CONFIG["attempts"]+1):
  status,headers,body=provider_enrich(request_body); last=(status,headers,body)
  if 200<=status<300 and body.get("enrichment_status")=="success":
   return {"success":True,"enrichment_status":"success","data":filter_enrichment_fields(body.get("data")),"retry_count":attempt-1}
  if hunter_quota_error(status,body): return failure("enrichment",status,attempt-1,headers,code="quota_exhausted")
  if not retryable(status) or attempt==CONFIG["attempts"]: return failure("enrichment",status,attempt-1,headers,code="invalid_response" if status==422 else None)
  wait(headers,status,attempt)
 return failure("enrichment",last[0],CONFIG["attempts"]-1,last[1])

class SafeThreadingHTTPServer(ThreadingHTTPServer):
 def handle_error(self,request,client_address):
  LOGGER.emit("ERROR","request_handler_error",error_type="internal_error",error_code="adapter_unexpected_error",stage="adapter")

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*_): pass
 def respond(self,status,payload):
  LOGGER.emit("INFO" if status<400 else "WARNING","http_response",http_status=status,status="success" if status<400 else "rejected")
  raw=json.dumps(payload,separators=(",",":")).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
 def payload(self):
  try: value=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0")))); return value if isinstance(value,dict) else None
  except Exception: return None
 def authorize(self,operation):
  provided=self.headers.get("X-LeadFlow-Adapter-Key","")
  if not provided or not hmac.compare_digest(provided,CONFIG["service_key"]):
   self.respond(401,{"error":{"type":"authentication_error","code":"adapter_identity_invalid","message":"adapter request rejected"}}); return False
  if operation not in CONFIG["allowed_operations"]:
   self.respond(403,{"error":{"type":"authorization_error","code":"adapter_operation_forbidden","message":"adapter request rejected"}}); return False
  return True
 def do_GET(self):
  if self.path=="/healthz": self.respond(200,{"ok":True})
  elif self.path=="/crm/capabilities":
   if not self.authorize("crm.capabilities"): return
   profile=dict(CONFIG["capabilities"]); profile["safe_ambiguous_create_retry"]=safe_ambiguous_create_retry(profile); self.respond(200,profile)
  else: self.respond(404,{"error":canonical_error(404)})
 def do_POST(self):
  operations={"/crm/process":"crm.process","/enrichment/enrich":"enrichment.enrich","/alert":"alert.send"}
  operation=operations.get(self.path)
  if operation is not None and not self.authorize(operation): return
  payload=self.payload()
  if payload is None: return self.respond(400,{"error":canonical_error(400)})
  if self.path=="/crm/process": result=crm_process(payload)
  elif self.path=="/enrichment/enrich": result=enrich(payload)
  elif self.path=="/alert":
   allowed={"execution_id","stage","error_code"}
   if set(payload)!=allowed or not opaque_id(payload.get("execution_id")) or not technical_code(payload.get("stage"),"") or not technical_code(payload.get("error_code"),""): return self.respond(400,{"delivered":False,"error_code":"invalid_alert"})
   status,_,_=call("POST",CONFIG["alert"],payload); result={"delivered":200<=status<300,"alert_error_code":None if 200<=status<300 else "slack_delivery_failed"}
  else: return self.respond(404,{"error":canonical_error(404)})
  self.respond(200,result)
 def do_PATCH(self):
  prefix="/crm/update-enrichment/"
  if not self.path.startswith(prefix): return self.respond(404,{"error":canonical_error(404)})
  if not self.authorize("crm.update_enrichment"): return
  payload=self.payload()
  if payload is None: return self.respond(400,{"error":canonical_error(400)})
  contact_id=opaque_id(self.path[len(prefix):])
  if not contact_id: return self.respond(400,{"error":canonical_error(400,"invalid_contact_id")})
  fields=filter_enrichment_fields(payload.get("fields"))
  status,_,body=crm_update(contact_id,fields,True)
  self.respond(200,{"contact_id":body.get("contact_id",contact_id)}) if 200<=status<300 else self.respond(502,{"error":canonical_error(status)})

if __name__=="__main__":
 CONFIG=load_config()
 SafeThreadingHTTPServer(("0.0.0.0",int(os.environ.get("ADAPTER_PORT","8080"))),Handler).serve_forever()
