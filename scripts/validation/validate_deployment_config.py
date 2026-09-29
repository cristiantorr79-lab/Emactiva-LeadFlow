"""Fail-closed development/production configuration validation for LF-002.4."""
import os, sys
from urllib.parse import urlparse

PRODUCTION_REQUIRED=(
 "POSTGRES_DB","POSTGRES_MIGRATOR_USER","POSTGRES_MIGRATOR_PASSWORD",
 "POSTGRES_APP_USER","POSTGRES_APP_PASSWORD","LEADFLOW_WEBHOOK_KEY",
 "N8N_ENCRYPTION_KEY","RECOVERY_CONTEXT_KEY","RECOVERY_ADAPTER_URL",
 "ADAPTER_SERVICE_KEY","ADAPTER_ALLOWED_OPERATIONS","DSR_SUBJECT_KEY",
 "CRM_UPSTREAM_URL","ENRICHMENT_UPSTREAM_URL","SLACK_WEBHOOK_URL","PUBLIC_WEBHOOK_HOST",
 "CRM_PROVIDER","ENRICHMENT_PROVIDER",
)
SECRET_NAMES={"POSTGRES_MIGRATOR_PASSWORD","POSTGRES_APP_PASSWORD","LEADFLOW_WEBHOOK_KEY","N8N_ENCRYPTION_KEY","RECOVERY_CONTEXT_KEY","ADAPTER_SERVICE_KEY","DSR_SUBJECT_KEY","SLACK_WEBHOOK_URL","CRM_API_KEY","ENRICHMENT_API_KEY"}
UNSAFE_HOSTS={"localhost","127.0.0.1","crm-mock","enrichment-mock","slack-mock"}

def validate_config(env):
 errors=[]; app_env=str(env.get("APP_ENV","")).strip().lower()
 if app_env not in {"development","production"}: return ["invalid_app_env"]
 if app_env=="development": return errors
 for name in PRODUCTION_REQUIRED:
  if not str(env.get(name,"")).strip(): errors.append("missing_"+name.lower())
 for name in ("POSTGRES_MIGRATOR_PASSWORD","POSTGRES_APP_PASSWORD","LEADFLOW_WEBHOOK_KEY","N8N_ENCRYPTION_KEY","RECOVERY_CONTEXT_KEY","ADAPTER_SERVICE_KEY","DSR_SUBJECT_KEY"):
  value=str(env.get(name,""))
  if value and len(value)<32: errors.append("weak_"+name.lower())
 if env.get("POSTGRES_MIGRATOR_USER")==env.get("POSTGRES_APP_USER"): errors.append("shared_postgres_role")
 if env.get("POSTGRES_MIGRATOR_PASSWORD")==env.get("POSTGRES_APP_PASSWORD"): errors.append("shared_postgres_password")
 if env.get("CRM_PROVIDER")!="hubspot": errors.append("invalid_crm_provider")
 elif not str(env.get("CRM_API_KEY","")).strip(): errors.append("missing_crm_api_key")
 if env.get("ENRICHMENT_PROVIDER")!="hunter": errors.append("invalid_enrichment_provider")
 elif not str(env.get("ENRICHMENT_API_KEY","")).strip(): errors.append("missing_enrichment_api_key")
 for name in ("CRM_UPSTREAM_URL","ENRICHMENT_UPSTREAM_URL","SLACK_WEBHOOK_URL"):
  value=str(env.get(name,"")); parsed=urlparse(value)
  if value and (parsed.scheme!="https" or not parsed.hostname or parsed.hostname.lower() in UNSAFE_HOSTS): errors.append("unsafe_"+name.lower())
 recovery=str(env.get("RECOVERY_ADAPTER_URL","")); parsed=urlparse(recovery)
 if recovery and (parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.hostname.lower() in UNSAFE_HOSTS): errors.append("unsafe_recovery_adapter_url")
 host=str(env.get("PUBLIC_WEBHOOK_HOST","")).strip().lower()
 if host and ("://" in host or host in UNSAFE_HOSTS or "/" in host): errors.append("unsafe_public_webhook_host")
 return sorted(set(errors))

def main():
 errors=validate_config(os.environ)
 if errors:
  print("Deployment configuration: FAIL ("+",".join(errors)+")")
  return 1
 print("Deployment configuration: PASS")
 return 0

if __name__=="__main__": sys.exit(main())
