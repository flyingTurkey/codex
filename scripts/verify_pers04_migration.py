# ruff: noqa: S101 -- assertions are executable migration evidence.
"""Replay PERS-04 on an isolated loopback PostgreSQL database."""

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


def _url() -> str:
    value = os.environ.get("SRBG_DATABASE_URL", "")
    parsed = urlsplit(value.replace("postgresql+asyncpg", "postgresql", 1))
    name = parsed.path.removeprefix("/")
    try:
        loopback = parsed.hostname == "localhost" or (
            parsed.hostname is not None and ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(name) is None:
        raise RuntimeError("PERS-04 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, expected: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version")) == expected
            )
            exists = await connection.scalar(
                text("SELECT to_regclass('public.source_profile_snapshot') IS NOT NULL")
            )
            if expected == "0024_automatic_source_profiles":
                assert exists
                assert await connection.scalar(
                    text("SELECT count(*) FROM source_profile_run")
                ) == await connection.scalar(text("SELECT count(*) FROM source"))
                assert await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_worker_role',"
                        "'source_profile_snapshot','INSERT')"
                    )
                )
                assert not await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_api_role',"
                        "'source_profile_snapshot','UPDATE')"
                    )
                )
            else:
                assert not exists
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0024_automatic_source_profiles")
    asyncio.run(_verify(database_url, "0024_automatic_source_profiles"))
    command.downgrade(config, "0023_personal_source_runtime")
    asyncio.run(_verify(database_url, "0023_personal_source_runtime"))
    command.upgrade(config, "0024_automatic_source_profiles")
    asyncio.run(_verify(database_url, "0024_automatic_source_profiles"))
    print("PERS-04 migration replay passed: 0023 -> 0024 -> 0023 -> 0024")


if __name__ == "__main__":
    main()
