"""Integrated focused R3 battery for REM-13, REM-14 and REM-15."""
from pathlib import Path
import hashlib,hmac,importlib.util,json,os,secrets,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]; ADMIN=os.environ["POSTGRES_MIGRATOR_USER"]; BASE=os.environ["POSTGRES_DB"]
DB="leadflow_r3_"+secrets.token_hex(4); PREFIX="r3_"+secrets.token_hex(4); SECRET="r3-synthetic-subject-key-at-least-32"; checks={}
def run(sql,database=DB,ok=True):
 result=subprocess.run(["docker","compose","exec","-T","postgres","psql","-X","-q","-v","ON_ERROR_STOP=1","-U",ADMIN,"-d",database,"-At"],cwd=ROOT,input=sql,text=True,capture_output=True)
 if ok and result.returncode: raise AssertionError("database operation failed")
 return result
def scalar(sql): return run(sql).stdout.strip()
def q(v): return "NULL" if v is None else "'"+str(v).replace("'","''")+"'"
def identity(email):
 value=email.lower(); return hashlib.sha256(value.encode()).hexdigest(),hmac.new(SECRET.encode(),value.encode(),hashlib.sha256).hexdigest()
def fixture(label,email,crm="crm_one"):
 lead,token=identity(email); execution=PREFIX+"_"+label; idem=hashlib.sha256(execution.encode()).hexdigest()
 run(f"INSERT INTO leadflow.executions(execution_id,idempotency_key,source,lead_identifier,subject_token,status,stage,crm_action,crm_contact_id,enrichment_status,started_at,finished_at) VALUES({q(execution)},{q(idem)},'website',{q(lead)},{q(token)},'success','crm_enrichment_update','created',{q(crm)},'success',clock_timestamp()-interval '1 hour',clock_timestamp()); INSERT INTO leadflow.execution_events(execution_id,status,stage) VALUES({q(execution)},'success','crm_enrichment_update');")
 return lead,token,execution
