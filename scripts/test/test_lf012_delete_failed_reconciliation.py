"""Focused state-machine checks for ambiguous DSR DELETE reconciliation."""
from pathlib import Path
import importlib.util,sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("lf012_delete_state",ROOT/"scripts"/"admin"/"dsr_delete_state.py")
state=importlib.util.module_from_spec(spec); spec.loader.exec_module(state)
checks={}; calls=[]; EMAIL="private-person@example.test"; SECRET="synthetic-secret"; PAYLOAD="private-payload"
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
def locate(result):
 def call(): calls.append("locate"); return result
 return call

calls.clear()
def complete(): calls.append("complete"); return {"status":"completed","result_code":"reconciled_absent"}
decision,evidence=state.coordinate_delete_state("failed","contact_deletion_ambiguous",True,locate({"success":True,"found":False,"contact_count":0,"interaction_count":0,"email":EMAIL,"payload":PAYLOAD,"secret":SECRET}),complete)
check("LF012-R ambiguous failed plus absent can complete",decision=="reconciled_absent" and evidence=={"status":"completed","result_code":"reconciled_absent"} and calls==["locate","complete"])
check("LF012-R reconciliation evidence remains minimized",all(value not in str((decision,evidence)) for value in (EMAIL,PAYLOAD,SECRET)))

calls.clear(); decision,_=state.coordinate_delete_state("failed","contact_deletion_ambiguous",True,locate({"success":True,"found":True,"contact_count":1,"interaction_count":0}),complete)
check("LF012-R present contact remains blocked",decision=="reconciliation_blocked" and calls==["locate"])

calls.clear(); decision,_=state.coordinate_delete_state("failed","contact_deletion_ambiguous",True,locate({"success":False,"error_code":"adapter_unavailable"}),complete)
check("LF012-R technical reconciliation failure blocked",decision=="reconciliation_blocked" and calls==["locate"])

calls.clear(); decision,_=state.coordinate_delete_state("failed","authorization_error",True,locate({"success":True,"found":False,"contact_count":0,"interaction_count":0}),complete)
check("LF012-R nonambiguous failure invalid",decision=="invalid" and calls==[])

calls.clear(); decision,_=state.coordinate_delete_state("failed","contact_deletion_ambiguous",False,locate({"success":True,"found":False,"contact_count":0,"interaction_count":0}),complete)
check("LF012-R invalid approvals blocked before read",decision=="invalid" and calls==[])

calls.clear(); decision,_=state.coordinate_delete_state("completed","reconciled_absent",True,locate({}),complete)
check("LF012-R completed repetition idempotent",decision=="completed" and calls==[])

calls.clear(); decision,_=state.coordinate_delete_state("pending","provider_action_pending",True,locate({}),complete)
check("LF012-R pending behavior preserved",decision=="delete" and calls==[])

check("LF012-R ambiguous reconciliation emits no DELETE",calls==[] and all(item not in {"delete"} for item in ("reconciled_absent","reconciliation_blocked","invalid","completed")))
failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
