"""Focused completion criteria for the LF012 real DSR DELETE runner."""
from pathlib import Path
import importlib.util,sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("lf012_real_runner_completion",ROOT/"scripts"/"test"/"test_lf012_real_hubspot_delete_opt_in.py")
runner=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
checks={}
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)

deleted={"provider_status":"completed","provider_result_code":"completed_ticket_archive_warn","resolution":"deleted","found":True,"interaction_count":1,"reconciled":True}
check("LF012-C deleted accepted",runner.valid_admin_delete_result(0,deleted))

already={"provider_status":"completed","provider_result_code":"already_absent","resolution":"already_absent","found":False,"interaction_count":0}
check("LF012-C already absent accepted",runner.valid_admin_delete_result(0,already))

reconciled={"provider_status":"completed","provider_result_code":"reconciled_absent","resolution":"reconciled_absent","reconciled":True,"found":False,"interaction_count":0}
check("LF012-C reconciled absent accepted",runner.valid_admin_delete_result(0,reconciled))
check("LF012-C reconciled flag required",not runner.valid_admin_delete_result(0,{**reconciled,"reconciled":False}))
check("LF012-C reconciled found must be false",not runner.valid_admin_delete_result(0,{**reconciled,"found":True}))
check("LF012-C reconciled interaction count must be zero",not runner.valid_admin_delete_result(0,{**reconciled,"interaction_count":1}))
check("LF012-C provider must be completed",not runner.valid_admin_delete_result(0,{**reconciled,"provider_status":"failed"}))

inventory={"success":True,"found":True,"contact_count":1,"interaction_count":1}
check("LF012-C prior inventory one accepted",runner.valid_predelete_inventory(200,inventory))
check("LF012-C prior inventory other than one rejected",not runner.valid_predelete_inventory(200,{**inventory,"interaction_count":0}) and not runner.valid_predelete_inventory(200,{**inventory,"interaction_count":2}))

def sequence(items):
 values=list(items); calls=[]
 def run_admin(): calls.append("admin"); return values.pop(0)
 return run_admin,calls

for label,result in (("deleted",deleted),("already absent",already),("reconciled absent",reconciled)):
 run_admin,calls=sequence([(0,result)]); valid,_,_=runner.run_admin_to_safe_terminal(run_admin)
 check("LF012-S "+label+" terminal uses one call",valid and calls==["admin"])

ambiguous=(0,{"provider_status":"failed","provider_result_code":"contact_deletion_ambiguous"})
run_admin,calls=sequence([ambiguous,(0,reconciled)]); valid,_,terminal=runner.run_admin_to_safe_terminal(run_admin)
check("LF012-S ambiguous then reconciled uses exactly two calls",valid and terminal==reconciled and calls==["admin","admin"])

run_admin,calls=sequence([ambiguous,(1,{"provider_status":"failed","provider_result_code":"destructive_reconciliation_inconclusive"})]); valid,_,_=runner.run_admin_to_safe_terminal(run_admin)
check("LF012-S invalid second reconciliation fails",not valid and calls==["admin","admin"])

other_failure=(1,{"provider_status":"failed","provider_result_code":"authorization_error"})
run_admin,calls=sequence([other_failure]); valid,_,_=runner.run_admin_to_safe_terminal(run_admin)
check("LF012-S other failure has no second call",not valid and calls==["admin"])

for label,invalid_reconciled in (("found true",{**reconciled,"found":True}),("reconciled false",{**reconciled,"reconciled":False}),("count nonzero",{**reconciled,"interaction_count":1}),("provider failed",{**reconciled,"provider_status":"failed"})):
 run_admin,calls=sequence([ambiguous,(0,invalid_reconciled)]); valid,_,_=runner.run_admin_to_safe_terminal(run_admin)
 check("LF012-S second rejects "+label,not valid and calls==["admin","admin"])

run_admin,calls=sequence([ambiguous,(0,reconciled),(0,reconciled)]); valid,_,_=runner.run_admin_to_safe_terminal(run_admin); repeat_status,repeat=run_admin()
check("LF012-S later idempotence repetition remains third call",valid and runner.valid_admin_delete_result(repeat_status,repeat) and calls==["admin","admin","admin"])

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