def execute(request_id,action,lead,token,approver=None,annotation=None,ok=True): return run(f"SELECT * FROM leadflow.execute_dsr_request({q(request_id)},{q(action)},{q(lead)},{q(token)},'dsr_operator',{q(approver)},{q(annotation)});",ok=ok)
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
try:
 run(f'CREATE DATABASE "{DB}";',BASE)
 for migration in sorted((ROOT/"database"/"migrations").glob("*.sql")): run(migration.read_text(encoding="utf-8"))
 lead,token,execution=fixture("subject","subject-one@example.test")
 locate=execute(PREFIX+"_locate","locate",lead,token).stdout.strip().split("|")
 check("R3-01 locate existing",locate[4]=="1" and locate[2]=="completed")
 missing_lead,missing_token=identity("missing@example.test"); missing=execute(PREFIX+"_missing","locate",missing_lead,missing_token).stdout.strip().split("|")
 check("R3-02 locate nonexistent",missing[2]=="not_found" and missing[4]=="0")
 export_id=PREFIX+"_export"; execute(export_id,"export",lead,token); exported=scalar(f"SELECT * FROM leadflow.dsr_export_minimized({q(export_id)},{q(lead)});")
 check("R3-03 minimized export",execution in exported and lead not in exported and token not in exported and "subject-one" not in exported)
 annotation_id=PREFIX+"_annotate"; execute(annotation_id,"annotate",lead,token,annotation="verified_correction_note")
 check("R3-04 correction annotation traceable",scalar(f"SELECT annotation_code FROM leadflow.dsr_annotations WHERE request_id={q(annotation_id)};")=="verified_correction_note")
 delete_lead,delete_token,delete_execution=fixture("delete","delete-me@example.test"); delete_id=PREFIX+"_delete"; deleted=execute(delete_id,"delete",delete_lead,delete_token,"dsr_approver").stdout.strip().split("|")
 check("R3-05 authorized delete",deleted[5]=="1" and scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(delete_execution)};")=="0")
 repeated=execute(delete_id,"delete",delete_lead,delete_token,"dsr_approver").stdout.strip().split("|"); check("R3-06 repeated delete idempotent",repeated[:4]==deleted[:4] and scalar(f"SELECT count(*) FROM leadflow.dsr_requests WHERE request_id={q(delete_id)};")=="1")
 no_approval=execute(PREFIX+"_noapproval","delete",lead,token,ok=False); check("R3-07 delete without approval rejected",no_approval.returncode!=0)
 restrict_lead,restrict_token,restrict_execution=fixture("restrict","restrict-me@example.test"); restriction=execute(PREFIX+"_restrict","restrict",restrict_lead,restrict_token,"dsr_approver").stdout.strip().split("|")
 blocked=run(f"SELECT * FROM leadflow.claim_event('{PREFIX}_blocked','website','evt_r3_001','{hashlib.sha256(b'website:evt_r3_001').hexdigest()}','{restrict_lead}','{restrict_token}');",ok=False)
 check("R3-08 authorized restriction blocks processing",restriction[2]=="completed" and blocked.returncode!=0)
 ambiguous_lead,ambiguous_token,_=fixture("ambiguous_one","ambiguous@example.test","crm_one"); fixture("ambiguous_two","ambiguous@example.test","crm_two")
 ambiguous=execute(PREFIX+"_ambiguous","delete",ambiguous_lead,ambiguous_token,"dsr_approver").stdout.strip().split("|"); check("R3-09 ambiguous subject blocked",ambiguous[1]=="ambiguous" and ambiguous[5]=="0")
 columns=scalar("SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='leadflow' AND table_name='dsr_tombstones';")
 check("R3-10 minimal nonreversible tombstone",columns=="subject_token,disposition,created_at,updated_at" and scalar(f"SELECT count(*) FROM leadflow.dsr_tombstones WHERE subject_token={q(delete_token)};")=="1")
 evidence=scalar(f"SELECT row_to_json(r)::text FROM leadflow.dsr_requests r WHERE request_id={q(delete_id)};"); check("R3-11 evidence excludes deleted PII","delete-me@example.test" not in evidence and delete_lead not in evidence)
 providers=scalar(f"SELECT provider||'|'||status FROM leadflow.dsr_provider_actions WHERE request_id={q(delete_id)} ORDER BY provider;")
 check("R3-12 HubSpot coordination registered","hubspot|pending" in providers)
 check("R3-13 Hunter coordination registered","hunter|pending" in providers)
 check("R3-14 Slack explicit no action","slack|not_applicable" in providers)
 check("R3-15 provider pending keeps partial",scalar(f"SELECT status FROM leadflow.dsr_requests WHERE request_id={q(delete_id)};")=="partial")
 sanitized=scalar(f"SELECT * FROM leadflow.record_dsr_provider_result({q(delete_id)},'hubspot','delete','failed','hubspot_case_1','raw payload token=secret');")
 check("R3-16 provider result sanitized",sanitized.endswith("|provider_error") and "raw payload" not in sanitized)
 execute(delete_id,"delete",delete_lead,delete_token,"dsr_approver"); check("R3-17 coordination repetition deduplicated",scalar(f"SELECT count(*) FROM leadflow.dsr_provider_actions WHERE request_id={q(delete_id)};")=="3")
 spec=importlib.util.spec_from_file_location("backup_policy",ROOT/"scripts"/"validation"/"validate_backup_policy.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
 policy=json.loads((ROOT/"config"/"backup-policy.json").read_text(encoding="utf-8")); check("R3-18 backup contract valid",module.validate(policy)==[])
 check("R3-19 RPO RTO retention defined",policy["retention_days"]==30 and policy["rpo_hours"]<=24 and policy["rto_hours"]<=8 and policy["frequency_hours"]==24)
 runbook=(ROOT/"docs"/"runbooks"/"BACKUP_RESTORE.md").read_text(encoding="utf-8"); check("R3-20 restore reapplies DSR state",policy["restore_requires_dsr_replay"] and "dsr_tombstones" in runbook and "restricted" in runbook)
 check("R3-21 environment remains unverified",all(value in {"NOT_VERIFIED","HYBRID"} for value in policy["environment_controls"].values()))
finally: run(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE);',BASE,False)
failed=[name for name,value in checks.items() if not value]; print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}"); sys.exit(1 if failed else 0)
