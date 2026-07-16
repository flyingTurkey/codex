"""Allowlisted JSON logging shared by API and Worker processes."""

import json
import logging
import re
import traceback
from datetime import UTC, datetime
from typing import Any

ALLOWED_EXTRA_FIELDS = (
    "request_id",
    "task_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "dependency",
    "error_code",
    "event_name",
    "action",
    "outcome",
    "reason_code",
    "reason_codes",
    "source_id",
    "object_id",
    "connector_type",
    "trial_kind",
    "trial_status",
    "ready_ratio_bps",
    "gap_cell_count",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info is not None and record.args:
            message = "operation_failed"
        message = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", message)
        message = re.sub(
            r"(?i)(bearer\s+|token=|cookie=|api[_-]?key=)[^\s&]+",
            r"\1[REDACTED]",
            message,
        )[:500]
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        for field in ALLOWED_EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info is not None:
            exception_type = record.exc_info[0]
            payload["exception"] = {
                "type": exception_type.__name__ if exception_type is not None else "Exception",
                "frames": [
                    {"module": frame.name, "line": frame.lineno}
                    for frame in traceback.extract_tb(record.exc_info[2])[-8:]
                ],
            }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
