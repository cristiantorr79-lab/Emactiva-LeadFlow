"""Focused REM-12 retention, holds, purge evidence and idempotency checks."""
from pathlib import Path
import hashlib
import os
import secrets
import subprocess
import sys


ROOT=Path(__file__).resolve().parents[2]
ADMIN=os.environ["POSTGRES_MIGRATOR_USER"]
BASE_DB=os.environ["POSTGRES_DB"]
TEST_DB="leadflow_retention_"+secrets.token_hex(4)
PREFIX="rem12_"+secrets.token_hex(5)
CANARY="synthetic-person@example.test"
checks={}


def run(sql,database=TEST_DB,check_result=True):
 command=["docker","compose","exec","-T","postgres","psql","-X","-q","-v","ON_ERROR_STOP=1","-U",ADMIN,"-d",database,"-At"]
 result=subprocess.run(command,cwd=ROOT,input=sql,text=True,capture_output=True,check=False)
 if check_result and result.returncode: raise AssertionError("database operation failed")
 return result


def scalar(sql): return run(sql).stdout.strip()
def check(name,value): checks[name]=bool(value); print(("PASS" if value else "FAIL")+" "+name)
def q(value): return "'"+value.replace("'","''")+"'"


def terminal(label,status,age_days,duplicate_of=None):
 execution=f"{PREFIX}_{label}"
 key="NULL" if status=="duplicate" else q(hashlib.sha256((PREFIX+label).encode()).hexdigest())
 duplicate="NULL" if duplicate_of is None else q(duplicate_of)
 success=status=="success"
 sql=("INSERT INTO leadflow.executions(execution_id,idempotency_key,source,lead_identifier,status,stage,crm_action,crm_contact_id,enrichment_status,started_at,created_at,finished_at,updated_at,duplicate_of) VALUES("+
  f"{q(execution)},{key},'website','{'b'*64}',{q(status)},"+
  ("'crm_enrichment_update','created','crm_fixture','success'," if success else "'idempotency',NULL,NULL,'not_started',")+
  f"clock_timestamp()-interval '{age_days} days 1 hour',clock_timestamp()-interval '{age_days} days 1 hour',clock_timestamp()-interval '{age_days} days',clock_timestamp()-interval '{age_days} days',{duplicate});"+
  f"INSERT INTO leadflow.execution_events(execution_id,status,stage) VALUES({q(execution)},{q(status)},{q('crm_enrichment_update' if success else 'idempotency')});")
 run(sql); return execution


def processing(label,age_days,context=False):
 execution=f"{PREFIX}_{label}"
 idem=hashlib.sha256((PREFIX+label).encode()).hexdigest()
 run(f"INSERT INTO leadflow.executions(execution_id,idempotency_key,source,lead_identifier,status,stage,updated_at) VALUES({q(execution)},{q(idem)},'website','{'d'*64}','processing','idempotency',clock_timestamp()-interval '{age_days} days');")
 run(f"INSERT INTO leadflow.execution_events(execution_id,status,stage) VALUES({q(execution)},'processing','idempotency');")
 if context: run(f"INSERT INTO leadflow.recovery_contexts(execution_id,email_ciphertext,created_at) VALUES({q(execution)},decode('00','hex'),clock_timestamp()-interval '{age_days} days');")
 return execution


try:
 run(f'CREATE DATABASE "{TEST_DB}";',BASE_DB)
 for migration in sorted((ROOT/"database"/"migrations").glob("*.sql")):
  run(migration.read_text(encoding="utf-8"))

 success_recent=terminal("success_recent","success",89)
 success_old=terminal("success_old","success",91)
 duplicate_owner_recent=terminal("duplicate_owner_recent","success",1)
 duplicate_recent=terminal("duplicate_recent","duplicate",89,duplicate_owner_recent)
 duplicate_owner_old=terminal("duplicate_owner_old","success",91)
 duplicate_old=terminal("duplicate_old","duplicate",91,duplicate_owner_old)
 failed_recent=terminal("failed_recent","failed",179)
 failed_old=terminal("failed_old","failed",181)
 processing_recent=processing("processing_recent",6,True)
 processing_old=processing("processing_old",8,True)
 held=terminal("held_success_old","success",120)
 run(f"INSERT INTO leadflow.retention_holds(execution_id,reason_code,owner_id,approved_by,review_at) VALUES({q(held)},'incident_review','retention_owner','retention_approver',clock_timestamp()+interval '30 days');")
 expired_hold=terminal("expired_hold_success_old","success",120)
 run(f"INSERT INTO leadflow.retention_holds(execution_id,reason_code,owner_id,approved_by,starts_at,review_at) VALUES({q(expired_hold)},'incident_review','retention_owner','retention_approver',clock_timestamp()-interval '2 days',clock_timestamp()-interval '1 day');")

 first=scalar("SELECT * FROM leadflow.purge_retained_data(90,180,7,1000);")
 check("REM12-1 success below 90 days retained",scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(success_recent)};")=="1")
 check("REM12-2 success above 90 days deleted",scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(success_old)};")=="0")
 check("REM12-3 duplicate below 90 days retained",scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(duplicate_recent)};")=="1")
 check("REM12-4 duplicate above 90 days deleted",scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(duplicate_old)};")=="0")
 check("REM12-5 failed below 180 days retained",scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(failed_recent)};")=="1")
 check("REM12-6 failed above 180 days deleted",scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(failed_old)};")=="0")
 check("REM12-7 active processing below 7 days retained",scalar(f"SELECT status FROM leadflow.executions WHERE execution_id={q(processing_recent)};")=="processing")
 old_state=scalar(f"SELECT status||'|'||error_code FROM leadflow.executions WHERE execution_id={q(processing_old)};")
 old_context=scalar(f"SELECT count(*) FROM leadflow.recovery_contexts WHERE execution_id={q(processing_old)};")
 check("REM12-8 stale processing terminalized before purge",old_state=="failed|retention_processing_expired" and old_context=="0")
 check("REM12-9 active hold retained",scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(held)};")=="1" and scalar(f"SELECT count(*) FROM leadflow.executions WHERE execution_id={q(expired_hold)};")=="0")
 deleted_events=scalar(f"SELECT count(*) FROM leadflow.execution_events WHERE execution_id IN ({q(success_old)},{q(duplicate_old)},{q(failed_old)});")
 retained_events=scalar(f"SELECT count(*) FROM leadflow.execution_events WHERE execution_id IN ({q(success_recent)},{q(duplicate_recent)},{q(failed_recent)},{q(held)});")
 check("REM12-10 child events consistent",deleted_events=="0" and int(retained_events)>=4)
 second=scalar("SELECT * FROM leadflow.purge_retained_data(90,180,7,1000);")
 second_counts=second.split("|")[1:5]
 check("REM12-11 repeated purge idempotent",second_counts==["0","0","0","0"])
 evidence_columns=scalar("SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='leadflow' AND table_name='retention_purge_runs';")
 evidence=scalar("SELECT processing_terminalized||'|'||execution_events_deleted||'|'||recovery_contexts_deleted||'|'||executions_deleted||'|'||evidence_rows_pruned FROM leadflow.retention_purge_runs ORDER BY completed_at;")
 check("REM12-12 minimized count-only evidence",evidence_columns=="run_id,completed_at,processing_terminalized,execution_events_deleted,recovery_contexts_deleted,executions_deleted,evidence_rows_pruned" and CANARY not in first+second+evidence)
finally:
 run(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE);',BASE_DB,False)

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
