"""Focused synthetic tests for the authorized Linux n8n provisioner."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SECRET = "synthetic-postgres-password-never-print"


def load_module():
    path = ROOT / "scripts" / "n8n" / "provision_n8n.py"
    spec = importlib.util.spec_from_file_location("n8n_linux_provision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Runtime:
    GcpSecretManagerProvider = object

    @staticmethod
    def resolved_environment(_path, _provider):
        return {
            "PATH": os.environ.get("PATH", ""), "POSTGRES_DB": "leadflow_synthetic",
            "POSTGRES_APP_USER": "leadflow_app", "POSTGRES_APP_PASSWORD": SECRET,
            "COMPOSE_DISABLE_ENV_FILE": "1",
        }


class FakeRunner:
    def __init__(self, *, workflow=None, credential="absent", active=False, fail_operation=None, mutate_on_failure=False):
        self.desired = json.loads((ROOT / "workflows" / "leadflow_core_initial.json").read_text(encoding="utf-8"))
        self.workflow = workflow
        self.credential = credential
        self.active = active
        self.fail_operation = fail_operation
        self.mutate_on_failure = mutate_on_failure
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        joined = " ".join(command)
        if self.fail_operation and self.fail_operation in joined:
            if self.mutate_on_failure:
                if "import:credentials" in joined: self.credential = "equivalent"
                elif "import:workflow" in joined: self.workflow = self.desired.copy(); self.active = False
                elif "publish:workflow" in joined: self.active = True
            return subprocess.CompletedProcess(command, 9, b"", (SECRET + " upstream").encode())
        output = b""
        if " ps " in f" {joined} ":
            output = b"n8n\n"
        elif "list:workflow" in command:
            output = b"leadflow-core-initial|LeadFlow Core Initial\n" if self.workflow is not None else b""
        elif "export:workflow" in joined:
            if self.workflow == "ambiguous":
                output = json.dumps([self.desired, self.desired]).encode()
            else:
                value = dict(self.workflow); value["active"] = self.active
                output = json.dumps([value]).encode()
        elif "export:credentials" in joined:
            output = (self.credential + "\n").encode()
        elif "import:credentials" in joined:
            self.credential = "equivalent"
        elif "import:workflow" in command:
            self.workflow = self.desired.copy(); self.active = False
        elif "publish:workflow" in command:
            self.active = True
        return subprocess.CompletedProcess(command, 0, output, b"")


class N8nLinuxProvisionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.map = Path(self.temporary.name) / "map.json"
        self.map.write_text("{}", encoding="utf-8")
        self.runtime = mock.patch.object(self.module, "load_secret_runtime", return_value=Runtime())
        self.runtime.start(); self.addCleanup(self.runtime.stop)
        self.environment = mock.patch.dict(os.environ, {"LEADFLOW_COMPOSE_PROJECT": "leadflow-production"}, clear=True)
        self.environment.start(); self.addCleanup(self.environment.stop)

    def invoke(self, arguments, runner):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.module.main(arguments + ["--map", str(self.map)], object, runner)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_new_install_imports_both_and_remains_inactive_without_publish(self):
        runner = FakeRunner()
        code, out, err = self.invoke(["preflight"], runner)
        self.assertEqual((code, out, err), (0, "n8n_linux_provision phase=preflight status=PASS\n", ""))
        rendered = [" ".join(call[0]) for call in runner.calls]
        self.assertTrue(any("config -q" in item for item in rendered))
        self.assertFalse(any("import:" in item or "publish:" in item for item in rendered))
        inventory = next(item for item in rendered if "export:credentials" in item)
        self.assertIn("umask 077", inventory); self.assertIn("trap cleanup", inventory); self.assertIn("rm -f", inventory)
        self.assertIn("--id=leadflow-postgres", inventory); self.assertNotIn("--all", inventory)
        self.assertLess(inventory.index("trap cleanup"), inventory.index("mktemp"))
        self.assertIn('chmod 600 "$a" "$d"', inventory)
        self.assertEqual(self.invoke(["apply", "--authorize-provision"], runner)[0], 0)
        self.assertEqual((runner.credential, runner.workflow is not None, runner.active), ("equivalent", True, False))

    def test_apply_requires_explicit_authorization_before_any_command(self):
        runner = FakeRunner()
        code, _, err = self.invoke(["apply"], runner)
        self.assertEqual(code, 1); self.assertIn("provision_not_authorized", err)
        self.assertEqual(runner.calls, [])

    def test_equivalent_install_is_not_reimported_and_active_state_is_preserved(self):
        desired = json.loads((ROOT / "workflows" / "leadflow_core_initial.json").read_text(encoding="utf-8"))
        for active in (False, True):
            runner = FakeRunner(workflow=desired.copy(), credential="equivalent", active=active)
            code, _, _ = self.invoke(["apply", "--authorize-provision"], runner)
            self.assertEqual(code, 0)
            rendered = "\n".join(" ".join(call[0]) for call in runner.calls)
            self.assertNotIn("import:credentials", rendered); self.assertNotIn("import:workflow", rendered)
            self.assertNotIn("publish:workflow", rendered); self.assertEqual(runner.active, active)

    def test_partial_install_imports_only_missing_item(self):
        desired = json.loads((ROOT / "workflows" / "leadflow_core_initial.json").read_text(encoding="utf-8"))
        runner = FakeRunner(workflow=desired.copy(), credential="absent")
        self.assertEqual(self.invoke(["apply", "--authorize-provision"], runner)[0], 0)
        rendered = "\n".join(" ".join(call[0]) for call in runner.calls)
        self.assertIn("import:credentials", rendered); self.assertNotIn("import:workflow", rendered)

    def test_credential_inventory_is_individual_and_fail_closed(self):
        for state in ("absent", "equivalent", "divergent", "ambiguous"):
            runner = FakeRunner(credential=state)
            if state == "ambiguous":
                self.assertEqual(self.invoke(["preflight"], runner)[0], 1)
            else:
                arguments = ["preflight"]
                if state == "divergent":
                    arguments.append("--authorize-replace-credential")
                self.assertEqual(self.invoke(arguments, runner)[0], 0)
            command = next(" ".join(call[0]) for call in runner.calls if "export:credentials" in " ".join(call[0]))
            self.assertIn("--id=leadflow-postgres", command)
            self.assertNotIn("--all", command)

        runner = FakeRunner(fail_operation="export:credentials")
        code, out, err = self.invoke(["preflight"], runner)
        self.assertEqual(code, 1); self.assertEqual(out, "")
        self.assertIn("credential_inventory_failed", err)
        self.assertNotIn(SECRET, err)

    def test_divergence_and_active_replacement_require_specific_authorizations(self):
        divergent = json.loads((ROOT / "workflows" / "leadflow_core_initial.json").read_text(encoding="utf-8")); divergent["name"] = "Divergent"
        credential = FakeRunner(credential="divergent")
        code, _, err = self.invoke(["preflight"], credential)
        self.assertEqual(code, 1); self.assertIn("credential_divergence_requires_authorization", err)
        credential_args = ["apply", "--authorize-provision", "--authorize-replace-credential"]
        self.assertEqual(self.invoke(credential_args, credential)[0], 0)
        self.assertEqual(credential.credential, "equivalent")
        workflow = FakeRunner(workflow=divergent, credential="equivalent", active=True)
        code, _, err = self.invoke(["preflight", "--authorize-replace-workflow"], workflow)
        self.assertEqual(code, 1); self.assertIn("active_workflow_requires_authorization", err)
        args = ["apply", "--authorize-provision", "--authorize-replace-workflow", "--authorize-active-replacement"]
        self.assertEqual(self.invoke(args, workflow)[0], 0); self.assertTrue(workflow.active)

    def test_publish_is_independent_and_authorized(self):
        runner = FakeRunner()
        code, out, err = self.invoke(["apply", "--authorize-provision", "--authorize-publish"], runner)
        self.assertEqual((code, out, err), (0, "n8n_linux_provision phase=apply status=PASS\n", ""))
        commands = [call[0] for call in runner.calls]
        credential_call = next(call for call in runner.calls if "import:credentials" in " ".join(call[0]))
        shell = " ".join(credential_call[0])
        self.assertIn("umask 077", shell); self.assertIn("trap", shell); self.assertIn("rm -f", shell)
        self.assertIn(SECRET.encode(), credential_call[1]["input"])
        self.assertNotIn(SECRET, " ".join(" ".join(command) for command in commands) + out + err)
        self.assertTrue(any("publish:workflow" in command for command in commands))
        self.assertTrue(runner.workflow is not None and runner.credential == "equivalent" and runner.active)

    def test_ambiguous_inventory_and_ambiguous_mutation_fail_closed(self):
        ambiguous = FakeRunner(credential="ambiguous")
        code, _, err = self.invoke(["preflight"], ambiguous)
        self.assertEqual(code, 1); self.assertIn("installation_state_ambiguous", err)
        workflow_ambiguous = FakeRunner(workflow="ambiguous", credential="equivalent")
        code, _, err = self.invoke(["preflight"], workflow_ambiguous)
        self.assertEqual(code, 1); self.assertIn("installation_state_ambiguous", err)
        runner = FakeRunner(fail_operation="import:credentials")
        code, out, err = self.invoke(["apply", "--authorize-provision"], runner)
        self.assertEqual(code, 1); self.assertEqual(out, "")
        self.assertIn("credential_import_ambiguous", err); self.assertNotIn(SECRET, err)
        credential_call = next(call for call in runner.calls if "import:credentials" in " ".join(call[0]))
        self.assertIn("trap", " ".join(credential_call[0])); self.assertIn("rm -f", " ".join(credential_call[0]))

    def test_ambiguous_command_success_is_reconciled_without_repeating_mutation(self):
        runner = FakeRunner(fail_operation="import:credentials", mutate_on_failure=True)
        self.assertEqual(self.invoke(["apply", "--authorize-provision"], runner)[0], 0)
        imports = [call for call in runner.calls if "import:credentials" in " ".join(call[0])]
        self.assertEqual(len(imports), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
