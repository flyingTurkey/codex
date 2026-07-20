"""Replay the T06 migration on an isolated loopback PostgreSQL database."""

# ruff: noqa: S101 -- assertions are executable migration evidence.

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_DISPOSABLE_DATABASE = re.compile(r"srbg_it_[0-9a-f]{24}\Z")
_T06_TABLES = (
    "source_excerpt_version_v2",
    "ai_approved_content_success_v2",
    "ai_summary_state_event_v2",
    "ai_projection_refresh_outbox_v2",
)


def _isolated_database_url() -> str:
    value = os.environ.get("SRBG_DATABASE_URL", "")
    parsed = urlsplit(value.replace("postgresql+asyncpg", "postgresql", 1))
    database = parsed.path.removeprefix("/")
    try:
        loopback = parsed.hostname == "localhost" or (
            parsed.hostname is not None and ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(database) is None:
        raise RuntimeError("T06 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert current == revision
            installed = revision == "0041_t06_ai_runtime_projection"
            for table in _T06_TABLES:
                exists = await connection.scalar(
                    text("SELECT to_regclass(:table) IS NOT NULL"),
                    {"table": f"public.{table}"},
                )
                assert bool(exists) is installed
            if installed:
                prompt = await connection.scalar(
                    text(
                        "SELECT count(*) FROM ai_prompt_version "
                        "WHERE step='SUMMARIZE' AND version='t06-content-summary-v1'"
                    )
                )
                schema = await connection.scalar(
                    text(
                        "SELECT count(*) FROM ai_schema_version "
                        "WHERE step='SUMMARIZE' AND version='summarize-v2-output-1.0.0'"
                    )
                )
                assert prompt == schema == 1
                assert await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_worker_role',"
                        "'ai_approved_content_success_v2','INSERT')"
                    )
                )
                assert not await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_worker_role',"
                        "'intelligence_projection_v2','INSERT')"
                    )
                )
                assert await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_publication_writer',"
                        "'ai_projection_refresh_outbox_v2','UPDATE')"
                    )
                )
                assert not await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_publication_writer',"
                        "'ai_projection_refresh_outbox_v2','INSERT')"
                    )
                )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0040_t05_reader_projection")
    command.upgrade(config, "0041_t06_ai_runtime_projection")
    asyncio.run(_verify(database_url, "0041_t06_ai_runtime_projection"))
    command.downgrade(config, "0040_t05_reader_projection")
    asyncio.run(_verify(database_url, "0040_t05_reader_projection"))
    command.upgrade(config, "0041_t06_ai_runtime_projection")
    asyncio.run(_verify(database_url, "0041_t06_ai_runtime_projection"))
    print("T06 migration replay passed: 0040 -> 0041 -> 0040 -> 0041")


if __name__ == "__main__":
    main()
