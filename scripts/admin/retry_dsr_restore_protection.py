#!/usr/bin/env python3
"""Retry only DSR evidence preservation from the durable database outbox."""
from pathlib import Path
import json,os,re,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
TECH=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
def result(status,code,**extra):
 print(json.dumps({"status":status,"result_code":code,**extra},separators=(",",":")))
def quote(value): return "NULL" if value is None else "'"+str(value).replace("'","''")+"'"
request={}
try: request=json.load(sys.stdin); request_id=request.get("request_id") if isinstance(request,dict) else None
except Exception: request_id=None
if set(request if isinstance(request,dict) else {})!={"request_id"} or not isinstance(request_id,str) or not TECH.fullmatch(request_id): result("failed","retry_request_invalid"); raise SystemExit(1)
password=os.environ.get("POSTGRES_MIGRATOR_PASSWORD",""); user=os.environ.get("POSTGRES_MIGRATOR_USER",""); database_name=os.environ.get("POSTGRES_DB","")
if not all((password,user,database_name)): result("failed","retry_configuration_invalid"); raise SystemExit(1)
command=["docker","compose","exec","-T","postgres","sh","-c",'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql -h 127.0.0.1 -X -q -v ON_ERROR_STOP=1 -U "$1" -d "$2" -At',"sh",user,database_name]
def database(statement):
 completed=subprocess.run(command,cwd=ROOT,input=password+"\n"+statement+"\n",text=True,capture_output=True)
 if completed.returncode: raise RuntimeError("database operation failed")
 return completed.stdout.strip()
evidence_id=None
try:
 evidence=database(f"SELECT * FROM leadflow.get_dsr_restore_evidence({quote(request_id)});").split("|")
 if len(evidence)!=5: raise ValueError("outbox entry unavailable")
 staged=subprocess.run([sys.executable,str(ROOT/"scripts"/"backup"/"dsr_restore_evidence.py"),"stage","--key-file",os.environ.get("DSR_EVIDENCE_KEY_FILE",""),"--spool-dir",os.environ.get("DSR_EVIDENCE_SPOOL_DIR","")],cwd=ROOT,input=json.dumps({"subject_token":evidence[0],"disposition":evidence[1],"effective_at_utc":evidence[2]},separators=(",",":")),text=True,capture_output=True)
 if staged.returncode: raise RuntimeError("stage failed")
 staged_result=json.loads(staged.stdout); evidence_id=staged_result["evidence_id"]
 database(f"SELECT leadflow.record_dsr_restore_evidence({quote(request_id)},'staged',{quote(evidence_id)},'evidence_staged');")
 status="staged"; code="evidence_staged"
 if os.environ.get("DSR_EVIDENCE_AUTO_PUBLISH","").lower()=="true":
  published=subprocess.run([sys.executable,str(ROOT/"scripts"/"backup"/"dsr_restore_evidence.py"),"publish","--artifact",staged_result["artifact"],"--gcs-prefix",os.environ.get("DSR_EVIDENCE_GCS_PREFIX",""),"--writer-identity",os.environ.get("DSR_EVIDENCE_WRITER_IDENTITY","")],cwd=ROOT,text=True,capture_output=True)
  if published.returncode: raise RuntimeError("publish failed")
  database(f"SELECT leadflow.record_dsr_restore_evidence({quote(request_id)},'pending_confirmation',{quote(evidence_id)},'publication_unconfirmed');")
  status="pending_confirmation"; code="publication_unconfirmed"
 result(status,code,request_id=request_id,evidence_id=evidence_id)
except Exception:
 try: database(f"SELECT leadflow.record_dsr_restore_evidence({quote(request_id)},'failed',{quote(evidence_id)},'evidence_not_preserved');")
 except Exception: pass
 result("failed","evidence_not_preserved",request_id=request_id); raise SystemExit(1)
