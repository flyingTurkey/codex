import asyncio
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest
from redis.asyncio import from_url
from sqlalchemy import text
from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.scheduling.domain import HealthObservation
from srbg_api.scheduling.service import PostgresSchedulingService

pytestmark = pytest.mark.skipif(
    urlsplit(os.environ.get("SRBG_WORKER_DATABASE_URL", "")).hostname
    not in {"127.0.0.1", "localhost"},
    reason="requires the isolated PostgreSQL runner",
)


async def test_concurrent_claim_execution_lease_and_redis_rebuild_are_authoritative() -> None:
    first = PostgresSchedulingService(
        create_database_engine(Settings(database_url=os.environ["SRBG_WORKER_DATABASE_URL"]))
    )
    second = PostgresSchedulingService(
        create_database_engine(Settings(database_url=os.environ["SRBG_WORKER_DATABASE_URL"]))
    )
    now = datetime.now(UTC)
    try:
        claims = await asyncio.gather(first.claim_due(now=now), second.claim_due(now=now))
        claimed = [claim for claim in claims if claim is not None]
        assert len(claimed) == 1
        run = claimed[0]
        assert run is not None
        async with first._engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM fetch_run WHERE schedule_id IS NOT NULL")
                )
                == 1
            )

        await first.mark_dispatched(run.run_id, now=now)
        execution = await asyncio.gather(
            first.acquire_execution(source_id=run.source_id, run_id=run.run_id, now=now),
            second.acquire_execution(source_id=run.source_id, run_id=run.run_id, now=now),
        )
        assert execution.count(True) == 1

        async with first._engine.begin() as connection:
            await connection.execute(
                text("UPDATE fetch_run SET execution_lease_until=:expired WHERE id=:run"),
                {"run": run.run_id, "expired": now - timedelta(seconds=1)},
            )
        assert await second.acquire_execution(
            source_id=run.source_id,
            run_id=run.run_id,
            now=now,
        )

        async with first._engine.begin() as connection:
            await connection.execute(
                text(
                    """UPDATE fetch_schedule
                          SET daily_request_budget=1,requests_used=0,
                              budget_window_started_at=:now
                        WHERE source_id=:source"""
                ),
                {"source": run.source_id, "now": now},
            )
        reservations = await asyncio.gather(
            first.reserve_request(source_id=run.source_id, run_id=run.run_id, now=now),
            second.reserve_request(source_id=run.source_id, run_id=run.run_id, now=now),
        )
        assert reservations.count(True) == 1
        async with first._engine.connect() as connection:
            round17_accounting = bool(
                await connection.scalar(
                    text(
                        """SELECT EXISTS (
                               SELECT 1 FROM information_schema.columns
                                WHERE table_schema='public'
                                  AND table_name='fetch_run'
                                  AND column_name='request_count'
                           )"""
                    )
                )
            )
            assert (
                await connection.scalar(
                    text("SELECT requests_used FROM fetch_schedule WHERE source_id=:source"),
                    {"source": run.source_id},
                )
                == 1
            )
            if round17_accounting:
                assert (
                    await connection.scalar(
                        text("SELECT request_count FROM fetch_run WHERE id=:run"),
                        {"run": run.run_id},
                    )
                    == 1
                )

        assert await first.record_response_bytes(
            source_id=run.source_id,
            run_id=run.run_id,
            response_bytes=17,
        )

        await first.record_outcome(
            source_id=run.source_id,
            run_id=run.run_id,
            observation=HealthObservation(transport_succeeded=True),
            discovered_count=0,
            parsed_count=0,
            request_count=1,
            response_bytes=17,
            now=now,
        )
        async with first._engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT requests_used FROM fetch_schedule WHERE source_id=:source"),
                    {"source": run.source_id},
                )
                == 1
            )
            if round17_accounting:
                persisted = (
                    await connection.execute(
                        text(
                            "SELECT request_count,response_bytes FROM fetch_run WHERE id=:run"
                        ),
                        {"run": run.run_id},
                    )
                ).one()
                assert tuple(persisted) == (1, 17)
            assert (
                await connection.scalar(
                    text("SELECT bytes_used FROM fetch_schedule WHERE source_id=:source"),
                    {"source": run.source_id},
                )
                == 17
            )

        async with first._engine.begin() as connection:
            await connection.execute(
                text("UPDATE fetch_run SET status='DISPATCHED' WHERE id=:run"),
                {"run": run.run_id},
            )
        redis_url = os.environ.get("SRBG_REDIS_URL", "redis://127.0.0.1:6379/0")
        recovery_cache = from_url(redis_url.rsplit("/", 1)[0] + "/15")
        try:
            await recovery_cache.set("round16:disposable-queue-marker", "lost")
            await recovery_cache.flushdb()
        finally:
            await recovery_cache.aclose()
        rebuilt = await second.pending_messages()
        assert [(item.source_id, item.run_id) for item in rebuilt] == [(run.source_id, run.run_id)]

        async with first._engine.begin() as connection:
            await connection.execute(
                text(
                    """UPDATE fetch_schedule SET status='PAUSED',next_run_at=:now,
                           leased_until=NULL WHERE source_id=:source"""
                ),
                {"source": run.source_id, "now": now},
            )
            await connection.execute(
                text(
                    """UPDATE fetch_run SET status='DISPATCHED',
                           execution_lease_until=:expired WHERE id=:run"""
                ),
                {"run": run.run_id, "expired": now - timedelta(seconds=1)},
            )
        assert await second.claim_due(now=now) is None
        assert not await second.acquire_execution(
            source_id=run.source_id,
            run_id=run.run_id,
            now=now,
        )
        assert await second.cancel_ineligible(
            source_id=run.source_id,
            run_id=run.run_id,
            now=now,
        )
        async with first._engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT status FROM fetch_run WHERE id=:run"), {"run": run.run_id}
                )
                == "CANCELLED"
            )
    finally:
        await first.close()
        await second.close()
