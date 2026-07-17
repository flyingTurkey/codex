"""Replay the R-AI01 migration on an isolated PostgreSQL database."""

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
        raise RuntimeError("R-AI01 migration replay requires an isolated loopback database")
    return database_url


async def _verify_upgrade(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == "0020_ai_content_preparation"
            tables = await connection.scalars(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "AND tablename LIKE 'ai_%'"
                )
            )
            assert {
                "ai_budget_policy",
                "ai_budget_month",
                "ai_budget_reservation",
                "ai_candidate_claim_origin",
                "ai_claim_review_decision",
                "ai_secret_change_audit",
            }.issubset(set(tables.all()))
            policy = (
                await connection.execute(
                    text(
                        "SELECT monthly_points,document_points,alert_points,points_per_usd "
                        "FROM ai_budget_policy WHERE provider='deepseek' AND active"
                    )
                )
            ).one()
            assert tuple(policy) == (20_000, 100, 16_000, 800)
            functions = await connection.scalars(
                text(
                    "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='public' AND p.proname IN "
                    "('reserve_ai_budget','settle_ai_budget','release_ai_budget',"
                    "'promote_ai01_pilot_to_shadow')"
                )
            )
            assert set(functions.all()) == {
                "reserve_ai_budget",
                "settle_ai_budget",
                "release_ai_budget",
                "promote_ai01_pilot_to_shadow",
            }
    finally:
        await engine.dispose()


async def _verify_rollback(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == "0019_source_content_bridge"
            exists = await connection.scalar(
                text("SELECT to_regclass('public.ai_budget_policy') IS NOT NULL")
            )
            assert exists is False
    finally:
        await engine.dispose()


async def _verify_budget_ledger(database_url: str) -> None:
    engine = create_async_engine(database_url)
    run_id = "019d0000-0000-7000-8000-000000002900"
    raw_id = "019d0000-0000-7000-8000-000000002901"
    document_id = "019d0000-0000-7000-8000-000000002902"
    version_id = "019d0000-0000-7000-8000-000000002903"
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO raw_object(id,sha256,object_key,byte_size,declared_mime,"
                    "detected_mime,scan_status,created_at) VALUES("
                    "CAST(:raw AS uuid),repeat('b',64),"
                    "'ai01-budget-fixture',1,'application/pdf','application/pdf','CLEAN',now())"
                ),
                {"raw": raw_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO document(id,source_id,canonical_url,document_kind,"
                    "first_discovered_at) SELECT CAST(:document AS uuid),id,"
                    "'https://example.invalid/ai01-budget-fixture','PDF',now() FROM source "
                    "WHERE registry_code='GOV-003'"
                ),
                {"document": document_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO document_version(id,document_id,raw_object_id,version_number,"
                    "content_hash,original_filename,acquired_at) VALUES(CAST(:version AS uuid),"
                    "CAST(:document AS uuid),CAST(:raw AS uuid),1,repeat('b',64),"
                    "'fixture.pdf',now())"
                ),
                {"version": version_id, "document": document_id, "raw": raw_id},
            )
            await connection.execute(
                text(
                    "UPDATE document SET current_version_id=CAST(:version AS uuid) "
                    "WHERE id=CAST(:document AS uuid)"
                ),
                {"version": version_id, "document": document_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO ai_pipeline_run(id,document_version_id,mode,status,input_sha256,"
                    "started_at) VALUES(CAST(:run_id AS uuid),CAST(:version AS uuid),'SHADOW',"
                    "'QUEUED',repeat('a',64),now())"
                ),
                {"run_id": run_id, "version": version_id},
            )

        async def reserve(step: str, attempt: int) -> None:
            tail = 2910 + (0 if step == "CLASSIFY" else 4) + attempt
            reservation_id = f"019d0000-0000-7000-8000-{tail:012d}"
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "SELECT * FROM reserve_ai_budget(CAST(:id AS uuid),CAST(:run AS uuid),"
                        ":step,:attempt,12,now())"
                    ),
                    {
                        "id": reservation_id,
                        "run": run_id,
                        "step": step,
                        "attempt": attempt,
                    },
                )

        await asyncio.gather(
            *(reserve(step, attempt) for step in ("CLASSIFY", "EXTRACT") for attempt in range(1, 5))
        )
        async with engine.connect() as connection:
            points = await connection.scalar(
                text(
                    "SELECT sum(reserved_points) FROM ai_budget_reservation "
                    "WHERE pipeline_run_id=CAST(:run AS uuid)"
                ),
                {"run": run_id},
            )
            assert points == 96
            duplicate = (
                await connection.execute(
                    text(
                        "SELECT * FROM reserve_ai_budget("
                        "'019d0000-0000-7000-8000-000000002999',CAST(:run AS uuid),"
                        "'CLASSIFY',1,12,now())"
                    ),
                    {"run": run_id},
                )
            ).one()
            assert str(duplicate.reservation_id) == "019d0000-0000-7000-8000-000000002911"
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM ai_budget_reservation WHERE pipeline_run_id=CAST(:run AS uuid)"
                ),
                {"run": run_id},
            )
            await connection.execute(text("DELETE FROM ai_budget_month"))
            await connection.execute(
                text("DELETE FROM ai_pipeline_run WHERE id=CAST(:run AS uuid)"),
                {"run": run_id},
            )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _require_isolated_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0020_ai_content_preparation")
    asyncio.run(_verify_upgrade(database_url))
    asyncio.run(_verify_budget_ledger(database_url))
    command.downgrade(config, "0019_source_content_bridge")
    asyncio.run(_verify_rollback(database_url))
    command.upgrade(config, "0020_ai_content_preparation")
    asyncio.run(_verify_upgrade(database_url))
    print("R-AI01 migration replay passed: 0019 -> 0020 -> 0019 -> 0020")


if __name__ == "__main__":
    main()
