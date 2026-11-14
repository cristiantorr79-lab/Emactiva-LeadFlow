#!/usr/bin/env python3
"""Resolve production secrets in memory before validating or starting Compose."""
from __future__ import annotations

import argparse
import base64
import http.client
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[2]
COMPOSE_FILES=(ROOT/"compose.yaml",ROOT/"compose.production.yaml")
METADATA_HOST="metadata.google.internal"
METADATA_EMAIL_PATH="/computeMetadata/v1/instance/service-accounts/default/email"
METADATA_TOKEN_PATH="/computeMetadata/v1/instance/service-accounts/default/token"
SECRET_MANAGER_HOST="secretmanager.googleapis.com"
MAP_VERSION="LF015-SECRET-MAP-2"
PROVIDER_NAME="gcp-secret-manager"
OPERATION_NAME="runtime-compose"
SERVICE_ACCOUNT=re.compile(r"^[a-z0-9][a-z0-9-]{4,28}[a-z0-9]@[a-z0-9][a-z0-9-]{4,61}[a-z0-9]\.iam\.gserviceaccount\.com$")
SECRET_REFERENCE=re.compile(r"^projects/[a-z0-9][a-z0-9-]{4,61}[a-z0-9]/secrets/[A-Za-z0-9_-]{1,255}/versions/[1-9][0-9]*$")
COMPOSE_VARIABLE=re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")
OPERATION_ENV={"PATH","HOME","USERPROFILE","SYSTEMROOT","WINDIR","DOCKER_HOST","DOCKER_CONTEXT","DOCKER_CONFIG","XDG_CONFIG_HOME","TMPDIR","TEMP","TMP"}


class SecretRuntimeError(RuntimeError):
 pass


def load_validator():
 path=ROOT/"scripts"/"validation"/"validate_deployment_config.py"
 spec=importlib.util.spec_from_file_location("leadflow_deployment_config",path)
 if spec is None or spec.loader is None: raise SecretRuntimeError("validation unavailable")
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
 return module


def load_map(path:Path,required_names:set[str]):
 try: value=json.loads(path.read_text(encoding="utf-8"))
 except Exception as error: raise SecretRuntimeError("invalid secret map") from error
 if not isinstance(value,dict) or value.get("version")!=MAP_VERSION or value.get("provider")!=PROVIDER_NAME or value.get("operation")!=OPERATION_NAME: raise SecretRuntimeError("invalid secret map")
 identity=value.get("expected_identity"); secrets=value.get("secrets")
 if not isinstance(identity,str) or not SERVICE_ACCOUNT.fullmatch(identity) or not isinstance(secrets,dict) or set(secrets)!=required_names: raise SecretRuntimeError("invalid secret map")
 if any(not isinstance(reference,str) or not SECRET_REFERENCE.fullmatch(reference) for reference in secrets.values()): raise SecretRuntimeError("invalid secret map")
 if len(set(secrets.values()))!=len(secrets): raise SecretRuntimeError("invalid secret map")
 return identity,secrets


def metadata_get(path:str,timeout:int):
 connection=http.client.HTTPConnection(METADATA_HOST,timeout=timeout)
 try:
  try:
   connection.request("GET",path,headers={"Metadata-Flavor":"Google"})
   response=connection.getresponse(); payload=response.read(16385)
  except (OSError,TimeoutError,http.client.HTTPException) as error: raise SecretRuntimeError("managed identity unavailable") from error
 finally: connection.close()
 if response.status!=200 or len(payload)>16384: raise SecretRuntimeError("managed identity unavailable")
 return payload


class GcpSecretManagerProvider:
 def __init__(self,expected_identity:str,timeout:int):
  if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE") or os.environ.get("GCE_METADATA_HOST") or os.environ.get("GCE_METADATA_IP"): raise SecretRuntimeError("ambiguous credentials")
  identity=metadata_get(METADATA_EMAIL_PATH,timeout)
  try: actual=identity.decode("ascii").strip()
  except Exception as error: raise SecretRuntimeError("managed identity unavailable") from error
  if actual!=expected_identity: raise SecretRuntimeError("managed identity mismatch")
  token_payload=metadata_get(METADATA_TOKEN_PATH,timeout)
  try: token=json.loads(token_payload)["access_token"]
  except Exception as error: raise SecretRuntimeError("managed identity unavailable") from error
  if not isinstance(token,str) or not token or len(token)>8192: raise SecretRuntimeError("managed identity unavailable")
  self._token=token; self._timeout=timeout

 def resolve(self,reference:str):
  path=f"/v1/{quote(reference,safe='/')}:access"
  connection=http.client.HTTPSConnection(SECRET_MANAGER_HOST,timeout=self._timeout)
  try:
   try:
    connection.request("GET",path,headers={"Authorization":f"Bearer {self._token}"})
    response=connection.getresponse(); payload=response.read(131073)
   except (OSError,TimeoutError,http.client.HTTPException) as error: raise SecretRuntimeError("secret access failed") from error
  finally: connection.close()
  if response.status!=200 or len(payload)>131072: raise SecretRuntimeError("secret access failed")
  try:
   encoded=json.loads(payload)["payload"]["data"]
   raw=base64.b64decode(encoded,validate=True); value=raw.decode("utf-8")
  except Exception as error: raise SecretRuntimeError("secret payload invalid") from error
  if not value or "\x00" in value: raise SecretRuntimeError("secret payload invalid")
  return value


