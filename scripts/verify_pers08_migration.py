# ruff: noqa: S101
"""Replay PERS-08 on the isolated loopback integration database."""

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
        raise RuntimeError("PERS-08 migration replay requires an isolated loopback database")
    return value


async def _verify(database_url: str, expected: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version")) == expected
            )
            exists = await connection.scalar(
                text(
                    "SELECT to_regclass('public.automatic_relationship_decision_version') "
                    "IS NOT NULL"
                )
            )
            if expected == "0028_automatic_relationships":
                assert exists
                for table_name in (
                    "automatic_relationship_member",
                    "owner_relationship_correction",
                    "owner_relationship_withdrawal",
                    "automatic_relationship_invalidation",
                ):
                    assert await connection.scalar(
                        text("SELECT to_regclass(:name) IS NOT NULL"),
                        {"name": f"public.{table_name}"},
                    )
                assert await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_publication_writer',"
                        "'owner_relationship_correction','INSERT')"
                    )
                )
                assert not await connection.scalar(
                    text(
                        "SELECT has_table_privilege('srbg_worker_role',"
                        "'owner_relationship_correction','INSERT')"
                    )
                )
            else:
                assert not exists
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0028_automatic_relationships")
    asyncio.run(_verify(database_url, "0028_automatic_relationships"))
    command.downgrade(config, "0027_ai_judgment_versions")
    asyncio.run(_verify(database_url, "0027_ai_judgment_versions"))
    command.upgrade(config, "0028_automatic_relationships")
    asyncio.run(_verify(database_url, "0028_automatic_relationships"))
    print("PERS-08 migration replay passed: 0027 -> 0028 -> 0027 -> 0028")


if __name__ == "__main__":
    main()
