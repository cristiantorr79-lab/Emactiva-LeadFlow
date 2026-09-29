"""Focused REM-08 authentication and operation authorization checks."""
from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import importlib.util
import json
import os
import sys


ROOT = Path(__file__).resolve().parents[2]
KEY = "rem08-test-key-with-at-least-32-characters"
os.environ.update({
    "APP_ENV": "development",
    "ADAPTER_SERVICE_KEY": KEY,
    "ADAPTER_ALLOWED_OPERATIONS": "enrichment.enrich",
    "CRM_UPSTREAM_URL": "http://crm.synthetic",
    "ENRICHMENT_UPSTREAM_URL": "http://enrichment.synthetic",
    "ALERT_UPSTREAM_URL": "http://alert.synthetic",
})
spec = importlib.util.spec_from_file_location("adapter_server_rem08", ROOT / "adapters" / "server.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


checks = {}


def check(name, value):
    checks[name] = bool(value)
    print(f"{'PASS' if value else 'FAIL'} {name}")


def request(base, path, key=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["X-LeadFlow-Adapter-Key"] = key
    raw = json.dumps(payload or {}).encode()
    try:
        with urlopen(Request(base + path, data=raw, method="POST", headers=headers), timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


base_env = {
    "APP_ENV": "development",
    "ADAPTER_SERVICE_KEY": KEY,
    "ADAPTER_ALLOWED_OPERATIONS": "enrichment.enrich",
}
try:
    adapter.load_config({key: value for key, value in base_env.items() if key != "ADAPTER_SERVICE_KEY"})
    missing_secret_closed = False
except ValueError as error:
    missing_secret_closed = str(error) == "missing or invalid ADAPTER_SERVICE_KEY"
check("REM08-E fail closed without configured secret", missing_secret_closed)

adapter.CONFIG = adapter.load_config(base_env)
adapter.call = lambda method, url, body=None, headers=None: (
    200,
    {},
    {"enrichment_status": "success", "data": {"industry": "software"}},
)
server = ThreadingHTTPServer(("127.0.0.1", 0), adapter.Handler)
thread = Thread(target=server.serve_forever, daemon=True)
captured_out, captured_err = StringIO(), StringIO()
try:
    with redirect_stdout(captured_out), redirect_stderr(captured_err):
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        no_identity = request(base, "/enrichment/enrich", payload={"email": "synthetic@example.test"})
        invalid = request(base, "/enrichment/enrich", "incorrect-credential", {"email": "synthetic@example.test"})
        allowed = request(base, "/enrichment/enrich", KEY, {"email": "synthetic@example.test"})
        forbidden = request(base, "/alert", KEY, {"execution_id": "synthetic", "stage": "alert", "error_code": "test"})
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)

check("REM08-A missing identity rejected", no_identity[0] == 401 and no_identity[1]["error"]["code"] == "adapter_identity_invalid")
check("REM08-B invalid identity rejected", invalid[0] == 401 and invalid[1]["error"]["code"] == "adapter_identity_invalid")
check("REM08-C valid identity allowed", allowed[0] == 200 and allowed[1].get("success") is True)
check("REM08-D unauthorized operation rejected", forbidden[0] == 403 and forbidden[1]["error"]["code"] == "adapter_operation_forbidden")
check("REM08-F secret absent from output and errors", KEY not in captured_out.getvalue() + captured_err.getvalue() + repr((no_identity, invalid, allowed, forbidden)))
check("REM08-G existing legitimate operation works", allowed[1].get("data") == {"industry": "software"})

failed = [name for name, passed in checks.items() if not passed]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
