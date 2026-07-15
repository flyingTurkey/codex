from datetime import UTC, datetime
from uuid import UUID

from srbg_contracts import (
    ContentSeverity,
    ProjectionLevel,
    PublicationRiskTier,
    PublishedEventDetailV1,
    PublishedEventSummaryV1,
)


def test_round13_enums_are_independent() -> None:
    assert [value.value for value in PublicationRiskTier] == ["R1", "R2", "R3", "R4"]
    assert [value.value for value in ContentSeverity] == [
        "UNASSESSED",
        "LOW",
        "MODERATE",
        "HIGH",
        "CRITICAL",
    ]
    assert [value.value for value in ProjectionLevel] == ["NONE", "METADATA_ONLY", "FULL"]


def test_r3_published_event_contract_contains_only_metadata() -> None:
    summary = PublishedEventSummaryV1(
        id=UUID("019b0000-0000-7000-8000-000000001301"),
        publication_revision_id=None,
        projection_version="1.0.0",
        generation=1,
        domain="SAFETY",
        content_type="SAFETY_REGULATION",
        title="官方题录",
        source_name="官方来源",
        source_published_at=None,
        first_discovered_at=datetime(2026, 7, 15, tzinfo=UTC),
        original_url="https://example.test/official",
        review_status="PENDING",
        discovery_status="MACHINE_DISCOVERED",
        fact_review_status="PENDING_HUMAN_REVIEW",
        publication_risk_tier="R3",
        content_severity="UNASSESSED",
        projection_level="METADATA_ONLY",
        one_sentence_fact=None,
        type_summary=None,
    )
    detail = PublishedEventDetailV1(summary=summary, claims=[], evidence=[])
    assert detail.model_dump(mode="json", exclude_none=True)["claims"] == []
    assert "one_sentence_fact" not in summary.model_dump(mode="json", exclude_none=True)
