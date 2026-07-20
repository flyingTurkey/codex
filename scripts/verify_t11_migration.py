"""Replay T11 ReaderAppendix migration on an isolated loopback PostgreSQL database."""

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
        raise RuntimeError("T11 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert current == revision
            exists = bool(
                await connection.scalar(
                    text("SELECT to_regclass('public.reader_appendix_governance_v2') IS NOT NULL")
                )
            )
            expected = revision == "0044_t11_reader_appendix"
            assert exists is expected
            if expected:
                can_read = await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_projection_reader',"
                        "'reader_appendix_governance_v2','SELECT')"
                    )
                )
                assert bool(can_read)
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0043_t09_hotspot_awards")
    command.upgrade(config, "0044_t11_reader_appendix")
    asyncio.run(_verify(database_url, "0044_t11_reader_appendix"))
    command.downgrade(config, "0043_t09_hotspot_awards")
    asyncio.run(_verify(database_url, "0043_t09_hotspot_awards"))
    command.upgrade(config, "0044_t11_reader_appendix")
    asyncio.run(_verify(database_url, "0044_t11_reader_appendix"))
    print("T11 migration replay passed: 0043 -> 0044 -> 0043 -> 0044")


if __name__ == "__main__":
    main()
