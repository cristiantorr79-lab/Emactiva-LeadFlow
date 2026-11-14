#!/usr/bin/env python3
"""Resolve the production Gateway abuse token in memory and run isolated Compose."""
from __future__ import annotations

import argparse, importlib.util, ipaddress, json, os, re, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
COMPOSE_FILE=ROOT/"compose.web-gateway.production.yaml"
MAP_VERSION="LF015-WEB-GATEWAY-SECRET-MAP-1"
PROVIDER_NAME="gcp-secret-manager"
OPERATION_NAME="web-gateway-compose"
SECRET_NAME="WEB_BRIDGE_ABUSE_TOKEN"
AUTHORIZED_SECRET_ID="leadflow-web-bridge-abuse-token"
PROJECT_RE=re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
NETWORK_RE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
REQUIRED_NONSECRETS={"WEB_GATEWAY_BIND_ADDRESS","WEB_GATEWAY_PUBLIC_IP","WEB_GATEWAY_PUBLIC_PATH","WEB_GATEWAY_ALLOWED_ORIGINS","WEB_GATEWAY_UPSTREAM_URL","WEB_GATEWAY_MAX_BODY_BYTES","WEB_GATEWAY_REQUEST_TIMEOUT_SECONDS","WEB_GATEWAY_UPSTREAM_TIMEOUT_SECONDS","WEB_GATEWAY_RATE_REQUESTS","WEB_GATEWAY_RATE_WINDOW_SECONDS","WEB_GATEWAY_RATE_MAX_KEYS","WEB_BRIDGE_UPSTREAM_NETWORK"}
OPERATION_ENV={"PATH","HOME","USERPROFILE","SYSTEMROOT","WINDIR","DOCKER_HOST","DOCKER_CONTEXT","DOCKER_CONFIG","XDG_CONFIG_HOME","TMPDIR","TEMP","TMP"}

class WebGatewaySecretError(RuntimeError): pass

def secure_runtime():
 path=ROOT/"scripts"/"admin"/"compose_with_secrets.py"
 spec=importlib.util.spec_from_file_location("leadflow_gateway_secret_runtime",path)
 if spec is None or spec.loader is None: raise WebGatewaySecretError("secure provider unavailable")
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def load_map(path, runtime):
 try: value=json.loads(path.read_text(encoding="utf-8"))
 except Exception as error: raise WebGatewaySecretError("invalid secret map") from error
 if not isinstance(value,dict) or set(value)!={"version","provider","operation","expected_identity","secrets"}: raise WebGatewaySecretError("invalid secret map")
 if value["version"]!=MAP_VERSION or value["provider"]!=PROVIDER_NAME or value["operation"]!=OPERATION_NAME: raise WebGatewaySecretError("invalid secret map")
 identity=value["expected_identity"]; references=value["secrets"]
 if not isinstance(identity,str) or not runtime.SERVICE_ACCOUNT.fullmatch(identity) or not isinstance(references,dict) or set(references)!={SECRET_NAME}: raise WebGatewaySecretError("invalid secret map")
 reference=references[SECRET_NAME]; project=identity.split("@",1)[1].removesuffix(".iam.gserviceaccount.com")
 if not isinstance(reference,str) or not runtime.SECRET_REFERENCE.fullmatch(reference) or reference.split("/")[1]!=project or reference.split("/")[3]!=AUTHORIZED_SECRET_ID: raise WebGatewaySecretError("invalid secret map")
 return identity,references

