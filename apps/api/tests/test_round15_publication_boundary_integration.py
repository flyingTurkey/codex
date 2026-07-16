import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.config import get_settings
from srbg_api.database import create_publication_engine
from srbg_api.publication import repository as publication_repository

pytestmark = pytest.mark.skipif(
    os.environ.get("SRBG_RUN_SAFETY_INTEGRATION") != "1",
    reason="run through the isolated PostgreSQL integration harness",
)


def test_publication_writer_can_execute_v2_authoritative_source_query() -> None:
    asyncio.run(_execute_authoritative_query())


async def _execute_authoritative_query() -> None:
    get_settings.cache_clear()
    engine = create_publication_engine(get_settings())
    try:
        async with engine.connect() as connection:
            facts = await publication_repository._publication_facts(  # pyright: ignore[reportPrivateUsage]
                connection,
                UUID("019b1500-0000-7000-8000-000000009199"),
                evaluated_at=datetime(2026, 7, 16, 8, 0, tzinfo=UTC),
            )
        assert facts is None
    finally:
        await engine.dispose()
        get_settings.cache_clear()
