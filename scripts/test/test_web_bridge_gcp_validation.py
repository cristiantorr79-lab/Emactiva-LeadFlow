"""Focused tests for the non-destructive GCP Web Bridge validation procedure."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]


def load_module():
    path = ROOT / "scripts" / "test" / "validate_web_bridge_gcp.py"
    spec = importlib.util.spec_from_file_location("validate_web_bridge_gcp", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GcpValidationProcedureTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.env = {
            "WEB_BRIDGE_COMPOSE_PROJECT": "bridge-qa",
            "LEADFLOW_COMPOSE_PROJECT": "leadflow-main",
            "WEB_BRIDGE_UPSTREAM_NETWORK": "synthetic-network",
            "WEB_BRIDGE_N8N_HEALTH_URL": "http://n8n:5678/healthz",
            "WEB_BRIDGE_PUBLIC_PATH": "/lead",
            "WEB_BRIDGE_ALLOWED_ORIGIN": "https://form.example.invalid",
        }

    @staticmethod
    def result(stdout="", code=0):
        return subprocess.CompletedProcess([], code, stdout=stdout, stderr="sensitive-must-not-print")

    def test_preflight_is_read_only_and_functional_remains_not_verified(self):
        commands = []
        responses = iter(("bridge-id\n", "true\n", '{"8080/tcp":null}\n', "synthetic-network\n", ""))
        def runner(command, **_kwargs): commands.append(command); return self.result(next(responses))
        with mock.patch("builtins.print") as output:
            code = self.module.main([], env=self.env, runner=runner)
        self.assertEqual(code, 0)
        rendered = [" ".join(command) for command in commands]
        self.assertTrue(all(" compose " not in command and " up " not in command and " start " not in command for command in rendered))
        self.assertEqual(sum("docker exec" in command for command in rendered), 1)
        output.assert_any_call("web_bridge_gcp phase=functional status=NOT_VERIFIED")

    def test_missing_network_published_port_or_unsafe_functional_gate_fails_closed(self):
        with self.subTest(case="missing_network"):
            self.assertEqual(self.module.main([], env={**self.env, "WEB_BRIDGE_UPSTREAM_NETWORK": ""}, runner=mock.Mock()), 1)
        responses = iter(("bridge-id\n", "true\n", '{"8080/tcp":[{"HostPort":"8080"}]}\n', "synthetic-network\n"))
        with self.subTest(case="published_port"):
            self.assertEqual(self.module.main([], env=self.env, runner=lambda *_args, **_kwargs: self.result(next(responses))), 1)
        responses = iter(("bridge-id\n", "true\n", '{"8080/tcp":null}\n', "synthetic-network\n", ""))
        token_reader = mock.Mock(side_effect=AssertionError("token must not be requested"))
        with self.subTest(case="safety_gate"):
            self.assertEqual(self.module.main(["--functional"], env=self.env,
                runner=lambda *_args, **_kwargs: self.result(next(responses)), token_reader=token_reader), 1)
        token_reader.assert_not_called()

    def test_functional_probe_uses_stdin_and_never_places_sensitive_values_in_arguments(self):
        responses = iter(("bridge-id\n", "true\n", '{"8080/tcp":null}\n', "synthetic-network\n", "", ""))
        calls = []
        def runner(command, **kwargs): calls.append((command, kwargs.get("input"))); return self.result(next(responses))
        env = {**self.env, "WEB_BRIDGE_QA_EXTERNAL_EFFECTS_DISABLED": "true", "WEB_BRIDGE_SYNTHETIC_INTEREST": "automatizacion"}
        token = "synthetic-sensitive-turnstile-token"
        self.assertEqual(self.module.main(["--functional"], env=env, runner=runner, token_reader=lambda _prompt: token), 0)
        arguments = " ".join(item for command, _input in calls for item in command)
        self.assertNotIn(token, arguments)
        functional_input = json.loads(calls[-1][1])
        self.assertEqual(functional_input["turnstile_token"], token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
