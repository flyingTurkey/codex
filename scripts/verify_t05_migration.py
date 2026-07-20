"""Replay T05, then leave the isolated database at head for the shared suite."""

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
        raise RuntimeError("T05 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert current == revision
            for table in (
                "qualification_acceptance_v2",
                "publication_decision_v2",
                "projection_archive_row_v2",
            ):
                exists = await connection.scalar(
                    text("SELECT to_regclass(:table) IS NOT NULL"), {"table": f"public.{table}"}
                )
                assert bool(exists) is (revision == "0040_t05_reader_projection")
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0039_t04_content_candidates")
    command.upgrade(config, "0040_t05_reader_projection")
    asyncio.run(_verify(database_url, "0040_t05_reader_projection"))
    command.downgrade(config, "0039_t04_content_candidates")
    asyncio.run(_verify(database_url, "0039_t04_content_candidates"))
    command.upgrade(config, "0040_t05_reader_projection")
    asyncio.run(_verify(database_url, "0040_t05_reader_projection"))
    # The T05 integration scenario is intentionally cumulative and now exercises
    # later closed slices (through T12). Keep the focused 0039/0040 replay above,
    # then provide the shared suite with the complete engineering baseline schema.
    command.upgrade(config, "head")
    print("T05 migration replay passed: 0039 -> 0040 -> 0039 -> 0040")


if __name__ == "__main__":
    main()
