"""Structured operational logging with an explicit technical metadata allowlist."""
import json
import os
import re
import sys

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_ALLOWED = {"operation", "stage", "error_type", "error_code", "status", "http_status", "retry_count", "execution_id"}
_TECHNICAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class StructuredLogger:
    def __init__(self, component, env=None, stdout=None, stderr=None):
        values = os.environ if env is None else env
        self.level = str(values.get("LOG_LEVEL", "INFO")).strip().upper()
        self.output = str(values.get("LOG_OUTPUT", "stderr")).strip().lower()
        if self.level not in _LEVELS:
            raise ValueError("invalid LOG_LEVEL")
        if self.output not in {"stdout", "stderr"}:
            raise ValueError("invalid LOG_OUTPUT")
        if not _TECHNICAL.fullmatch(component):
            raise ValueError("invalid log component")
        self.component = component
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr

    def emit(self, level, event, **metadata):
        normalized = str(level).upper()
        if normalized not in _LEVELS:
            normalized = "ERROR"
        if _LEVELS[normalized] < _LEVELS[self.level]:
            return
        safe_event = event if isinstance(event, str) and _TECHNICAL.fullmatch(event) else "operational_event"
        record = {"component": self.component, "event": safe_event, "level": normalized}
        for key, value in metadata.items():
            if key not in _ALLOWED or value is None or isinstance(value, bool):
                continue
            if key in {"http_status", "retry_count"} and isinstance(value, int) and 0 <= value <= 999999:
                record[key] = value
            elif isinstance(value, str) and _TECHNICAL.fullmatch(value):
                record[key] = value
            elif key in {"error_type", "error_code"}:
                record[key] = "external_error"
        stream = self.stdout if self.output == "stdout" else self.stderr
        print(json.dumps(record, separators=(",", ":"), sort_keys=True), file=stream, flush=True)
