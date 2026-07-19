from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

MIGRATION = Path("apps/api/migrations/versions/0036_ai_content_result_lifecycle.py")


def test_migration_terminalizes_existing_and_future_ai_handoffs() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "0035_intelligence_v2_closeout"' in source
    assert "'COMPLETED'" in source
    assert "finalize_source_content_ai_run" in source
    assert "pipeline.status IN ('FAILED','DEGRADED')" in source
    assert "content.status='WAITING_AI'" in source
    assert '"ck_source_content_outbox_consistency"' in source
    assert "GRANT EXECUTE ON FUNCTION " in source
    assert "finalize_source_content_ai_run(uuid,text,text,timestamptz)" in source
    assert "TO srbg_worker_role" in source


def test_migration_keeps_direct_outbox_table_writes_denied_to_worker() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "GRANT UPDATE ON source_content_outbox TO srbg_worker_role" not in source
    assert "SECURITY DEFINER" in source
    assert "SET search_path=pg_catalog,public" in source


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("SRBG_AI_LIFECYCLE_TEST_DATABASE_URL"),
    reason="requires a loopback PostgreSQL database already migrated to 0036",
)
async def test_terminal_pipeline_closes_waiting_ai_handoff_in_postgres() -> None:
    database_url = os.environ["SRBG_AI_LIFECYCLE_TEST_DATABASE_URL"]
    assert "127.0.0.1" in database_url or "localhost" in database_url
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                row = (
                    await connection.execute(
                        text(
                            "SELECT content.id,pipeline.id AS pipeline_id "
                            "FROM source_content_outbox content "
                            "JOIN ai_pipeline_run pipeline "
                            "ON pipeline.id=content.pipeline_run_id "
                            "ORDER BY content.created_at LIMIT 1"
                        )
                    )
                ).mappings().one()
                await connection.execute(
                    text(
                        "UPDATE ai_pipeline_run SET status='FAILED',"
                        "failure_code='REGRESSION_TEST_FAILURE',"
                        "completed_at=clock_timestamp() WHERE id=:pipeline_id"
                    ),
                    {"pipeline_id": row["pipeline_id"]},
                )
                await connection.execute(
                    text(
                        "UPDATE source_content_outbox SET status='WAITING_AI',"
                        "attempt_count=1,last_error_code=NULL WHERE id=:outbox_id"
                    ),
                    {"outbox_id": row["id"]},
                )

                finalized = await connection.scalar(
                    text(
                        "SELECT finalize_source_content_ai_run("
                        ":pipeline_id,'FAILED','REGRESSION_TEST_FAILURE',"
                        "clock_timestamp())"
                    ),
                    {"pipeline_id": row["pipeline_id"]},
                )
                closed = (
                    await connection.execute(
                        text(
                            "SELECT status,attempt_count,last_error_code "
                            "FROM source_content_outbox WHERE id=:outbox_id"
                        ),
                        {"outbox_id": row["id"]},
                    )
                ).mappings().one()

                assert finalized == row["id"]
                assert closed == {
                    "status": "DEAD_LETTER",
                    "attempt_count": 5,
                    "last_error_code": "REGRESSION_TEST_FAILURE",
                }
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
