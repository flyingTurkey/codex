"""Verify the durable Owner Gold seal, least privilege and append-only trigger."""

from __future__ import annotations

import asyncio

from persist_intelligence_v2_owner_gold_seal import _local_database_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def _verify() -> None:
    engine = create_async_engine(_local_database_url())
    try:
        async with engine.connect() as connection:
            count = (
                await connection.execute(
                    text(
                        "SELECT count(id) FROM owner_gold_prediction_seal_v2 "
                        "WHERE corpus_version=:corpus_version AND case_count=40"
                    ),
                    {"corpus_version": "owner-gold-2026-07-20.4"},
                )
            ).scalar_one()
            grants = (
                await connection.execute(
                    text(
                        "SELECT count(id) FROM owner_gold_calibration_v2 "
                        "WHERE prediction_seal_sha256=("
                        "SELECT prediction_seal_sha256 "
                        "FROM owner_gold_prediction_seal_v2 "
                        "WHERE corpus_version=:corpus_version) "
                        "AND decision='GO' AND authorizes_auto_pass=true"
                    ),
                    {"corpus_version": "owner-gold-2026-07-20.4"},
                )
            ).scalar_one()
            permissions = (
                await connection.execute(
                    text(
                        "SELECT "
                        "has_table_privilege('srbg_api_role',"
                        "'owner_gold_prediction_seal_v2','insert'),"
                        "has_table_privilege('srbg_worker_role',"
                        "'owner_gold_prediction_seal_v2','select'),"
                        "has_table_privilege('srbg_worker_role',"
                        "'owner_gold_prediction_seal_v2','update'),"
                        "has_table_privilege('srbg_publication_writer',"
                        "'owner_gold_prediction_seal_v2','select')"
                    )
                )
            ).one()
            await connection.rollback()
            transaction = await connection.begin()
            blocked = False
            try:
                await connection.execute(
                    text(
                        "UPDATE owner_gold_prediction_seal_v2 SET case_count=40 "
                        "WHERE corpus_version=:corpus_version"
                    ),
                    {"corpus_version": "owner-gold-2026-07-20.4"},
                )
            except Exception:
                blocked = True
            finally:
                await transaction.rollback()
        if (
            count != 1
            or grants != 0
            or tuple(permissions) != (True, True, False, True)
            or not blocked
        ):
            raise RuntimeError("OWNER_GOLD_PREDICTION_SEAL_DATABASE_VERIFICATION_FAILED")
    finally:
        await engine.dispose()
    print("OWNER_GOLD_PREDICTION_SEAL_DATABASE_VERIFIED")


if __name__ == "__main__":
    asyncio.run(_verify())
