# ruff: noqa: S101
"""Replay and corruption-check the PERS-10 retirement migration."""

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
_HEAD = "0030_pers10_role_archive_repair"
_RETIRED = "0029_legacy_governance_retirement"
_PARENT = "0028_automatic_relationships"


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
        raise RuntimeError("PERS-10 migration replay requires an isolated loopback database")
    return value


async def _verify_upgraded(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == _HEAD
            assert await connection.scalar(
                text(
                    "SELECT to_regclass("
                    "'legacy_governance_archive.legacy_governance_archive_record') IS NOT NULL"
                )
            )
            assert await connection.scalar(
                text("SELECT to_regclass('public.source_candidate') IS NULL")
            )
            assert await connection.scalar(
                text("SELECT to_regclass('legacy_governance_archive.source_candidate') IS NOT NULL")
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_schema_privilege("
                    "'srbg_api_role','legacy_governance_archive','USAGE')"
                )
            )
            mismatches = await connection.scalar(
                text(
                    "SELECT count(*) FROM "
                    "legacy_governance_archive.legacy_governance_archive_manifest "
                    "WHERE original_count<>archive_count"
                )
            )
            assert mismatches == 0
            for role in (
                "srbg_admin_role",
                "srbg_model_role",
                "srbg_source_governance_writer",
            ):
                assert not await connection.scalar(
                    text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"),
                    {"role": role},
                )
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM legacy_governance_archive."
                        "legacy_governance_archive_record WHERE entity_type='database_role'"
                    )
                )
                == 3
            )
            assert not await connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_trigger "
                    "WHERE tgrelid='public.event'::regclass "
                    "AND tgname='trg_event_pending_insert')"
                )
            )
    finally:
        await engine.dispose()


async def _verify_parent(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert version == _PARENT
            assert await connection.scalar(
                text("SELECT to_regclass('public.source_candidate') IS NOT NULL")
            )
            assert await connection.scalar(
                text("SELECT to_regnamespace('legacy_governance_archive') IS NULL")
            )
            for role in (
                "srbg_admin_role",
                "srbg_model_role",
                "srbg_source_governance_writer",
            ):
                assert await connection.scalar(
                    text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"),
                    {"role": role},
                )
            assert await connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_trigger "
                    "WHERE tgrelid='public.event'::regclass "
                    "AND tgname='trg_event_pending_insert')"
                )
            )
    finally:
        await engine.dispose()


async def _verify_retired(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert version == _RETIRED
            assert await connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_roles "
                    "WHERE rolname='srbg_source_governance_writer')"
                )
            )
            for role in ("srbg_admin_role", "srbg_model_role"):
                assert not await connection.scalar(
                    text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"),
                    {"role": role},
                )
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM legacy_governance_archive."
                        "legacy_governance_archive_record WHERE entity_type='database_role'"
                    )
                )
                == 2
            )
    finally:
        await engine.dispose()


async def _corrupt_manifest(database_url: str, *, delta: int) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE legacy_governance_archive.legacy_governance_archive_manifest "
                    "DISABLE TRIGGER trg_pers10_archive_read_only"
                )
            )
            await connection.execute(
                text(
                    "UPDATE legacy_governance_archive.legacy_governance_archive_manifest "
                    "SET archive_count=archive_count+:delta "
                    "WHERE entity_type='database_role'"
                ),
                {"delta": delta},
            )
            await connection.execute(
                text(
                    "ALTER TABLE legacy_governance_archive.legacy_governance_archive_manifest "
                    "ENABLE TRIGGER trg_pers10_archive_read_only"
                )
            )
    finally:
        await engine.dispose()


async def _simulate_applied_0029_role_drift(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for relation in (
                "legacy_governance_archive_record",
                "legacy_governance_archive_manifest",
            ):
                await connection.execute(
                    text(
                        "ALTER TABLE legacy_governance_archive."
                        f"{relation} DISABLE TRIGGER trg_pers10_archive_read_only"
                    )
                )
            await connection.execute(
                text(
                    "DELETE FROM legacy_governance_archive.legacy_governance_archive_record "
                    "WHERE entity_type='database_role'"
                )
            )
            await connection.execute(
                text(
                    "DELETE FROM legacy_governance_archive.legacy_governance_archive_manifest "
                    "WHERE entity_type='database_role'"
                )
            )
            for relation in (
                "legacy_governance_archive_record",
                "legacy_governance_archive_manifest",
            ):
                await connection.execute(
                    text(
                        "ALTER TABLE legacy_governance_archive."
                        f"{relation} ENABLE TRIGGER trg_pers10_archive_read_only"
                    )
                )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, _HEAD)
    asyncio.run(_verify_upgraded(database_url))
    asyncio.run(_corrupt_manifest(database_url, delta=1))
    try:
        command.downgrade(config, _RETIRED)
    except Exception as exc:  # Alembic wraps the migration RuntimeError.
        if not any(
            reason in str(exc)
            for reason in (
                "PERS10_ARCHIVE_CORRUPT",
                "PERS10_ROLE_ARCHIVE_CORRUPT",
            )
        ):
            raise
    else:
        raise AssertionError("corrupt archive downgrade unexpectedly succeeded")
    asyncio.run(_corrupt_manifest(database_url, delta=-1))
    command.downgrade(config, _RETIRED)
    asyncio.run(_verify_retired(database_url))
    command.downgrade(config, _PARENT)
    asyncio.run(_verify_parent(database_url))
    command.upgrade(config, _RETIRED)
    asyncio.run(_simulate_applied_0029_role_drift(database_url))
    command.upgrade(config, _HEAD)
    asyncio.run(_verify_upgraded(database_url))
    command.downgrade(config, _PARENT)
    asyncio.run(_verify_parent(database_url))
    command.upgrade(config, _HEAD)
    asyncio.run(_verify_upgraded(database_url))
    print("PERS-10 migration replay passed: 0028 -> 0029 -> 0030 -> 0029 -> 0028 -> 0029 -> 0030")


if __name__ == "__main__":
    main()
