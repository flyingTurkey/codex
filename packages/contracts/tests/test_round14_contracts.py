from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import EventDetail, EventStatus, EventSummary, EventType


def test_event_summary_has_explicit_stable_identity_and_type() -> None:
    event_id = UUID("019b0000-0000-7000-8000-000000001401")
    summary = EventSummary(
        id=event_id,
        publication_revision_id=None,
        domain="DIGITAL",
        content_type="DIGITAL_CASE",
        title="数字孪生项目",
        source_name="测试来源",
        source_published_at=None,
        first_discovered_at=datetime(2026, 7, 15, tzinfo=UTC),
        activity_at=datetime(2026, 7, 15, tzinfo=UTC),
        original_url="https://example.test/event",
        review_status="APPROVED",
        event_type=EventType.DIGITAL_PROJECT,
        event_status=EventStatus.ACTIVE,
        canonical_event_id=event_id,
        event_version=1,
    )
    assert summary.event_type is EventType.DIGITAL_PROJECT
    assert summary.canonical_event_id == summary.id


def test_event_detail_never_defaults_to_a_safety_incident() -> None:
    with pytest.raises(ValidationError):
        EventDetail(
            id=UUID("019b0000-0000-7000-8000-000000001401"),
            title="未指定类型",
            confirmed_facts=[],
            unverified_facts=[],
            timeline={"event_id": "019b0000-0000-7000-8000-000000001401", "items": []},
            relations=[],
            similar_scenario_tags=[],
            prevention_measure_tags=[],
        )
