"""Replay the T12 media-delivery migration on an isolated loopback database."""

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
        raise RuntimeError("T12 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    expected = revision == "0045_t12_media_delivery"
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert current == revision
            view_exists = await connection.scalar(
                text("SELECT to_regclass('public.media_delivery_reader_v2') IS NOT NULL")
            )
            trigger_exists = await connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_trigger "
                    "WHERE tgname='trg_media_v2_authority' AND NOT tgisinternal)"
                )
            )
            columns = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='media_rights_v2' "
                    "AND column_name IN ('attachment_id','rights_evidence_ref',"
                    "'preview_object_key','preview_sha256','preview_mime_type',"
                    "'preview_byte_size')"
                )
            )
            assert bool(view_exists) is expected
            assert bool(trigger_exists) is expected
            assert int(columns or 0) == (6 if expected else 0)
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0044_t11_reader_appendix")
    command.upgrade(config, "0045_t12_media_delivery")
    asyncio.run(_verify(database_url, "0045_t12_media_delivery"))
    command.downgrade(config, "0044_t11_reader_appendix")
    asyncio.run(_verify(database_url, "0044_t11_reader_appendix"))
    command.upgrade(config, "0045_t12_media_delivery")
    asyncio.run(_verify(database_url, "0045_t12_media_delivery"))
    print("T12 migration replay passed: 0044 -> 0045 -> 0044 -> 0045")


if __name__ == "__main__":
    main()
