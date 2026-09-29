"""Separate administrative DSR entrypoint; reads verified requests from stdin."""
from pathlib import Path
import hashlib, hmac, json, os, re, subprocess, sys

ROOT=Path(__file__).resolve().parents[2]
TECH=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
def fail(): print(json.dumps({"status":"failed","result_code":"dsr_request_invalid"})); raise SystemExit(1)
try: request=json.load(sys.stdin)
except Exception: fail()
email=str(request.get("verified_email","")).strip().lower(); secret=os.environ.get("DSR_SUBJECT_KEY","")
required=(request.get("request_id"),request.get("action"),request.get("operator_id"))
if len(secret)<32 or not email or "@" not in email or not all(isinstance(v,str) and TECH.fullmatch(v) for v in required): fail()
lead=hashlib.sha256(email.encode()).hexdigest(); token=hmac.new(secret.encode(),email.encode(),hashlib.sha256).hexdigest()
def q(value): return "NULL" if value is None else "'"+str(value).replace("'","''")+"'"
sql=f"SELECT * FROM leadflow.execute_dsr_request({q(request['request_id'])},{q(request['action'])},{q(lead)},{q(token)},{q(request['operator_id'])},{q(request.get('approver_id'))},{q(request.get('annotation_code'))});"
password=os.environ.get("POSTGRES_MIGRATOR_PASSWORD",""); user=os.environ.get("POSTGRES_MIGRATOR_USER",""); database=os.environ.get("POSTGRES_DB","")
if not password or not user or not database: fail()
command=["docker","compose","exec","-T","postgres","sh","-c",'IFS= read -r PGPASSWORD; export PGPASSWORD; exec psql -h 127.0.0.1 -X -q -v ON_ERROR_STOP=1 -U "$1" -d "$2" -At',"sh",user,database]
result=subprocess.run(command,cwd=ROOT,input=password+"\n"+sql+"\n",text=True,capture_output=True)
if result.returncode: print(json.dumps({"status":"failed","result_code":"dsr_database_error"})); raise SystemExit(1)
parts=result.stdout.strip().split("|")
print(json.dumps({"request_id":parts[0],"status":parts[1],"local_status":parts[2],"result_code":parts[3],"matched_count":int(parts[4]),"deleted_count":int(parts[5])},separators=(",",":")))
