# ruff: noqa: S101 -- assertions are executable migration evidence.
"""Replay PERS-02 on an isolated loopback PostgreSQL database."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_contracts import PersonalSourceCreateRequest

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
        raise RuntimeError("PERS-02 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, expected: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version")) == expected
            )
            if expected == "0022_personal_source_streams":
                assert await connection.scalar(
                    text("SELECT to_regclass('public.stream_probe_run') IS NOT NULL")
                )
                assert await connection.scalar(
                    text("SELECT to_regclass('public.stream_config_version') IS NOT NULL")
                )
                columns = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT column_name FROM information_schema.columns "
                                "WHERE table_name='source_stream'"
                            )
                        )
                    ).scalars()
                )
                assert {
                    "stream_type",
                    "allowed_hosts",
                    "config_sha256",
                    "discovery_method",
                } <= columns
            else:
                assert await connection.scalar(
                    text("SELECT to_regclass('public.stream_probe_run') IS NULL")
                )
    finally:
        await engine.dispose()


async def _verify_personal_url_idempotency(database_url: str) -> None:
    repository = SourceVaultRepository(create_async_engine(database_url))
    actor_id = UUID("019b0000-0000-7000-8000-000000009001")
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    try:
        first = await repository.create_personal_source(
            PersonalSourceCreateRequest(url="https://pers02.example.test/news"),
            actor_id=actor_id,
            request_id="pers02-first",
            now=now,
        )
        duplicate = await repository.create_personal_source(
            PersonalSourceCreateRequest(url="https://pers02.example.test/news"),
            actor_id=actor_id,
            request_id="pers02-duplicate",
            now=now,
        )
        second_stream = await repository.create_personal_source(
            PersonalSourceCreateRequest(url="https://pers02.example.test/feed.xml"),
            actor_id=actor_id,
            request_id="pers02-second-stream",
            now=now,
        )
        assert first.id == duplicate.id == second_stream.id
        assert second_stream.desired_enabled is True
        assert len(second_stream.streams) == 2
        assert second_stream.latest_probe_run is not None
    finally:
        await repository.close()


def main() -> None:
    database_url = _url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0022_personal_source_streams")
    asyncio.run(_verify(database_url, "0022_personal_source_streams"))
    asyncio.run(_verify_personal_url_idempotency(database_url))
    command.downgrade(config, "0021_personal_source_core")
    asyncio.run(_verify(database_url, "0021_personal_source_core"))
    command.upgrade(config, "0022_personal_source_streams")
    asyncio.run(_verify(database_url, "0022_personal_source_streams"))
    print("PERS-02 migration replay passed: 0021 -> 0022 -> 0021 -> 0022")


if __name__ == "__main__":
    main()
