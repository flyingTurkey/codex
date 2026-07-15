from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from srbg_api.publication.service import PublicationDenied, PublicationService

NOW = datetime(2026, 7, 15, tzinfo=UTC)
SUBMITTER = UUID("019b0000-0000-7000-8000-000000001410")
REVIEWER = UUID("019b0000-0000-7000-8000-000000001411")
FIRST = UUID("019b0000-0000-7000-8000-000000001412")
SECOND = UUID("019b0000-0000-7000-8000-000000001413")
REQUEST = UUID("019b0000-0000-7000-8000-000000001414")


class RecordingRepository:
    requested: dict[str, Any] | None = None
    decided: dict[str, Any] | None = None

    async def request_event_identity_change(self, **values: Any) -> UUID:
        self.requested = values
        return REQUEST

    async def decide_event_identity_change(self, **values: Any) -> None:
        self.decided = values


@pytest.mark.asyncio
async def test_merge_and_rollback_commands_cross_publication_service() -> None:
    repository = RecordingRepository()
    service = PublicationService(
        repository=cast(Any, repository), gate=cast(Any, object()), now=lambda: NOW
    )

    request_id = await service.request_event_identity_change(
        operation="MERGE",
        event_ids=[FIRST, SECOND],
        canonical_event_id=FIRST,
        allocations={},
        submitted_by=SUBMITTER,
        reason="same exact authority identity",
    )
    await service.decide_event_identity_change(
        request_id, approve=True, reviewer_id=REVIEWER, reason="evidence reviewed"
    )

    assert request_id == REQUEST
    assert repository.requested is not None
    assert repository.requested["operation"] == "MERGE"
    assert repository.decided is not None
    assert repository.decided["approve"] is True


@pytest.mark.asyncio
async def test_split_requires_an_explicit_item_allocation() -> None:
    service = PublicationService(
        repository=cast(Any, RecordingRepository()),
        gate=cast(Any, object()),
        now=lambda: NOW,
    )

    with pytest.raises(PublicationDenied, match="EVENT_SPLIT_ALLOCATION_REQUIRED"):
        await service.request_event_identity_change(
            operation="SPLIT",
            event_ids=[FIRST, SECOND],
            canonical_event_id=FIRST,
            allocations={},
            submitted_by=SUBMITTER,
            reason="documents describe different events",
        )
