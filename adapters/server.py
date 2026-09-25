"""Provider-neutral HTTP adapter boundary for LeadFlow."""
import json, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ALLOWED_ENRICHMENT={"industry","company_size","website"}

def load_config(env=os.environ):
 def integer(name,default,low,high=None):
  try: value=int(env.get(name,str(default)))
  except ValueError as error: raise ValueError(f"invalid {name}") from error
  if value<low or (high is not None and value>high): raise ValueError(f"invalid {name}")
  return value
 config={"attempts":integer("RETRY_MAX_ATTEMPTS",3,1,3),"delay1":integer("RETRY_DELAY_FIRST_SECONDS",5,1),"delay2":integer("RETRY_DELAY_SECOND_SECONDS",15,1),"timeout_ms":integer("ADAPTER_HTTP_TIMEOUT_MS",2000,1)}
 config.update(crm=env.get("CRM_UPSTREAM_URL","http://crm-mock:8080"),enrichment=env.get("ENRICHMENT_UPSTREAM_URL","http://enrichment-mock:8080"),alert=env.get("ALERT_UPSTREAM_URL","http://slack-mock:8080/webhook"),crm_api_key=env.get("CRM_API_KEY",""),enrichment_api_key=env.get("ENRICHMENT_API_KEY",""))
 if not all(str(config[name]).startswith(("http://","https://")) for name in ("crm","enrichment","alert")): raise ValueError("invalid upstream URL")
 return config

CONFIG=load_config()
def call(method,url,body):
 data=json.dumps(body,separators=(",",":")).encode()
 try:
  with urlopen(Request(url,data=data,method=method,headers={"Content-Type":"application/json"}),timeout=CONFIG["timeout_ms"]/1000) as response:
   raw=response.read(); return response.status,dict(response.headers),json.loads(raw) if raw else {}
 except HTTPError as error:
  raw=error.read(); return error.code,dict(error.headers),json.loads(raw) if raw else {}
 except (URLError,TimeoutError): return 0,{},{}
def classify(status): return "validation_error" if status==400 else "authentication_error" if status==401 else "authorization_error" if status==403 else "technical_not_found" if status==404 else "conflict_error" if status==409 else "rate_limit" if status==429 else "timeout" if status==0 else "upstream_error"
def retryable(status): return status==0 or status in (408,429,500,502,503,504)
def wait(headers,status,attempt):
 delay=(CONFIG["delay1"],CONFIG["delay2"])[attempt-1]
 if status==429:
  try: delay=max(delay,float(headers.get("Retry-After",headers.get("retry-after",0))))
  except ValueError: pass
 time.sleep(delay)
def request_with_retry(method,path,body):
 last=(0,{},{}); attempts=CONFIG["attempts"]
 for attempt in range(1,attempts+1):
  last=call(method,CONFIG["crm"]+path,body)
  if 200<=last[0]<300 or not retryable(last[0]) or attempt==attempts: return (*last,attempt-1)
  wait(last[1],last[0],attempt)
 return (*last,attempts-1)
def crm_process(payload):
 email=payload.get("email"); lead=payload.get("lead"); fields=payload.get("present_fields"); operation_key=payload.get("operation_key")
 status,headers,body,retries=request_with_retry("POST","/crm/lookup",{"email":email})
 if status!=200: return {"success":False,"stage":"crm_lookup","error_type":classify(status),"error_code":"timeout" if status==0 else f"http_{status}","retry_count":retries}
 if body.get("found"):
  contact=body.get("contact") or {}; contact_id=contact.get("id")
  status,headers,body,used=request_with_retry("PATCH",f"/crm/contacts/{contact_id}",{"fields":fields or {}}); retries+=used
  return {"success":True,"contact_id":contact_id,"crm_action":"updated","retry_count":retries} if 200<=status<300 else {"success":False,"stage":"crm_update","contact_id":contact_id,"crm_action":"updated","error_type":classify(status),"error_code":"timeout" if status==0 else f"http_{status}","retry_count":retries}
 for attempt in range(1,CONFIG["attempts"]+1):
  status,headers,body=call("POST",CONFIG["crm"]+"/crm/contacts",{"lead":lead,"operation_key":operation_key})
  if 200<=status<300: return {"success":True,"contact_id":body.get("contact_id"),"crm_action":"created","retry_count":retries+attempt-1}
  if status in (0,409):
   lookup,_,found=call("POST",CONFIG["crm"]+"/crm/lookup",{"email":email})
   if lookup==200 and found.get("found"): return {"success":True,"contact_id":found["contact"]["id"],"crm_action":"created","retry_count":retries+attempt-1}
   if status==409: return {"success":False,"stage":"crm_create","error_type":"conflict_error","error_code":"http_409","retry_count":retries+attempt-1}
  if not retryable(status) or attempt==CONFIG["attempts"]: return {"success":False,"stage":"crm_create","error_type":classify(status),"error_code":"ambiguous_create" if status==0 else f"http_{status}","retry_count":retries+attempt-1}
  wait(headers,status,attempt)
def enrich(payload):
 for attempt in range(1,CONFIG["attempts"]+1):
  status,headers,body=call("POST",CONFIG["enrichment"]+"/enrich",{k:payload[k] for k in ("email","company") if payload.get(k)})
  if 200<=status<300 and body.get("enrichment_status")=="success": return {"success":True,"data":{k:v for k,v in (body.get("data") or {}).items() if k in ALLOWED_ENRICHMENT},"retry_count":attempt-1}
  if not retryable(status) or attempt==CONFIG["attempts"]: return {"success":False,"error_type":classify(status),"error_code":"timeout" if status==0 else f"http_{status}","retry_count":attempt-1}
  wait(headers,status,attempt)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*_): pass
 def respond(self,status,payload):
  raw=json.dumps(payload,separators=(",",":")).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
 def payload(self):
  try: value=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0")))); return value if isinstance(value,dict) else None
  except Exception: return None
 def do_GET(self): self.respond(200,{"ok":True}) if self.path=="/healthz" else self.respond(404,{"error":{"type":"technical_not_found"}})
 def do_POST(self):
  payload=self.payload()
  if payload is None: return self.respond(400,{"error":{"type":"validation_error"}})
  if self.path=="/crm/process": result=crm_process(payload)
  elif self.path=="/enrichment/enrich": result=enrich(payload)
  elif self.path=="/alert":
   allowed={"execution_id","stage","error_code"}
   if set(payload)!=allowed: return self.respond(400,{"delivered":False,"error_code":"invalid_alert"})
   status,_,_=call("POST",CONFIG["alert"],payload); result={"delivered":200<=status<300,"alert_error_code":None if 200<=status<300 else "slack_delivery_failed"}
  else: return self.respond(404,{"error":{"type":"technical_not_found"}})
  self.respond(200,result)
 def do_PATCH(self):
  payload=self.payload(); prefix="/crm/update-enrichment/"
  if payload is None or not self.path.startswith(prefix): return self.respond(404,{"error":{"type":"technical_not_found"}})
  contact_id=self.path[len(prefix):]; fields={k:v for k,v in (payload.get("fields") or {}).items() if k in ALLOWED_ENRICHMENT}; status,_,body=call("PATCH",CONFIG["crm"]+f"/crm/contacts/{contact_id}/enrichment",{"fields":fields}); self.respond(200,{"contact_id":body.get("contact_id",contact_id)}) if 200<=status<300 else self.respond(502,{"error":{"type":classify(status)}})
if __name__=="__main__": ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("ADAPTER_PORT","8080"))),Handler).serve_forever()
