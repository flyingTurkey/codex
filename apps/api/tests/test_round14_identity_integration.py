import asyncio
import os
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import text
from srbg_api.config import get_settings
from srbg_api.database import create_publication_engine
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_api.safety_regulations.query import PostgresIntelligenceQueryService

pytestmark = pytest.mark.skipif(
    os.environ.get("SRBG_RUN_SAFETY_INTEGRATION") != "1",
    reason="run through make phase2-round14-test",
)

FIRST = UUID("019b0000-0000-7000-8000-000000001421")
SECOND = UUID("019b0000-0000-7000-8000-000000001422")
SUBMITTER = UUID("019b0000-0000-7000-8000-000000001423")
REVIEWER = UUID("019b0000-0000-7000-8000-000000001424")
NOW = datetime(2026, 7, 15, tzinfo=UTC)
SPLIT_REQUEST = UUID("019b0000-0000-7000-8000-000000001425")


def test_merge_and_rollback_preserve_redirect_audit_and_versions() -> None:
    asyncio.run(_exercise_merge_and_rollback())


async def _exercise_merge_and_rollback() -> None:
    get_settings.cache_clear()
    repository = PostgresPublicationRepository(create_publication_engine(get_settings()))
    service = PublicationService(
        repository=repository, gate=cast(Any, object()), now=lambda: NOW
    )
    try:
        async with repository._engine.begin() as connection:
            for event_id, title in ((FIRST, "canonical"), (SECOND, "alias")):
                await connection.execute(
                    text(
                        """
                        INSERT INTO event
                          (id,event_type,title,subject_names,confirmation_status,created_at,updated_at)
                        VALUES (:id,'DIGITAL_PROJECT',:title,'[]'::jsonb,'PENDING_REVIEW',:now,:now)
                        """
                    ),
                    {"id": event_id, "title": title, "now": NOW},
                )
        merge = await service.request_event_identity_change(
            operation="MERGE",
            event_ids=[FIRST, SECOND],
            canonical_event_id=FIRST,
            allocations={},
            submitted_by=SUBMITTER,
            reason="exact authority identity",
        )
        await service.decide_event_identity_change(
            merge, approve=True, reviewer_id=REVIEWER, reason="reviewed exact identity"
        )
        async with repository._engine.connect() as connection:
            merged = (
                await connection.execute(
                    text("SELECT status,canonical_event_id,version FROM event WHERE id=:id"),
                    {"id": SECOND},
                )
            ).mappings().one()
            assert merged["status"] == "MERGED"
            assert merged["canonical_event_id"] == FIRST
            assert merged["version"] == 2

        rollback = await service.request_event_identity_change(
            operation="ROLLBACK",
            event_ids=[FIRST, SECOND],
            canonical_event_id=None,
            allocations={},
            submitted_by=SUBMITTER,
            reason="rollback reviewed merge",
        )
        await service.decide_event_identity_change(
            rollback, approve=True, reviewer_id=REVIEWER, reason="rollback approved"
        )
        async with repository._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT id,status,canonical_event_id,version FROM event "
                            "WHERE id=ANY(CAST(:ids AS uuid[])) ORDER BY id"
                        ),
                        {"ids": [FIRST, SECOND]},
                    )
                ).mappings()
            )
            assert all(row["status"] == "ACTIVE" for row in rows)
            assert all(row["canonical_event_id"] == row["id"] for row in rows)
            assert all(row["version"] >= 2 for row in rows)
            audit_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM audit_log "
                    "WHERE target_type='event_identity_change_request'"
                )
            )
            assert int(audit_count or 0) == 4

        async with repository._engine.begin() as connection:
            await connection.execute(
                text("UPDATE event SET status='SPLIT',version=version+1 WHERE id=:id"),
                {"id": FIRST},
            )
            await connection.execute(
                text(
                    "INSERT INTO event_identity_change_request "
                    "(id,operation,status,reason,submitted_by,created_at) "
                    "VALUES (:id,'SPLIT','APPLIED','reviewed split',:actor,:now)"
                ),
                {"id": SPLIT_REQUEST, "actor": SUBMITTER, "now": NOW},
            )
            for target, role in ((FIRST, "SOURCE"), (SECOND, "CHILD")):
                await connection.execute(
                    text(
                        "INSERT INTO event_identity_change_target "
                        "(request_id,event_id,target_role) VALUES (:request,:event,:role)"
                    ),
                    {"request": SPLIT_REQUEST, "event": target, "role": role},
                )
        split_landing = await PostgresIntelligenceQueryService(repository._engine).get_event(FIRST)
        assert split_landing.event_status.value == "SPLIT"
        assert split_landing.split_child_event_ids == [SECOND]
    finally:
        await service.close()
        get_settings.cache_clear()
