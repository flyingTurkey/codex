# ruff: noqa: S101 -- assertions are executable migration evidence.
"""Replay PERS-05 on an isolated loopback PostgreSQL database."""

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
        raise RuntimeError("PERS-05 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, expected: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version")) == expected
            )
            exists = await connection.scalar(
                text("SELECT to_regclass('public.discovery_topic') IS NOT NULL")
            )
            if expected == "0025_personal_source_discovery":
                assert exists
                assert await connection.scalar(text("SELECT count(*) FROM discovery_topic")) == 7
                assert await connection.scalar(
                    text("SELECT count(*) FROM source_auto_score_run")
                ) == await connection.scalar(text("SELECT count(*) FROM source"))
                assert await connection.scalar(
                    text(
                        "SELECT has_function_privilege('srbg_worker_role',"
                        "'reserve_personal_probe_budget(timestamptz)','EXECUTE')"
                    )
                )
                assert await connection.scalar(
                    text(
                        "SELECT has_function_privilege('srbg_worker_role',"
                        "'auto_enable_personal_source(uuid,uuid,uuid,timestamptz)','EXECUTE')"
                    )
                )
            else:
                assert not exists
    finally:
        await engine.dispose()


async def _verify_budget_boundaries(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            probe = [
                await connection.scalar(text("SELECT reserve_personal_probe_budget(now())"))
                for _ in range(101)
            ]
            enable = [
                await connection.scalar(text("SELECT reserve_personal_auto_enable_budget(now())"))
                for _ in range(21)
            ]
            assert probe.count(True) == 100 and probe[-1] is False
            assert enable.count(True) == 20 and enable[-1] is False
            assert await connection.scalar(
                text(
                    "SELECT personal_discovery_local_date("
                    "'2026-07-17 15:59:59+00'::timestamptz)="
                    "personal_discovery_local_date('2026-07-17 16:00:00+00'::timestamptz)-1"
                )
            )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0025_personal_source_discovery")
    asyncio.run(_verify(database_url, "0025_personal_source_discovery"))
    command.downgrade(config, "0024_automatic_source_profiles")
    asyncio.run(_verify(database_url, "0024_automatic_source_profiles"))
    command.upgrade(config, "0025_personal_source_discovery")
    asyncio.run(_verify(database_url, "0025_personal_source_discovery"))
    asyncio.run(_verify_budget_boundaries(database_url))
    print("PERS-05 migration replay passed: 0024 -> 0025 -> 0024 -> 0025")


if __name__ == "__main__":
    main()
