# ruff: noqa: S101 -- assertions are executable migration evidence.
"""Replay PERS-03 on an isolated loopback PostgreSQL database."""

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
        raise RuntimeError("PERS-03 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, expected: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert version == expected
            columns = set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name='fetch_schedule'"
                        )
                    )
                ).scalars()
            )
            if expected == "0023_personal_source_runtime":
                assert {
                    "source_stream_id",
                    "stream_config_version_id",
                    "authority_mode",
                    "self_heal_state",
                    "next_self_heal_at",
                    "health_reason",
                } <= columns
                assert await connection.scalar(
                    text(
                        "SELECT has_function_privilege('srbg_worker_role',"
                        "'claim_due_fetch_schedule(timestamptz,timestamptz,uuid)','EXECUTE')"
                    )
                )
            else:
                assert "authority_mode" not in columns
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0023_personal_source_runtime")
    asyncio.run(_verify(database_url, "0023_personal_source_runtime"))
    command.downgrade(config, "0022_personal_source_streams")
    asyncio.run(_verify(database_url, "0022_personal_source_streams"))
    command.upgrade(config, "0023_personal_source_runtime")
    asyncio.run(_verify(database_url, "0023_personal_source_runtime"))
    print("PERS-03 migration replay passed: 0022 -> 0023 -> 0022 -> 0023")


if __name__ == "__main__":
    main()
