from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from srbg_api.publication.service import PublicationService
from srbg_contracts import DailyReport

REPORT_ID = UUID("019b0000-0000-7000-8000-000000001003")
ACTOR_ID = UUID("019b0000-0000-7000-8000-000000009001")
NOW = datetime(2026, 7, 15, tzinfo=UTC)


class FakeGate:
    pass


class FakeRepository:
    def __init__(self) -> None:
        self.created: list[tuple[date, UUID, str, datetime]] = []
        self.published: list[tuple[UUID, UUID, str, datetime]] = []

    async def create_daily_draft(self, *, report_date, actor_id, idempotency_key, created_at):
        self.created.append((report_date, actor_id, idempotency_key, created_at))
        return _report("DRAFT")

    async def publish_daily_report(self, *, report_id, reviewer_id, idempotency_key, published_at):
        self.published.append((report_id, reviewer_id, idempotency_key, published_at))
        return _report("PUBLISHED")


def _report(status: str) -> DailyReport:
    return DailyReport(
        id=REPORT_ID,
        report_date=date(2026, 7, 15),
        status=status,
        snapshot_at=NOW,
        published_at=NOW if status == "PUBLISHED" else None,
        requires_regeneration=False,
        sections=[],
    )


@pytest.mark.asyncio
async def test_daily_draft_and_publish_enter_through_publication_service() -> None:
    repository = FakeRepository()
    service = PublicationService(repository=repository, gate=FakeGate(), now=lambda: NOW)  # type: ignore[arg-type]

    draft = await service.create_daily_draft(
        report_date=date(2026, 7, 15), actor_id=ACTOR_ID, idempotency_key="daily-draft-0001"
    )
    published = await service.publish_daily_report(
        REPORT_ID, reviewer_id=ACTOR_ID, idempotency_key="daily-publish-0001"
    )

    assert draft.status == "DRAFT"
    assert published.status == "PUBLISHED"
    assert repository.created == [(date(2026, 7, 15), ACTOR_ID, "daily-draft-0001", NOW)]
    assert repository.published == [(REPORT_ID, ACTOR_ID, "daily-publish-0001", NOW)]
