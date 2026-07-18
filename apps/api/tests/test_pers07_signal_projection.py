from datetime import UTC, datetime
from uuid import UUID

from srbg_api.publication.personal_signals import (
    PersonalSignalInput,
    build_personal_signal_projections,
)

EVENT_ID = UUID("019b0000-0000-7000-8000-000000000001")
ITEM_ID = UUID("019b0000-0000-7000-8000-000000000002")
VERSION_ID = UUID("019b0000-0000-7000-8000-000000000003")
JUDGMENT_ID = UUID("019b0000-0000-7000-8000-000000000004")


def _input(status: str, *, payload: dict | None = None) -> PersonalSignalInput:
    return PersonalSignalInput(
        event_id=EVENT_ID,
        item_id=ITEM_ID,
        document_version_id=VERSION_ID,
        title="桥梁智能巡检案例",
        original_url="https://example.com/case",
        source_name="公开来源",
        first_discovered_at=datetime(2026, 7, 18, tzinfo=UTC),
        activity_at=datetime(2026, 7, 18, tzinfo=UTC),
        evidence_facts=[
            {
                "claim_id": "019b0000-0000-7000-8000-000000000101",
                "field_name": "title",
                "value": "桥梁智能巡检案例",
                "evidence": [],
            }
        ],
        judgment_version_id=JUDGMENT_ID,
        judgment_status=status,
        judgment_payload=payload,
        failure_reason_codes=("INVALID_JSON_OR_SCHEMA",),
    )


def test_verified_judgment_and_fact_have_independent_signal_cards() -> None:
    result = build_personal_signal_projections(
        _input(
            "AI_JUDGMENT",
            payload={
                "why_worth_attention": "可能提升巡检效率",
                "potential_industry_impacts": [],
                "potential_engineering_scenarios": ["桥梁巡检"],
                "current_limitations": [],
                "questions_to_verify": [],
                "used_claim_ids": ["019b0000-0000-7000-8000-000000000101"],
            },
        )
    )
    assert [signal.result_type for signal in result] == ["EVIDENCE_FACT", "AI_JUDGMENT"]
    assert result[0].signal_id != result[1].signal_id
    assert result[0].search_surface == "PRIMARY"
    assert result[1].search_surface == "PRIMARY"
    assert result[0].daily_section == "EVIDENCE_FACTS"
    assert result[1].daily_section is None


def test_unverified_ai_is_isolated_and_keeps_structured_reason_and_link() -> None:
    result = build_personal_signal_projections(
        _input("UNVERIFIED_AI", payload={"why_worth_attention": "候选判断"})
    )[-1]
    assert result.result_type == "UNVERIFIED_AI"
    assert result.search_surface == "UNVERIFIED"
    assert result.daily_section == "UNVERIFIED_AI"
    assert result.payload["original_url"] == "https://example.com/case"
    assert result.payload["failure_reason_codes"] == ["INVALID_JSON_OR_SCHEMA"]


def test_processing_failure_never_projects_raw_provider_text() -> None:
    failure = build_personal_signal_projections(
        _input(
            "AI_PROCESSING_FAILED",
            payload={"raw_output": "malformed provider text must not escape"},
        )
    )[-1]
    assert failure.result_type == "AI_PROCESSING_FAILED"
    assert failure.search_surface is None
    assert failure.daily_section is None
    assert "raw_output" not in failure.payload
    assert "malformed provider text" not in str(failure.payload)
