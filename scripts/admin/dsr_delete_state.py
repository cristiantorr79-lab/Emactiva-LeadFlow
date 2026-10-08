"""Pure fail-closed state decision for an approved HubSpot DSR DELETE."""
RECONCILABLE_FAILURES={"contact_deletion_ambiguous"}

def conclusive_absence(result):
 return isinstance(result,dict) and result.get("success") is True and result.get("found") is False and result.get("contact_count")==0 and result.get("interaction_count")==0

def resolve_delete_state(status,result_code,approved,locate):
 if not approved: return "invalid",None
 if status=="completed": return "completed",None
 if status=="pending": return "delete",None
 if status=="failed" and result_code in RECONCILABLE_FAILURES:
  located=locate()
  return ("reconciled_absent",None) if conclusive_absence(located) else ("reconciliation_blocked",None)
 return "invalid",None

def coordinate_delete_state(status,result_code,approved,locate,complete):
 decision,_=resolve_delete_state(status,result_code,approved,locate)
 if decision=="reconciled_absent": return decision,complete()
 return decision,None
