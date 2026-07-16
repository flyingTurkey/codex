import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from sqlalchemy import text
from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.operations.replays import claim_replay, finish_replay
from srbg_api.operations.service import PostgresOperationsService
from srbg_contracts import ReplayRequest

pytestmark = pytest.mark.skipif(
    urlsplit(os.environ.get("SRBG_WORKER_DATABASE_URL", "")).hostname
    not in {"127.0.0.1", "localhost"},
    reason="requires the isolated PostgreSQL runner",
)


async def test_replay_lease_recovers_and_disabled_ai_is_blocked_without_payload() -> None:
    worker = create_database_engine(Settings(database_url=os.environ["SRBG_WORKER_DATABASE_URL"]))
    operations = PostgresOperationsService(create_database_engine(Settings()))
    now = datetime.now(UTC)
    failed_id = UUID("019b1600-0000-7000-8000-000000000301")
    ai_failed_id = UUID("019b1600-0000-7000-8000-000000000302")
    actor = UUID("019b1600-0000-7000-8000-000000000303")
    try:
        async with worker.begin() as connection:
            await connection.execute(
                text(
                    """INSERT INTO failed_task
                       (id,task_kind,execution_id,replayable,error_code,priority,
                        attempts,failed_at,reconstruction_status)
                       VALUES (:id,'PUBLICATION_OUTBOX',:id,true,'TEST',9,1,:now,
                               'REPLAYABLE')"""
                ),
                {"id": failed_id, "now": now},
            )
        replay = await operations.request_replay(
            ReplayRequest(
                failed_task_id=failed_id,
                reason="round16 lease recovery approval",
                priority=9,
            ),
            actor_id=actor,
            idempotency_key="round16-replay-lease",
        )
        claimed = await claim_replay(worker, now=now)
        assert claimed is not None and claimed.id == replay.id
        assert await claim_replay(worker, now=now) is None
        async with worker.begin() as connection:
            await connection.execute(
                text("UPDATE replay_request SET leased_until=:expired WHERE id=:id"),
                {"id": replay.id, "expired": now - timedelta(seconds=1)},
            )
        recovered = await claim_replay(worker, now=now)
        assert recovered is not None and recovered.id == replay.id
        assert recovered.lease_token != claimed.lease_token
        await finish_replay(worker, recovered, succeeded=True, now=now)

        async with worker.begin() as connection:
            await connection.execute(
                text(
                    """INSERT INTO failed_task
                       (id,task_kind,execution_id,replayable,error_code,priority,
                        attempts,failed_at,reconstruction_status)
                       VALUES (:id,'AI',:id,true,'TEST',8,1,:now,'REPLAYABLE')"""
                ),
                {"id": ai_failed_id, "now": now},
            )
        blocked = await operations.request_replay(
            ReplayRequest(
                failed_task_id=ai_failed_id,
                reason="round16 verify disabled ai policy",
                priority=8,
            ),
            actor_id=actor,
            idempotency_key="round16-replay-ai",
        )
        assert await claim_replay(worker, now=now) is None
        async with worker.connect() as connection:
            status, reason = (
                await connection.execute(
                    text("SELECT status,outcome_reason FROM replay_request WHERE id=:id"),
                    {"id": blocked.id},
                )
            ).one()
        assert (status, reason) == ("BLOCKED", "AI_DISABLED")
    finally:
        await worker.dispose()
        await operations.close()
