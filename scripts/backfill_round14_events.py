"""Run the resumable Round 14 Event identity shadow backfill."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from srbg_api.config import get_settings
from srbg_api.database import create_publication_engine
from srbg_api.event_unification.backfill import backfill_event_unification


async def _run() -> None:
    engine = create_publication_engine(get_settings())
    try:
        report = await backfill_event_unification(engine)
        print(json.dumps(asdict(report), default=str, sort_keys=True))
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