def compose_variable_names():
 names=set()
 for path in COMPOSE_FILES:
  try: names.update(COMPOSE_VARIABLE.findall(path.read_text(encoding="utf-8")))
  except OSError as error: raise SecretRuntimeError("compose configuration unavailable") from error
 return names


def runtime_dependency_blockers(validator):
 production=(COMPOSE_FILES[1]).read_text(encoding="utf-8")
 compose_blockers={name for name in validator.PRIVILEGED_SECRET_NAMES if f"{name}: !reset null" not in production}
 runtime_errors=set(validator.validate_config({"APP_ENV":"production"},context="runtime"))
 validation_blockers={name for name in validator.PRIVILEGED_SECRET_NAMES if "missing_"+name.lower() in runtime_errors}
 return compose_blockers|validation_blockers


def resolve_authorized_secrets(references,expected_identity,timeout,provider_factory=GcpSecretManagerProvider):
 provider=provider_factory(expected_identity,timeout)
 return {name:provider.resolve(reference) for name,reference in sorted(references.items())}


def resolved_environment(map_path:Path,provider_factory=GcpSecretManagerProvider):
 validator=load_validator(); all_secret_names=set(validator.SECRET_NAMES); runtime_names=set(validator.RUNTIME_SECRET_NAMES); privileged_names=set(validator.PRIVILEGED_SECRET_NAMES)
 if runtime_names|privileged_names!=all_secret_names or runtime_names&privileged_names: raise SecretRuntimeError("secret classification incomplete")
 expected_identity,references=load_map(map_path,runtime_names)
 if runtime_dependency_blockers(validator): raise SecretRuntimeError("privileged startup dependency")
 try: timeout=int(os.environ.get("SECRET_FETCH_TIMEOUT_SECONDS","5"))
 except ValueError as error: raise SecretRuntimeError("invalid timeout") from error
 if not 1<=timeout<=30: raise SecretRuntimeError("invalid timeout")
 secrets=resolve_authorized_secrets(references,expected_identity,timeout,provider_factory)
 validation_names=set(validator.PRODUCTION_REQUIRED)|all_secret_names|{"APP_ENV"}
 validation_env={name:os.environ[name] for name in validation_names if name in os.environ and name not in all_secret_names}
 validation_env.update(secrets); validation_env["APP_ENV"]="production"
 if validator.validate_config(validation_env,context="runtime"): raise SecretRuntimeError("deployment configuration invalid")
 compose_names=compose_variable_names()
 compose_env={name:value for name,value in os.environ.items() if name in OPERATION_ENV or name in compose_names and name not in all_secret_names}
 compose_env.update(secrets); compose_env["APP_ENV"]="production"; compose_env["COMPOSE_DISABLE_ENV_FILE"]="1"
 for name in privileged_names: compose_env[name]="-"
 return compose_env


def run_compose(action:str,environment:dict[str,str],runner=subprocess.run):
 command=["docker","compose","-f",str(COMPOSE_FILES[0]),"-f",str(COMPOSE_FILES[1])]
 command += ["config","-q"] if action=="preflight" else ["up","-d"]
 timeout=60 if action=="preflight" else 300
 try: result=runner(command,cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
 except (OSError,subprocess.SubprocessError) as error: raise SecretRuntimeError("compose failed") from error
 if result.returncode!=0: raise SecretRuntimeError("compose failed")


def main(argv=None,provider_factory=GcpSecretManagerProvider,runner=subprocess.run):
 parser=argparse.ArgumentParser(); parser.add_argument("action",choices=("preflight","start")); parser.add_argument("--map",type=Path); args=parser.parse_args(argv)
 try:
  map_path=args.map or (Path(os.environ["LEADFLOW_SECRET_MAP_FILE"]) if os.environ.get("LEADFLOW_SECRET_MAP_FILE") else None)
  if map_path is None: raise SecretRuntimeError("secret map required")
  environment=resolved_environment(map_path,provider_factory); run_compose("preflight",environment,runner)
  if args.action=="start": run_compose("start",environment,runner)
  print(f"secret_runtime phase={args.action} status=PASS"); return 0
 except Exception:
  print(f"secret_runtime phase={args.action} status=FAIL",file=sys.stderr); return 1


if __name__=="__main__": raise SystemExit(main())
