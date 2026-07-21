"""Build an Owner Gold candidate frame from a compact private source pool."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

try:
    from scripts.select_intelligence_v2_owner_gold_corpus import build_candidate_frame
except ModuleNotFoundError:  # Direct ``python scripts/...py`` execution.
    from select_intelligence_v2_owner_gold_corpus import build_candidate_frame


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("OWNER_GOLD_CANDIDATE_FRAME_ALREADY_EXISTS")
    pool = json.loads(args.source_pool.read_text(encoding="utf-8"))
    if (
        pool.get("schema_version") != "intelligence-v2-owner-gold-source-pool-1.0.0"
        or pool.get("corpus_version") != "owner-gold-2026-07-20.5"
    ):
        raise ValueError("OWNER_GOLD_SOURCE_POOL_VERSION_INVALID")
    raw_slots = pool.get("slots")
    if not isinstance(raw_slots, dict):
        raise ValueError("OWNER_GOLD_SOURCE_POOL_INVALID")
    frame = build_candidate_frame(
        cast(Mapping[str, Sequence[Mapping[str, object]]], raw_slots),
        preregistered_at=datetime.fromisoformat(str(pool["preregistered_at"])),
        versions=pool,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(frame, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OWNER_GOLD_CANDIDATE_FRAME_CREATED:{frame['candidate_count']}:{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
