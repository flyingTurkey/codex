import os
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from sqlalchemy import text
from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.operations.replays import claim_replay, finish_replay
from srbg_api.operations.service import PostgresOperationsService
from srbg_api.safety_regulations.query import PostgresIntelligenceQueryService
from srbg_contracts import ReplayRequest

FAILED_ID = UUID('019b0000-0000-7000-8000-000000001201')
TARGET_ID = UUID('019b0000-0000-7000-8000-000000001202')
ACTOR_ID = UUID('019b0000-0000-7000-8000-000000001203')

pytestmark = pytest.mark.skipif(
    urlsplit(os.environ.get('SRBG_DATABASE_URL', '')).hostname not in {'127.0.0.1', 'localhost'},
    reason='requires the isolated integration runner',
)


async def test_operations_overview_and_priority_replay_use_postgres_authority() -> None:
    engine = create_database_engine(Settings())
    service = PostgresOperationsService(engine)
    worker_engine = create_database_engine(
        Settings(database_url=os.environ['SRBG_WORKER_DATABASE_URL'])
    )
    now = datetime.now(UTC)
    async with worker_engine.begin() as connection:
        await connection.execute(
            text(
                """INSERT INTO failed_task
                   (id, task_kind, execution_id, replayable, error_code,
                    priority, attempts, failed_at)
                   VALUES (:id, 'PUBLICATION_OUTBOX', :execution_id, true,
                           'TEST_FAILURE', 5, 1, :now)"""
            ),
            {
                'id': FAILED_ID,
                'execution_id': TARGET_ID,
                'now': now,
            },
        )
    replay = await service.request_replay(
        ReplayRequest(
            failed_task_id=FAILED_ID,
            reason='integration recovery approval',
            priority=9,
        ),
        actor_id=ACTOR_ID,
        idempotency_key='round11-integration-replay',
    )
    assert replay.status == 'QUEUED'
    claimed = await claim_replay(worker_engine)
    assert claimed is not None
    assert claimed.id == replay.id
    assert claimed.priority == 9
    await finish_replay(worker_engine, claimed, succeeded=True)
    overview = await service.overview()
    by_code = {metric.code: metric.value for metric in overview.metrics}
    assert by_code['FAILED_TASKS'] == 0
    assert by_code['QUEUED_REPLAYS'] == 0
    await worker_engine.dispose()
    await service.close()


async def test_processing_metrics_render_against_real_postgres_rows() -> None:
    service = PostgresIntelligenceQueryService(create_database_engine(Settings()))
    try:
        rendered = await service.render_processing_metrics()
        assert '# TYPE srbg_digital_case_outcomes gauge' in rendered
    finally:
        await service.close()


async def test_round11_database_roles_are_least_privilege_and_usage_is_anonymous() -> None:
    engine = create_database_engine(Settings())
    try:
        async with engine.connect() as connection:
            columns = set(
                (
                    await connection.execute(
                        text(
                            """SELECT column_name FROM information_schema.columns
                               WHERE table_schema = 'public'
                                 AND table_name = 'usage_metric_bucket'"""
                        )
                    )
                ).scalars()
            )
            assert "actor_id" not in columns
            assert "target_id" not in columns
            assert await connection.scalar(
                text("SELECT has_table_privilege(current_user, 'failed_task', 'INSERT')")
            ) is False
            assert await connection.scalar(
                text("SELECT has_table_privilege(current_user, 'replay_request', 'INSERT')")
            ) is True
            assert await connection.scalar(
                text("SELECT has_table_privilege('srbg_worker_role', 'failed_task', 'INSERT')")
            ) is True
            assert await connection.scalar(
                text("SELECT has_table_privilege('srbg_worker_role', 'replay_request', 'INSERT')")
            ) is False
            assert await connection.scalar(
                text("SELECT has_table_privilege(current_user, 'publication', 'UPDATE')")
            ) is False
    finally:
        await engine.dispose()