def resolve_environment(map_path, provider_factory=None):
 runtime=secure_runtime(); identity,references=load_map(map_path,runtime)
 try: timeout=int(os.environ.get("WEB_GATEWAY_SECRET_FETCH_TIMEOUT_SECONDS","5"))
 except ValueError as error: raise WebGatewaySecretError("invalid timeout") from error
 if not 1<=timeout<=30: raise WebGatewaySecretError("invalid timeout")
 projects=[os.environ.get(name,"").strip() for name in ("WEB_GATEWAY_COMPOSE_PROJECT","WEB_BRIDGE_COMPOSE_PROJECT","LEADFLOW_COMPOSE_PROJECT")]
 if any(not PROJECT_RE.fullmatch(item) for item in projects) or len(set(projects))!=3: raise WebGatewaySecretError("compose project separation required")
 if any(not os.environ.get(name,"").strip() for name in REQUIRED_NONSECRETS): raise WebGatewaySecretError("nonsecret configuration incomplete")
 if os.environ["WEB_GATEWAY_PUBLIC_PATH"]!="/lead" or os.environ["WEB_GATEWAY_ALLOWED_ORIGINS"]!="https://emactivaspa.lovable.app" or os.environ["WEB_GATEWAY_UPSTREAM_URL"]!="http://web-bridge:8080/lead": raise WebGatewaySecretError("public contract invalid")
 try:
  public_ip=ipaddress.ip_address(os.environ["WEB_GATEWAY_PUBLIC_IP"]); bind_ip=ipaddress.ip_address(os.environ["WEB_GATEWAY_BIND_ADDRESS"])
 except ValueError as error: raise WebGatewaySecretError("public address invalid") from error
 if not public_ip.is_global or bind_ip not in (public_ip,ipaddress.ip_address("0.0.0.0"),ipaddress.ip_address("::")): raise WebGatewaySecretError("public address invalid")
 if not NETWORK_RE.fullmatch(os.environ["WEB_BRIDGE_UPSTREAM_NETWORK"]): raise WebGatewaySecretError("external network invalid")
 try: secrets=runtime.resolve_authorized_secrets(references,identity,timeout,provider_factory or runtime.GcpSecretManagerProvider)
 except Exception as error: raise WebGatewaySecretError("secret resolution failed") from error
 token=secrets.get(SECRET_NAME)
 if not isinstance(token,str) or len(token)<32 or "\x00" in token: raise WebGatewaySecretError("secret resolution failed")
 environment={name:value for name,value in os.environ.items() if name in OPERATION_ENV or name in REQUIRED_NONSECRETS}
 environment[SECRET_NAME]=token; environment["COMPOSE_DISABLE_ENV_FILE"]="1"
 return environment,projects[0]

def run_compose(action,environment,project,runner=subprocess.run):
 if action not in {"preflight","start"}: raise WebGatewaySecretError("compose action invalid")
 base=["docker","compose","--project-name",project,"-f",str(COMPOSE_FILE),"--profile","web-gateway-production"]
 commands=[base+["config","-q"]]
 if action=="preflight": commands.append(base+["run","--rm","--no-deps","--pull","never","--entrypoint","caddy","caddy","validate","--config","/etc/caddy/Caddyfile","--adapter","caddyfile"])
 else: commands.append(base+["up","-d","--no-build"])
 for command in commands:
  try: result=runner(command,cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60 if action=="preflight" else 180,check=False)
  except (OSError,subprocess.SubprocessError) as error: raise WebGatewaySecretError("compose failed") from error
  if result.returncode: raise WebGatewaySecretError("compose failed")

def main(argv=None,provider_factory=None,runner=subprocess.run):
 parser=argparse.ArgumentParser(); parser.add_argument("action",choices=("preflight","start")); parser.add_argument("--map",type=Path); args=parser.parse_args(argv)
 try:
  path=args.map or (Path(os.environ["WEB_GATEWAY_SECRET_MAP_FILE"]) if os.environ.get("WEB_GATEWAY_SECRET_MAP_FILE") else None)
  if path is None: raise WebGatewaySecretError("secret map required")
  environment,project=resolve_environment(path,provider_factory); run_compose("preflight",environment,project,runner)
  if args.action=="start": run_compose("start",environment,project,runner)
  print(f"web_gateway_secret_runtime phase={args.action} status=PASS"); return 0
 except Exception:
  print(f"web_gateway_secret_runtime phase={args.action} status=FAIL",file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
