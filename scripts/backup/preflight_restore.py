#!/usr/bin/env python3
"""Non-destructive grouped preflight for an isolated LF015 restore."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import hashlib,json,os,re,shutil,stat,subprocess,sys
BACKUP_DIR=Path(__file__).resolve().parent
if str(BACKUP_DIR) not in sys.path: sys.path.insert(0,str(BACKUP_DIR))
from dsr_restore_evidence import authority_from_export

PROJECT=re.compile(r"^[a-z0-9][a-z0-9_-]*$")
IDENTITY=re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+$")
GCS=re.compile(r"^gs://[^/]+/.+$")
HEX64=re.compile(r"^[0-9a-f]{64}$"); TECH=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
AUTHORITY_KEYS={"version","authority_export_id","coverage_started_at_utc","covered_through_utc","complete_through_sequence","event_count","evidence_ids","evidence_ids_sha256"}

def validate_projects(source,restore): return bool(PROJECT.fullmatch(source) and PROJECT.fullmatch(restore) and source!=restore)
def validate_identities(values): return len(set(values))==4 and all(IDENTITY.fullmatch(value) for value in values)
def volume_names(config): return {value.get("name",key) for key,value in config.get("volumes",{}).items() if isinstance(value,dict)}
def network_names(config): return {value.get("name",key) for key,value in config.get("networks",{}).items() if isinstance(value,dict)}
def validate_compose(source,destination):
 errors=[]
 for label,config in (("source",source),("restore",destination)):
  services=config.get("services",{}); networks=config.get("networks",{})
  if not {"postgres","n8n"}.issubset(services): errors.append(f"{label}_services")
  else:
   if services["postgres"].get("ports") or services["n8n"].get("ports"): errors.append(f"{label}_ports")
   postgres=set(services["postgres"].get("networks",{})); n8n=set(services["n8n"].get("networks",{})); used=postgres|n8n
   if not postgres&n8n or any(networks.get(name,{}).get("internal") is not True for name in used): errors.append(f"{label}_network")
 if volume_names(source)&volume_names(destination): errors.append("shared_volumes")
 if network_names(source)&network_names(destination): errors.append("shared_networks")
 return errors

def secure_file(value):
 path=Path(value)
 return path.is_absolute() and path.is_file() and path.stat().st_size>0 and stat.S_IMODE(path.stat().st_mode)&0o177==0
def secure_dir(value):
 path=Path(value)
 return path.is_absolute() and path.is_dir() and stat.S_IMODE(path.stat().st_mode)==0o700
def load_compose(root,project,override):
 result=subprocess.run(["docker","compose","-p",project,"-f",str(root/"compose.yaml"),"-f",override,"config","--format","json"],capture_output=True,text=True,timeout=30)
 if result.returncode: raise ValueError("compose config failed")
 return json.loads(result.stdout)
def authority_manifest(path):
 value=json.loads(Path(path).read_text(encoding="utf-8"))
 if set(value)!=AUTHORITY_KEYS or value.get("version")!="LF015-DSR-AUTHORITY-1" or not TECH.fullmatch(str(value.get("authority_export_id",""))) or not isinstance(value.get("complete_through_sequence"),int) or value["complete_through_sequence"]<0 or not isinstance(value.get("event_count"),int) or value["event_count"]<0 or not isinstance(value.get("evidence_ids"),list) or value["event_count"]!=len(value["evidence_ids"]) or len(set(value["evidence_ids"]))!=len(value["evidence_ids"]) or not all(HEX64.fullmatch(str(item)) for item in value["evidence_ids"]) or not HEX64.fullmatch(str(value.get("evidence_ids_sha256",""))): raise ValueError("invalid authority manifest")
 started=datetime.fromisoformat(str(value.get("coverage_started_at_utc","")).replace("Z","+00:00")); covered=datetime.fromisoformat(str(value.get("covered_through_utc","")).replace("Z","+00:00"))
 if started.tzinfo is None or covered.tzinfo is None or covered<started: raise ValueError("invalid authority manifest")
 digest=hashlib.sha256((json.dumps(value["evidence_ids"],sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
 if digest!=value["evidence_ids_sha256"]: raise ValueError("invalid authority manifest")
 return value
def authority_matches_export(export_path,manifest_path,backup_manifest):
 try: return authority_from_export(Path(export_path),Path(backup_manifest))==authority_manifest(manifest_path)
 except Exception: return False

def main():
 root=Path(__file__).resolve().parents[2]; results=[]
 def record(name,status): results.append((name,status)); print(f"preflight control={name} status={status}")
 tools=("docker","python3","node","sha256sum","curl","gcloud")
 if all(shutil.which(tool) for tool in tools): record("tools","PASS")
 else: record("tools","FAIL")
 source=os.environ.get("SOURCE_COMPOSE_PROJECT",""); restore=os.environ.get("RESTORE_COMPOSE_PROJECT","")
 if validate_projects(source,restore): record("projects","PASS")
 else: record("projects","FAIL")
 source_override=os.environ.get("BACKUP_COMPOSE_OVERRIDE",""); restore_override=os.environ.get("RESTORE_COMPOSE_OVERRIDE","")
 if all(Path(value).is_absolute() and Path(value).is_file() for value in (source_override,restore_override)) and source_override!=restore_override: record("compose_files","PASS")
 else: record("compose_files","FAIL")
 if not any(status=="FAIL" for _,status in results):
  try:
   errors=validate_compose(load_compose(root,source,source_override),load_compose(root,restore,restore_override)); record("compose_isolation","PASS" if not errors else "FAIL")
  except Exception: record("compose_isolation","FAIL")
 state=os.environ.get("RESTORE_STATE_DIR","")
 record("state_directory","PASS" if secure_dir(state) else "FAIL")
 backup_key=os.environ.get("BACKUP_KEY_FILE",""); dsr_key=os.environ.get("DSR_EVIDENCE_KEY_FILE","")
 record("keys","PASS" if backup_key!=dsr_key and secure_file(backup_key) and secure_file(dsr_key) else "FAIL")
 identities=[os.environ.get(name,"") for name in ("BACKUP_GCP_IDENTITY","DSR_EVIDENCE_WRITER_IDENTITY","DSR_EVIDENCE_ADMIN_IDENTITY","RESTORE_GCP_IDENTITY")]
 record("identities","PASS" if validate_identities(identities) else "FAIL")
 uris=[os.environ.get("RESTORE_GCS_URI",""),os.environ.get("DSR_EVIDENCE_URI","")]
 record("gcs_inputs","PASS" if len(set(uris))==2 and all(GCS.fullmatch(value) for value in uris) else "FAIL")
 manifest=os.environ.get("DSR_AUTHORITY_MANIFEST",""); export=os.environ.get("DSR_AUTHORITY_EXPORT",""); backup_manifest=os.environ.get("DSR_BACKUP_MANIFEST","")
 try:
  export_path=Path(export).resolve(); backup_path=Path(backup_manifest).resolve(); independent=secure_file(export_path) and secure_file(backup_path) and root.resolve() not in export_path.parents and root.resolve() not in backup_path.parents
  if not independent or not authority_matches_export(export_path,manifest,backup_path): raise ValueError("authority mismatch")
  record("authority_structure","PASS")
 except Exception: record("authority_structure","FAIL")
 mode=os.environ.get("LF015_DSR_AUTHORITY_MODE","")
 if mode=="synthetic_closed_set" and not any(status=="FAIL" for _,status in results): record("authority_scope","WARN")
 else: record("authority_scope","NOT_VERIFIED")
 record("iam_gcs_runtime","NOT_VERIFIED")
 if any(status=="FAIL" for _,status in results): return 1
 if any(status=="NOT_VERIFIED" for _,status in results): return 2
 return 0
if __name__=="__main__": raise SystemExit(main())
