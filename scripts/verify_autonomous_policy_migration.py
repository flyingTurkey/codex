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
    expected = revision == "0048_autonomous_policy_foundation"
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
                {"tables": list(_TABLES)},
            )
            _require(
                int(table_count or 0) == (len(_TABLES) if expected else 0),
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
                    "AUTONOMOUS_POLICY_GATE" in authority_check,
                    "authority constraint does not bind autonomous policy gate",
                )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _isolated_database_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0047_owner_gold_override_go")
    command.upgrade(config, "0048_autonomous_policy_foundation")
    asyncio.run(_verify(database_url, "0048_autonomous_policy_foundation"))
    command.downgrade(config, "0047_owner_gold_override_go")
    asyncio.run(_verify(database_url, "0047_owner_gold_override_go"))
    command.upgrade(config, "0048_autonomous_policy_foundation")
    asyncio.run(_verify(database_url, "0048_autonomous_policy_foundation"))
    print("Autonomous-policy migration replay passed: 0047 -> 0048 -> 0047 -> 0048")


if __name__ == "__main__":
    main()
