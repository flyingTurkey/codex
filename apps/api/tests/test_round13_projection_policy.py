from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from srbg_api.internal_projection.domain import ProjectionInput, decide_projection
from srbg_api.publication.service import PublicationService


def test_r3_pending_official_is_metadata_only_and_excluded_from_distribution() -> None:
    decision = decide_projection(
        ProjectionInput(
            publication_risk_tier="R3",
            review_status="PENDING",
            publication_status=None,
            official_source=True,
        )
    )
    assert decision.level == "METADATA_ONLY"
    assert decision.allowed_surfaces == frozenset({"FEED", "EVENT", "TITLE_SEARCH"})


def test_r4_is_never_projected() -> None:
    decision = decide_projection(
        ProjectionInput(
            publication_risk_tier="R4",
            review_status="APPROVED",
            publication_status="PUBLISHED",
            official_source=True,
        )
    )
    assert decision.level == "NONE"
    assert not decision.allowed_surfaces


def test_severity_cannot_grant_projection() -> None:
    low = ProjectionInput("R4", "APPROVED", "PUBLISHED", True, "LOW")
    critical = ProjectionInput("R4", "APPROVED", "PUBLISHED", True, "CRITICAL")
    assert decide_projection(low) == decide_projection(critical)


@pytest.mark.asyncio
async def test_shadow_build_is_owned_by_publication_service() -> None:
    expected = object()
    called: dict[str, object] = {}
    now = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)

    class Repository:
        async def build_internal_projection(
            self, *, actor_id: UUID, generated_at: datetime
        ) -> object:
            called.update(actor_id=actor_id, generated_at=generated_at)
            return expected

    actor_id = UUID("019b0000-0000-7000-8000-000000001313")
    service = PublicationService(
        repository=cast(Any, Repository()),
        gate=cast(Any, object()),
        now=lambda: now,
    )

    assert await service.build_internal_projection(actor_id=actor_id) is expected
    assert called == {"actor_id": actor_id, "generated_at": now}


def test_shadow_backfill_cli_uses_publication_service_boundary() -> None:
    source = Path("scripts/backfill_round13_projection.py").read_text(encoding="utf-8")
    assert "PublicationService" in source
    assert ".build_internal_projection(" in source
