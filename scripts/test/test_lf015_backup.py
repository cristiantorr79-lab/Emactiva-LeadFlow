"""Focused synthetic tests for LF015; no Docker or Google Cloud operations."""
from __future__ import annotations
import importlib.util,io,json,os,shutil,subprocess,sys,tarfile,tempfile,unittest
from datetime import datetime,timedelta,timezone
from unittest import mock
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; CRYPTO=ROOT/"scripts"/"backup"/"backup_crypto.mjs"
PROBE=ROOT/"scripts"/"backup"/"qa_restore_probe.sh"
_git_bash=Path(r"C:\Program Files\Git\bin\bash.exe"); BASH=str(_git_bash) if os.name=="nt" and _git_bash.exists() else shutil.which("bash")

class GcsJsonUploadTests(unittest.TestCase):
 def module(self):
  spec=importlib.util.spec_from_file_location("gcs_json_upload",ROOT/"scripts"/"backup"/"gcs_json_upload.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
 class Response:
  def __init__(self,status,payload=b"",location=None): self.status=status; self.payload=payload; self.location=location
  def read(self,_limit=None): return self.payload
  def getheader(self,name): return self.location if name=="Location" else None
 class Connection:
  def __init__(self,response,request_error=None): self.response=response; self.request_error=request_error; self.sent=bytearray()
  def request(self,*args,**kwargs):
   self.request_args=(args,kwargs)
   if self.request_error: raise self.request_error
  def getresponse(self): return self.response
  def close(self): pass
  def putrequest(self,*_args): pass
  def putheader(self,*_args): pass
  def endheaders(self): pass
  def send(self,value): self.sent.extend(value)
 def test_stream_upload_success_and_callers(self):
  module=self.module()
  with tempfile.TemporaryDirectory() as temporary:
   source=Path(temporary)/"artifact"; source.write_bytes(b"binary\x00payload")
   metadata=self.Connection(self.Response(200,b'{"access_token":"token"}')); session=self.Connection(self.Response(200,location="https://storage.googleapis.com/session?id=1")); upload=self.Connection(self.Response(200))
   with mock.patch.object(module.http.client,"HTTPConnection",return_value=metadata),mock.patch.object(module.http.client,"HTTPSConnection",side_effect=[session,upload]):
    self.assertEqual(module.upload_file(source,"gs://bucket-qa/path/artifact",30),"gs://bucket-qa/path/artifact")
   self.assertEqual(bytes(upload.sent),source.read_bytes())
   self.assertIn("ifGenerationMatch=0",session.request_args[0][1])
  backup=(ROOT/"scripts"/"backup"/"backup.sh").read_text(encoding="utf-8"); dsr=(ROOT/"scripts"/"backup"/"dsr_restore_evidence.py").read_text(encoding="utf-8")
  self.assertIn("gcs_json_upload.py",backup); self.assertIn("upload_file(artifact",dsr); self.assertNotIn("gcloud --quiet storage cp",backup+dsr)
 def test_conflict_forbidden_timeout_and_missing_token_fail_without_secrets(self):
  module=self.module()
  with tempfile.TemporaryDirectory() as temporary:
   source=Path(temporary)/"artifact"; source.write_bytes(b"x")
   def invoke(metadata_response,session_response=None,error=None):
    metadata=self.Connection(metadata_response,request_error=error)
    patches=[mock.patch.object(module.http.client,"HTTPConnection",return_value=metadata)]
    if session_response: patches.append(mock.patch.object(module.http.client,"HTTPSConnection",return_value=self.Connection(session_response)))
    with patches[0]:
     with (patches[1] if len(patches)>1 else mock.patch.object(module.http.client,"HTTPSConnection")):
      with self.assertRaises(Exception) as raised: module.upload_file(source,"gs://bucket-qa/object",2)
    return str(raised.exception)
   token=b'{"access_token":"secret-token"}'
   for status in (403,412):
    message=invoke(self.Response(200,token),self.Response(status,b"secret-response")); self.assertNotIn("secret",message); self.assertIn(str(status) if status==403 else "conflict",message)
   self.assertNotIn("secret",invoke(self.Response(200,token),error=TimeoutError("secret timeout")))
   self.assertIn("authentication failed",invoke(self.Response(200,b"{}")))
 def test_bundle_sidecar_failure_is_fail_closed(self):
  spec=importlib.util.spec_from_file_location("dsr",ROOT/"scripts"/"backup"/"dsr_restore_evidence.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as temporary:
   artifact=Path(temporary)/("d"*64+".dsr-bundle.gcm"); artifact.write_bytes(b"ciphertext"); Path(str(artifact)+".sha256").write_text("0"*64+"\n",encoding="ascii")
   response=mock.MagicMock(); response.__enter__.return_value.read.return_value=b"admin@example.iam.gserviceaccount.com"
   identities={"DSR_EVIDENCE_WRITER_IDENTITY":"writer@example.iam.gserviceaccount.com","DSR_EVIDENCE_ADMIN_IDENTITY":"admin@example.iam.gserviceaccount.com","RESTORE_GCP_IDENTITY":"restore@example.iam.gserviceaccount.com","BACKUP_GCP_IDENTITY":"backup@example.iam.gserviceaccount.com"}
   with mock.patch.dict(os.environ,identities,clear=False),mock.patch.object(module.urllib.request,"build_opener") as opener,mock.patch.object(module,"upload_file",side_effect=[None,RuntimeError("sidecar failed")]) as upload:
    opener.return_value.open.return_value=response
    with self.assertRaises(RuntimeError): module.publish(artifact,"gs://evidence-test/prefix","admin@example.iam.gserviceaccount.com")
    self.assertEqual(upload.call_count,2)

class RestorePreflightTests(unittest.TestCase):
 def module(self):
  spec=importlib.util.spec_from_file_location("preflight_restore",ROOT/"scripts"/"backup"/"preflight_restore.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
 def configs(self):
  source={"services":{"postgres":{"ports":[],"networks":{"source_net":{}},"volumes":[{"source":"source_pg","target":"/var/lib/postgresql/data"}]},"n8n":{"ports":[],"networks":{"source_net":{}},"volumes":[{"source":"source_n8n","target":"/home/node/.n8n"}]}},"networks":{"source_net":{"name":"source_net","internal":True}},"volumes":{"source_pg":{"name":"source_pg"},"source_n8n":{"name":"source_n8n"}}}
  restore={"services":{"postgres":{"ports":[],"networks":{"restore_net":{}},"volumes":[{"source":"restore_pg","target":"/var/lib/postgresql/data"}]},"n8n":{"ports":[],"networks":{"restore_net":{}},"volumes":[{"source":"restore_n8n","target":"/home/node/.n8n"}]}},"networks":{"restore_net":{"name":"restore_net","internal":True}},"volumes":{"restore_pg":{"name":"restore_pg"},"restore_n8n":{"name":"restore_n8n"}}}
  return source,restore
 def test_isolated_configs_pass(self):
  module=self.module(); source,restore=self.configs(); self.assertEqual(module.validate_compose(source,restore),[]); self.assertTrue(module.validate_projects("lf015-qa","lf015-restore-run"))
  override=(ROOT/"labs"/"LAB-LF-015"/"restore-isolated.override.yaml").read_text(encoding="utf-8"); self.assertIn("ports: !reset []",override); self.assertIn("internal: true",override); self.assertNotIn("password",override.lower()); self.assertNotIn("C:\\",override)
 def test_same_project_shared_volume_and_published_port_fail(self):
  module=self.module(); source,restore=self.configs(); self.assertFalse(module.validate_projects("lf015-qa","lf015-qa"))
  restore["volumes"]["restore_pg"]["name"]="source_pg"; restore["networks"]["restore_net"]["name"]="source_net"; restore["services"]["n8n"]["ports"]=[{"published":5678,"target":5678}]
  errors=module.validate_compose(source,restore); self.assertIn("shared_volumes",errors); self.assertIn("shared_networks",errors); self.assertIn("restore_ports",errors)
  del restore["services"]["postgres"]; self.assertIn("restore_services",module.validate_compose(source,restore))
 def test_identity_configuration_and_missing_authority_fail(self):
  module=self.module(); identities=["backup@example.test","writer@example.test","admin@example.test","restore@example.test"]; self.assertTrue(module.validate_identities(identities)); self.assertFalse(module.validate_identities([identities[0]]*4))
  with self.assertRaises(Exception): module.authority_manifest("missing-authority.json")

class DsrQaAuthorityTests(unittest.TestCase):
 def modules(self):
  spec=importlib.util.spec_from_file_location("dsr_authority",ROOT/"scripts"/"backup"/"dsr_restore_evidence.py"); dsr=importlib.util.module_from_spec(spec); spec.loader.exec_module(dsr)
  spec=importlib.util.spec_from_file_location("restore_preflight",ROOT/"scripts"/"backup"/"preflight_restore.py"); preflight=importlib.util.module_from_spec(spec); spec.loader.exec_module(preflight)
  spec=importlib.util.spec_from_file_location("dsr_qa_authority",ROOT/"scripts"/"backup"/"dsr_qa_authority.py"); journal=importlib.util.module_from_spec(spec); spec.loader.exec_module(journal); return dsr,preflight,journal
 def export(self,events=(),complete=None):
  return {"version":"LF015-DSR-ADMIN-EXPORT-1","scope":"synthetic_qa_closed_set","source_system_id":"lf015-qa-admin-journal","authority_export_id":"lf015-export-1","coverage_started_at_utc":"2025-11-10T10:00:00Z","covered_through_utc":"2025-11-10T12:00:00Z","complete_through_sequence":len(events) if complete is None else complete,"events":list(events)}
 def event(self,sequence,fill,disposition): return {"sequence":sequence,"evidence_id":fill*64,"disposition":disposition,"effective_at_utc":f"2025-11-10T11:0{sequence}:00Z","publication_state":"confirmed"}
 def backup(self,path,created="20251110T103000Z"):
  path.write_text(json.dumps({"created_utc":created}),encoding="utf-8"); return path
 def test_zero_events_has_demonstrable_closed_sequence(self):
  dsr,_,_=self.modules()
  with tempfile.TemporaryDirectory() as temporary:
   path=Path(temporary)/"export.json"; path.write_text(json.dumps(self.export()),encoding="utf-8"); authority=dsr.authority_from_export(path)
   self.assertEqual((authority["complete_through_sequence"],authority["event_count"],authority["evidence_ids"]),(0,0,[]))
 def test_delete_restrict_export_and_manifest_match(self):
  dsr,preflight,_=self.modules(); events=[self.event(1,"a","deleted"),self.event(2,"b","restricted")]
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); export=root/"export.json"; manifest=root/"authority.json"; backup=self.backup(root/"backup.json"); export.write_text(json.dumps(self.export(events)),encoding="utf-8"); value=dsr.write_authority_manifest(export,manifest,backup)
   self.assertEqual(value["evidence_ids"],["a"*64,"b"*64]); self.assertTrue(preflight.authority_matches_export(export,manifest,backup))
   altered=json.loads(manifest.read_text()); altered["evidence_ids"]=["a"*64]; manifest.write_text(json.dumps(altered)); self.assertFalse(preflight.authority_matches_export(export,manifest,backup))
 def test_missing_pending_or_incomplete_sequences_fail_closed(self):
  dsr,_,_=self.modules(); valid=[self.event(1,"a","deleted"),self.event(2,"b","restricted")]
  cases=[self.export([valid[1]],complete=2),self.export(valid,complete=3),self.export([{**valid[0],"publication_state":"pending"}])]
  with tempfile.TemporaryDirectory() as temporary:
   for index,value in enumerate(cases):
    path=Path(temporary)/f"bad-{index}.json"; path.write_text(json.dumps(value),encoding="utf-8")
    with self.assertRaises(ValueError): dsr.authority_from_export(path)
   with self.assertRaises(FileNotFoundError): dsr.authority_from_export(Path(temporary)/"absent.json")
 def test_missing_evidence_rejects_bundle_authority(self):
  dsr,_,_=self.modules(); events=[self.event(1,"a","deleted"),self.event(2,"b","restricted")]
  with tempfile.TemporaryDirectory() as temporary:
   path=Path(temporary)/"export.json"; path.write_text(json.dumps(self.export(events)),encoding="utf-8"); authority=dsr.authority_from_export(path)
   evidence=[{"version":"LF015-DSR-1","evidence_id":"a"*64,"subject_token":"c"*64,"disposition":"deleted","effective_at_utc":events[0]["effective_at_utc"]}]
   with self.assertRaises(ValueError): dsr.validate_authority(authority,evidence)
 def test_journal_records_confirmed_events_and_exports_checkpoint(self):
  dsr,_,journal=self.modules()
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); spool=root/"spool"; spool.mkdir(); spool.chmod(0o700); key=root/"key"; key.write_bytes(b"k"*32); key.chmod(0o600)
   first=root/"journal-000.json"; journal.initialize(first,"lf015-qa-admin-journal","2025-11-10T10:00:00Z")
   current=first
   for index,(fill,disposition) in enumerate((("d","deleted"),("e","restricted")),1):
    _,artifact=dsr.stage({"subject_token":fill*64,"disposition":disposition,"effective_at_utc":f"2025-11-10T11:0{index}:00Z"},key,spool)
    following=root/f"journal-00{index}.json"; journal.record(current,artifact,key,following); current=following
   checkpoint=root/"journal-003.json"; journal.checkpoint(current,"2025-11-10T12:00:00Z",0,checkpoint)
   export=root/"export.json"; journal.export(checkpoint,export,"lf015-export-1"); value=json.loads(export.read_text())
   self.assertEqual((value["complete_through_sequence"],[item["disposition"] for item in value["events"]]),(2,["deleted","restricted"]))
   self.assertEqual(dsr.authority_from_export(export,self.backup(root/"backup.json"))["event_count"],2)
 def test_journal_and_backup_coverage_fail_closed(self):
  dsr,_,journal=self.modules()
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); initial=root/"journal.json"; journal.initialize(initial,"lf015-qa-admin-journal","2025-11-10T10:00:00Z")
   with self.assertRaises(ValueError): journal.checkpoint(initial,"2025-11-10T11:00:00Z",1,root/"pending.json")
   export=root/"export.json"; journal.export(initial,export,"lf015-export-1")
   with self.assertRaises(ValueError): dsr.authority_from_export(export,self.backup(root/"old-backup.json","20251110T090000Z"))
   broken=json.loads(initial.read_text()); broken["snapshot_sequence"]=1; broken["previous_snapshot_sha256"]="0"*64; broken["latest_event_sequence"]=1; initial2=root/"broken.json"; initial2.write_text(json.dumps(broken))
   with self.assertRaises(ValueError): journal.load(initial2)

