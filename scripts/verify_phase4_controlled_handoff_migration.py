"""Replay the phase-4 controlled-handoff edge on a disposable database."""

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
_HEAD = "0056_phase4_controlled_handoff"
_PREVIOUS = "0055_phase3_trustworthy_event"


def _isolated_database_url() -> str:
    value = os.environ.get("SRBG_DATABASE_URL", "")
    parsed = urlsplit(value.replace("postgresql+asyncpg", "postgresql", 1))
    database = parsed.path.removeprefix("/")
    try:
        loopback = parsed.hostname == "localhost" or (
            parsed.hostname is not None
            and ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(database) is None:
        raise RuntimeError(
            "phase-4 migration replay requires an isolated loopback database"
        )
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert current == revision
            definition = str(
                await connection.scalar(
                    text(
                        "SELECT pg_get_functiondef(to_regprocedure("
                        "'handoff_source_content_to_ai(uuid,uuid,uuid,"
                        "timestamp with time zone)'))"
                    )
                )
            )
            propagates_controlled_run = (
                "run.controlled_run_id" in definition
                and "v_controlled_run_id" in definition
            )
            assert propagates_controlled_run is (revision == _HEAD)
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, _PREVIOUS)
    command.upgrade(config, _HEAD)
    asyncio.run(_verify(database_url, _HEAD))
    command.downgrade(config, _PREVIOUS)
    asyncio.run(_verify(database_url, _PREVIOUS))
    command.upgrade(config, _HEAD)
    asyncio.run(_verify(database_url, _HEAD))
    print("Phase-4 migration replay passed: 0055 -> 0056 -> 0055 -> 0056")


if __name__ == "__main__":
    main()
