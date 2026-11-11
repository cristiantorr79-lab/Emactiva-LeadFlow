#!/usr/bin/env python3
"""Stream files to GCS JSON API with managed credentials and no-overwrite."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
import argparse,http.client,json,re,sys

METADATA_HOST="metadata.google.internal"
TOKEN_PATH="/computeMetadata/v1/instance/service-accounts/default/token"
IAM_CREDENTIALS_HOST="iamcredentials.googleapis.com"
BUCKET=re.compile(r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")
OBJECT=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}$")
SERVICE_ACCOUNT=re.compile(r"^[a-z0-9][a-z0-9-]{4,28}[a-z0-9]@[a-z0-9][a-z0-9-]{4,61}[a-z0-9]\.iam\.gserviceaccount\.com$")

class UploadError(RuntimeError): pass

def parse_destination(value:str):
 if not value.startswith("gs://") or "?" in value or "#" in value: raise ValueError("invalid destination")
 bucket,separator,name=value[5:].partition("/")
 if not separator or not BUCKET.fullmatch(bucket) or not OBJECT.fullmatch(name) or any(part in {"",".",".."} for part in name.split("/")): raise ValueError("invalid destination")
 return bucket,name

def metadata_token(timeout:int):
 connection=http.client.HTTPConnection(METADATA_HOST,timeout=timeout)
 try:
  try:
   connection.request("GET",TOKEN_PATH,headers={"Metadata-Flavor":"Google"})
   response=connection.getresponse(); payload=response.read(4096)
  except (OSError,TimeoutError,http.client.HTTPException) as error: raise UploadError("authentication failed") from error
 finally: connection.close()
 if response.status!=200: raise UploadError("authentication failed")
 try: value=json.loads(payload); token=value["access_token"]
 except Exception as error: raise UploadError("authentication failed") from error
 if not isinstance(token,str) or not token or len(token)>8192: raise UploadError("authentication failed")
 return token

def impersonated_token(service_account:str,source_token:str,timeout:int):
 if not isinstance(service_account,str) or not SERVICE_ACCOUNT.fullmatch(service_account): raise ValueError("invalid service account")
 if not isinstance(source_token,str) or not source_token or len(source_token)>8192: raise UploadError("authentication failed")
 payload=json.dumps({"scope":["https://www.googleapis.com/auth/devstorage.read_write"],"lifetime":"3600s"},separators=(",",":")).encode("ascii")
 path=f"/v1/projects/-/serviceAccounts/{quote(service_account,safe='')}:generateAccessToken"
 connection=http.client.HTTPSConnection(IAM_CREDENTIALS_HOST,timeout=timeout)
 try:
  try:
   connection.request("POST",path,body=payload,headers={"Authorization":f"Bearer {source_token}","Content-Type":"application/json","Content-Length":str(len(payload))})
   response=connection.getresponse(); response_payload=response.read(16384)
  except (OSError,TimeoutError,http.client.HTTPException) as error: raise UploadError("impersonation failed") from error
 finally: connection.close()
 if response.status!=200: raise UploadError(f"impersonation failed HTTP {response.status}")
 try:
  value=json.loads(response_payload); token=value["accessToken"]; expires=value["expireTime"]
  expiry=datetime.fromisoformat(expires.replace("Z","+00:00"))
 except Exception as error: raise UploadError("impersonation failed") from error
 now=datetime.now(timezone.utc)
 if not isinstance(token,str) or not token or len(token)>8192 or expiry.tzinfo is None or expiry<=now or expiry>now+timedelta(seconds=3700): raise UploadError("impersonation failed")
 return token

def request_session(bucket,name,size,token,timeout):
 path=f"/upload/storage/v1/b/{quote(bucket,safe='')}/o?uploadType=resumable&ifGenerationMatch=0&name={quote(name,safe='')}"
 connection=http.client.HTTPSConnection("storage.googleapis.com",timeout=timeout)
 try:
  try:
   connection.request("POST",path,headers={"Authorization":f"Bearer {token}","Content-Length":"0","X-Upload-Content-Length":str(size),"X-Upload-Content-Type":"application/octet-stream"})
   response=connection.getresponse(); response.read(4096); location=response.getheader("Location")
  except (OSError,TimeoutError,http.client.HTTPException) as error: raise UploadError("session failed") from error
 finally: connection.close()
 if response.status==412: raise UploadError("object conflict")
 if response.status not in {200,201} or not location: raise UploadError(f"session failed HTTP {response.status}")
 parsed=urlsplit(location)
 if parsed.scheme!="https" or parsed.hostname!="storage.googleapis.com" or parsed.username or parsed.password or not parsed.path: raise UploadError("invalid upload session")
 return parsed

def stream_file(path:Path,session,size,token,timeout):
 target=session.path+("?"+session.query if session.query else "")
 connection=http.client.HTTPSConnection("storage.googleapis.com",timeout=timeout)
 try:
  try:
   connection.putrequest("PUT",target); connection.putheader("Authorization",f"Bearer {token}"); connection.putheader("Content-Type","application/octet-stream"); connection.putheader("Content-Length",str(size)); connection.endheaders()
   with path.open("rb") as stream:
    while chunk:=stream.read(1024*1024): connection.send(chunk)
   response=connection.getresponse(); response.read(4096)
  except (OSError,TimeoutError,http.client.HTTPException) as error: raise UploadError("upload failed") from error
 finally: connection.close()
 if response.status==412: raise UploadError("object conflict")
 if response.status not in {200,201}: raise UploadError(f"upload failed HTTP {response.status}")

def upload_file(source:Path,destination:str,timeout:int=300,impersonate_service_account:str|None=None):
 if not isinstance(timeout,int) or not 1<=timeout<=3600: raise ValueError("invalid timeout")
 source=Path(source)
 if not source.is_file(): raise ValueError("invalid source")
 size=source.stat().st_size
 if size<=0: raise ValueError("invalid source")
 bucket,name=parse_destination(destination); token=metadata_token(min(timeout,5))
 if impersonate_service_account is not None: token=impersonated_token(impersonate_service_account,token,min(timeout,30))
 session=request_session(bucket,name,size,token,timeout); stream_file(source,session,size,token,timeout)
 return destination

def main():
 parser=argparse.ArgumentParser(); parser.add_argument("--source",required=True,type=Path); parser.add_argument("--destination",required=True); parser.add_argument("--timeout",type=int,default=300); parser.add_argument("--impersonate-service-account"); args=parser.parse_args()
 try: upload_file(args.source,args.destination,args.timeout,args.impersonate_service_account); print("gcs_upload status=PASS"); return 0
 except Exception: print("gcs_upload status=FAIL",file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())
