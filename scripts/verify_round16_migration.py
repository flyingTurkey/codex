"""Replay Round 16 migration only on an isolated loopback database."""

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


async def _verify_guard(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            source_id = await connection.scalar(text("SELECT id FROM source ORDER BY id LIMIT 1"))
            if source_id is None:
                raise RuntimeError("isolated migration fixture has no source")
            await connection.execute(
                text(
                    """INSERT INTO fetch_schedule
                       (id,source_id,authority_level,status,interval_seconds,next_run_at,
                        freshness_slo_seconds,rate_limit_per_minute,daily_request_budget,
                        daily_byte_budget,budget_window_started_at,updated_at)
                       VALUES ('019b1600-0000-7000-8000-000000000099',:source,'A1','PAUSED',
                               3600,now(),86400,1,24,1000000,now(),now())"""
                ),
                {"source": source_id},
            )
    finally:
        await engine.dispose()


async def _seed_authorized_schedule(database_url: str) -> None:
    """Seed one approved, loopback-only scheduling fact for concurrency tests."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            source_id = await connection.scalar(text("SELECT id FROM source ORDER BY id LIMIT 1"))
            definition_id = await connection.scalar(
                text(
                    "SELECT id FROM connector_definition "
                    "WHERE connector_type='JSON_API' ORDER BY definition_version DESC LIMIT 1"
                )
            )
            if source_id is None or definition_id is None:
                raise RuntimeError("isolated migration fixture lacks source connector metadata")
            await connection.execute(
                text(
                    """INSERT INTO source_policy_version
                       (id,source_id,schema_version,policy_version,status,document,
                        document_sha256,valid_from,valid_until,submitted_by,created_at)
                       VALUES ('019b1600-0000-7000-8000-000000000101',:source,
                               '2.0','round16-integration','APPROVED',
                               CAST(:document AS jsonb),
                               repeat('a',64),now()-interval '1 day',
                               now()+interval '1 day',
                               '019b1600-0000-7000-8000-000000000111',now())"""
                ),
                {
                    "source": source_id,
                    "document": '{"fetch":{"rate_limit_per_minute":1}}',
                },
            )
            await connection.execute(
                text(
                    """INSERT INTO connector_config_version
                       (id,source_id,connector_definition_id,policy_version_id,
                        version_number,config_document,config_sha256,allowed_hosts,
                        credential_ref,validation_status,validation_reason_codes,
                        created_by,created_at)
                       VALUES ('019b1600-0000-7000-8000-000000000102',:source,:definition,
                               '019b1600-0000-7000-8000-000000000101',1,'{}'::jsonb,
                               repeat('b',64),ARRAY['example.invalid'],NULL,'VALID',ARRAY[]::text[],
                               '019b1600-0000-7000-8000-000000000111',now())"""
                ),
                {"source": source_id, "definition": definition_id},
            )
            await connection.execute(
                text(
                    """INSERT INTO source_trial_run
                       (id,source_id,kind,execution_domain,policy_version_id,
                        connector_config_version_id,requested_by,request_reason,created_at)
                       VALUES ('019b1600-0000-7000-8000-000000000103',:source,
                               'FIXTURE_REPLAY','FIXTURE',
                               '019b1600-0000-7000-8000-000000000101',
                               '019b1600-0000-7000-8000-000000000102',
                               '019b1600-0000-7000-8000-000000000111',
                               'round16 isolated concurrency evidence',now())"""
                ),
                {"source": source_id},
            )
            await connection.execute(
                text(
                    """INSERT INTO source_governance_decision
                       (id,source_id,decision_type,outcome,policy_version_id,
                        connector_config_version_id,trial_run_id,submitted_by,
                        decided_by,reason,valid_until,created_at)
                       VALUES ('019b1600-0000-7000-8000-000000000104',:source,
                               'PRODUCTION_APPROVAL','APPROVED',
                               '019b1600-0000-7000-8000-000000000101',
                               '019b1600-0000-7000-8000-000000000102',
                               '019b1600-0000-7000-8000-000000000103',
                               '019b1600-0000-7000-8000-000000000111',
                               '019b1600-0000-7000-8000-000000000112',
                               'round16 isolated authorization evidence',
                               now()+interval '1 day',now())"""
                ),
                {"source": source_id},
            )
            await connection.execute(
                text(
                    """UPDATE source SET lifecycle_state='ACTIVE',
                           current_policy_version_id=
                             '019b1600-0000-7000-8000-000000000101',
                           current_connector_config_version_id=
                             '019b1600-0000-7000-8000-000000000102'
                       WHERE id=:source"""
                ),
                {"source": source_id},
            )
            await connection.execute(
                text(
                    """UPDATE fetch_schedule SET status='ACTIVE',
                           next_run_at=now()-interval '1 minute',
                           leased_until=NULL,lease_token=NULL,updated_at=now()
                       WHERE source_id=:source"""
                ),
                {"source": source_id},
            )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = os.environ["SRBG_DATABASE_URL"]
    parsed = urlsplit(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    database_name = parsed.path.removeprefix("/")
    try:
        loopback = parsed.hostname == "localhost" or (
            parsed.hostname is not None and ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(database_name) is None:
        raise RuntimeError("Round16 migration replay requires an isolated loopback database")
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0015b_source_center_convergence")
    command.upgrade(config, "0016_scheduling_health_replay")
    command.downgrade(config, "0015b_source_center_convergence")
    command.upgrade(config, "0016_scheduling_health_replay")
    asyncio.run(_verify_guard(database_url))
    try:
        command.downgrade(config, "0015b_source_center_convergence")
    except RuntimeError as exc:
        if "0016_DOWNGRADE_BLOCKED" not in str(exc):
            raise
    else:
        raise RuntimeError("Round16 downgrade did not protect authoritative facts")
    asyncio.run(_seed_authorized_schedule(database_url))
    print(
        "Round16 migration replay passed: 0015b -> 0016 -> 0015b -> 0016; "
        "guarded downgrade verified"
    )


if __name__ == "__main__":
    main()
