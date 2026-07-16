import asyncio
import os
import threading
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from celery.contrib.testing.worker import start_worker
from celery.signals import task_postrun
from sqlalchemy import text
from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.identifiers import uuid7
from srbg_worker.app import celery_app


def test_beat_only_wakes_database_dispatcher_for_source_fetches() -> None:
    source_entries = {
        name: value
        for name, value in celery_app.conf.beat_schedule.items()
        if "source" in name or "discover" in name or "dispatch" in name
    }
    assert source_entries == {
        "dispatch-due-source-schedules": {
            "task": "srbg.schedules.dispatch",
            "schedule": 30.0,
        }
    }
    assert celery_app.conf.task_routes["srbg.source.fetch"] == {"queue": "parser"}


def test_real_celery_duplicate_delivery_has_one_database_execution_lease() -> None:
    database_url = os.environ.get("SRBG_DATABASE_URL", "")
    database_name = urlsplit(database_url.replace("postgresql+asyncpg", "postgresql", 1)).path
    if not database_name.removeprefix("/").startswith("srbg_it_"):
        pytest.skip("requires the disposable Round 16 integration database")
    run_id, source_id = asyncio.run(_seed_duplicate_delivery_run())
    queue = f"round16-{run_id}"
    expected_ids = {str(uuid7()), str(uuid7())}
    completed_ids: set[str] = set()
    completed = threading.Event()

    def completed_task(*, task_id: str | None = None, **_: object) -> None:
        if task_id in expected_ids:
            completed_ids.add(task_id)
            if completed_ids == expected_ids:
                completed.set()

    task_postrun.connect(completed_task, weak=False)
    try:
        with start_worker(
            celery_app,
            pool="solo",
            queues=(queue,),
            perform_ping_check=False,
            loglevel="WARNING",
        ):
            for task_id in expected_ids:
                celery_app.send_task(
                    "srbg.source.fetch",
                    kwargs={"source_id": str(source_id), "run_id": str(run_id)},
                    queue=queue,
                    task_id=task_id,
                    ignore_result=True,
                )
            assert completed.wait(timeout=10), "both duplicate Celery messages must complete"
    finally:
        task_postrun.disconnect(completed_task)
    assert completed_ids == expected_ids
    assert asyncio.run(_attempt_count(run_id)) == 1


async def _seed_duplicate_delivery_run() -> tuple[UUID, UUID]:
    engine = create_database_engine(Settings())
    run_id = uuid7()
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            source_id = await connection.scalar(
                text("SELECT source_id FROM fetch_schedule LIMIT 1")
            )
            if not isinstance(source_id, UUID):
                raise AssertionError("round16 integration source is missing")
            await connection.execute(
                text(
                    """UPDATE fetch_schedule SET status='ACTIVE',circuit_state='CLOSED',
                           requests_used=0,bytes_used=0,leased_until=NULL WHERE source_id=:source"""
                ),
                {"source": source_id},
            )
            await connection.execute(
                text(
                    """INSERT INTO fetch_run
                       (id,source_connector_id,trigger,status,started_at,discovered_count,
                        fetched_count,failed_count,request_id,execution_domain,source_id,
                        schedule_id,policy_version_id,connector_config_version_id,
                        idempotency_key,attempt_count)
                       SELECT :run,NULL,'SCHEDULED','DISPATCHED',:now,0,0,0,:request,
                              'PRODUCTION',fs.source_id,fs.id,s.current_policy_version_id,
                              s.current_connector_config_version_id,:idempotency,0
                         FROM fetch_schedule fs JOIN source s ON s.id=fs.source_id
                        WHERE fs.source_id=:source"""
                ),
                {
                    "run": run_id,
                    "now": now,
                    "request": f"round16-celery:{run_id}",
                    "idempotency": f"round16-celery:{run_id}",
                    "source": source_id,
                },
            )
        return run_id, source_id
    finally:
        await engine.dispose()


async def _attempt_count(run_id: UUID) -> int:
    engine = create_database_engine(Settings())
    try:
        async with engine.connect() as connection:
            value = await connection.scalar(
                text("SELECT attempt_count FROM fetch_run WHERE id=:run"), {"run": run_id}
            )
        return int(value)
    finally:
        await engine.dispose()
