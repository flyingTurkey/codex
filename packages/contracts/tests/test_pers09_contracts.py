from datetime import UTC, datetime
from uuid import UUID

from srbg_contracts import (
    EventAutomaticResultView,
    PersonalSourceActivityItemView,
    PersonalSourceActivityPage,
    PersonalSourceRunSummaryView,
)


def test_pers09_source_activity_contract_is_safe_and_pageable() -> None:
    now = datetime.now(UTC)
    summary = PersonalSourceRunSummaryView(
        last_run_at=now,
        last_run_status="FAILED",
        discovered_count=0,
        fetched_count=0,
        failed_count=1,
        next_run_at=now,
    )
    item = PersonalSourceActivityItemView(
        id=UUID("019b0000-0000-7000-8000-000000000901"),
        kind="COLLECTION_RUN",
        occurred_at=now,
        status="FAILED",
        reason_code="TIMEOUT",
        discovered_count=0,
        fetched_count=0,
        failed_count=1,
    )
    page = PersonalSourceActivityPage(items=[item], next_cursor=None, run_summary=summary)

    assert page.items[0].reason_code == "TIMEOUT"
    assert page.run_summary.failed_count == 1
    assert "raw_output" not in page.model_dump_json()


def test_pers09_event_automatic_result_never_requires_raw_model_output() -> None:
    result = EventAutomaticResultView(
        signal_id=UUID("019b0000-0000-7000-8000-000000000902"),
        result_type="AI_PROCESSING_FAILED",
        title="桥梁巡检案例",
        original_url="https://example.test/item",
        failure_reason_codes=["INVALID_JSON_OR_SCHEMA"],
    )

    assert result.result_type == "AI_PROCESSING_FAILED"
    assert result.judgment is None
    assert "raw_output" not in result.model_dump_json()
