"""Build and reconcile the Round 13 shadow projection without switching consumers."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from srbg_api.config import get_settings
from srbg_api.database import create_publication_engine
from srbg_api.internal_projection.backfill import backfill_internal_projection


async def _run() -> None:
    engine = create_publication_engine(get_settings())
    try:
        report = await backfill_internal_projection(engine)
        print(json.dumps(asdict(report), default=str, sort_keys=True))
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
