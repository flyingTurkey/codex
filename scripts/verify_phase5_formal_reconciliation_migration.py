"""Verify the formal sibling-to-head path on a disposable loopback database."""

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
_BASE = "0054_policy_optimization"
_LEGACY = "0055_crossref_metadata_admission"
_HEAD = "0058_phase5_technical_exception_acl"


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
            "phase-5 migration replay requires an isolated loopback database"
        )
    return value


async def _install_legacy_formal_shape(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE stream_config_version "
                    "ADD COLUMN admission_research_id uuid NULL"
                )
            )
            await connection.execute(
                text(
                    "ALTER TABLE stream_config_version "
                    "ALTER COLUMN probe_run_id DROP NOT NULL"
                )
            )
            await connection.execute(
                text(
                    "ALTER TABLE stream_config_version ADD CONSTRAINT "
                    "fk_stream_config_admission_research FOREIGN KEY "
                    "(admission_research_id) REFERENCES "
                    "source_research_disposition_v2(id) ON DELETE RESTRICT"
                )
            )
            await connection.execute(
                text(
                    "ALTER TABLE stream_config_version ADD CONSTRAINT "
                    "ck_stream_config_exactly_one_provenance CHECK "
                    "((probe_run_id IS NULL) <> "
                    "(admission_research_id IS NULL))"
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX ix_stream_config_admission_research "
                    "ON stream_config_version (admission_research_id)"
                )
            )
    finally:
        await engine.dispose()


async def _verify_reconciled_head(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revisions = tuple(
                (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version ORDER BY version_num")
                    )
                ).scalars()
            )
            assert revisions == (_HEAD,)

            provenance = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema='public' "
                    "AND table_name='stream_config_version' "
                    "AND column_name='admission_research_id'"
                )
            )
            if provenance != 1:
                raise RuntimeError("0057_CROSSREF_PROVENANCE_PRESERVATION_FAILED")

            authority = await connection.scalar(
                text(
                    "SELECT to_regclass("
                    "'public.automatic_publication_authority_v2') IS NOT NULL"
                )
            )
            if not bool(authority):
                raise RuntimeError("0057_PHASE3_AUTHORITY_MISSING")

            handoff = str(
                await connection.scalar(
                    text(
                        "SELECT pg_get_functiondef(to_regprocedure("
                        "'handoff_source_content_to_ai(uuid,uuid,uuid,"
                        "timestamp with time zone)'))"
                    )
                )
            )
            if "run.controlled_run_id" not in handoff:
                raise RuntimeError("0057_PHASE4_HANDOFF_MISSING")

            api_can_read_compensation = await connection.scalar(
                text(
                    "SELECT has_table_privilege("
                    "'srbg_api_role','ai_compensation_run_v2','SELECT')"
                )
            )
            if not bool(api_can_read_compensation):
                raise RuntimeError("0058_TECHNICAL_EXCEPTION_API_READ_MISSING")
            api_can_write_compensation = await connection.scalar(
                text(
                    "SELECT has_table_privilege("
                    "'srbg_api_role','ai_compensation_run_v2','INSERT') OR "
                    "has_table_privilege("
                    "'srbg_api_role','ai_compensation_run_v2','UPDATE') OR "
                    "has_table_privilege("
                    "'srbg_api_role','ai_compensation_run_v2','DELETE')"
                )
            )
            if bool(api_can_write_compensation):
                raise RuntimeError("0058_TECHNICAL_EXCEPTION_API_WRITE_LEAK")
    finally:
        await engine.dispose()


async def _verify_clean_base(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert revision == _BASE
            provenance = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema='public' "
                    "AND table_name='stream_config_version' "
                    "AND column_name='admission_research_id'"
                )
            )
            assert provenance == 0
            assert not bool(
                await connection.scalar(
                    text(
                        "SELECT has_table_privilege("
                        "'srbg_api_role','ai_compensation_run_v2','SELECT')"
                    )
                )
            )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, _BASE)
    command.upgrade(config, _HEAD)
    asyncio.run(_verify_reconciled_head(database_url))
    command.downgrade(config, _BASE)
    asyncio.run(_verify_clean_base(database_url))
    asyncio.run(_install_legacy_formal_shape(database_url))
    command.stamp(config, _LEGACY)
    command.upgrade(config, _HEAD)
    asyncio.run(_verify_reconciled_head(database_url))
    print(
        "Phase-5 formal migration replay passed: "
        "0055_crossref sibling -> 0058 single head with narrow API read"
    )


if __name__ == "__main__":
    main()
