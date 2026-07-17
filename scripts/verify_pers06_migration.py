# ruff: noqa: S101
"""Replay PERS-06 on the isolated loopback integration database."""

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
        raise RuntimeError("PERS-06 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, expected: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version")) == expected
            )
            exists = await connection.scalar(
                text("SELECT to_regclass('public.ai_judgment') IS NOT NULL")
            )
            if expected == "0026_automatic_evidence_facts":
                assert exists
                assert await connection.scalar(
                    text("SELECT to_regclass('public.personal_content_projection') IS NOT NULL")
                )
                assert not await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_worker_role',"
                        "'personal_content_projection','INSERT')"
                    )
                )
                assert await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_publication_writer',"
                        "'personal_content_projection','INSERT')"
                    )
                )
            else:
                assert not exists
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0026_automatic_evidence_facts")
    asyncio.run(_verify(database_url, "0026_automatic_evidence_facts"))
    command.downgrade(config, "0025_personal_source_discovery")
    asyncio.run(_verify(database_url, "0025_personal_source_discovery"))
    command.upgrade(config, "0026_automatic_evidence_facts")
    asyncio.run(_verify(database_url, "0026_automatic_evidence_facts"))
    print("PERS-06 migration replay passed: 0025 -> 0026 -> 0025 -> 0026")


if __name__ == "__main__":
    main()
