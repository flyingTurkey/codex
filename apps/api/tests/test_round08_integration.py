import os

import pytest
from sqlalchemy import text
from srbg_api.config import get_settings
from srbg_api.database import create_database_engine, create_publication_engine

pytestmark = pytest.mark.skipif(
    os.environ.get("SRBG_RUN_SAFETY_INTEGRATION") != "1",
    reason="requires the isolated PostgreSQL integration harness",
)


@pytest.mark.asyncio
async def test_round08_database_roles_keep_candidates_and_decisions_separate() -> None:
    settings = get_settings()
    runtime = create_database_engine(settings)
    publication = create_publication_engine(settings)
    try:
        async with runtime.connect() as connection:
            runtime_candidate_insert = await connection.scalar(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'duplicate_candidate', 'INSERT')"
                )
            )
            runtime_decision_insert = await connection.scalar(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'duplicate_decision', 'INSERT')"
                )
            )
        async with publication.connect() as connection:
            publication_decision_insert = await connection.scalar(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'duplicate_decision', 'INSERT')"
                )
            )
            event_constraint = await connection.scalar(
                text(
                    """
                    SELECT pg_get_constraintdef(oid)
                    FROM pg_constraint WHERE conname = 'ck_event_type'
                    """
                )
            )
    finally:
        await runtime.dispose()
        await publication.dispose()

    assert runtime_candidate_insert is True
    assert runtime_decision_insert is False
    assert publication_decision_insert is True
    assert event_constraint is not None
    assert "PRODUCT_RELEASE" in event_constraint
