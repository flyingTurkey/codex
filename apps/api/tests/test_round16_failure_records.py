import json
import logging
import sys
from uuid import UUID

from srbg_api.logging import JsonFormatter
from srbg_api.task_failures import failure_record

RUN_ID = UUID("019b1600-0000-7000-8000-000000000010")


def test_failure_record_uses_business_reference_not_celery_task_id() -> None:
    record = failure_record(
        task_name="srbg.source.fetch",
        task_id="019b1600-0000-7000-8000-000000000099",
        args=(),
        kwargs={"source_id": "019b1600-0000-7000-8000-000000000001", "run_id": str(RUN_ID)},
        exception=RuntimeError("secret payload must not survive"),
    )
    assert record.run_id == RUN_ID
    assert record.execution_id == RUN_ID
    assert record.reconstruction_status == "REPLAYABLE"
    assert "secret payload" not in repr(record)


def test_legacy_task_id_only_failure_is_non_replayable() -> None:
    record = failure_record(
        task_name="srbg.source.fetch",
        task_id="019b1600-0000-7000-8000-000000000099",
        args=(),
        kwargs={},
        exception=RuntimeError("bounded"),
    )
    assert record.replayable is False
    assert record.reconstruction_status == "NON_REPLAYABLE"
    assert record.blocked_reason == "LEGACY_TASK_ID_ONLY"


def test_failure_log_redacts_exception_payload_and_url_query_secrets() -> None:
    try:
        raise RuntimeError("private body cookie=session-secret")
    except RuntimeError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        "round16",
        logging.ERROR,
        __file__,
        1,
        "fetch failed %s",
        ("https://example.invalid/path?api_key=query-secret",),
        exc_info,
    )
    rendered = JsonFormatter().format(record)
    assert "session-secret" not in rendered
    assert "query-secret" not in rendered
    assert json.loads(rendered)["exception"]["type"] == "RuntimeError"
