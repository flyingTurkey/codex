"""Periodically anchor the latest audit-chain root to independent object storage."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from srbg_api.config import get_settings
from srbg_api.database import create_publication_engine
from srbg_api.internal_projection.audit_anchor import anchor_latest_audit_root


async def _run() -> None:
    settings = get_settings()
    engine = create_publication_engine(settings)
    try:
        result = await anchor_latest_audit_root(engine, settings)
        print(json.dumps(asdict(result), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
