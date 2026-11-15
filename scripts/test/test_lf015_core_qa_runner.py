import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
class CoreQaRunnerTests(unittest.TestCase):
 def test_isolated_mock_only_contract(self):
  compose=(ROOT/'compose.core-qa.yaml').read_text(encoding='utf-8'); runner=(ROOT/'scripts/test/run_lf015_core_qa.py').read_text(encoding='utf-8')
  self.assertIn('internal: true',compose); self.assertIn('CRM_PROVIDER: mock',compose); self.assertIn('ENRICHMENT_PROVIDER: mock',compose)
  self.assertNotIn('compose.production.yaml',runner); self.assertIn('qa_resources_preexist',runner); self.assertIn('main_before==main_after',runner)
  self.assertIn('ssl.create_default_context(cafile=',runner); self.assertIn('"--no-build"',runner)
  self.assertIn('if owned:',runner); self.assertIn('qa_resources_preexist',runner)
  self.assertIn('database","apply_migrations',runner); self.assertIn('safe_diagnostic',runner)
  self.assertNotIn('"ADAPTER_ALLOWED_OPERATIONS":"*"',runner)
  self.assertIn('crm.record_interaction,crm.reconcile_interaction,enrichment.enrich,alert.send',runner)
  self.assertIn("time.monotonic()+20",runner)
  self.assertIn("e.status='success' AND e.enrichment_status='success'",runner)
  self.assertIn("e.status IN ('processing','retrying')",runner)
  self.assertIn("count(c.execution_id) FILTER (WHERE e.status='success')",runner)
  self.assertIn('state_sql,synthetic["POSTGRES_BOOTSTRAP_USER"]',runner)
  self.assertIn('terminal_state_mismatch',runner)
  self.assertIn('configure_crm_apply_failure',runner)
  self.assertIn('update_enrichment',runner)
  self.assertIn('failed_apply_1',runner)
  self.assertIn('statuses[3] not in (202,502)',runner)
 def test_n8n_credential_location_is_externalized(self):
  provision=(ROOT/'scripts/n8n/provision_n8n.ps1').read_text(encoding='utf-8'); compose=(ROOT/'compose.core-qa.yaml').read_text(encoding='utf-8')
  self.assertIn('LEADFLOW_N8N_LOCAL_DIR',provision); self.assertIn('${LEADFLOW_N8N_LOCAL_DIR:',compose)
  self.assertIn('Remove-LeadFlowCredentialFile',provision)
  self.assertIn("LEADFLOW_N8N_PROBE_MODE -eq 'container'",provision)
  self.assertIn('ports: !reset []',compose)

if __name__=='__main__': unittest.main()
