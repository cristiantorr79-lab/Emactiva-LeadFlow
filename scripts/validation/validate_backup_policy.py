"""Validate the portable backup/restore contract without touching infrastructure."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
def validate(policy):
 errors=[]
 if policy.get("version")!=2: errors.append("version")
 if policy.get("frequency_hours")!=24: errors.append("frequency")
 if policy.get("retention_days")!=30: errors.append("retention")
 if not isinstance(policy.get("rpo_hours"),int) or policy["rpo_hours"]>24: errors.append("rpo")
 if not isinstance(policy.get("rto_hours"),int) or policy["rto_hours"]>8: errors.append("rto")
 if policy.get("encryption_required") is not True or policy.get("custody")!="environment_defined": errors.append("custody")
 if policy.get("restore_requires_dsr_replay") is not True: errors.append("dsr_replay")
 fmt=policy.get("format",{})
 if fmt!={"postgresql":"pg_dump_custom","n8n":"paused_volume_snapshot","encryption":"AES-256-GCM","key_source":"external_secret_file"}: errors.append("format")
 storage=policy.get("storage",{})
 if storage!={"provider":"gcs","bucket_source":"environment","credentials":"vm_service_account_temporary","overwrite":False,"lifecycle_owner":"bucket_policy"}: errors.append("storage")
 if policy.get("identity_separation_required") is not True: errors.append("identity_separation")
 if policy.get("independent_dsr_evidence_required") is not True or policy.get("dsr_evidence_encryption")!="AES-256-GCM" or policy.get("dsr_evidence_publication")!="immutable_content_addressed": errors.append("dsr_evidence")
 if policy.get("dsr_evidence_authority_manifest_required") is not True: errors.append("dsr_authority_manifest")
 if policy.get("soft_delete_additional_days")!=7: errors.append("soft_delete")
 controls=policy.get("environment_controls")
 if not isinstance(controls,dict) or not controls or any(value not in {"NOT_VERIFIED","HYBRID"} for value in controls.values()): errors.append("environment_controls")
 return errors
def main():
 policy=json.loads((ROOT/"config"/"backup-policy.json").read_text(encoding="utf-8")); errors=validate(policy)
 print("BACKUP_POLICY="+("PASS" if not errors else "FAIL")); return 1 if errors else 0
if __name__=="__main__": sys.exit(main())
