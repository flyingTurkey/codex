from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID

from srbg_api.safety_cases.candidates import (
    EventCandidateContext,
    EventCandidateRecord,
    SafetyEventCandidateService,
    _identity_from_row,
)
from srbg_api.safety_cases.domain import EventIdentity

EVENT_ID = UUID("019b0000-0000-7000-8000-000000000451")
ITEM_ID = UUID("019b0000-0000-7000-8000-000000000452")
CANDIDATE_ID = UUID("019b0000-0000-7000-8000-000000000454")


class FakeCandidateStore:
    def __init__(
        self,
        *,
        existing: EventIdentity,
        incoming: EventIdentity,
        confirmation_status: str = "CONFIRMED",
        member_count: int = 1,
        candidate_count: int = 0,
    ) -> None:
        self.existing = existing
        self.incoming = incoming
        self.confirmation_status = confirmation_status
        self.member_count = member_count
        self.candidate_count = candidate_count
        self.saved: list[EventCandidateRecord] = []

    async def close(self) -> None:
        return None

    async def create_candidate(
        self,
        *,
        event_id: UUID,
        item_id: UUID,
        build: Callable[[EventCandidateContext, EventIdentity], EventCandidateRecord | None],
    ) -> UUID | None:
        assert event_id == EVENT_ID
        assert item_id == ITEM_ID
        candidate = build(
            EventCandidateContext(
                identity=self.existing,
                confirmation_status=self.confirmation_status,
                member_count=self.member_count,
                candidate_count=self.candidate_count,
            ),
            self.incoming,
        )
        if candidate is None:
            return None
        self.saved.append(candidate)
        return CANDIDATE_ID


def _identity(
    *,
    region: str = "广东省梅州市大埔县",
    project: str = "梅大高速东延线K11+900～K11+950",  # noqa: RUF001
) -> EventIdentity:
    return EventIdentity(
        occurred_on=date(2024, 5, 1),
        region=region,
        project=project,
        subjects=("广东梅大高速公路有限公司梅大分公司",),
        accident_type="ROADBED_COLLAPSE",
    )


async def test_matching_service_persists_explainable_human_review_candidate() -> None:
    store = FakeCandidateStore(existing=_identity(), incoming=_identity())
    service = SafetyEventCandidateService(store)

    candidate_id = await service.generate_candidate(
        event_id=EVENT_ID,
        item_id=ITEM_ID,
    )

    assert candidate_id == CANDIDATE_ID
    assert store.saved == [
        EventCandidateRecord(
            event_id=EVENT_ID,
            item_id=ITEM_ID,
            score=100,
            matched_dimensions={
                "date": 25,
                "region": 20,
                "project": 30,
                "subject": 15,
                "accident_type": 10,
            },
            algorithm_version="safety-event-match-v1",
            requires_human_review=True,
        )
    ]


async def test_matching_service_does_not_persist_below_threshold() -> None:
    store = FakeCandidateStore(
        existing=_identity(),
        incoming=_identity(region="另一地区", project="另一项目"),
    )
    service = SafetyEventCandidateService(store)

    candidate_id = await service.generate_candidate(
        event_id=EVENT_ID,
        item_id=ITEM_ID,
    )

    assert candidate_id is None
    assert store.saved == []


async def test_first_item_generates_candidate_for_empty_provisional_event() -> None:
    empty_event = EventIdentity(
        occurred_on=None,
        region=None,
        project=None,
        subjects=(),
        accident_type=None,
    )
    store = FakeCandidateStore(
        existing=empty_event,
        incoming=_identity(),
        confirmation_status="PENDING_REVIEW",
        member_count=0,
    )

    candidate_id = await SafetyEventCandidateService(store).generate_candidate(
        event_id=EVENT_ID,
        item_id=ITEM_ID,
    )

    assert candidate_id == CANDIDATE_ID
    assert store.saved[0].score == 100
    assert set(store.saved[0].matched_dimensions) == {
        "date",
        "region",
        "project",
        "subject",
        "accident_type",
    }
    assert store.saved[0].requires_human_review is True


async def test_empty_confirmed_event_never_self_matches_unrelated_item() -> None:
    empty_event = EventIdentity(
        occurred_on=None,
        region=None,
        project=None,
        subjects=(),
        accident_type=None,
    )
    store = FakeCandidateStore(
        existing=empty_event,
        incoming=_identity(),
        confirmation_status="CONFIRMED",
        member_count=1,
    )

    candidate_id = await SafetyEventCandidateService(store).generate_candidate(
        event_id=EVENT_ID,
        item_id=ITEM_ID,
    )

    assert candidate_id is None
    assert store.saved == []


async def test_pending_event_with_an_existing_proposal_never_self_matches_second_item() -> None:
    empty_event = EventIdentity(
        occurred_on=None,
        region=None,
        project=None,
        subjects=(),
        accident_type=None,
    )
    store = FakeCandidateStore(
        existing=empty_event,
        incoming=_identity(),
        confirmation_status="PENDING_REVIEW",
        member_count=0,
        candidate_count=1,
    )

    candidate_id = await SafetyEventCandidateService(store).generate_candidate(
        event_id=EVENT_ID,
        item_id=ITEM_ID,
    )

    assert candidate_id is None
    assert store.saved == []


def test_candidate_date_uses_asia_shanghai_incident_day_at_utc_boundary() -> None:
    identity = _identity_from_row(  # pyright: ignore[reportPrivateUsage]
        {
            "occurred_at": datetime(2024, 4, 30, 17, 57, tzinfo=UTC),
            "region_name": "广东省",
            "project_name": "梅大高速",
            "subject_names": [],
            "accident_type": "ROADBED_COLLAPSE",
        }
    )

    assert identity.occurred_on == date(2024, 5, 1)
