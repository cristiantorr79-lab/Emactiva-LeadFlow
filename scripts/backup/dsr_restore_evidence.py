#!/usr/bin/env python3
"""Portable encrypted DSR restore-evidence outbox and bundle tooling."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys,tempfile,urllib.request
BACKUP_DIR=Path(__file__).resolve().parent
if str(BACKUP_DIR) not in sys.path: sys.path.insert(0,str(BACKUP_DIR))
from gcs_json_upload import upload_file
ROOT=Path(__file__).resolve().parents[2]; CRYPTO=ROOT/"scripts"/"backup"/"backup_crypto.mjs"
HEX64=re.compile(r"^[0-9a-f]{64}$"); TECH=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
def canonical(value): return (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()
def file_sha256(path):
 digest=hashlib.sha256()
 with path.open("rb") as stream:
  while chunk:=stream.read(1024*1024): digest.update(chunk)
 return digest.hexdigest()
def timestamp(value):
 parsed=datetime.fromisoformat(value.replace("Z","+00:00"));
 if parsed.tzinfo is None or parsed>datetime.now(timezone.utc).replace(microsecond=999999): raise ValueError("invalid timestamp")
 return parsed.astimezone(timezone.utc)
def validate_event(value):
 if set(value)!={"version","evidence_id","subject_token","disposition","effective_at_utc"} or value["version"]!="LF015-DSR-1" or not HEX64.fullmatch(value["evidence_id"]) or not HEX64.fullmatch(value["subject_token"]) or value["disposition"] not in {"deleted","restricted"}: raise ValueError("invalid event")
 timestamp(value["effective_at_utc"]); base={k:value[k] for k in ("version","subject_token","disposition","effective_at_utc")}
 if hashlib.sha256(canonical(base)).hexdigest()!=value["evidence_id"]: raise ValueError("invalid event digest")
 return value
def validate_authority(value,events):
 expected={"version","authority_export_id","coverage_started_at_utc","covered_through_utc","complete_through_sequence","event_count","evidence_ids","evidence_ids_sha256"}
 if set(value)!=expected or value["version"]!="LF015-DSR-AUTHORITY-1" or not TECH.fullmatch(str(value["authority_export_id"])) or not isinstance(value["complete_through_sequence"],int) or value["complete_through_sequence"]<0 or not isinstance(value["event_count"],int) or not isinstance(value["evidence_ids"],list): raise ValueError("invalid authority manifest")
 started=timestamp(value["coverage_started_at_utc"]); covered=timestamp(value["covered_through_utc"])
 if covered<started: raise ValueError("invalid authority coverage")
 ids=[event["evidence_id"] for event in events]
 if value["event_count"]!=len(ids) or value["evidence_ids"]!=ids or len(set(ids))!=len(ids) or not HEX64.fullmatch(str(value["evidence_ids_sha256"])) or hashlib.sha256(canonical(ids)).hexdigest()!=value["evidence_ids_sha256"]: raise ValueError("authority coverage mismatch")
 return value
def authority_from_export(path: Path,backup_manifest: Path|None=None):
 value=json.loads(Path(path).read_text(encoding="utf-8")); expected={"version","scope","source_system_id","authority_export_id","coverage_started_at_utc","covered_through_utc","complete_through_sequence","events"}
 if set(value)!=expected or value["version"]!="LF015-DSR-ADMIN-EXPORT-1" or value["scope"]!="synthetic_qa_closed_set" or not TECH.fullmatch(str(value["source_system_id"])) or not TECH.fullmatch(str(value["authority_export_id"])) or not isinstance(value["complete_through_sequence"],int) or value["complete_through_sequence"]<0 or not isinstance(value["events"],list): raise ValueError("invalid administrative export")
 started=timestamp(value["coverage_started_at_utc"]); covered=timestamp(value["covered_through_utc"])
 if covered<started: raise ValueError("invalid administrative coverage")
 if backup_manifest:
  backup=json.loads(Path(backup_manifest).read_text(encoding="utf-8")); created=datetime.strptime(backup["created_utc"],"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
  if created<started or created>covered: raise ValueError("backup outside administrative coverage")
 ids=[]; ordering=[]
 for expected_sequence,event in enumerate(value["events"],1):
  if set(event)!={"sequence","evidence_id","disposition","effective_at_utc","publication_state"} or event["sequence"]!=expected_sequence or not HEX64.fullmatch(str(event["evidence_id"])) or event["disposition"] not in {"deleted","restricted"} or event["publication_state"]!="confirmed": raise ValueError("incomplete administrative export")
  effective=timestamp(event["effective_at_utc"])
  if effective>covered: raise ValueError("administrative coverage excludes evidence")
  ids.append(event["evidence_id"]); ordering.append((event["effective_at_utc"],event["evidence_id"]))
 if value["complete_through_sequence"]!=len(value["events"]) or len(set(ids))!=len(ids) or ordering!=sorted(ordering): raise ValueError("incomplete administrative export")
 return {"version":"LF015-DSR-AUTHORITY-1","authority_export_id":value["authority_export_id"],"coverage_started_at_utc":value["coverage_started_at_utc"],"covered_through_utc":value["covered_through_utc"],"complete_through_sequence":value["complete_through_sequence"],"event_count":len(ids),"evidence_ids":ids,"evidence_ids_sha256":hashlib.sha256(canonical(ids)).hexdigest()}
def write_authority_manifest(export_path: Path,output: Path,backup_manifest: Path):
 encoded=canonical(authority_from_export(export_path,backup_manifest))
 if output.exists():
  if output.read_bytes()!=encoded: raise ValueError("authority manifest collision")
 else:
  with output.open("xb") as stream: stream.write(encoded)
  output.chmod(0o600)
 return json.loads(encoded)
def run_crypto(operation,key,source,destination):
 result=subprocess.run(["node",str(CRYPTO),operation,"--key-file",str(key),"--input",str(source),"--output",str(destination)],capture_output=True,text=True)
 if result.returncode: raise RuntimeError("cryptographic operation failed")
def secure_dir(value):
 path=Path(value).resolve(); mode=path.stat().st_mode&0o777
 if not path.is_dir() or mode!=0o700: raise ValueError("directory must be mode 0700")
 return path
def stage(record,key,spool):
 if set(record)!={"subject_token","disposition","effective_at_utc"} or not HEX64.fullmatch(record["subject_token"]) or record["disposition"] not in {"deleted","restricted"}: raise ValueError("invalid record")
 timestamp(record["effective_at_utc"]); base={"version":"LF015-DSR-1",**record}; event={"version":base["version"],"evidence_id":hashlib.sha256(canonical(base)).hexdigest(),**record}; validate_event(event)
 destination=spool/(event["evidence_id"]+".dsr.gcm")
 with tempfile.TemporaryDirectory(prefix="stage-",dir=spool) as temporary:
  temp=Path(temporary); plain=temp/"event.json"; encrypted=temp/"event.gcm"; plain.write_bytes(canonical(event)); plain.chmod(0o600)
  if destination.exists():
   restored=temp/"existing.json"; run_crypto("decrypt",key,destination,restored)
   if restored.read_bytes()!=canonical(event): raise ValueError("evidence collision")
  else:
   run_crypto("encrypt",key,plain,encrypted)
   try: os.link(encrypted,destination)
   except FileExistsError:
    restored=temp/"existing.json"; run_crypto("decrypt",key,destination,restored)
    if restored.read_bytes()!=canonical(event): raise ValueError("evidence collision")
   destination.chmod(0o600)
 return event,destination
def bundle(spool,key,output_dir,authority_manifest):
 events={}
 with tempfile.TemporaryDirectory(prefix="bundle-",dir=spool) as temporary:
  temp=Path(temporary)
  for artifact in sorted(spool.glob("*.dsr.gcm")):
   plain=temp/(artifact.stem+".json"); run_crypto("decrypt",key,artifact,plain); event=validate_event(json.loads(plain.read_text(encoding="utf-8"))); events[event["evidence_id"]]=event
  ordered=sorted(events.values(),key=lambda e:(e["effective_at_utc"],e["evidence_id"])); authority=validate_authority(json.loads(authority_manifest.read_text(encoding="utf-8")),ordered); covered=timestamp(authority["covered_through_utc"])
  if any(timestamp(e["effective_at_utc"])>covered for e in ordered): raise ValueError("authority coverage excludes evidence")
  value={"version":"LF015-DSR-BUNDLE-2","authority":authority,"event_count":len(ordered),"events_sha256":hashlib.sha256(canonical(ordered)).hexdigest(),"events":ordered}; encoded=canonical(value); bundle_id=hashlib.sha256(encoded).hexdigest(); output=output_dir/(bundle_id+".dsr-bundle.gcm")
  plain=temp/"bundle.json"; plain.write_bytes(encoded); plain.chmod(0o600)
  if output.exists():
   restored=temp/"existing-bundle.json"; run_crypto("decrypt",key,output,restored)
   if restored.read_bytes()!=encoded: raise ValueError("bundle collision")
  else:
   encrypted=temp/"bundle.gcm"; run_crypto("encrypt",key,plain,encrypted)
   try: os.link(encrypted,output)
   except FileExistsError:
    restored=temp/"existing-bundle.json"; run_crypto("decrypt",key,output,restored)
    if restored.read_bytes()!=encoded: raise ValueError("bundle collision")
   output.chmod(0o600)
 checksum=file_sha256(output)+"\n"; sidecar=Path(str(output)+".sha256")
 if sidecar.exists():
  if sidecar.read_text(encoding="ascii")!=checksum: raise ValueError("bundle checksum collision")
 else:
  with sidecar.open("x",encoding="ascii") as stream: stream.write(checksum)
  sidecar.chmod(0o600)
 return len(events),output,bundle_id
def validate_bundle(path,key,output,backup_manifest=None):
 run_crypto("decrypt",key,path,output); value=json.loads(output.read_text(encoding="utf-8"))
 if set(value)!={"version","authority","event_count","events_sha256","events"} or value["version"]!="LF015-DSR-BUNDLE-2" or not isinstance(value["events"],list) or not isinstance(value["event_count"],int) or value["event_count"]!=len(value["events"]) or not HEX64.fullmatch(value["events_sha256"]) or hashlib.sha256(canonical(value["events"])).hexdigest()!=value["events_sha256"]: raise ValueError("invalid bundle")
 ids=set()
 for event in value["events"]:
  validate_event(event)
  if event["evidence_id"] in ids: raise ValueError("invalid bundle ordering")
  ids.add(event["evidence_id"])
 if value["events"]!=sorted(value["events"],key=lambda e:(e["effective_at_utc"],e["evidence_id"])): raise ValueError("invalid bundle ordering")
 authority=validate_authority(value["authority"],value["events"]); covered=timestamp(authority["covered_through_utc"])
 if any(timestamp(event["effective_at_utc"])>covered for event in value["events"]): raise ValueError("authority coverage excludes evidence")
 if backup_manifest:
  backup=json.loads(backup_manifest.read_text(encoding="utf-8")); created=datetime.strptime(backup["created_utc"],"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
  if created<timestamp(authority["coverage_started_at_utc"]) or covered<created: raise ValueError("backup outside authority coverage")
 return value
def emit_sql(path: Path,output: Path):
 value=json.loads(path.read_text(encoding="utf-8")); events=value.get("events");
 if not isinstance(events,list): raise ValueError("invalid bundle")
 payload=canonical(events).decode().strip(); output.write_text("WITH replay AS MATERIALIZED (SELECT * FROM leadflow.replay_dsr_restore_evidence($lf015$"+payload+"$lf015$::jsonb)) SELECT applied_count||'|'||verified_count||'|'||leadflow.verify_dsr_restore_enforcement($lf015$"+payload+"$lf015$::jsonb) FROM replay;\n",encoding="utf-8"); output.chmod(0o600)
def publish(artifact: Path,prefix: str,identity: str):
 if not re.fullmatch(r"gs://[^/]+(?:/[A-Za-z0-9._/-]+)?",prefix) or not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+",identity) or not re.fullmatch(r"[0-9a-f]{64}\.(?:dsr|dsr-bundle)\.gcm",artifact.name): raise ValueError("invalid publication configuration")
 if any(os.environ.get(name) for name in ("GOOGLE_APPLICATION_CREDENTIALS","CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE","GCE_METADATA_HOST","GCE_METADATA_IP")): raise ValueError("credential override forbidden")
 category="bundles" if artifact.name.endswith(".dsr-bundle.gcm") else "events"; expected_name="DSR_EVIDENCE_ADMIN_IDENTITY" if category=="bundles" else "DSR_EVIDENCE_WRITER_IDENTITY"
 if os.environ.get(expected_name)!=identity: raise ValueError("publication identity mismatch")
 others={os.environ.get(name) for name in ("BACKUP_GCP_IDENTITY","RESTORE_GCP_IDENTITY","DSR_EVIDENCE_WRITER_IDENTITY","DSR_EVIDENCE_ADMIN_IDENTITY") if name!=expected_name and os.environ.get(name)}
 if identity in others: raise ValueError("publication identity is not separated")
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); request=urllib.request.Request("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",headers={"Metadata-Flavor":"Google"})
 with opener.open(request,timeout=5) as response: managed=response.read(320).decode().strip()
 if managed!=identity: raise ValueError("managed identity mismatch")
 destination=prefix.rstrip("/")+"/"+category+"/"+artifact.name
 upload_file(artifact,destination,int(os.environ.get("GCS_UPLOAD_TIMEOUT_SECONDS","300")))
 if category=="bundles":
  sidecar=Path(str(artifact)+".sha256")
  if not sidecar.is_file(): raise ValueError("bundle checksum missing")
  upload_file(sidecar,destination+".sha256",int(os.environ.get("GCS_UPLOAD_TIMEOUT_SECONDS","300")))
 return destination
def main():
 parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
 p=sub.add_parser("stage"); p.add_argument("--key-file",required=True,type=Path); p.add_argument("--spool-dir",required=True)
 p=sub.add_parser("bundle"); p.add_argument("--key-file",required=True,type=Path); p.add_argument("--events-dir",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--authority-manifest",required=True,type=Path)
 p=sub.add_parser("validate-bundle"); p.add_argument("--key-file",required=True,type=Path); p.add_argument("--input",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--backup-manifest",type=Path)
 p=sub.add_parser("emit-sql"); p.add_argument("--input",required=True,type=Path); p.add_argument("--output",required=True,type=Path)
 p=sub.add_parser("authority-manifest"); p.add_argument("--admin-export",required=True,type=Path); p.add_argument("--backup-manifest",required=True,type=Path); p.add_argument("--output",required=True,type=Path)
 p=sub.add_parser("publish"); p.add_argument("--artifact",required=True,type=Path); p.add_argument("--gcs-prefix",required=True); p.add_argument("--writer-identity",required=True)
 args=parser.parse_args()
 try:
  if args.command=="stage":
   event,path=stage(json.load(sys.stdin),args.key_file,secure_dir(args.spool_dir)); print(json.dumps({"status":"pending_confirmation","evidence_id":event["evidence_id"],"artifact":str(path)},separators=(",",":")))
  elif args.command=="bundle":
   count,path,bundle_id=bundle(secure_dir(args.events_dir),args.key_file,secure_dir(args.output_dir),args.authority_manifest); print(json.dumps({"status":"created","event_count":count,"bundle_id":bundle_id,"artifact":str(path)},separators=(",",":")))
  elif args.command=="validate-bundle": print(json.dumps({"status":"valid","event_count":len(validate_bundle(args.input,args.key_file,args.output,args.backup_manifest)["events"])},separators=(",",":")))
  elif args.command=="emit-sql": emit_sql(args.input,args.output); print(json.dumps({"status":"created"},separators=(",",":")))
  elif args.command=="authority-manifest": value=write_authority_manifest(args.admin_export,args.output,args.backup_manifest); print(json.dumps({"status":"created","event_count":value["event_count"]},separators=(",",":")))
  else: print(json.dumps({"status":"pending_confirmation","object":publish(args.artifact,args.gcs_prefix,args.writer_identity)},separators=(",",":")))
  return 0
 except Exception: print(json.dumps({"status":"failed","result_code":"dsr_restore_evidence_error"},separators=(",",":"))); return 1
if __name__=="__main__": raise SystemExit(main())
