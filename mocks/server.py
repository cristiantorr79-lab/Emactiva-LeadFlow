import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


KIND = os.environ["MOCK_KIND"]
PORT = int(os.environ.get("MOCK_PORT", "8080"))
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CRM_FIELDS = {"first_name", "last_name", "phone", "company"}
ENRICHMENT_FIELDS = {"industry", "company_size", "website"}
contacts = {}
contacts_by_email = {}
contacts_by_operation = {}
interactions = {}
interactions_by_operation = {}
next_contact = 1
next_interaction = 1
lock = threading.Lock()
calls = {"lookup": 0, "create": 0, "update": 0, "update_enrichment": 0, "interaction": 0, "reconcile_interaction": 0, "enrich": 0}
alerts = []
failure = None
FAILURE_MODES = {"timeout", "http_400", "http_401", "http_403", "http_404", "http_408", "http_409", "http_429", "http_500", "http_502", "http_503", "http_504", "ambiguous_create", "ambiguous_interaction"}


def normalized_email(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if len(value) <= 254 and EMAIL_RE.fullmatch(value) else None


class Handler(BaseHTTPRequestHandler):
    server_version = "LeadFlowMock/1"

    def log_message(self, _format, *_args):
        return

    def respond(self, status, payload, headers=None):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, str(value))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            value = json.loads(self.rfile.read(length))
            return value if isinstance(value, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/healthz":
            self.respond(200, {"ok": True, "service": KIND})
        elif path == "/stats":
            with lock:
                result = {"calls": dict(calls), "contacts": len(contacts) if KIND == "crm" else None, "interactions": len(interactions) if KIND == "crm" else None}
                if KIND == "slack":
                    result.update({"alert_count": len(alerts), "last_alert": dict(alerts[-1]) if alerts else None})
            self.respond(200, result)
        elif KIND == "crm" and path == "/crm/contacts":
            visible_fields = ("id", "first_name", "last_name", "email", "company")
            with lock:
                result = [
                    {
                        **{name: contact[name] for name in visible_fields if name in contact},
                        "interactions": [
                            dict(interaction)
                            for _, interaction in sorted(interactions.items())
                            if interaction.get("contact_id") == contact.get("id")
                        ],
                    }
                    for _, contact in sorted(contacts.items())
                ]
            self.respond(200, {"contacts": result})
        elif KIND == "crm" and (match := re.fullmatch(r"/crm/contacts/([^/]+)", path)):
            with lock:
                contact = contacts.get(match.group(1))
                result = dict(contact) if contact is not None else None
            if result is None:
                self.respond(404, {"error": {"type": "technical_not_found"}})
            else:
                self.respond(200, {"contact": result})
        else:
            self.respond(404, {"error": {"type": "technical_not_found"}})

    def do_POST(self):
        path = urlparse(self.path).path
        payload = self.read_json()
        if payload is None:
            self.respond(400, {"error": {"type": "validation_error"}})
            return
        if path == "/control/failure":
            self.configure_failure(payload)
        elif KIND == "slack" and path == "/webhook":
            with lock:
                calls["alert"] = calls.get("alert", 0) + 1
            if not self.simulate("alert"):
                self.slack_alert(payload)
        elif KIND == "crm" and path == "/crm/lookup" and not self.simulate("lookup"):
            self.crm_lookup(payload)
        elif KIND == "crm" and path == "/crm/contacts" and not self.simulate("create", payload):
            self.crm_create(payload)
        elif KIND == "crm" and path == "/crm/interactions" and not self.simulate("interaction", payload):
            self.crm_interaction(payload)
        elif KIND == "crm" and path == "/crm/interactions/reconcile" and not self.simulate("reconcile_interaction"):
            self.reconcile_interaction(payload)
        elif KIND == "enrichment" and path == "/enrich" and not self.simulate("enrich"):
            self.enrich(payload)
        elif path not in {"/crm/lookup", "/crm/contacts", "/crm/interactions", "/crm/interactions/reconcile", "/enrich"}:
            self.respond(404, {"error": {"type": "technical_not_found"}})

    def do_PATCH(self):
        path = urlparse(self.path).path
        payload = self.read_json()
        if payload is None:
            self.respond(400, {"error": {"type": "validation_error"}})
            return
        match = re.fullmatch(r"/crm/contacts/([^/]+)(/enrichment)?", path)
        if KIND != "crm" or not match:
            self.respond(404, {"error": {"type": "technical_not_found"}})
            return
        operation = "update_enrichment" if match.group(2) else "update"
        if not self.simulate(operation):
            self.crm_update(match.group(1), payload, enrichment=bool(match.group(2)))

    def do_DELETE(self):
        global failure
        path = urlparse(self.path).path
        if KIND == "slack" and path == "/alerts":
            with lock:
                alerts.clear()
                calls["alert"] = 0
            self.respond(200, {"ok": True})
            return
        if path != "/control/failure":
            self.respond(404, {"error": {"type": "technical_not_found"}})
            return
        with lock:
            failure = None
        self.respond(200, {"ok": True})

    def configure_failure(self, payload):
        global failure
        mode = payload.get("mode")
        operation = payload.get("operation", "*")
        delay = payload.get("delay_seconds", 1)
        retry_after = payload.get("retry_after_seconds", 3)
        failures = payload.get("failures")
        allowed = ({"*", "lookup", "create", "update", "update_enrichment", "interaction", "reconcile_interaction"} if KIND == "crm"
                   else {"*", "enrich"} if KIND == "enrichment" else {"*", "alert"})
        if mode not in FAILURE_MODES or operation not in allowed or not isinstance(delay, (int, float)) or delay <= 0 or not isinstance(retry_after, int) or retry_after < 0 or (failures is not None and (not isinstance(failures, int) or failures < 1)):
            self.respond(400, {"error": {"type": "validation_error"}})
            return
        with lock:
            failure = {"mode": mode, "operation": operation, "delay": delay, "retry_after": retry_after, "remaining": failures}
        self.respond(200, {"ok": True, "mode": mode, "operation": operation})

    def simulate(self, operation, payload=None):
        with lock:
            configured = dict(failure) if failure and failure["operation"] in {"*", operation} else None
            if configured and configured["remaining"] == 0:
                configured = None
            elif configured and configured["remaining"] is not None:
                failure["remaining"] -= 1
        if configured is None:
            return False
        mode = configured["mode"]
        if mode in {"http_409", "ambiguous_create"} and operation == "create":
            created = self.create_contact(payload)
            if mode == "ambiguous_create":
                time.sleep(configured["delay"])
                return True
            self.respond(409, {"error": {"type": "conflict_error"}})
            return True
        if mode == "ambiguous_interaction" and operation == "interaction":
            self.create_interaction(payload)
            time.sleep(configured["delay"])
            return True
        if mode == "timeout":
            time.sleep(configured["delay"])
            return True
        status, error_type = {
            "http_400": (400, "validation_error"),
            "http_401": (401, "authentication_error"),
            "http_403": (403, "authorization_error"),
            "http_404": (404, "technical_not_found"),
            "http_408": (408, "timeout"),
            "http_409": (409, "conflict_error"),
            "http_429": (429, "rate_limit"),
            "http_500": (500, "upstream_error"),
            "http_502": (502, "upstream_error"),
            "http_503": (503, "upstream_error"),
            "http_504": (504, "upstream_error"),
        }[mode]
        headers = {"Retry-After": configured["retry_after"]} if status == 429 else None
        self.respond(status, {"error": {"type": error_type}}, headers)
        return True

    def crm_lookup(self, payload):
        email = normalized_email(payload.get("email"))
        if email is None:
            self.respond(400, {"error": {"type": "validation_error"}})
            return
        with lock:
            calls["lookup"] += 1
            contact_id = contacts_by_email.get(email)
            if contact_id is None:
                result = {"found": False}
            else:
                contact = contacts[contact_id]
                result = {"found": True, "contact": {"id": contact_id, "email": contact["email"]}}
        self.respond(200, result)

    def crm_create(self, payload):
        result = self.create_contact(payload)
        if result[0] == 201:
            self.respond(201, result[1])
        else:
            self.respond(result[0], result[1])

    def create_contact(self, payload):
        global next_contact
        lead = payload.get("lead")
        operation_key = payload.get("operation_key")
        if not isinstance(lead, dict) or not isinstance(operation_key, str) or not operation_key:
            return 400, {"error": {"type": "validation_error"}}
        email = normalized_email(lead.get("email"))
        if email is None:
            return 400, {"error": {"type": "validation_error"}}
        with lock:
            calls["create"] += 1
            previous_id = contacts_by_operation.get(operation_key)
            if previous_id is not None:
                return 200, {"contact_id": previous_id, "created": True}
            if email in contacts_by_email:
                return 409, {"error": {"type": "conflict_error"}}
            contact_id = f"crm_{next_contact:06d}"
            next_contact += 1
            contact = {"id": contact_id, "email": email}
            contact.update({name: lead[name] for name in CRM_FIELDS if name in lead})
            contacts[contact_id] = contact
            contacts_by_email[email] = contact_id
            contacts_by_operation[operation_key] = contact_id
        return 201, {"contact_id": contact_id, "created": True}

    def crm_update(self, contact_id, payload, enrichment=False):
        fields = payload.get("fields")
        allowed = ENRICHMENT_FIELDS if enrichment else CRM_FIELDS
        if not isinstance(fields, dict) or any(name not in allowed for name in fields):
            self.respond(400, {"error": {"type": "validation_error"}})
            return
        with lock:
            calls["update_enrichment" if enrichment else "update"] += 1
            contact = contacts.get(contact_id)
            if contact is None:
                self.respond(404, {"error": {"type": "technical_not_found"}})
                return
            contact.update(fields)
        self.respond(200, {"contact_id": contact_id})

    def create_interaction(self, payload):
        global next_interaction
        contact_id, interaction, operation_key = payload.get("contact_id"), payload.get("interaction"), payload.get("operation_key")
        if contact_id not in contacts or not isinstance(interaction, dict) or not interaction or set(interaction) - {"interest", "message"} or not isinstance(operation_key, str) or not operation_key:
            return 400, {"error": {"type": "validation_error"}}
        with lock:
            calls["interaction"] += 1
            existing = interactions_by_operation.get(operation_key)
            if existing is not None:
                return 200, {"interaction_id": existing, "created": False}
            interaction_id = f"int_{next_interaction:06d}"
            next_interaction += 1
            interactions[interaction_id] = {"id": interaction_id, "contact_id": contact_id, **interaction}
            interactions_by_operation[operation_key] = interaction_id
        return 201, {"interaction_id": interaction_id, "created": True}

    def crm_interaction(self, payload):
        status, result = self.create_interaction(payload)
        self.respond(status, result)

    def reconcile_interaction(self, payload):
        operation_key = payload.get("operation_key")
        if not isinstance(operation_key, str) or not operation_key:
            self.respond(400, {"error": {"type": "validation_error"}}); return
        with lock:
            calls["reconcile_interaction"] += 1
            interaction_id = interactions_by_operation.get(operation_key)
        self.respond(200, {"found": interaction_id is not None, "interaction_id": interaction_id, "absence_conclusive": True})

    def enrich(self, payload):
        email = normalized_email(payload.get("email"))
        company = payload.get("company")
        if email is None or (company is not None and not isinstance(company, str)):
            self.respond(400, {"error": {"type": "validation_error"}})
            return
        with lock:
            calls["enrich"] += 1
        data = {
            "industry": os.environ.get("ENRICHMENT_INDUSTRY", "software"),
            "company_size": os.environ.get("ENRICHMENT_COMPANY_SIZE", "small"),
            "website": os.environ.get("ENRICHMENT_WEBSITE", "https://example.test"),
        }
        self.respond(200, {"enrichment_status": "success", "data": data})

    def slack_alert(self, payload):
        allowed = {"execution_id", "stage", "error_code"}
        if set(payload) != allowed or not all(isinstance(payload[name], str) and payload[name] for name in allowed):
            self.respond(400, {"error": {"type": "validation_error"}})
            return
        minimal = {name: payload[name] for name in ("execution_id", "stage", "error_code")}
        with lock:
            alerts.append(minimal)
        self.respond(200, {"ok": True})


ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
