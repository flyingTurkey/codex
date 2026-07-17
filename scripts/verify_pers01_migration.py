"""Replay PERS-01 and verify personal-source invariants on isolated PostgreSQL."""

# ruff: noqa: S101 -- assertions are executable migration evidence.

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
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_contracts import PersonalSourcePatchRequest, PersonalSourceRuntimeState

_DISPOSABLE_DATABASE = re.compile(r"srbg_it_[0-9a-f]{24}\Z")
_OWNER_ID = "019b0000-0000-7000-8000-000000009001"


def _require_isolated_url() -> str:
    database_url = os.environ.get("SRBG_DATABASE_URL", "")
    parsed = urlsplit(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    database_name = parsed.path.removeprefix("/")
    try:
        loopback = parsed.hostname == "localhost" or (
            parsed.hostname is not None and ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(database_name) is None:
        raise RuntimeError("PERS-01 migration replay requires an isolated loopback database")
    return database_url


async def _verify_shape(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0021_personal_source_core"
            )
            assert await connection.scalar(
                text("SELECT count(*) FROM personal_automation_setting")
            ) == 1
            setting = (
                await connection.execute(
                    text(
                        "SELECT owner_id,automation_enabled FROM personal_automation_setting"
                    )
                )
            ).one()
            assert str(setting.owner_id) == _OWNER_ID
            assert setting.automation_enabled is False
            state = (
                await connection.execute(
                    text(
                        "SELECT bool_and(desired_enabled=false),"
                        "bool_and(runtime_state='PENDING_CONFIGURATION'),"
                        "bool_and(manual_disabled_at IS NULL) FROM source"
                    )
                )
            ).one()
            assert tuple(state) == (True, True, True)
    finally:
        await engine.dispose()


async def _verify_idempotent_manual_disable(database_url: str) -> None:
    engine = create_async_engine(database_url)
    repository = SourceVaultRepository(engine)
    try:
        source = (await repository.list_personal_sources())[0]
        assert source.runtime_state is PersonalSourceRuntimeState.PENDING_CONFIGURATION
        first = await repository.patch_personal_source(
            source.id,
            PersonalSourcePatchRequest(desired_enabled=False),
            actor_id=UUID(_OWNER_ID),
            request_id="pers01-disable-first",
            now=datetime(2026, 7, 17, 10, 0, tzinfo=UTC),
        )
        second = await repository.patch_personal_source(
            source.id,
            PersonalSourcePatchRequest(desired_enabled=False),
            actor_id=UUID(_OWNER_ID),
            request_id="pers01-disable-repeat",
            now=datetime(2026, 7, 17, 11, 0, tzinfo=UTC),
        )
        assert first.manual_disabled_at == second.manual_disabled_at
        assert second.runtime_state is PersonalSourceRuntimeState.PENDING_CONFIGURATION

        async with engine.connect() as connection:
            event_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM source_key_activity_event "
                    "WHERE source_id=:source_id AND event_type='MANUAL_DISABLED'"
                ),
                {"source_id": source.id},
            )
            assert event_count == 1
            assert await connection.scalar(
                text("SELECT enabled=false FROM source WHERE id=:source_id"),
                {"source_id": source.id},
            )

        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE source SET enabled=true WHERE id=:source_id"),
                    {"source_id": source.id},
                )
        except DBAPIError:
            pass
        else:
            raise AssertionError("automatic work must not override a manual disable")
    finally:
        await repository.close()


async def _verify_rollback(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0020_ai_content_preparation"
            )
            assert await connection.scalar(
                text("SELECT to_regclass('public.personal_automation_setting') IS NULL")
            )
            assert await connection.scalar(
                text(
                    "SELECT count(*)=0 FROM information_schema.columns "
                    "WHERE table_name='source' AND column_name IN "
                    "('desired_enabled','runtime_state','manual_disabled_at')"
                )
            )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _require_isolated_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0021_personal_source_core")
    asyncio.run(_verify_shape(database_url))
    asyncio.run(_verify_idempotent_manual_disable(database_url))
    command.downgrade(config, "0020_ai_content_preparation")
    asyncio.run(_verify_rollback(database_url))
    command.upgrade(config, "0021_personal_source_core")
    asyncio.run(_verify_shape(database_url))
    print("PERS-01 migration replay passed: 0020 -> 0021 -> 0020 -> 0021")


if __name__ == "__main__":
    main()
