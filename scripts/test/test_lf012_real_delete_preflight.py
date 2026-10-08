"""Safe mocked preflight checks for the gated real DELETE runner."""
from pathlib import Path
import importlib.util,sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("lf012_real_runner",ROOT/"scripts"/"test"/"test_lf012_real_hubspot_delete_opt_in.py")
runner=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
checks={}
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
def response(body,status=200):
 calls=[]
 def post(path,payload): calls.append((path,payload)); return status,body
 return post,calls

existing,calls=response({"success":True,"found":True,"contact_count":1,"interaction_count":0})
allowed,code=runner.preflight_absent(existing,"preflight-1","controlled@example.test")
check("LF012-P preexisting email blocks",not allowed and code=="preflight_subject_not_conclusively_absent")
check("LF012-P block occurs before any write",len(calls)==1 and calls[0][0]=="/crm/dsr-locate")

absent,calls=response({"success":True,"found":False,"contact_count":0,"interaction_count":0})
allowed,code=runner.preflight_absent(absent,"preflight-2","controlled@example.test")
check("LF012-P conclusive absence permits next logical gate",allowed and code=="preflight_absent")
check("LF012-P preflight itself remains read only",len(calls)==1 and calls[0][0]=="/crm/dsr-locate")

ambiguous,calls=response({"success":False,"error_code":"subject_ambiguous"})
allowed,_=runner.preflight_absent(ambiguous,"preflight-3","controlled@example.test")
check("LF012-P ambiguous or invalid response fails closed",not allowed and len(calls)==1)

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
