import json
import logging

import srbg_api.logging as app_logging


def test_json_formatter_emits_allowlisted_structured_fields() -> None:
    assert hasattr(app_logging, "JsonFormatter")
    record = logging.LogRecord(
        name="srbg.api",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "019f59e6-7ed8-7ed2-94e0-e8928aee2d30"
    record.status_code = 200
    record.document_body = "must-not-be-logged"

    payload = json.loads(app_logging.JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["message"] == "request_completed"
    assert payload["request_id"] == record.request_id
    assert payload["status_code"] == 200
    assert payload["timestamp"].endswith("Z")
    assert "document_body" not in payload
    assert "must-not-be-logged" not in json.dumps(payload)


def test_json_formatter_allows_publication_gate_reason_codes_without_evidence_values() -> None:
    record = logging.LogRecord(
        name="srbg.api",
        level=logging.WARNING,
        pathname=__file__,
        lineno=36,
        msg="publication_gate_denied",
        args=(),
        exc_info=None,
    )
    record.request_id = "019f59e6-7ed8-7ed2-94e0-e8928aee2d31"
    record.reason_codes = ["SAFETY_CASE_CASUALTY_LOSS_CONFLICT"]
    record.current_value_snapshot = 52

    payload = json.loads(app_logging.JsonFormatter().format(record))

    assert payload["reason_codes"] == ["SAFETY_CASE_CASUALTY_LOSS_CONFLICT"]
    assert "current_value_snapshot" not in payload
    assert 52 not in payload.values()
