"""Replay T09, then leave the isolated database at head for the shared suite."""

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
        raise RuntimeError("T09 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert current == revision
            for table in ("hotspot_candidate_v2", "hotspot_evaluation_v2"):
                exists = await connection.scalar(
                    text("SELECT to_regclass(:table) IS NOT NULL"),
                    {"table": f"public.{table}"},
                )
                assert bool(exists) is (revision == "0043_t09_hotspot_awards")
            columns = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='hotspot_award_v2' "
                    "AND column_name IN ('evaluation_id','document_version_id','evidence_sha256')"
                )
            )
            assert int(columns or 0) == (3 if revision == "0043_t09_hotspot_awards" else 0)
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0042_t07_controlled_stream")
    command.upgrade(config, "0043_t09_hotspot_awards")
    asyncio.run(_verify(database_url, "0043_t09_hotspot_awards"))
    command.downgrade(config, "0042_t07_controlled_stream")
    asyncio.run(_verify(database_url, "0042_t07_controlled_stream"))
    command.upgrade(config, "0043_t09_hotspot_awards")
    asyncio.run(_verify(database_url, "0043_t09_hotspot_awards"))
    # T08/T09 reuse the cumulative publication integration scenario, which now
    # covers later closed slices through T12. Preserve the focused replay, then
    # run that shared scenario against the complete engineering baseline schema.
    command.upgrade(config, "head")
    print("T09 migration replay passed: 0042 -> 0043 -> 0042 -> 0043")


if __name__ == "__main__":
    main()
