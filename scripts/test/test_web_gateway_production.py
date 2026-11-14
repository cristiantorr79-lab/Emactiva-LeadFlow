"""Focused SYSTEM validation for the production HTTPS Gateway."""
from __future__ import annotations

import importlib.util, json, os, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

def load_runtime():
 path=ROOT/"scripts/admin/web_gateway_with_secrets.py"; spec=importlib.util.spec_from_file_location("gateway_runtime_test",path)
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

class Provider:
 def __init__(self,identity,timeout): self.identity=identity
 def resolve(self,reference): return "synthetic-abuse-token-"+"x"*32

class GatewayProductionTests(unittest.TestCase):
 def setUp(self):
  self.runtime=load_runtime(); self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
  self.map=Path(self.temp.name)/"map.json"; self.map.write_text(json.dumps({
   "version":"LF015-WEB-GATEWAY-SECRET-MAP-1","provider":"gcp-secret-manager","operation":"web-gateway-compose",
   "expected_identity":"leadflow-runtime@project-example.iam.gserviceaccount.com",
   "secrets":{"WEB_BRIDGE_ABUSE_TOKEN":"projects/project-example/secrets/leadflow-web-bridge-abuse-token/versions/1"}}),encoding="utf-8")
  self.env={
   "WEB_GATEWAY_COMPOSE_PROJECT":"leadflow-gateway","WEB_BRIDGE_COMPOSE_PROJECT":"leadflow-bridge","LEADFLOW_COMPOSE_PROJECT":"emactiva-leadflow",
   "WEB_GATEWAY_BIND_ADDRESS":"0.0.0.0","WEB_GATEWAY_PUBLIC_IP":"1.1.1.1","WEB_GATEWAY_PUBLIC_PATH":"/lead","WEB_GATEWAY_ALLOWED_ORIGINS":"https://emactivaspa.lovable.app",
   "WEB_GATEWAY_UPSTREAM_URL":"http://web-bridge:8080/lead","WEB_GATEWAY_MAX_BODY_BYTES":"16384","WEB_GATEWAY_REQUEST_TIMEOUT_SECONDS":"5","WEB_GATEWAY_UPSTREAM_TIMEOUT_SECONDS":"10",
   "WEB_GATEWAY_RATE_REQUESTS":"5","WEB_GATEWAY_RATE_WINDOW_SECONDS":"60","WEB_GATEWAY_RATE_MAX_KEYS":"10000","WEB_BRIDGE_UPSTREAM_NETWORK":"leadflow_bridge_internal",
  }

 def test_compose_and_caddy_contract(self):
  compose=(ROOT/"compose.web-gateway.production.yaml").read_text(encoding="utf-8"); caddy=(ROOT/"gateway/Caddyfile.production").read_text(encoding="utf-8")
  self.assertIn("caddy:2.11.3-alpine",compose); self.assertEqual(compose.count("ports:"),1); self.assertIn(":443:443/tcp",compose); self.assertNotIn(":80",compose)
  self.assertIn("internal: true",compose); self.assertIn("external: true",compose); self.assertNotIn("tls internal",caddy); self.assertNotIn("zerossl",caddy.lower())
  for value in ("auto_https disable_redirects","default_sni {$WEB_GATEWAY_PUBLIC_IP}","disable_http_challenge","profile shortlived","https://acme-v02.api.letsencrypt.org/directory","handle /lead","method POST OPTIONS","header_up -X-LeadFlow-Abuse-Token"):
   self.assertIn(value,caddy)

 def test_secret_contract_and_preflight_never_start(self):
  calls=[]
  def runner(command,**kwargs): calls.append((command,kwargs)); return subprocess.CompletedProcess(command,0,b"",b"")
  with patch.dict(os.environ,self.env,clear=True):
   resolved,project=self.runtime.resolve_environment(self.map,Provider)
   self.runtime.run_compose("preflight",resolved,project,runner)
  self.assertEqual(set(resolved)-set(self.env),{"WEB_BRIDGE_ABUSE_TOKEN","COMPOSE_DISABLE_ENV_FILE"})
  self.assertEqual(len(calls),2); self.assertIn("config",calls[0][0]); self.assertIn("validate",calls[1][0]); self.assertIn("--pull",calls[1][0]); self.assertIn("never",calls[1][0])
  self.assertTrue(all("up" not in call[0] and "start" not in call[0] for call in calls))
  self.assertTrue(all("leadflow-gateway" in call[0] and "compose.web-gateway.production.yaml" in " ".join(call[0]) and "compose.yaml" not in call[0] for call in calls))
  self.assertNotIn("synthetic-abuse-token",str(calls[0][0]))

 def test_invalid_map_projects_origin_and_private_ip_fail_closed(self):
  for key,value in (("WEB_GATEWAY_COMPOSE_PROJECT","emactiva-leadflow"),("WEB_GATEWAY_ALLOWED_ORIGINS","https://evil.invalid"),("WEB_GATEWAY_PUBLIC_IP","10.0.0.2")):
   with self.subTest(key=key),patch.dict(os.environ,{**self.env,key:value},clear=True),self.assertRaises(self.runtime.WebGatewaySecretError):
    self.runtime.resolve_environment(self.map,Provider)

if __name__=="__main__": unittest.main()
