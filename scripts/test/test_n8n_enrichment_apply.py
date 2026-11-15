"""Focused structural contract for terminal CRM enrichment application."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class EnrichmentApplyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = json.loads((ROOT / "workflows" / "leadflow_core_initial.json").read_text(encoding="utf-8"))
        cls.nodes = {node["name"]: node for node in workflow["nodes"]}
        cls.connections = workflow["connections"]

    def test_created_and_updated_apply_are_terminalized(self):
        for suffix in ("Created", "Updated"):
            apply_node = self.nodes[f"Apply Enrichment {suffix}"]
            code = apply_node["parameters"]["jsCode"]
            self.assertEqual(apply_node["type"], "n8n-nodes-base.code")
            self.assertIn("ignoreHttpStatusErrors:true", code)
            self.assertIn("returnFullResponse:true", code)
            self.assertIn("if(!Object.keys(fields).length)", code)
            self.assertIn("error_code:timeout?'timeout':'adapter_unavailable'", code)
            decision = f"{suffix} Enrichment Applied"
            self.assertEqual(self.connections[f"Apply Enrichment {suffix}"]["main"][0][0]["node"], decision)
            branches = self.connections[decision]["main"]
            self.assertEqual(branches[0][0]["node"], f"Persist {suffix} Success")
            self.assertEqual(branches[1][0]["node"], f"Persist {suffix} Enrichment Failure")

    def test_persistence_uses_apply_result_without_new_external_effects(self):
        for suffix in ("Created", "Updated"):
            replacement = self.nodes[f"Persist {suffix} Success"]["parameters"]["options"]["queryReplacement"]
            self.assertIn("$json.retry_count", replacement)
            self.assertNotIn(f"$('Enrich {suffix} Contact').item.json.retry_count", replacement)
        workflow_text = (ROOT / "workflows" / "leadflow_core_initial.json").read_text(encoding="utf-8")
        self.assertEqual(workflow_text.count("/crm/update-enrichment/"), 2)


if __name__ == "__main__":
    unittest.main()
