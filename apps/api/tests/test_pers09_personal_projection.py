from datetime import UTC, datetime
from uuid import UUID

from srbg_api.publication.personal_signals import (
    PersonalSignalInput,
    build_personal_signal_projections,
)


def _input(status: str) -> PersonalSignalInput:
    now = datetime.now(UTC)
    return PersonalSignalInput(
        event_id=UUID("019b0000-0000-7000-8000-000000000901"),
        item_id=UUID("019b0000-0000-7000-8000-000000000902"),
        document_version_id=UUID("019b0000-0000-7000-8000-000000000903"),
        title="桥梁巡检案例",
        original_url="https://example.test/item",
        source_name="公开来源",
        first_discovered_at=now,
        activity_at=now,
        evidence_facts=[{"claim_id": str(UUID(int=1))}],
        judgment_status=status,
        failure_reason_codes=("INVALID_JSON_OR_SCHEMA",),
    )


def test_pers09_verified_ai_has_an_explicit_daily_section() -> None:
    result = build_personal_signal_projections(_input("AI_JUDGMENT"))[-1]

    assert result.search_surface == "PRIMARY"
    assert result.daily_section == "AI_JUDGMENTS"


def test_pers09_processing_failure_is_searchable_only_as_safe_status() -> None:
    result = build_personal_signal_projections(_input("AI_PROCESSING_FAILED"))[-1]

    assert result.search_surface == "UNVERIFIED"
    assert result.daily_section == "AI_PROCESSING_FAILURES"
    assert result.payload["failure_reason_codes"] == ["INVALID_JSON_OR_SCHEMA"]
    assert "judgment" not in result.payload
    assert "raw_output" not in result.payload
