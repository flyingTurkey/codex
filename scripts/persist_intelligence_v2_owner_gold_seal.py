"""Persist a private Owner Gold seal through the supported append-only service."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.intelligence_v2.owner_gold_calibration_service import (
    OwnerGoldCalibrationService,
    PostgresOwnerGoldCalibrationRepository,
)
from srbg_api.intelligence_v2.owner_gold_preparation import PredictionSeal


def _local_database_url() -> str:
    configured = os.environ.get("SRBG_DATABASE_URL")
    if configured:
        return configured
    values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    user = values.get("POSTGRES_USER") or "srbg"
    password = values.get("POSTGRES_PASSWORD") or "srbg_local_only"
    database = values.get("POSTGRES_DB") or "srbg"
    return f"postgresql+asyncpg://{user}:{password}@127.0.0.1:15432/{database}"


async def _persist(seal: PredictionSeal) -> PredictionSeal:
    engine = create_async_engine(_local_database_url())
    try:
        service = OwnerGoldCalibrationService(PostgresOwnerGoldCalibrationRepository(engine))
        await service.append_prediction_seal(seal)
    finally:
        await engine.dispose()
    return seal


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal", required=True, type=Path)
    args = parser.parse_args(argv)
    row = json.loads(args.seal.resolve().read_text(encoding="utf-8"))
    candidate = PredictionSeal(**{**row, "sealed_at": datetime.fromisoformat(row["sealed_at"])})
    seal = asyncio.run(_persist(candidate))
    print(f"OWNER_GOLD_PREDICTION_SEAL_PERSISTED:{seal.seal_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
