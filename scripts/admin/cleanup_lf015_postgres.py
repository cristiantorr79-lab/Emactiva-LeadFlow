#!/usr/bin/env python3
"""Transactional cleanup of the exact authorized LF015 PostgreSQL test set."""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
VERSION="LF015-POSTGRES-CLEANUP-1"; PROJECT="emactiva-leadflow"; SERVICE="postgres"
EXECUTIONS=("lf_exec_e20b9a532a0e4402a05d9947ca97105f","lf_exec_0ba8b0e10d344b3eb614773590bdd980","lf_exec_72290b2aca3944d795649f521bbdb34a","lf_exec_8fa5e3904bdb49e1b02671d598e01e9a","lf_exec_51970a21ec4e4a0a9a8ae26ffc8e08f8","lf_exec_7061a0d63bdd44a5aa896c57abd5a946","lf_exec_11419e2a4d094c319b427acd07865630")
EXPECTED={"executions":7,"execution_events":27,"recovery_contexts":0,"retention_holds":0}
HEX64=re.compile(r"^[0-9a-f]{64}$")
class CleanupError(RuntimeError): pass
def canonical(value): return (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def write_new(path,value):
 with Path(path).open("xb") as stream: stream.write(canonical(value))
 Path(path).chmod(0o600)
def values_sql(): return ",".join("'"+value+"'" for value in EXECUTIONS)
def state_sql(lock=False):
 prefix="SELECT pg_advisory_xact_lock(hashtext('lf015-synthetic-cleanup-v1')); LOCK TABLE leadflow.executions,leadflow.execution_events,leadflow.recovery_contexts,leadflow.retention_holds,leadflow.dsr_requests,leadflow.dsr_tombstones,leadflow.dsr_restore_evidence_outbox IN SHARE ROW EXCLUSIVE MODE;" if lock else ""
 ids=values_sql()
 return prefix+f"""SELECT json_build_object('executions',(SELECT count(*) FROM leadflow.executions WHERE execution_id IN ({ids})),'execution_events',(SELECT count(*) FROM leadflow.execution_events WHERE execution_id IN ({ids})),'recovery_contexts',(SELECT count(*) FROM leadflow.recovery_contexts WHERE execution_id IN ({ids})),'retention_holds',(SELECT count(*) FROM leadflow.retention_holds WHERE execution_id IN ({ids})),'all_executions',(SELECT count(*) FROM leadflow.executions),'all_execution_events',(SELECT count(*) FROM leadflow.execution_events),'outside_duplicate_children',(SELECT count(*) FROM leadflow.executions WHERE duplicate_of IN ({ids}) AND execution_id NOT IN ({ids})),'dsr_requests',(SELECT count(*) FROM leadflow.dsr_requests),'dsr_tombstones',(SELECT count(*) FROM leadflow.dsr_tombstones),'dsr_outbox',(SELECT count(*) FROM leadflow.dsr_restore_evidence_outbox));"""
def find_container(runner=subprocess.run):
 result=runner(["docker","ps","--filter",f"label=com.docker.compose.project={PROJECT}","--filter",f"label=com.docker.compose.service={SERVICE}","--format","{{.ID}}"],capture_output=True,text=True,timeout=15,check=False)
 ids=[line.strip() for line in result.stdout.splitlines() if line.strip()] if result.returncode==0 else []
 if len(ids)!=1: raise CleanupError("PostgreSQL container identity mismatch")
 return ids[0]
def database(sql,runner=subprocess.run):
 container=find_container(runner); command=["docker","exec","-i",container,"sh","-eu","-c",'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_MIGRATOR_USER" -d "$POSTGRES_DB" -At']
 result=runner(command,cwd=ROOT,input=sql,text=True,capture_output=True,timeout=60,check=False)
 if result.returncode: raise CleanupError("PostgreSQL operation failed")
 return result.stdout.strip().splitlines()[-1]
def validate_state(value,allow_absent=False):
 required=set(EXPECTED)|{"all_executions","all_execution_events","outside_duplicate_children","dsr_requests","dsr_tombstones","dsr_outbox"}
 if set(value)!=required or any(not isinstance(item,int) or isinstance(item,bool) or item<0 for item in value.values()): raise CleanupError("PostgreSQL inventory invalid")
 exact=all(value[name]==count for name,count in EXPECTED.items()) and value["all_executions"]==7 and value["all_execution_events"]==27 and value["outside_duplicate_children"]==0
 absent=allow_absent and all(value[name]==0 for name in ("executions","execution_events","recovery_contexts","retention_holds","all_executions","all_execution_events","outside_duplicate_children"))
 if not exact and not absent: raise CleanupError("PostgreSQL inventory mismatch")
 return value
def inventory(runner=subprocess.run): return validate_state(json.loads(database(state_sql(),runner)))
def load_manifest(path):
 value=json.loads(Path(path).read_text(encoding="utf-8"))
 if set(value)!={"version","scope","execution_ids","expected","dsr_before"} or value.get("version")!=VERSION or value.get("scope")!="authorized_synthetic_only" or value.get("execution_ids")!=list(EXECUTIONS) or value.get("expected")!=EXPECTED: raise CleanupError("cleanup manifest invalid")
 dsr=value.get("dsr_before")
 if set(dsr or {})!={"requests","tombstones","outbox"} or any(not isinstance(item,int) or isinstance(item,bool) or item<0 for item in dsr.values()): raise CleanupError("cleanup manifest invalid")
 return value
def apply(manifest,runner=subprocess.run):
 ids=values_sql(); before=manifest["dsr_before"]
 sql="BEGIN ISOLATION LEVEL SERIALIZABLE;"+state_sql(True)+f"""
DO $cleanup$ BEGIN
 IF NOT (
  (
   (SELECT count(*) FROM leadflow.executions)=7
   AND (SELECT count(*) FROM leadflow.execution_events)=27
   AND (SELECT count(*) FROM leadflow.executions WHERE execution_id IN ({ids}))=7
   AND (SELECT count(*) FROM leadflow.execution_events WHERE execution_id IN ({ids}))=27
  )
  OR (
   (SELECT count(*) FROM leadflow.executions)=0
   AND (SELECT count(*) FROM leadflow.execution_events)=0
  )
 ) THEN RAISE EXCEPTION 'inventory mismatch'; END IF;
 IF EXISTS(SELECT 1 FROM leadflow.recovery_contexts WHERE execution_id IN ({ids})) THEN RAISE EXCEPTION 'unexpected recovery context'; END IF;
 IF (SELECT count(*) FROM leadflow.executions WHERE execution_id IN ({ids})) NOT IN (0,7) THEN RAISE EXCEPTION 'authorized set mismatch'; END IF;
 IF EXISTS(SELECT 1 FROM leadflow.executions WHERE duplicate_of IN ({ids}) AND execution_id NOT IN ({ids})) THEN RAISE EXCEPTION 'unauthorized dependency'; END IF;
 IF EXISTS(SELECT 1 FROM leadflow.retention_holds WHERE execution_id IN ({ids})) THEN RAISE EXCEPTION 'retention evidence dependency'; END IF;
 IF (SELECT count(*) FROM leadflow.dsr_requests)<>{before['requests']} OR (SELECT count(*) FROM leadflow.dsr_tombstones)<>{before['tombstones']} OR (SELECT count(*) FROM leadflow.dsr_restore_evidence_outbox)<>{before['outbox']} THEN RAISE EXCEPTION 'DSR state changed'; END IF;
END $cleanup$;
DELETE FROM leadflow.execution_events WHERE execution_id IN ({ids});
DELETE FROM leadflow.recovery_contexts WHERE execution_id IN ({ids});
DELETE FROM leadflow.executions WHERE execution_id IN ({ids}) AND duplicate_of IS NOT NULL;
DELETE FROM leadflow.executions WHERE execution_id IN ({ids});
DO $postcheck$ BEGIN
 IF EXISTS(SELECT 1 FROM leadflow.executions)
 OR EXISTS(SELECT 1 FROM leadflow.execution_events)
 OR EXISTS(SELECT 1 FROM leadflow.recovery_contexts WHERE execution_id IN ({ids}))
 OR EXISTS(SELECT 1 FROM leadflow.retention_holds WHERE execution_id IN ({ids}))
 THEN RAISE EXCEPTION 'cleanup postcheck failed'; END IF;
 IF (SELECT count(*) FROM leadflow.dsr_requests)<>{before['requests']}
 OR (SELECT count(*) FROM leadflow.dsr_tombstones)<>{before['tombstones']}
 OR (SELECT count(*) FROM leadflow.dsr_restore_evidence_outbox)<>{before['outbox']}
 THEN RAISE EXCEPTION 'DSR postcheck failed'; END IF;
END $postcheck$;
SELECT json_build_object('executions',(SELECT count(*) FROM leadflow.executions WHERE execution_id IN ({ids})),'events',(SELECT count(*) FROM leadflow.execution_events WHERE execution_id IN ({ids})),'contexts',(SELECT count(*) FROM leadflow.recovery_contexts WHERE execution_id IN ({ids})),'holds',(SELECT count(*) FROM leadflow.retention_holds WHERE execution_id IN ({ids})),'dsr_requests',(SELECT count(*) FROM leadflow.dsr_requests),'dsr_tombstones',(SELECT count(*) FROM leadflow.dsr_tombstones),'dsr_outbox',(SELECT count(*) FROM leadflow.dsr_restore_evidence_outbox)); COMMIT;"""
 result=json.loads(database(sql,runner))
 expected={"executions":0,"events":0,"contexts":0,"holds":0,"dsr_requests":before["requests"],"dsr_tombstones":before["tombstones"],"dsr_outbox":before["outbox"]}
 if result!=expected: raise CleanupError("PostgreSQL cleanup not reconciled")
 return result
def main(argv=None,runner=subprocess.run):
 parser=argparse.ArgumentParser(); parser.add_argument("action",choices=("dry-run","apply","verify")); parser.add_argument("--manifest",required=True,type=Path); parser.add_argument("--authorize-manifest-sha256"); args=parser.parse_args(argv)
 try:
  if args.action=="dry-run":
   current=inventory(runner); value={"version":VERSION,"scope":"authorized_synthetic_only","execution_ids":list(EXECUTIONS),"expected":EXPECTED,"dsr_before":{"requests":current["dsr_requests"],"tombstones":current["dsr_tombstones"],"outbox":current["dsr_outbox"]}}; write_new(args.manifest,value); print(f"lf015_postgres_cleanup phase=dry_run status=PASS executions=7 events=27 manifest_sha256={digest(value)}"); return 0
  value=load_manifest(args.manifest)
  if not args.authorize_manifest_sha256 or args.authorize_manifest_sha256!=digest(value): raise CleanupError("manifest authorization mismatch")
  if args.action=="apply": apply(value,runner)
  current=validate_state(json.loads(database(state_sql(),runner)),True)
  if any(current[name] for name in ("executions","execution_events","recovery_contexts","retention_holds","all_executions","all_execution_events")): raise CleanupError("PostgreSQL cleanup incomplete")
  if {"requests":current["dsr_requests"],"tombstones":current["dsr_tombstones"],"outbox":current["dsr_outbox"]}!=value["dsr_before"]: raise CleanupError("DSR state changed")
  print(f"lf015_postgres_cleanup phase={args.action.replace('-','_')} status=PASS executions=0 events=0 dsr_preserved=PASS"); return 0
 except Exception:
  print(f"lf015_postgres_cleanup phase={getattr(args,'action','validation').replace('-','_')} status=FAIL error_id=LF015-POSTGRES-CLEANUP",file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())
