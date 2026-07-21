from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from srbg_api.intelligence_v2.gold_calibration import AutoPassCalibrationGrant
from srbg_api.publication.service import PublicationService

EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000011")
VERSION_ID = UUID("019f7c00-0000-7000-8000-000000000012")
OUTBOX_ID = UUID("019f7c00-0000-7000-8000-000000000013")
NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _grant(*, corpus_version: str) -> AutoPassCalibrationGrant:
    return AutoPassCalibrationGrant(
        threshold_bps=9300,
        corpus_version=corpus_version,
        rule_version="intelligence-v2-qualification-1.0.0",
        model_id="deepseek-v4-flash",
        prompt_version="ai01-classify-v1",
        prediction_seal_sha256="e" * 64,
        fact_sha256="f" * 64,
    )


@pytest.mark.asyncio
async def test_v2_projection_refresh_accepts_only_authoritative_identifiers() -> None:
    repository = AsyncMock()
    service = PublicationService(repository=repository, gate=object(), now=lambda: NOW)  # type: ignore[arg-type]

    await service.refresh_v2_projection(
        event_id=EVENT_ID,
        document_version_id=VERSION_ID,
    )

    repository.refresh_v2_projection.assert_awaited_once_with(
        event_id=EVENT_ID,
        document_version_id=VERSION_ID,
        projected_at=NOW,
    )


@pytest.mark.asyncio
async def test_review_reprocessing_accepts_only_outbox_identifier() -> None:
    repository = AsyncMock()
    service = PublicationService(repository=repository, gate=object(), now=lambda: NOW)  # type: ignore[arg-type]

    await service.process_v2_review_reprocessing(outbox_id=OUTBOX_ID)

    repository.process_v2_review_reprocessing.assert_awaited_once_with(
        outbox_id=OUTBOX_ID,
        processed_at=NOW,
    )


@pytest.mark.asyncio
async def test_publication_calibration_read_fails_closed_for_a_retired_fact() -> None:
    repository = AsyncMock()
    repository.load_auto_pass_calibration.return_value = _grant(
        corpus_version="owner-gold-2026-07-20.3"
    )
    service = PublicationService(repository=repository, gate=object(), now=lambda: NOW)  # type: ignore[arg-type]

    grant = await service.load_auto_pass_calibration(
        corpus_version="owner-gold-2026-07-20.4",
        rule_version="intelligence-v2-qualification-1.0.0",
        model_id="deepseek-v4-flash",
        prompt_version="ai01-classify-v1",
    )

    assert grant is None