class QaRestoreProbeTests(unittest.TestCase):
 def setUp(self):
  if not BASH: self.skipTest("bash unavailable")
  self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.bin=self.root/"bin"; self.bin.mkdir(); self.state=self.root/"state"; self.state.mkdir(); self.override=self.root/"override.yaml"; self.override.write_text("services: {}\n",encoding="utf-8")
  docker=self.bin/"docker"; docker.write_text("""#!/usr/bin/env bash
set -eu
args="$*"
if [[ "$1" == compose && "$args" == *" config --format json"* ]]; then printf '%s\n' '{"services":{"postgres":{"networks":{"internal":{}}},"n8n":{"networks":{"internal":{}}}},"networks":{"internal":{"internal":true}}}'; exit 0; fi
if [[ "$1" == compose && "$args" == *" ps -q n8n"* ]]; then echo n8n-id; exit 0; fi
if [[ "$1" == compose && "$args" == *" ps -q postgres"* ]]; then echo postgres-id; exit 0; fi
if [[ "$1" == inspect && "$args" == *".Mounts"* ]]; then [[ "$args" == *"n8n-id"* ]] && echo 'volume|qa_n8n' || echo 'volume|qa_pg'; exit 0; fi
if [[ "$1" == inspect ]]; then [[ "$args" == *"n8n-id"* ]] && echo "$LF015_QA_COMPOSE_PROJECT|n8n" || echo "$LF015_QA_COMPOSE_PROJECT|postgres"; exit 0; fi
if [[ "$1" == volume && "$2" == inspect ]]; then echo "$LF015_QA_COMPOSE_PROJECT"; exit 0; fi
if [[ "$1" == compose && "$args" == *" psql "* ]]; then
 payload=$(cat)
 if [[ "$args" == *" -c "* && "$args" == *":'execution_id'"* ]]; then echo 'ERROR: syntax error at or near ":"' >&2; exit 1; fi
 if [[ "$payload" == *"leadflow.claim_event"* ]]; then
  [[ "${FAKE_SQL_FAIL:-0}" != 1 ]] || exit 1; : >"$FAKE_STATE/pg"
  for value in "$@"; do [[ "$value" == execution_id=* ]] && execution_id=${value#execution_id=}; done
  case "${FAKE_CLAIM_RESULT:-true}" in
   true) [[ "$payload" == *"CASE WHEN claimed THEN 't' ELSE 'f' END"* ]] && echo "t|$execution_id|" || echo "true|$execution_id|" ;;
   false) echo "f|$execution_id|other-execution" ;;
   malformed) echo "unexpected" ;;
  esac
  exit 0
 fi
 if [[ "$payload" == *"WITH owned AS MATERIALIZED"* ]]; then rm -f "$FAKE_STATE/pg"; echo '2|1'; exit 0; fi
 if [[ "$payload" == *"FROM leadflow.executions WHERE"* ]]; then [[ "${FAKE_INCONSISTENT:-0}" != 1 ]] || { echo '1|1|2'; exit 0; }; [[ -f "$FAKE_STATE/pg" ]] && echo '1|2|2' || echo '0|0|0'; exit 0; fi
fi
if [[ "$1" == exec && "$args" == *"sha256sum"* ]]; then sha256sum "$FAKE_STATE/probe"; exit 0; fi
if [[ "$1" == exec && "$args" == *"mkdir -p"* ]]; then [[ "${FAKE_N8N_WRITE_FAIL:-0}" != 1 ]] || exit 1; test ! -e "$FAKE_STATE/probe"; cat >"$FAKE_STATE/probe"; exit 0; fi
if [[ "$1" == exec && "$args" == *"if test -e"* ]]; then rm -f "$FAKE_STATE/probe"; exit 0; fi
exit 90
""",encoding="utf-8"); docker.chmod(0o755)
  python3=self.bin/"python3"; python3.write_text("#!/usr/bin/env bash\ncat >/dev/null\n",encoding="utf-8"); python3.chmod(0o755)
  def shell_path(path):
   value=path.resolve().as_posix(); return f"/{value[0].lower()}{value[2:]}" if len(value)>2 and value[1]==":" else value
  self.env={**os.environ,"PATH":str(self.bin)+os.pathsep+os.environ.get("PATH",""),"FAKE_STATE":shell_path(self.state),"LF015_QA_COMPOSE_PROJECT":"lf015-qa","LF015_QA_AUTHORIZED_PROJECT":"lf015-qa","LF015_QA_COMPOSE_OVERRIDE":shell_path(self.override),"POSTGRES_DB":"qa","POSTGRES_APP_USER":"app","POSTGRES_BOOTSTRAP_USER":"bootstrap"}
  self.run_id="lf015-20261026T120000Z-a1b2c3d4"
 def tearDown(self): self.temp.cleanup()
 def invoke(self,action,env=None): return subprocess.run([BASH,str(PROBE),action,self.run_id],text=True,capture_output=True,env=env or self.env)
 def test_prepare_verify_alteration_and_cleanup(self):
  inspected=self.invoke("inspect"); self.assertEqual(inspected.returncode,0); self.assertIn("postgres=0|0|0 n8n_sha256=ABSENT",inspected.stdout)
  prepared=self.invoke("prepare"); self.assertEqual(prepared.returncode,0,(prepared.stdout,prepared.stderr)); present=self.invoke("inspect"); self.assertEqual(present.returncode,0); self.assertIn("postgres=1|2|2",present.stdout); verified=self.invoke("verify"); self.assertEqual(verified.returncode,0,(verified.stdout,verified.stderr))
  duplicate=self.invoke("prepare"); self.assertNotEqual(duplicate.returncode,0); self.assertIn("phase=collision",duplicate.stderr)
  inconsistent=self.invoke("cleanup",{**self.env,"FAKE_INCONSISTENT":"1"}); self.assertNotEqual(inconsistent.returncode,0); self.assertTrue((self.state/"pg").exists())
  (self.state/"probe").write_text("altered\n",encoding="utf-8"); altered=self.invoke("verify"); self.assertNotEqual(altered.returncode,0); self.assertIn("phase=n8n_verify",altered.stderr)
  (self.state/"probe").write_text(json.dumps({"format":"LF015-QA-PROBE-1","run_id":self.run_id},separators=(",",":"))+"\n",encoding="utf-8")
  cleaned=self.invoke("cleanup"); self.assertEqual(cleaned.returncode,0,(cleaned.stdout,cleaned.stderr)); self.assertEqual(self.invoke("cleanup").returncode,0); self.assertFalse((self.state/"pg").exists()); self.assertFalse((self.state/"probe").exists())
 def test_wrong_or_missing_project_configuration_fails_closed(self):
  wrong={**self.env,"LF015_QA_AUTHORIZED_PROJECT":"original"}; result=self.invoke("prepare",wrong); self.assertNotEqual(result.returncode,0); self.assertIn("phase=compose_project",result.stderr,(result.stdout,result.stderr))
  missing={**self.env}; missing.pop("LF015_QA_COMPOSE_OVERRIDE"); result=self.invoke("prepare",missing); self.assertNotEqual(result.returncode,0); self.assertIn("phase=compose_override",result.stderr)
  invalid=subprocess.run([BASH,str(PROBE),"prepare","invalid"],text=True,capture_output=True,env=self.env); self.assertNotEqual(invalid.returncode,0); self.assertIn("phase=run_id",invalid.stderr)
 def test_sql_and_n8n_failures_leave_no_partial_probe(self):
  sql_failed=self.invoke("prepare",{**self.env,"FAKE_SQL_FAIL":"1"}); self.assertNotEqual(sql_failed.returncode,0); self.assertFalse((self.state/"pg").exists()); self.assertFalse((self.state/"probe").exists())
  n8n_failed=self.invoke("prepare",{**self.env,"FAKE_N8N_WRITE_FAIL":"1"}); self.assertNotEqual(n8n_failed.returncode,0); self.assertFalse((self.state/"pg").exists()); self.assertFalse((self.state/"probe").exists())
 def test_claim_boolean_is_normalized_and_false_or_malformed_are_rejected(self):
  accepted=self.invoke("prepare"); self.assertEqual(accepted.returncode,0,(accepted.stdout,accepted.stderr)); self.assertEqual(self.invoke("cleanup").returncode,0)
  for claim_result in ("false","malformed"):
   rejected=self.invoke("prepare",{**self.env,"FAKE_CLAIM_RESULT":claim_result}); self.assertNotEqual(rejected.returncode,0); self.assertIn("phase=postgres_prepare",rejected.stderr); self.assertFalse((self.state/"pg").exists()); self.assertFalse((self.state/"probe").exists())
class BackupCryptoTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.dir=Path(self.temp.name); self.key=self.dir/"key"; self.key.write_bytes(os.urandom(32))
  if os.name=="posix": self.key.chmod(0o600)
 def tearDown(self): self.temp.cleanup()
 def invoke(self,operation,source,destination):
  return subprocess.run(["node",str(CRYPTO),operation,"--key-file",str(self.key),"--input",str(source),"--output",str(destination)],text=True,capture_output=True)
 def test_round_trip_and_no_plaintext(self):
  plain=self.dir/"plain"; encrypted=self.dir/"backup.gcm"; restored=self.dir/"restored"; payload=b"synthetic-record\x00"*10000; plain.write_bytes(payload)
  self.assertEqual(self.invoke("encrypt",plain,encrypted).returncode,0); self.assertNotIn(b"synthetic-record",encrypted.read_bytes()); self.assertEqual(self.invoke("decrypt",encrypted,restored).returncode,0); self.assertEqual(restored.read_bytes(),payload)
 def test_tamper_fails_and_cleans_output(self):
  plain=self.dir/"plain"; encrypted=self.dir/"backup.gcm"; restored=self.dir/"restored"; plain.write_bytes(b"synthetic"); self.assertEqual(self.invoke("encrypt",plain,encrypted).returncode,0)
  data=bytearray(encrypted.read_bytes()); data[-17]^=1; encrypted.write_bytes(data); result=self.invoke("decrypt",encrypted,restored); self.assertNotEqual(result.returncode,0); self.assertFalse(restored.exists()); self.assertNotIn("synthetic",result.stderr)
 def test_refuses_overwrite_and_bad_key(self):
  plain=self.dir/"plain"; encrypted=self.dir/"encrypted"; output=self.dir/"output"; plain.write_bytes(b"x"); output.write_bytes(b"valid"); self.assertNotEqual(self.invoke("encrypt",plain,output).returncode,0); self.assertEqual(output.read_bytes(),b"valid"); self.assertEqual(self.invoke("encrypt",plain,encrypted).returncode,0); self.assertNotEqual(self.invoke("decrypt",encrypted,output).returncode,0); self.assertEqual(output.read_bytes(),b"valid"); self.key.write_bytes(b"short"); self.assertNotEqual(self.invoke("encrypt",plain,self.dir/"new").returncode,0)
