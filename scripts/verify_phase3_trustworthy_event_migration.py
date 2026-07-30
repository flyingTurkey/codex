"""Replay the phase-3 authority migration on a disposable loopback database."""

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
_HEAD = "0055_phase3_trustworthy_event"
_PREVIOUS = "0054_policy_optimization"


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
            "phase-3 migration replay requires an isolated loopback database"
        )
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert current == revision
            phase3 = revision == _HEAD
            for object_name in (
                "automatic_publication_authority_v2",
                "event_publication_control_event_v2",
                "projection_rebuild_outbox_v2",
            ):
                exists = await connection.scalar(
                    text("SELECT to_regclass(:name) IS NOT NULL"),
                    {"name": f"public.{object_name}"},
                )
                assert bool(exists) is phase3
            definition = await connection.scalar(
                text(
                    "SELECT pg_get_viewdef('visible_intelligence_projection_v2'::regclass,true)"
                )
            )
            if phase3:
                assert "publication_revision_id" in str(definition)
                assert "owner_veto" in str(definition)
                source_authority_columns = await connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema='public' "
                        "AND table_name='publication_revision' "
                        "AND column_name IN ("
                        "'source_stream_config_version_id',"
                        "'source_stream_config_sha256')"
                    )
                )
                assert source_authority_columns == 2
                authority_constraint = await connection.scalar(
                    text(
                        "SELECT pg_get_constraintdef(oid) "
                        "FROM pg_constraint "
                        "WHERE conname="
                        "'ck_publication_revision_source_authority_v2'"
                    )
                )
                assert "num_nonnulls" in str(authority_constraint)
                assert bool(
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "'srbg_publication_writer',"
                            "'automatic_publication_authority_v2','INSERT')"
                        )
                    )
                )
                assert not bool(
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "'srbg_worker_role',"
                            "'automatic_publication_authority_v2','INSERT')"
                        )
                    )
                )
                assert bool(
                    await connection.scalar(
                        text(
                            "SELECT has_function_privilege("
                            "'srbg_worker_role',"
                            "'lock_source_content_ai_handoff(uuid,uuid)',"
                            "'EXECUTE')"
                        )
                    )
                )
                assert not bool(
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "'srbg_worker_role','source_content_outbox','UPDATE')"
                        )
                    )
                )
                assert bool(
                    await connection.scalar(
                        text(
                            "SELECT has_function_privilege("
                            "'srbg_publication_writer',"
                            "'load_automatic_publication_context("
                            "uuid,uuid,timestamp with time zone)','EXECUTE')"
                        )
                    )
                )
                assert not bool(
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "'srbg_publication_writer','document_version','UPDATE')"
                        )
                    )
                )
                assert bool(
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "'srbg_projection_reader',"
                            "'visible_intelligence_projection_v2','SELECT')"
                        )
                    )
                )
                assert not bool(
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "'srbg_projection_reader',"
                            "'intelligence_projection_v2','SELECT')"
                        )
                    )
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM automatic_publication_authority_v2"
                        )
                    )
                    == 0
                )
                reserve_definition = await connection.scalar(
                    text(
                        "SELECT pg_get_functiondef("
                        "'reserve_ai_budget("
                        "uuid,uuid,text,integer,integer,"
                        "timestamp with time zone)'::regprocedure)"
                    )
                )
                assert "'VERIFY'" in str(reserve_definition)
            else:
                assert "publication_revision_id" not in str(definition)
                assert (
                    await connection.scalar(
                        text(
                            "SELECT to_regprocedure("
                            "'lock_source_content_ai_handoff(uuid,uuid)')"
                        )
                    )
                    is None
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT to_regprocedure("
                            "'load_automatic_publication_context("
                            "uuid,uuid,timestamp with time zone)')"
                        )
                    )
                    is None
                )
                source_authority_columns = await connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema='public' "
                        "AND table_name='publication_revision' "
                        "AND column_name IN ("
                        "'source_stream_config_version_id',"
                        "'source_stream_config_sha256')"
                    )
                )
                assert source_authority_columns == 0
                assert bool(
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "'srbg_projection_reader',"
                            "'intelligence_projection_v2','SELECT')"
                        )
                    )
                )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, _PREVIOUS)
    command.upgrade(config, _HEAD)
    asyncio.run(_verify(database_url, _HEAD))
    command.downgrade(config, _PREVIOUS)
    asyncio.run(_verify(database_url, _PREVIOUS))
    command.upgrade(config, _HEAD)
    asyncio.run(_verify(database_url, _HEAD))
    print(
        "Phase-3 migration replay passed: "
        "0054 -> 0055 -> 0054 -> 0055"
    )


if __name__ == "__main__":
    main()
