from datetime import UTC, datetime
from inspect import getsource
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_contracts import OwnerRelationshipCorrectionRequest


def test_new_pipeline_never_creates_claim_review_tasks() -> None:
    source = Path("apps/worker/src/srbg_worker/ai_content_preparation.py").read_text(
        encoding="utf-8"
    )
    assert "INSERT INTO review_task" not in source
    assert "'CLAIM_REVIEW'" not in source
    assert "AUTOMATED_EVIDENCE_GATE" in source


def test_publication_service_is_the_only_personal_projection_writer() -> None:
    repository_source = getsource(PostgresPublicationRepository)
    service_source = getsource(PublicationService)
    assert "INSERT INTO personal_content_projection" in repository_source
    assert "process_personal_content_once" in service_source
    for root in (Path("apps/worker/src"), Path("apps/api/src")):
        for path in root.rglob("*.py"):
            if path.as_posix().endswith("publication/repository.py"):
                continue
            source = path.read_text(encoding="utf-8")
            assert "INSERT INTO personal_content_projection" not in source, path


@pytest.mark.asyncio
async def test_personal_projection_and_owner_correction_cross_publication_service() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    repository = AsyncMock()
    repository.process_personal_content_once.return_value = True
    repository.correct_automatic_relationship.return_value = {"status": "WITHDRAWN"}
    service = PublicationService(repository=repository, gate=object(), now=lambda: now)  # type: ignore[arg-type]

    assert await service.process_personal_content_once() is True
    repository.process_personal_content_once.assert_awaited_once_with(processed_at=now)

    event_id = UUID("019d0000-0000-7000-8000-000000002610")
    owner_id = UUID("019d0000-0000-7000-8000-000000002611")
    payload = OwnerRelationshipCorrectionRequest(
        command_id=UUID("019d0000-0000-7000-8000-000000002613"),
        action="KEEP_INDEPENDENT",
        member_item_ids=[
            UUID("019d0000-0000-7000-8000-000000002612"),
            UUID("019d0000-0000-7000-8000-000000002614"),
        ],
        reason="owner correction backed by the current evidence set",
    )
    assert await service.correct_automatic_relationship(
        event_id, payload=payload, owner_id=owner_id
    ) == {"status": "WITHDRAWN"}
    repository.correct_automatic_relationship.assert_awaited_once_with(
        event_id=event_id,
        payload=payload,
        owner_id=owner_id,
        corrected_at=now,
    )