class ArchiveValidationTests(unittest.TestCase):
 def module(self):
  spec=importlib.util.spec_from_file_location("archive",ROOT/"scripts"/"backup"/"validate_restore_archive.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
  return module
 def archive(self,path,extra=(),payload=b"n8n"):
  manifest=json.dumps({"format":"LF015-1","backup_id":"leadflow-20261010T120000Z-aabbccddeeff.tar.gcm","created_utc":"20261010T120000Z","consistency":"n8n_paused_before_pg_dump_until_volume_copy"}).encode()
  with tarfile.open(path,"w") as archive:
   for name,data in (("manifest.json",manifest),("postgres.dump",b"pg"),("n8n/config",payload),*extra):
    info=tarfile.TarInfo(name); info.size=len(data); archive.addfile(info,io.BytesIO(data))
 def test_extracts_expected_layout_and_rejects_traversal(self):
  module=self.module()
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); good=root/"good.tar"; bad=root/"bad.tar"; self.archive(good); self.archive(bad,(("../escape",b"x"),))
   result=module.extract(good,root/"output",20,1024,512); self.assertEqual(result["format"],"LF015-1"); self.assertEqual((root/"output"/"n8n"/"config").read_bytes(),b"n8n")
   with self.assertRaises(ValueError): module.extract(bad,root/"bad-output",20,1024,512)
 def test_limits_fail_closed(self):
  module=self.module()
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); archive=root/"large.tar"; self.archive(archive,payload=b"x"*20)
   with self.assertRaises(ValueError): module.extract(archive,root/"limited",20,10,10)
 def test_rejects_duplicate_link_and_unexpected_content(self):
  module=self.module()
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary)
   duplicate=root/"duplicate.tar"; self.archive(duplicate,(("n8n/config",b"again"),))
   unexpected=root/"unexpected.tar"; self.archive(unexpected,(("secret.txt",b"x"),))
   linked=root/"linked.tar"; self.archive(linked)
   with tarfile.open(linked,"a") as archive:
    info=tarfile.TarInfo("n8n/link"); info.type=tarfile.SYMTYPE; info.linkname="/etc/passwd"; archive.addfile(info)
   for index,path in enumerate((duplicate,unexpected,linked)):
    with self.assertRaises(ValueError): module.extract(path,root/f"rejected-{index}",20,4096,1024)
