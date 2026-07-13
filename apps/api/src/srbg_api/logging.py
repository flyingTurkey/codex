"""Allowlisted JSON logging shared by API and Worker processes."""

import json
import logging
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
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ALLOWED_EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
