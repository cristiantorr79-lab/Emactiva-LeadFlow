import contextlib,importlib.util,io,json,subprocess,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def load(name):
 path=ROOT/"scripts"/"admin"/name; spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

class FakeHubSpot:
 def __init__(self,inventory,fail=None): self.current={key:list(value) for key,value in inventory.items()}; self.fail=fail; self.calls=[]
 def inventory(self): return {key:list(value) for key,value in self.current.items()}
 def archive(self,kind,object_id):
  self.calls.append((kind,object_id))
  if self.fail==(kind,object_id): raise RuntimeError("synthetic transport failure")
  self.current[kind].remove(object_id)

class HubSpotCleanupTests(unittest.TestCase):
 def setUp(self):
  self.module=load("cleanup_lf015_hubspot.py")
  self.inventory={"contacts":["262843762244","262824626777",*[str(300000000000+index) for index in range(11)]],"tickets":sorted(self.module.KNOWN["tickets"]),"companies":["400000000001","400000000002"]}
 def test_manifest_apply_order_and_idempotent_reconciliation(self):
  manifest=self.module.manifest_from(self.inventory); client=FakeHubSpot(self.inventory)
  self.assertEqual(self.module.apply(client,manifest),19); self.assertEqual([kind for kind,_ in client.calls[:4]],["tickets"]*4); self.assertTrue(all(not values for values in client.current.values()))
  self.assertEqual(self.module.apply(client,manifest),0)
 def test_inventory_mismatch_and_unexpected_object_fail_closed(self):
  altered={key:list(value) for key,value in self.inventory.items()}; altered["contacts"].pop()
  with self.assertRaises(self.module.CleanupError): self.module.manifest_from(altered)
  manifest=self.module.manifest_from(self.inventory); client=FakeHubSpot(self.inventory); client.current["companies"].append("499999999999")
  with self.assertRaises(self.module.CleanupError): self.module.apply(client,manifest)
  self.assertEqual(client.calls,[])
 def test_partial_failure_is_reconcilable_without_repeating_archived_objects(self):
  manifest=self.module.manifest_from(self.inventory); target=manifest["objects"]["tickets"][1]; client=FakeHubSpot(self.inventory,fail=("tickets",target))
  with self.assertRaises(RuntimeError): self.module.apply(client,manifest)
  first=manifest["objects"]["tickets"][0]; self.assertNotIn(first,client.current["tickets"])
  client.fail=None; self.module.apply(client,manifest); self.assertEqual(sum(call==("tickets",first) for call in client.calls),1)
 def test_manifest_is_create_only_and_output_is_sanitized(self):
  with tempfile.TemporaryDirectory() as temporary:
   path=Path(temporary)/"manifest.json"; value=self.module.manifest_from(self.inventory); self.module.write_new(path,value)
   with self.assertRaises(FileExistsError): self.module.write_new(path,value)
  output=io.StringIO()
  with contextlib.redirect_stderr(output):
   original=self.module.resolve_token; self.module.resolve_token=lambda *_args,**_kwargs:"secret-canary"
   try: code=self.module.main(["verify","--map","unused","--manifest","missing","--authorize-manifest-sha256","0"*64],client_factory=lambda _token: (_ for _ in ()).throw(RuntimeError("secret-canary")))
   finally: self.module.resolve_token=original
  self.assertEqual(code,1); self.assertNotIn("secret-canary",output.getvalue())

class FakeRunner:
 def __init__(self,outputs,fail_at=None): self.outputs=list(outputs); self.calls=[]; self.fail_at=fail_at
 def __call__(self,command,**kwargs):
  self.calls.append((command,kwargs.get("input","")))
  if command[:2]==["docker","ps"]: return subprocess.CompletedProcess(command,0,"container-1\n","")
  index=sum(1 for cmd,_ in self.calls if cmd[:2]==["docker","exec"])-1
  if self.fail_at==index: return subprocess.CompletedProcess(command,1,"","synthetic-secret")
  return subprocess.CompletedProcess(command,0,self.outputs[index]+"\n","")

class PostgresCleanupTests(unittest.TestCase):
 def setUp(self): self.module=load("cleanup_lf015_postgres.py")
 def state(self,present=True,**changes):
  value={"executions":7 if present else 0,"execution_events":27 if present else 0,"recovery_contexts":0,"retention_holds":0,"all_executions":7 if present else 0,"all_execution_events":27 if present else 0,"outside_duplicate_children":0,"dsr_requests":0,"dsr_tombstones":0,"dsr_outbox":0}; value.update(changes); return value
 def manifest(self): return {"version":self.module.VERSION,"scope":"authorized_synthetic_only","execution_ids":list(self.module.EXECUTIONS),"expected":self.module.EXPECTED,"dsr_before":{"requests":0,"tombstones":0,"outbox":0}}
 def test_dry_run_rejects_unexpected_records_and_dependencies(self):
  with self.assertRaises(self.module.CleanupError): self.module.inventory(FakeRunner([json.dumps(self.state(all_executions=8))]))
  with self.assertRaises(self.module.CleanupError): self.module.inventory(FakeRunner([json.dumps(self.state(outside_duplicate_children=1))]))
 def test_transaction_is_manifest_scoped_and_preserves_dsr(self):
  result={"executions":0,"events":0,"contexts":0,"holds":0,"dsr_requests":0,"dsr_tombstones":0,"dsr_outbox":0}; runner=FakeRunner([json.dumps(result)])
  self.module.apply(self.manifest(),runner); sql=next(value for command,value in runner.calls if command[:2]==["docker","exec"])
  self.assertIn("BEGIN ISOLATION LEVEL SERIALIZABLE",sql); self.assertIn("pg_advisory_xact_lock",sql); self.assertNotIn("TRUNCATE",sql.upper()); self.assertNotIn("DELETE FROM leadflow.dsr_",sql)
  self.assertTrue(all(execution in sql for execution in self.module.EXECUTIONS))
 def test_apply_failure_is_reported_and_database_controls_rollback(self):
  runner=FakeRunner([],fail_at=0)
  with self.assertRaises(self.module.CleanupError): self.module.apply(self.manifest(),runner)
  sql=next(value for command,value in runner.calls if command[:2]==["docker","exec"]); self.assertIn("BEGIN ISOLATION LEVEL SERIALIZABLE",sql); self.assertIn("COMMIT",sql)
 def test_absent_state_is_idempotent_but_dsr_change_is_rejected(self):
  self.module.validate_state(self.state(False),True)
  with self.assertRaises(self.module.CleanupError): self.module.validate_state(self.state(False,dsr_requests=-1),True)
 def test_manifest_authorization_and_create_only(self):
  with tempfile.TemporaryDirectory() as temporary:
   path=Path(temporary)/"manifest.json"; value=self.manifest(); self.module.write_new(path,value); self.assertEqual(self.module.load_manifest(path),value)
   with self.assertRaises(FileExistsError): self.module.write_new(path,value)

if __name__=="__main__": unittest.main()
