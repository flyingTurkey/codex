"""Replay T07 on an isolated loopback PostgreSQL database."""

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
_T07_TABLES = (
    "source_research_disposition_v2",
    "source_owner_intent_v2",
    "source_stream_admission_decision_v2",
    "source_stream_runtime_event_v2",
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
        raise RuntimeError("T07 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert current == revision
            for table in _T07_TABLES:
                exists = await connection.scalar(
                    text("SELECT to_regclass(:table) IS NOT NULL"),
                    {"table": f"public.{table}"},
                )
                assert bool(exists) is (revision == "0042_t07_controlled_stream")
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0041_t06_ai_runtime_projection")
    command.upgrade(config, "0042_t07_controlled_stream")
    asyncio.run(_verify(database_url, "0042_t07_controlled_stream"))
    command.downgrade(config, "0041_t06_ai_runtime_projection")
    asyncio.run(_verify(database_url, "0041_t06_ai_runtime_projection"))
    command.upgrade(config, "0042_t07_controlled_stream")
    asyncio.run(_verify(database_url, "0042_t07_controlled_stream"))
    print("T07 migration replay passed: 0041 -> 0042 -> 0041 -> 0042")


if __name__ == "__main__":
    main()
