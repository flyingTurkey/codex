import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from srbg_api.config import get_settings
from srbg_api.database import create_database_engine, create_publication_engine

pytestmark = pytest.mark.skipif(
    os.environ.get("SRBG_RUN_SAFETY_INTEGRATION") != "1",
    reason="run through make safety-regulation-test",
)


def test_runtime_cannot_bypass_publication_service_database_role() -> None:
    asyncio.run(_assert_role_boundary())


async def _assert_role_boundary() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    runtime = create_database_engine(settings)
    publisher = create_publication_engine(settings)
    try:
        async with runtime.connect() as connection:
            for role in (
                "srbg_api_role",
                "srbg_worker_role",
                "srbg_admin_role",
                "srbg_model_role",
            ):
                assert (
                    await connection.scalar(
                        text("SELECT has_table_privilege(:role, 'publication', 'INSERT')"),
                        {"role": role},
                    )
                    is False
                )
            assert (
                await connection.scalar(
                    text("SELECT has_table_privilege(current_user, 'publication', 'INSERT')")
                )
                is False
            )
            with pytest.raises(DBAPIError, match="permission denied"):
                await connection.execute(text("INSERT INTO publication DEFAULT VALUES"))
            await connection.rollback()
        async with publisher.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT has_table_privilege(current_user, 'publication', 'INSERT')")
                )
                is True
            )
            assert (
                await connection.scalar(
                    text(
                        "SELECT has_table_privilege(current_user, 'publication_revision', 'INSERT')"
                    )
                )
                is True
            )
    finally:
        await runtime.dispose()
        await publisher.dispose()
