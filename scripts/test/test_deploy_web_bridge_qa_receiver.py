"""Focused tests for the resumable QA receiver deployment procedure."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module():
    path = ROOT / "scripts" / "test" / "deploy_web_bridge_qa_receiver.py"
    spec = importlib.util.spec_from_file_location("deploy_web_bridge_qa_receiver", path)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


class DeployQaReceiverTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.env = {
            "LEADFLOW_COMPOSE_PROJECT": "leadflow-main",
            "LEADFLOW_EXPECTED_MAIN_CONTAINERS": "6",
            "WEB_BRIDGE_COMPOSE_PROJECT": "bridge-qa",
            "WEB_BRIDGE_QA_RECEIVER_PROJECT": "receiver-qa",
            "LEADFLOW_MAIN_NETWORK": "leadflow-main-network",
            "WEB_BRIDGE_QA_NETWORK": "bridge-qa-network",
            "WEB_BRIDGE_QA_EGRESS_NETWORK": "bridge-qa-egress-network",
            "WEB_BRIDGE_UPSTREAM_NETWORK": "bridge-qa-network",
            "QA_RECEIVER_PORT": "8090",
            "QA_EGRESS_PORT": "8899",
            "QA_RECEIVER_PATH": "/qa/receive",
            "WEB_BRIDGE_UPSTREAM_URL": "http://qa-receiver:8090/qa/receive",
            "WEB_BRIDGE_TURNSTILE_PROXY_URL": "http://qa-egress:8899",
            "WEB_BRIDGE_ALLOWED_ORIGIN": "https://form.example.invalid",
            "WEB_BRIDGE_PUBLIC_PATH": "/lead",
        }
        self.bridge_env = {
            **self.env,
            "WEB_BRIDGE_TURNSTILE_SECRET_KEY": "s" * 40,
            "WEB_BRIDGE_ABUSE_TOKEN": "a" * 40,
            "LEADFLOW_WEBHOOK_KEY": "w" * 40,
            "WEB_BRIDGE_EVENT_ID_KEY": "e" * 40,
        }
        self.commands = []
        self.egress_network_exists = False

    def runner(self, command, **_kwargs):
        self.commands.append(command)
        rendered = " ".join(command)
        if command[:2] == ["docker", "ps"]:
            if "leadflow-main" in rendered:
                output = "\n".join(f"main-{number}" for number in range(6))
            elif "bridge-qa" in rendered:
                output = "bridge-id"
            else:
                output = ""
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")
        if command[:3] == ["docker", "network", "ls"]:
            rendered_filter = " ".join(command)
            if "bridge-qa-egress-network" in rendered_filter:
                output = "bridge-qa-egress-network" if self.egress_network_exists else ""
            else:
                output = "bridge-qa-network" if "bridge-qa-network" in rendered_filter else ""
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")
        if command[:3] == ["docker", "network", "inspect"]:
            owner = "web-bridge-qa-egress-network" if "egress" in command[-1] else "web-bridge-qa-network"
            return subprocess.CompletedProcess(command, 0, stdout=owner, stderr="")
        if command[:3] == ["docker", "network", "rm"]:
            self.egress_network_exists = False
            return subprocess.CompletedProcess(command, 0, stdout=command[-1], stderr="")
        if "up" in command and "qa-egress" in command:
            self.egress_network_exists = True
        return subprocess.CompletedProcess(command, 0, stdout="synthetic-version", stderr="")

    def resolver(self, _path):
        return dict(self.bridge_env), "bridge-qa"

    def invoke(self, arguments, env=None):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "map.json"; path.write_text("{}", encoding="utf-8")
            return self.module.main([*arguments, "--map", str(path)], env=self.env if env is None else env, runner=self.runner, resolver=self.resolver)

    def test_preflight_is_non_mutating_and_uses_only_qa_compose_files(self):
        self.assertEqual(self.invoke(["preflight"]), 0)
        rendered = [" ".join(command) for command in self.commands]
        self.assertFalse(any(" up " in command or " down " in command for command in rendered))
        compose_files = [command for command in rendered if " compose " in command and " config " in command]
        self.assertTrue(any("compose.web-bridge-qa-receiver.yaml" in command for command in compose_files))
        self.assertTrue(any("compose.web-bridge.yaml" in command for command in compose_files))
        self.assertFalse(any("compose.yaml" in command.replace("compose.web-bridge.yaml", "") for command in rendered))

    def test_apply_requires_authorization_before_any_mutating_command(self):
        self.assertEqual(self.invoke(["apply"]), 1)
        self.assertFalse(any("up" in command or "down" in command for command in self.commands))

    def test_authorized_apply_targets_only_receiver_and_bridge_projects(self):
        self.assertEqual(self.invoke(["apply", "--authorize-apply"]), 0)
        rendered = [" ".join(command) for command in self.commands]
        build = next(index for index, command in enumerate(rendered) if " build web-bridge" in command)
        receiver_up = next(index for index, command in enumerate(rendered) if " up " in command and "--project-name receiver-qa" in command)
        bridge_up = next(index for index, command in enumerate(rendered) if " up " in command and "--project-name bridge-qa" in command)
        self.assertLess(build, receiver_up)
        self.assertLess(receiver_up, bridge_up)
        self.assertIn("--no-build", rendered[bridge_up])
        mutating = [" ".join(command) for command in self.commands if "up" in command or "down" in command]
        self.assertEqual(len(mutating), 2)
        self.assertTrue(any("receiver-qa" in command and "qa-receiver" in command for command in mutating))
        self.assertTrue(any("receiver-qa" in command and "qa-egress" in command for command in mutating))
        self.assertTrue(any("bridge-qa" in command and "compose.web-bridge.yaml" in command for command in mutating))
        self.assertFalse(any("leadflow-main" in command for command in mutating))

    def test_bridge_build_failure_stops_before_any_service_start(self):
        original = self.runner
        def failing_runner(command, **kwargs):
            result = original(command, **kwargs)
            if "build" in command and "web-bridge" in command:
                return subprocess.CompletedProcess(command, 17, stdout="", stderr="synthetic build failure")
            return result
        self.runner = failing_runner
        try:
            self.assertEqual(self.invoke(["apply", "--authorize-apply"]), 1)
        finally:
            self.runner = original
        self.assertFalse(any("up" in command for command in self.commands))

    def test_receiver_environment_contains_only_the_normal_webhook_credential(self):
        config = self.module.read_config(self.env)
        receiver_env = self.module.receiver_environment(self.bridge_env, config)
        self.assertEqual(set(receiver_env) & {
            "WEB_BRIDGE_TURNSTILE_SECRET_KEY", "WEB_BRIDGE_ABUSE_TOKEN",
            "LEADFLOW_WEBHOOK_KEY", "WEB_BRIDGE_EVENT_ID_KEY",
        }, {"LEADFLOW_WEBHOOK_KEY"})

    def test_commercial_or_ambiguous_upstream_is_rejected(self):
        for changes in (
            {"WEB_BRIDGE_UPSTREAM_URL": "http://n8n:5678/webhook/leadflow"},
            {"WEB_BRIDGE_QA_NETWORK": "leadflow-main-network", "WEB_BRIDGE_UPSTREAM_NETWORK": "leadflow-main-network"},
        ):
            with self.subTest(changes=changes), self.assertRaises(self.module.ProcedureError):
                self.module.read_config({**self.env, **changes})

    def test_main_inventory_count_is_external_positive_and_exact(self):
        self.assertEqual(self.module.read_config(self.env).expected_main_count, 6)
        for value in (None, "0", "invalid"):
            candidate = dict(self.env)
            if value is None:
                candidate.pop("LEADFLOW_EXPECTED_MAIN_CONTAINERS")
            else:
                candidate["LEADFLOW_EXPECTED_MAIN_CONTAINERS"] = value
            with self.subTest(value=value), self.assertRaises(self.module.ProcedureError):
                self.module.read_config(candidate)
        mismatch = {**self.env, "LEADFLOW_EXPECTED_MAIN_CONTAINERS": "8"}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "map.json"; path.write_text("{}", encoding="utf-8")
            code = self.module.main(
                ["preflight", "--map", str(path)], env=mismatch,
                runner=self.runner, resolver=self.resolver,
            )
        self.assertEqual(code, 1)

    def test_egress_configuration_is_explicit_and_cannot_be_main_or_direct(self):
        config = self.module.read_config(self.env)
        self.assertEqual((config.egress_network, config.proxy_url), ("bridge-qa-egress-network", "http://qa-egress:8899"))
        for changes in (
            {"WEB_BRIDGE_QA_EGRESS_NETWORK": "leadflow-main-network"},
            {"WEB_BRIDGE_QA_EGRESS_NETWORK": "bridge-qa-network"},
            {"WEB_BRIDGE_TURNSTILE_PROXY_URL": "https://qa-egress:8899"},
            {"WEB_BRIDGE_TURNSTILE_PROXY_URL": "http://metadata.google.internal:80"},
            {"WEB_BRIDGE_TURNSTILE_PROXY_URL": ""},
        ):
            with self.subTest(changes=changes), self.assertRaises(self.module.ProcedureError):
                self.module.read_config({**self.env, **changes})

    def test_rollback_restores_bridge_before_cleaning_only_egress(self):
        values = {
            **self.env,
            "WEB_BRIDGE_PREVIOUS_UPSTREAM_URL": self.env["WEB_BRIDGE_UPSTREAM_URL"],
            "WEB_BRIDGE_PREVIOUS_UPSTREAM_NETWORK": self.env["WEB_BRIDGE_UPSTREAM_NETWORK"],
            "WEB_BRIDGE_PREVIOUS_TURNSTILE_PROXY_URL": "DIRECT",
        }
        self.egress_network_exists = True
        self.assertEqual(self.invoke(["rollback", "--authorize-apply"], values), 0)
        mutating = [" ".join(command) for command in self.commands if "up" in command or "rm" in command]
        self.assertEqual(len(mutating), 3)
        self.assertIn("bridge-qa", mutating[0])
        self.assertIn("receiver-qa", mutating[1])
        self.assertIn("rm --stop --force qa-egress", mutating[1])
        self.assertIn("docker network rm bridge-qa-egress-network", mutating[2])
        self.assertFalse(any(command.endswith(" qa-receiver") for command in mutating[1:]))
        self.assertFalse(any("leadflow-main" in command for command in mutating))


if __name__ == "__main__":
    unittest.main(verbosity=2)
