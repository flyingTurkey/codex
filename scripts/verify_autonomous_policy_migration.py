"""Replay the autonomous-policy expand migration on an isolated database."""

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
_TABLES = (
    "qualification_policy_bundle_v2",
    "automated_qualification_decision_v2",
    "owner_exception_v2",
    "owner_exception_event_v2",
    "feed_suppression_rule_v2",
    "qualification_policy_evaluation_v2",
    "qualification_shadow_decision_v2",
)
_SUPPRESSION_READ_MODEL_TABLE = "event_suppression_match_v2"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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
            "autonomous-policy migration replay requires an isolated loopback database"
        )
    return value


async def _verify(database_url: str, revision: str) -> None:
    engine = create_async_engine(database_url)
    expected = revision in {
        "0048_autonomous_policy_foundation",
        "0049_autonomous_content_switch",
        "0050_autonomous_handoff_state_order",
        "0051_technical_exception_recovery",
        "0052_feed_suppression_projection",
    }
    try:
        async with engine.connect() as connection:
            current = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            _require(current == revision, "unexpected Alembic revision")
            table_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=ANY(:tables)"
                ),
                {"tables": [*_TABLES, _SUPPRESSION_READ_MODEL_TABLE]},
            )
            _require(
                int(table_count or 0)
                == (
                    len(_TABLES) + (revision == "0052_feed_suppression_projection")
                    if expected
                    else 0
                ),
                "autonomous-policy table set mismatch",
            )
            historical_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name IN "
                    "('owner_gold_prediction_seal_v2','owner_gold_calibration_v2')"
                )
            )
            _require(int(historical_count or 0) == 2, "historical tables were not preserved")
            if expected:
                authority_check = await connection.scalar(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conname='ck_qualification_policy_authority_v2'"
                    )
                )
                _require(authority_check is not None, "authority constraint is missing")
                _require(
                    "SERVER_ADJUDICATION_ONLY" in authority_check,
                    "authority constraint does not bind server-only adjudication",
                )
            if revision == "0049_autonomous_content_switch":
                registry_count = await connection.scalar(
                    text(
                        "SELECT (SELECT count(*) FROM ai_prompt_version WHERE "
                        "version='autonomous-classify-2.7.0') + "
                        "(SELECT count(*) FROM ai_schema_version WHERE "
                        "version='autonomous-classify-output-2.0.0')"
                    )
                )
                _require(int(registry_count or 0) == 2, "production AI registry is incomplete")
            if revision in {
                "0050_autonomous_handoff_state_order",
                "0051_technical_exception_recovery",
                "0052_feed_suppression_projection",
            }:
                handoff_definition = await connection.scalar(
                    text(
                        "SELECT pg_get_functiondef("
                        "'handoff_source_content_to_ai(uuid,uuid,timestamptz)'::regprocedure)"
                    )
                )
                _require(
                    "WHEN 'READY' THEN 80" in str(handoff_definition),
                    "handoff state order is not deterministic",
                )
            if revision == "0051_technical_exception_recovery":
                retry_definition = await connection.scalar(
                    text(
                        "SELECT pg_get_functiondef("
                        "'reopen_source_content_ai_run(uuid,uuid,uuid,uuid,timestamptz,timestamptz)'"
                        "::regprocedure)"
                    )
                )
                _require(
                    "event.event_type='RETRY_REQUESTED'" in str(retry_definition),
                    "technical retry is not bound to an Owner command",
                )
            if revision == "0052_feed_suppression_projection":
                views = await connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.views "
                        "WHERE table_schema='public' AND table_name IN ("
                        "'feed_suppression_effective_v2',"
                        "'visible_intelligence_projection_v2')"
                    )
                )
                _require(int(views or 0) == 2, "suppression security views are incomplete")
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0047_owner_gold_override_go")
    command.upgrade(config, "0048_autonomous_policy_foundation")
    asyncio.run(_verify(database_url, "0048_autonomous_policy_foundation"))
    command.upgrade(config, "0049_autonomous_content_switch")
    asyncio.run(_verify(database_url, "0049_autonomous_content_switch"))
    command.downgrade(config, "0048_autonomous_policy_foundation")
    asyncio.run(_verify(database_url, "0048_autonomous_policy_foundation"))
    command.upgrade(config, "0049_autonomous_content_switch")
    asyncio.run(_verify(database_url, "0049_autonomous_content_switch"))
    command.upgrade(config, "0050_autonomous_handoff_state_order")
    asyncio.run(_verify(database_url, "0050_autonomous_handoff_state_order"))
    command.downgrade(config, "0049_autonomous_content_switch")
    asyncio.run(_verify(database_url, "0049_autonomous_content_switch"))
    command.upgrade(config, "0050_autonomous_handoff_state_order")
    asyncio.run(_verify(database_url, "0050_autonomous_handoff_state_order"))
    command.upgrade(config, "0051_technical_exception_recovery")
    asyncio.run(_verify(database_url, "0051_technical_exception_recovery"))
    command.downgrade(config, "0050_autonomous_handoff_state_order")
    asyncio.run(_verify(database_url, "0050_autonomous_handoff_state_order"))
    command.upgrade(config, "0051_technical_exception_recovery")
    asyncio.run(_verify(database_url, "0051_technical_exception_recovery"))
    command.upgrade(config, "0052_feed_suppression_projection")
    asyncio.run(_verify(database_url, "0052_feed_suppression_projection"))
    command.downgrade(config, "0051_technical_exception_recovery")
    asyncio.run(_verify(database_url, "0051_technical_exception_recovery"))
    command.upgrade(config, "0052_feed_suppression_projection")
    asyncio.run(_verify(database_url, "0052_feed_suppression_projection"))
    print(
        "Autonomous-policy migration replay passed: "
        "0048 -> 0049 -> 0048 -> 0049 -> 0050 -> 0049 -> 0050 -> 0051 -> 0050 -> "
        "0051 -> 0052 -> 0051 -> 0052"
    )


if __name__ == "__main__":
    main()
