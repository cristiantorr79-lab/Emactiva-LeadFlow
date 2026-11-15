#!/usr/bin/env python3
"""Manifest-bound archival of the explicitly authorized LF015 HubSpot test set."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,re,sys
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode,urlparse
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[2]
VERSION="LF015-HUBSPOT-CLEANUP-1"
EXPECTED={"contacts":13,"tickets":4,"companies":2}
KNOWN={"contacts":{"262843762244","262824626777"},"tickets":{"51166307726","51193723436","51199259216","51189969488"},"companies":set()}
ID=re.compile(r"^[1-9][0-9]{0,29}$")

class CleanupError(RuntimeError): pass
def canonical(value): return (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def write_new(path,value):
 with Path(path).open("xb") as stream: stream.write(canonical(value))
 Path(path).chmod(0o600)
def load_runtime():
 path=ROOT/"scripts"/"admin"/"compose_with_secrets.py"; spec=importlib.util.spec_from_file_location("lf015_secret_runtime",path)
 if spec is None or spec.loader is None: raise CleanupError("secret resolver unavailable")
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def resolve_token(map_path,provider_factory=None):
 runtime=load_runtime(); validator=runtime.load_validator(); required=set(validator.RUNTIME_SECRET_NAMES)
 identity,references=runtime.load_map(Path(map_path),required)
 timeout=int(os.environ.get("SECRET_FETCH_TIMEOUT_SECONDS","5"))
 if not 1<=timeout<=30: raise CleanupError("invalid secret timeout")
 provider=(provider_factory or runtime.GcpSecretManagerProvider)(identity,timeout)
 return provider.resolve(references["CRM_API_KEY"])

class HubSpot:
 def __init__(self,token,base="https://api.hubapi.com",timeout=10,opener=urlopen):
  parsed=urlparse(base)
  if parsed.scheme!="https" or parsed.netloc!="api.hubapi.com" or parsed.path not in {"","/"}: raise CleanupError("invalid HubSpot endpoint")
  if not token or "\x00" in token: raise CleanupError("invalid HubSpot credential")
  self.base=base.rstrip("/"); self.timeout=timeout; self.opener=opener; self.headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"}
 def request(self,method,path):
  try:
   with self.opener(Request(self.base+path,method=method,headers=self.headers),timeout=self.timeout) as response:
    raw=response.read(1048577); status=response.status
  except HTTPError as error: raw=error.read(1048577); status=error.code
  except (URLError,TimeoutError,OSError) as error: raise CleanupError("HubSpot transport ambiguous") from error
  if len(raw)>1048576: raise CleanupError("HubSpot response too large")
  if method=="DELETE":
   if status not in {204,404}: raise CleanupError(f"HubSpot archive rejected http_{status}")
   return status,{}
  if status==404: return status,{}
  if status!=200: raise CleanupError(f"HubSpot read rejected http_{status}")
  try: value=json.loads(raw) if raw else {}
  except Exception as error: raise CleanupError("HubSpot response invalid") from error
  return status,value
 def inventory(self):
  result={}
  for object_type in ("tickets","contacts","companies"):
   ids=[]; after=None
   while True:
    query={"limit":"100","archived":"false","properties":"hs_object_id"}
    if after is not None: query["after"]=after
    _,body=self.request("GET",f"/crm/v3/objects/{object_type}?{urlencode(query)}")
    rows=body.get("results"); paging=body.get("paging") or {}
    if not isinstance(rows,list): raise CleanupError("HubSpot inventory invalid")
    for row in rows:
     object_id=str(row.get("id","")) if isinstance(row,dict) else ""
     if not ID.fullmatch(object_id): raise CleanupError("HubSpot object id invalid")
     ids.append(object_id)
    if len(ids)>1000 or len(set(ids))!=len(ids): raise CleanupError("HubSpot inventory invalid")
    next_page=(paging.get("next") or {}) if isinstance(paging,dict) else {}
    after=next_page.get("after") if isinstance(next_page,dict) else None
    if after is None: break
    if not isinstance(after,str) or not after.isdigit(): raise CleanupError("HubSpot pagination invalid")
   result[object_type]=sorted(ids,key=int)
  return result
 def absent(self,object_type,object_id): return self.request("GET",f"/crm/v3/objects/{object_type}/{object_id}?archived=false&properties=hs_object_id")[0]==404
 def archive(self,object_type,object_id):
  self.request("DELETE",f"/crm/v3/objects/{object_type}/{object_id}")
  if not self.absent(object_type,object_id): raise CleanupError("HubSpot archival not reconciled")

def validate_inventory(inventory):
 if set(inventory)!=set(EXPECTED): raise CleanupError("HubSpot inventory types mismatch")
 for kind,count in EXPECTED.items():
  ids=inventory[kind]
  if not isinstance(ids,list) or len(ids)!=count or len(set(ids))!=count or any(not ID.fullmatch(str(item)) for item in ids) or not KNOWN[kind].issubset(set(ids)): raise CleanupError("HubSpot inventory mismatch")
 return inventory
def manifest_from(inventory): return {"version":VERSION,"portal_scope":"current_active_test_inventory","counts":EXPECTED,"objects":validate_inventory(inventory)}
def load_manifest(path):
 value=json.loads(Path(path).read_text(encoding="utf-8"))
 if set(value)!={"version","portal_scope","counts","objects"} or value.get("version")!=VERSION or value.get("portal_scope")!="current_active_test_inventory" or value.get("counts")!=EXPECTED: raise CleanupError("cleanup manifest invalid")
 validate_inventory(value["objects"]); return value
def apply(client,manifest):
 current=client.inventory()
 for kind in EXPECTED:
  if not set(current[kind]).issubset(set(manifest["objects"][kind])): raise CleanupError("unexpected active HubSpot object")
 for kind in ("tickets","contacts","companies"):
  for object_id in manifest["objects"][kind]:
   if object_id in set(current[kind]): client.archive(kind,object_id)
 remaining=client.inventory()
 if any(remaining.values()): raise CleanupError("HubSpot cleanup incomplete")
 return sum(len(values) for values in current.values())
def main(argv=None,provider_factory=None,client_factory=HubSpot):
 parser=argparse.ArgumentParser(); parser.add_argument("action",choices=("inventory","apply","verify")); parser.add_argument("--map",required=True,type=Path); parser.add_argument("--manifest",required=True,type=Path); parser.add_argument("--authorize-manifest-sha256"); args=parser.parse_args(argv)
 try:
  token=resolve_token(args.map,provider_factory); client=client_factory(token)
  if args.action=="inventory":
   value=manifest_from(client.inventory()); write_new(args.manifest,value); print(f"lf015_hubspot_cleanup phase=inventory status=PASS objects={sum(EXPECTED.values())} manifest_sha256={digest(value)}"); return 0
  value=load_manifest(args.manifest)
  if not args.authorize_manifest_sha256 or args.authorize_manifest_sha256!=digest(value): raise CleanupError("manifest authorization mismatch")
  if args.action=="apply":
   affected=apply(client,value); print(f"lf015_hubspot_cleanup phase=apply status=PASS reconciled={affected}"); return 0
  remaining=client.inventory()
  if any(remaining.values()): raise CleanupError("HubSpot cleanup incomplete")
  print("lf015_hubspot_cleanup phase=verify status=PASS active=0 archival=logical"); return 0
 except Exception:
  print(f"lf015_hubspot_cleanup phase={getattr(args,'action','validation')} status=FAIL error_id=LF015-HUBSPOT-CLEANUP",file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())
