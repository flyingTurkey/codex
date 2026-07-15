"""Build and reconcile the Round 13 shadow projection without switching consumers."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from srbg_api.config import get_settings
from srbg_api.database import create_publication_engine
from srbg_api.internal_projection.backfill import SYSTEM_ACTOR
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService


async def _run() -> None:
    policy_root = Path("docs/codex-kit/assets/validation")
    service = PublicationService(
        repository=PostgresPublicationRepository(create_publication_engine(get_settings())),
        gate=PublicationGate.from_files(
            policy_root / "publication_gate.json",
            policy_root / "publication_evaluation.schema.json",
        ),
    )
    try:
        report = await service.build_internal_projection(actor_id=SYSTEM_ACTOR)
        print(json.dumps(asdict(report), default=str, sort_keys=True))
    finally:
        await service.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
