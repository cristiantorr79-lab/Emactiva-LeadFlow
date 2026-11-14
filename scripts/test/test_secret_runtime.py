"""Focused synthetic tests for least-privilege secret resolution."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr,redirect_stdout
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]


def load_module():
 spec=importlib.util.spec_from_file_location("compose_with_secrets",ROOT/"scripts"/"admin"/"compose_with_secrets.py")
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


class Response:
 def __init__(self,status,payload=b""): self.status=status; self.payload=payload
 def read(self,_limit=None): return self.payload


class Connection:
 def __init__(self,responses=()): self.responses=list(responses)
 def request(self,*_args,**_kwargs): pass
 def getresponse(self): return self.responses.pop(0)
 def close(self): pass


class SecretRuntimeTests(unittest.TestCase):
 def setUp(self):
  self.module=load_module()
  self.validator=self.module.load_validator(); self.runtime_names=set(self.validator.RUNTIME_SECRET_NAMES); self.privileged_names=set(self.validator.PRIVILEGED_SECRET_NAMES)
  self.production={
   "POSTGRES_DB":"leadflow","POSTGRES_BOOTSTRAP_USER":"bootstrap","POSTGRES_MIGRATOR_USER":"migrator","POSTGRES_APP_USER":"app",
   "RECOVERY_ADAPTER_URL":"http://adapters:8080","ADAPTER_ALLOWED_OPERATIONS":"crm.process",
   "CRM_UPSTREAM_URL":"https://crm.example.invalid","ENRICHMENT_UPSTREAM_URL":"https://enrichment.example.invalid",
   "PUBLIC_WEBHOOK_HOST":"leadflow.example.invalid","CRM_PROVIDER":"hubspot","ENRICHMENT_PROVIDER":"hunter",
  }

 def secret_map(self,path,drop=None,version="2",provider="gcp-secret-manager",operation="runtime-compose"):
  secrets={name:f"projects/example-project/secrets/{name.lower().replace('_','-')}/versions/{version}" for name in self.runtime_names if name!=drop}
  value={"version":"LF015-SECRET-MAP-2","provider":provider,"operation":operation,"expected_identity":"leadflow-runtime@example-project.iam.gserviceaccount.com","secrets":secrets}
  path.write_text(json.dumps(value),encoding="utf-8"); return path

 def factory(self):
  runtime_names=set(self.module.load_validator().RUNTIME_SECRET_NAMES)
  class Provider:
   def __init__(self,_identity,_timeout): pass
   def resolve(self,reference):
    name=next(name for name in runtime_names if f"/{name.lower().replace('_','-')}/" in reference)
    return "https://hooks.example.invalid/synthetic" if name=="SLACK_WEBHOOK_URL" else ("synthetic-"+name.lower()+"-"+"x"*40)[:48]
  return Provider

 def invoke(self,path,provider=None,runner=None,environment=None):
  output=io.StringIO(); error=io.StringIO()
  with mock.patch.dict(os.environ,environment or {},clear=True),redirect_stdout(output),redirect_stderr(error):
   code=self.module.main(["preflight","--map",str(path)],provider or self.factory(),runner or mock.Mock())
  return code,output.getvalue(),error.getvalue()

 def test_runtime_contract_has_explicit_versions_and_excludes_privileged_secrets(self):
  with tempfile.TemporaryDirectory() as temporary:
   path=self.secret_map(Path(temporary)/"map.json"); identity,references=self.module.load_map(path,self.runtime_names)
   self.assertTrue(identity.endswith(".iam.gserviceaccount.com")); self.assertEqual(set(references),self.runtime_names)
   self.assertFalse(set(references)&self.privileged_names); self.assertTrue(all(reference.endswith("/versions/2") for reference in references.values()))

 def test_runtime_preflight_uses_no_privileged_credentials_and_never_starts(self):
  with tempfile.TemporaryDirectory() as temporary:
   path=self.secret_map(Path(temporary)/"map.json"); captured={}
   def runner(command,**kwargs): captured.update(command=command,environment=kwargs["env"]); return mock.Mock(returncode=0)
   code,out,err=self.invoke(path,runner=runner,environment=self.production)
   self.assertEqual((code,out,err),(0,"secret_runtime phase=preflight status=PASS\n","")); self.assertEqual(captured["command"][-2:],["config","-q"])
   validator=self.module.load_validator(); self.assertEqual(self.module.runtime_dependency_blockers(validator),set())
   self.assertTrue(set(validator.RUNTIME_SECRET_NAMES)<=set(captured["environment"])); self.assertTrue(all(captured["environment"][name]=="-" for name in validator.PRIVILEGED_SECRET_NAMES))

 def test_missing_runtime_alias_wrong_provider_or_operation_fail_closed(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); runner=mock.Mock(); provider=mock.Mock()
   cases=(
    self.secret_map(root/"missing.json",drop=next(iter(self.runtime_names))),self.secret_map(root/"alias.json",version="latest"),
    self.secret_map(root/"provider.json",provider="environment"),self.secret_map(root/"operation.json",operation="postgres-admin"),
   )
   for path in cases:
    with self.subTest(path=path.name):
     code,out,err=self.invoke(path,provider,runner); self.assertEqual(code,1); self.assertEqual(out,""); self.assertNotIn("latest",err)
   provider.assert_not_called(); runner.assert_not_called()

 def test_authorized_resolution_returns_only_runtime_values(self):
  module=self.module; references={name:f"projects/example-project/secrets/{name.lower()}/versions/2" for name in self.runtime_names}
  calls=[]
  class Provider:
   def __init__(self,identity,timeout): calls.append((identity,timeout))
   def resolve(self,reference): calls.append(reference); return "synthetic-"+"x"*32
  values=module.resolve_authorized_secrets(references,"leadflow-runtime@example-project.iam.gserviceaccount.com",5,Provider)
  self.assertEqual(set(values),self.runtime_names); self.assertFalse(set(values)&self.privileged_names)

 def test_gcp_identity_and_secret_access_fail_closed_without_sensitive_output(self):
  module=self.module; identity=b"leadflow-runtime@example-project.iam.gserviceaccount.com"; token=b'{"access_token":"metadata-token"}'
  metadata=Connection([Response(200,identity),Response(200,token)]); secret=Connection([Response(200,json.dumps({"payload":{"data":base64.b64encode(b"synthetic-value").decode()}}).encode())])
  with mock.patch.dict(os.environ,{},clear=True),mock.patch.object(module.http.client,"HTTPConnection",return_value=metadata),mock.patch.object(module.http.client,"HTTPSConnection",return_value=secret):
   provider=module.GcpSecretManagerProvider(identity.decode(),5); self.assertEqual(provider.resolve("projects/example-project/secrets/test/versions/2"),"synthetic-value")
  mismatch=Connection([Response(200,b"other-runtime@example-project.iam.gserviceaccount.com")])
  with mock.patch.dict(os.environ,{},clear=True),mock.patch.object(module.http.client,"HTTPConnection",return_value=mismatch):
   with self.assertRaises(module.SecretRuntimeError): module.GcpSecretManagerProvider(identity.decode(),5)
  for status in (400,403,404):
   metadata=Connection([Response(200,identity),Response(200,token)]); denied=Connection([Response(status,b"sensitive-response")])
   with mock.patch.dict(os.environ,{},clear=True),mock.patch.object(module.http.client,"HTTPConnection",return_value=metadata),mock.patch.object(module.http.client,"HTTPSConnection",return_value=denied):
    provider=module.GcpSecretManagerProvider(identity.decode(),5)
    with self.assertRaises(module.SecretRuntimeError) as raised: provider.resolve("projects/example-project/secrets/test/versions/2")
    self.assertNotIn("sensitive",str(raised.exception))

 def test_development_validation_remains_unchanged(self):
  validator=self.module.load_validator(); self.assertEqual(validator.validate_config({"APP_ENV":"development"}),[])
  runtime={**self.production,"APP_ENV":"production",**{name:"synthetic-"+name.lower()+"-"+"x"*40 for name in validator.RUNTIME_SECRET_NAMES}}
  runtime["SLACK_WEBHOOK_URL"]="https://hooks.example.invalid/synthetic"
  self.assertEqual(validator.validate_config(runtime,context="runtime"),[])
  for name in validator.PRIVILEGED_SECRET_NAMES:
   self.assertIn("forbidden_"+name.lower(),validator.validate_config({**runtime,name:"x"*32},context="runtime"))
  production=(ROOT/"compose.production.yaml").read_text(encoding="utf-8"); compose=(ROOT/"compose.yaml").read_text(encoding="utf-8")
  for name in validator.PRIVILEGED_SECRET_NAMES: self.assertIn(f"{name}: !reset null",production)
  self.assertEqual(production.count("DSR_ADAPTER_SERVICE_KEY: !reset null"),2); self.assertIn("POSTGRES_PASSWORD: !reset null",production)
  self.assertIn("profiles: [administration]",compose); self.assertIn('restart: "no"',compose); self.assertIn("test $${#DSR_ADAPTER_SERVICE_KEY} -ge 32",compose)
  adapter=(ROOT/"adapters"/"server.py").read_text(encoding="utf-8"); self.assertIn("X-LeadFlow-DSR-Adapter-Key",adapter); self.assertIn("hmac.compare_digest(provided,configured)",adapter)
  sync=(ROOT/"scripts"/"database"/"sync_database_roles.sh").read_text(encoding="utf-8"); migrations=(ROOT/"scripts"/"database"/"apply_migrations.sh").read_text(encoding="utf-8")
  for name in validator.POSTGRES_ADMIN_SECRET_NAMES|{"POSTGRES_APP_PASSWORD"}: self.assertIn("-e "+name,sync); self.assertIn("-e "+name,migrations)


if __name__=="__main__": unittest.main(verbosity=2)
