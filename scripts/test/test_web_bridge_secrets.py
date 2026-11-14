"""Focused synthetic tests for the isolated Web Bridge secret loader."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SENSITIVE = "synthetic-sensitive-value-never-print"


def load_module():
    path = ROOT / "scripts" / "admin" / "web_bridge_with_secrets.py"
    spec = importlib.util.spec_from_file_location("web_bridge_with_secrets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WebBridgeSecretTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.base_env = {
            "WEB_BRIDGE_COMPOSE_PROJECT": "leadflow-web-bridge",
            "LEADFLOW_COMPOSE_PROJECT": "leadflow-main",
            "WEB_BRIDGE_ENV": "production",
            "WEB_BRIDGE_PUBLIC_PATH": "/contacto",
            "WEB_BRIDGE_UPSTREAM_URL": "http://leadflow.internal/webhook/leadflow",
            "WEB_BRIDGE_SOURCE": "emactiva_web",
            "WEB_BRIDGE_EVENT_ID_KEY": "synthetic-event-key-" + "e" * 32,
            "WEB_BRIDGE_ALLOWED_ORIGINS": "https://form.example.invalid",
            "WEB_BRIDGE_ABUSE_CONTROL": "external",
            "WEB_BRIDGE_TURNSTILE_MODE": "siteverify",
            "WEB_BRIDGE_TURNSTILE_HOSTNAMES": "form.example.invalid",
            "LEADFLOW_WEBHOOK_KEY": "synthetic-webhook-key-" + "w" * 32,
            "LEADFLOW_ALLOWED_SOURCES": "emactiva_web",
            "LEADFLOW_ALLOWED_INTERESTS": "automatizacion",
            "WEB_BRIDGE_UPSTREAM_NETWORK": "synthetic-upstream-network",
        }

    def write_map(self, path: Path, *, drop=None, identity="leadflow-runtime@example-project.iam.gserviceaccount.com", reference_override=None):
        secrets = {
            name: f"projects/example-project/secrets/{self.module.AUTHORIZED_SECRET_IDS[name]}/versions/1"
            for name in self.module.SECRET_NAMES if name != drop
        }
        if reference_override:
            secrets.update(reference_override)
        value = {
            "version": self.module.MAP_VERSION,
            "provider": self.module.PROVIDER_NAME,
            "operation": self.module.OPERATION_NAME,
            "expected_identity": identity,
            "secrets": secrets,
        }
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def invoke(self, path, provider_factory=None, runner=mock.Mock(), env=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or self.base_env, clear=True), redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.module.main(["preflight", "--map", str(path)], provider_factory, runner)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_authorized_resolution_runs_only_bridge_preflight(self):
        calls = []
        class Provider:
            def __init__(self, identity, timeout): calls.append((identity, timeout))
            def resolve(self, reference): calls.append(reference); return SENSITIVE + reference.split("/")[3]
        captured = {}
        def runner(command, **kwargs): captured.update(command=command, env=kwargs["env"]); return mock.Mock(returncode=0)
        with tempfile.TemporaryDirectory() as temporary:
            inherited = {**self.base_env, **{name: "inherited-must-not-win" for name in self.module.SECRET_NAMES}}
            code, out, err = self.invoke(self.write_map(Path(temporary) / "map.json"), Provider, runner, inherited)
        self.assertEqual((code, out, err), (0, "web_bridge_secret_runtime phase=preflight status=PASS\n", ""))
        self.assertEqual(set(self.module.SECRET_NAMES), set(captured["env"]) & set(self.module.SECRET_NAMES))
        self.assertEqual(len(self.module.SECRET_NAMES), 4)
        self.assertTrue(all(captured["env"][name].startswith(SENSITIVE) for name in self.module.SECRET_NAMES))
        self.assertEqual(len([item for item in calls if isinstance(item, str) and item.startswith("projects/")]), 4)
        self.assertEqual(captured["command"][-2:], ["config", "-q"])
        self.assertIn("compose.web-bridge.yaml", " ".join(captured["command"]))
        self.assertNotIn("compose.yaml", " ".join(captured["command"]).replace("compose.web-bridge.yaml", ""))
        self.assertNotIn("up", captured["command"])

    def test_wrong_identity_and_ambiguous_credentials_fail_closed(self):
        class WrongIdentityProvider:
            def __init__(self, _identity, _timeout): raise RuntimeError(SENSITIVE)
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_map(Path(temporary) / "map.json")
            code, out, err = self.invoke(path, WrongIdentityProvider)
        self.assertEqual(code, 1); self.assertEqual(out, ""); self.assertNotIn(SENSITIVE, err)
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_map(Path(temporary) / "map.json")
            ambiguous = {**self.base_env, "GOOGLE_APPLICATION_CREDENTIALS": "C:/synthetic/credential.json"}
            code, out, err = self.invoke(path, env=ambiguous)
        self.assertEqual(code, 1); self.assertEqual(out, ""); self.assertNotIn("credential.json", err)

    def test_unauthorized_or_incomplete_map_is_rejected_before_provider(self):
        provider = mock.Mock()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (
                self.write_map(root / "missing.json", drop="WEB_BRIDGE_ABUSE_TOKEN"),
                self.write_map(root / "latest.json", reference_override={"WEB_BRIDGE_ABUSE_TOKEN": "projects/example-project/secrets/abuse/versions/latest"}),
                self.write_map(root / "unauthorized.json", reference_override={"WEB_BRIDGE_ABUSE_TOKEN": "projects/example-project/secrets/other-secret/versions/1"}),
                self.write_map(root / "cross-project.json", reference_override={"WEB_BRIDGE_ABUSE_TOKEN": "projects/other-project/secrets/leadflow-web-bridge-abuse-token/versions/1"}),
                self.write_map(root / "duplicate.json", reference_override={
                    "WEB_BRIDGE_ABUSE_TOKEN": "projects/example-project/secrets/leadflow-turnstile-secret/versions/1",
                }),
            )
            for path in cases:
                with self.subTest(path=path.name):
                    code, _, _ = self.invoke(path, provider)
                    self.assertEqual(code, 1)
        provider.assert_not_called()

    def test_missing_denied_or_timed_out_secret_is_sanitized(self):
        for failure in (KeyError("missing " + SENSITIVE), PermissionError(SENSITIVE), socket.timeout(SENSITIVE)):
            class Provider:
                def __init__(self, _identity, _timeout): pass
                def resolve(self, _reference): raise failure
            with self.subTest(kind=type(failure).__name__), tempfile.TemporaryDirectory() as temporary:
                code, out, err = self.invoke(self.write_map(Path(temporary) / "map.json"), Provider)
                self.assertEqual(code, 1); self.assertEqual(out, ""); self.assertNotIn(SENSITIVE, err)

    def test_project_separation_and_configuration_are_mandatory(self):
        provider = mock.Mock()
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_map(Path(temporary) / "map.json")
            for env in (
                {**self.base_env, "WEB_BRIDGE_COMPOSE_PROJECT": "leadflow-main"},
                {key: value for key, value in self.base_env.items() if key != "LEADFLOW_COMPOSE_PROJECT"},
                {key: value for key, value in self.base_env.items() if key != "WEB_BRIDGE_UPSTREAM_URL"},
            ):
                with self.subTest(env=set(env)):
                    code, _, _ = self.invoke(path, provider, env=env)
                    self.assertEqual(code, 1)
        provider.assert_not_called()

    def test_secret_values_never_appear_in_process_arguments_or_output(self):
        class Provider:
            def __init__(self, _identity, _timeout): pass
            def resolve(self, _reference): return SENSITIVE
        captured = {}
        def runner(command, **kwargs): captured["command"] = command; return mock.Mock(returncode=7, stdout=SENSITIVE.encode(), stderr=SENSITIVE.encode())
        with tempfile.TemporaryDirectory() as temporary:
            code, out, err = self.invoke(self.write_map(Path(temporary) / "map.json"), Provider, runner)
        self.assertEqual(code, 1)
        self.assertNotIn(SENSITIVE, out + err + " ".join(captured["command"]))

    def test_external_network_is_configurable_and_required_without_published_ports(self):
        compose = (ROOT / "compose.web-bridge.yaml").read_text(encoding="utf-8")
        self.assertIn("external: true", compose)
        self.assertIn("name: ${WEB_BRIDGE_UPSTREAM_NETWORK:?", compose)
        self.assertNotIn("emactiva-leadflow_default", compose)
        self.assertNotIn("\n    ports:", compose)
        provider = mock.Mock()
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_map(Path(temporary) / "map.json")
            for env in (
                {key: value for key, value in self.base_env.items() if key != "WEB_BRIDGE_UPSTREAM_NETWORK"},
                {**self.base_env, "WEB_BRIDGE_UPSTREAM_NETWORK": "invalid network"},
            ):
                with self.subTest(network=env.get("WEB_BRIDGE_UPSTREAM_NETWORK")):
                    code, _, _ = self.invoke(path, provider, env=env)
                    self.assertEqual(code, 1)
        provider.assert_not_called()

    def test_bridge_start_rebuilds_and_cached_apply_does_not_build_twice(self):
        commands = []
        def runner(command, **_kwargs):
            commands.append(command)
            return mock.Mock(returncode=0)
        environment = {"COMPOSE_DISABLE_ENV_FILE": "1"}
        self.module.run_compose("start", environment, "bridge-qa", runner)
        self.module.run_compose("build", environment, "bridge-qa", runner)
        self.module.run_compose("start-built", environment, "bridge-qa", runner)
        self.module.run_compose("restore", environment, "bridge-qa", runner)
        rendered = [" ".join(command) for command in commands]
        self.assertIn("up -d --build web-bridge", rendered[0])
        self.assertTrue(rendered[1].endswith("build web-bridge"))
        self.assertIn("up -d --no-build web-bridge", rendered[2])
        self.assertIn("up -d --no-build web-bridge", rendered[3])
        def failing(command, **_kwargs):
            return mock.Mock(returncode=19)
        with self.assertRaises(self.module.WebBridgeSecretError):
            self.module.run_compose("build", environment, "bridge-qa", failing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