class DsrRestoreEvidenceTests(unittest.TestCase):
 def module(self):
  spec=importlib.util.spec_from_file_location("evidence",ROOT/"scripts"/"backup"/"dsr_restore_evidence.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
 def authority(self,path,events,covered,sequence=2):
  import hashlib
  ids=[event["evidence_id"] for event in sorted(events,key=lambda e:(e["effective_at_utc"],e["evidence_id"]))]
  value={"version":"LF015-DSR-AUTHORITY-1","authority_export_id":"synthetic-export-1","coverage_started_at_utc":"2020-01-01T00:00:00Z","covered_through_utc":covered,"complete_through_sequence":sequence,"event_count":len(ids),"evidence_ids":ids,"evidence_ids_sha256":hashlib.sha256((json.dumps(ids,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()}
  path.write_text(json.dumps(value),encoding="utf-8"); return path
 def test_old_backup_replays_later_delete_and_restriction_idempotently(self):
  module=self.module(); now=datetime.now(timezone.utc).replace(microsecond=0); backup_time=now-timedelta(minutes=3); delete_time=now-timedelta(minutes=2); restrict_time=now-timedelta(minutes=1)
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); spool=root/"spool"; spool.mkdir(mode=0o700); key=root/"key"; key.write_bytes(os.urandom(32)); key.chmod(0o600)
   delete={"subject_token":"a"*64,"disposition":"deleted","effective_at_utc":delete_time.isoformat().replace("+00:00","Z")}; restrict={"subject_token":"b"*64,"disposition":"restricted","effective_at_utc":restrict_time.isoformat().replace("+00:00","Z")}
   first,path=module.stage(delete,key,spool); again,same=module.stage(delete,key,spool); self.assertEqual((first["evidence_id"],path),(again["evidence_id"],same)); second,_=module.stage(restrict,key,spool)
   self.assertNotIn(b"a"*64,path.read_bytes())
   bundles=root/"bundles"; bundles.mkdir(mode=0o700); covered=now.isoformat().replace("+00:00","Z"); authority=self.authority(root/"authority.json",[first,second],covered); count,bundle,bundle_id=module.bundle(spool,key,bundles,authority); count_again,same_bundle,same_id=module.bundle(spool,key,bundles,authority); self.assertEqual((count,bundle,bundle_id),(count_again,same_bundle,same_id)); self.assertEqual(count,2)
   manifest=root/"manifest.json"; manifest.write_text(json.dumps({"created_utc":backup_time.strftime("%Y%m%dT%H%M%SZ")}),encoding="utf-8")
   plain=root/"bundle.json"; value=module.validate_bundle(bundle,key,plain,manifest); self.assertEqual([e["disposition"] for e in value["events"]],["deleted","restricted"])
   sql=root/"replay.sql"; module.emit_sql(plain,sql); generated=sql.read_text(encoding="utf-8"); self.assertIn("WITH replay AS MATERIALIZED",generated); self.assertIn("verify_dsr_restore_enforcement",generated); self.assertLess(generated.index("replay_dsr_restore_evidence"),generated.index("verify_dsr_restore_enforcement")); self.assertIn('"deleted"',generated); self.assertIn('"restricted"',generated)
 def test_missing_altered_incomplete_and_stale_evidence_fail(self):
  module=self.module(); now=datetime.now(timezone.utc).replace(microsecond=0)
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); spool=root/"spool"; spool.mkdir(mode=0o700); key=root/"key"; key.write_bytes(os.urandom(32)); key.chmod(0o600)
   with self.assertRaises(Exception): module.validate_bundle(root/"missing",key,root/"out")
   event,_=module.stage({"subject_token":"c"*64,"disposition":"deleted","effective_at_utc":(now-timedelta(minutes=2)).isoformat().replace("+00:00","Z")},key,spool)
   bundles=root/"bundles"; bundles.mkdir(mode=0o700); covered=(now-timedelta(minutes=1)).isoformat().replace("+00:00","Z"); authority=self.authority(root/"authority.json",[event],covered,1); _,bundle,_=module.bundle(spool,key,bundles,authority); data=bytearray(bundle.read_bytes()); data[-17]^=1; bundle.write_bytes(data)
   with self.assertRaises(Exception): module.validate_bundle(bundle,key,root/"altered")
   clean_dir=root/"clean-bundles"; clean_dir.mkdir(mode=0o700); current=self.authority(root/"current-authority.json",[event],now.isoformat().replace("+00:00","Z"),1); _,clean,_=module.bundle(spool,key,clean_dir,current); manifest=root/"manifest.json"; manifest.write_text(json.dumps({"created_utc":(now+timedelta(minutes=1)).strftime("%Y%m%dT%H%M%SZ")}),encoding="utf-8")
   with self.assertRaises(ValueError): module.validate_bundle(clean,key,root/"stale",manifest)
   incomplete={"version":"LF015-DSR-BUNDLE-2","authority":{},"event_count":2,"events_sha256":"0"*64,"events":[{"version":"LF015-DSR-1"}]}; incomplete_plain=root/"incomplete.json"; incomplete_plain.write_text(json.dumps(incomplete),encoding="utf-8"); incomplete_encrypted=root/"incomplete.gcm"; module.run_crypto("encrypt",key,incomplete_plain,incomplete_encrypted)
   with self.assertRaises(ValueError): module.validate_bundle(incomplete_encrypted,key,root/"incomplete-output")
   wrong=self.authority(root/"wrong-authority.json",[],now.isoformat().replace("+00:00","Z"),1)
   with self.assertRaises(ValueError): module.bundle(spool,key,clean_dir,wrong)
 def test_publication_failure_is_not_confirmed(self):
  module=self.module()
  with tempfile.TemporaryDirectory() as temporary:
   artifact=Path(temporary)/("d"*64+".dsr.gcm"); artifact.write_bytes(b"ciphertext")
   response=mock.MagicMock(); response.__enter__.return_value.read.return_value=b"writer@example.iam.gserviceaccount.com"
   identities={"DSR_EVIDENCE_WRITER_IDENTITY":"writer@example.iam.gserviceaccount.com","DSR_EVIDENCE_ADMIN_IDENTITY":"admin@example.iam.gserviceaccount.com","RESTORE_GCP_IDENTITY":"restore@example.iam.gserviceaccount.com","BACKUP_GCP_IDENTITY":"backup@example.iam.gserviceaccount.com"}
   with mock.patch.dict(os.environ,identities,clear=False),mock.patch.object(module.urllib.request,"build_opener") as opener,mock.patch.object(module,"upload_file",side_effect=RuntimeError("publication failed")):
    opener.return_value.open.return_value=response
    with self.assertRaises(RuntimeError): module.publish(artifact,"gs://evidence-test/prefix","writer@example.iam.gserviceaccount.com")
class ContractTests(unittest.TestCase):
 def test_retry_rejects_invalid_request_without_database_access(self):
  completed=subprocess.run([sys.executable,str(ROOT/"scripts"/"admin"/"retry_dsr_restore_protection.py")],input="{}",text=True,capture_output=True)
  self.assertNotEqual(completed.returncode,0); self.assertEqual(json.loads(completed.stdout)["result_code"],"retry_request_invalid")
 def test_policy_and_scripts(self):
  spec=importlib.util.spec_from_file_location("policy",ROOT/"scripts"/"validation"/"validate_backup_policy.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); policy=json.loads((ROOT/"config"/"backup-policy.json").read_text(encoding="utf-8")); self.assertEqual(module.validate(policy),[])
  backup=(ROOT/"scripts"/"backup"/"backup.sh").read_text(encoding="utf-8"); restore=(ROOT/"scripts"/"backup"/"restore.sh").read_text(encoding="utf-8"); schedule=(ROOT/"scripts"/"backup"/"install_schedule.sh").read_text(encoding="utf-8")
  self.assertNotIn("gcloud auth list",backup+restore)
  for required in ("metadata.google.internal","GCS_UPLOAD_TIMEOUT_SECONDS","gcs_json_upload.py","BACKUP_PAUSE_TIMEOUT_SECONDS","pg_dump","docker pause","docker unpause","trap cleanup","BACKUP_COMPOSE_PROJECT","SOURCE_COMPOSE_PROJECT","BACKUP_COMPOSE_OVERRIDE","com.docker.compose.project","com.docker.compose.service","N8N_MOUNT","docker volume inspect"): self.assertIn(required,backup)
  self.assertNotIn('COMPOSE_PROJECT_NAME:-leadflow',backup)
  self.assertIn('COMPOSE=(docker compose -p "$BACKUP_COMPOSE_PROJECT"',backup)
  self.assertIn('"$SOURCE_COMPOSE_PROJECT" == "$BACKUP_COMPOSE_PROJECT"',backup)
  self.assertIn('"${BACKUP_COMPOSE_OVERRIDE:-}" == /*',backup)
  self.assertLess(backup.index("docker pause"),backup.index("pg_dump"))
  for required in ("LEADFLOW_RESTORE_ISOLATED","RESTORE_GCP_IDENTITY","DSR_EVIDENCE_URI","DSR_EVIDENCE_KEY_FILE","validate-bundle","emit-sql","RECOVERABLE_FAILURE","traffic=DISABLED"): self.assertIn(required,restore)
  self.assertLess(restore.index("validate-bundle"),restore.index("MUTATED=1")); self.assertLess(restore.index("TARGET_N8N_MOUNT="),restore.index("MUTATED=1")); self.assertLess(restore.index("MUTATED=1"),restore.index("pg_restore --exit-on-error")); self.assertNotIn("SELECT disposition",restore)
  for required in ("BACKUP_SERVICE_USER","runuser","ProtectSystem=strict","NoNewPrivileges=true"): self.assertIn(required,schedule)
  migration=(ROOT/"database"/"migrations"/"024_dsr_restore_evidence.sql").read_text(encoding="utf-8"); admin=(ROOT/"scripts"/"admin"/"dsr_admin.py").read_text(encoding="utf-8")
  for required in ("dsr_restore_evidence_outbox","capture_dsr_restore_evidence_outbox","CREATE TRIGGER","record_dsr_restore_evidence","get_dsr_restore_evidence","replay_dsr_restore_evidence","verify_dsr_restore_enforcement","claim_event","DSR enforcement verification failed"): self.assertIn(required,migration)
  for required in ("restore_protection_status","pending_confirmation","evidence_not_preserved"): self.assertIn(required,admin)
  retry=(ROOT/"scripts"/"admin"/"retry_dsr_restore_protection.py").read_text(encoding="utf-8"); self.assertIn("get_dsr_restore_evidence",retry); self.assertNotIn("execute_dsr_request",retry)
 def test_backup_project_selection_fails_closed(self):
  backup=(ROOT/"scripts"/"backup"/"backup.sh").read_text(encoding="utf-8")
  self.assertIn('[[ -n "${BACKUP_COMPOSE_PROJECT:-}"',backup)
  self.assertIn('[[ -n "${SOURCE_COMPOSE_PROJECT:-}" && "$SOURCE_COMPOSE_PROJECT" == "$BACKUP_COMPOSE_PROJECT" ]] || die compose_project',backup)
  self.assertIn('[[ "${BACKUP_COMPOSE_OVERRIDE:-}" == /* && -f "$BACKUP_COMPOSE_OVERRIDE" && -r "$BACKUP_COMPOSE_OVERRIDE" ]] || die compose_override',backup)
  self.assertNotIn('COMPOSE_PROJECT_NAME:-leadflow',backup)
  self.assertLess(backup.index('com.docker.compose.project'),backup.index('docker pause'))
 def test_qa_probe_contract_and_cleanup_are_scoped(self):
  probe=(ROOT/"scripts"/"backup"/"qa_restore_probe.sh").read_text(encoding="utf-8")
  for required in ("LF015_QA_COMPOSE_PROJECT","LF015_QA_AUTHORIZED_PROJECT","LF015_QA_COMPOSE_OVERRIDE","com.docker.compose.project","docker volume inspect","LF015-QA-PROBE-1","leadflow.claim_event","1|2|2","0|0|0","2|1","cleanup_precondition"):
   self.assertIn(required,probe)
  self.assertNotIn("docker compose down",probe); self.assertNotIn("docker volume rm",probe); self.assertNotIn("DROP TABLE",probe)
  self.assertLess(probe.index("compose_config"),probe.index("leadflow.claim_event"))
  self.assertIn("test ! -e \"$path\"",probe)
 def test_qa_probe_matches_minimized_six_argument_claim_contract(self):
  probe=(ROOT/"scripts"/"backup"/"qa_restore_probe.sh").read_text(encoding="utf-8")
  minimized=(ROOT/"database"/"migrations"/"013_minimize_event_identity.sql").read_text(encoding="utf-8")
  dsr=(ROOT/"database"/"migrations"/"016_dsr_operations.sql").read_text(encoding="utf-8")
  self.assertIn("ALTER TABLE leadflow.executions DROP COLUMN event_id",minimized)
  self.assertIn("claim_event(p_execution_id text,p_source text,p_event_id text,p_idempotency_key text,p_lead_identifier text,p_subject_token text)",dsr)
  self.assertNotIn("AND event_id=",probe); self.assertNotIn("e.event_id",probe)
  self.assertIn(":'idempotency_key',:'lead_identifier',:'subject_token'",probe)
  self.assertIn("('received','validation'),('processing','idempotency')",probe)
  self.assertIn("CASE WHEN claimed THEN 't' ELSE 'f' END",probe)
if __name__=="__main__": unittest.main(verbosity=2)
