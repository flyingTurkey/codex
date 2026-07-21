"""Retarget a preserved source pool through an explicit, hashed amendment."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import cast


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def apply_source_pool_amendment(
    base: Mapping[str, object], amendment: Mapping[str, object]
) -> dict[str, object]:
    if (
        base.get("schema_version") != "intelligence-v2-owner-gold-source-pool-1.0.0"
        or amendment.get("schema_version")
        != "intelligence-v2-owner-gold-source-pool-amendment-1.0.0"
    ):
        raise ValueError("OWNER_GOLD_SOURCE_POOL_AMENDMENT_SCHEMA_INVALID")
    expected_hash = amendment.get("base_source_pool_sha256")
    if expected_hash is not None and expected_hash != sha256(_canonical_json(base)).hexdigest():
        raise ValueError("OWNER_GOLD_SOURCE_POOL_AMENDMENT_BASE_HASH_MISMATCH")
    raw_slots = base.get("slots")
    raw_replacements = amendment.get("replacements")
    if not isinstance(raw_slots, dict) or not isinstance(raw_replacements, dict):
        raise ValueError("OWNER_GOLD_SOURCE_POOL_AMENDMENT_INVALID")
    if not raw_replacements or not set(raw_replacements).issubset(raw_slots):
        raise ValueError("OWNER_GOLD_SOURCE_POOL_AMENDMENT_SLOT_INVALID")
    resolved = json.loads(json.dumps(base, ensure_ascii=False))
    slots = cast(dict[str, object], resolved["slots"])
    for slot, alternatives in raw_replacements.items():
        if not isinstance(alternatives, list) or len(alternatives) < 2:
            raise ValueError("OWNER_GOLD_SOURCE_POOL_AMENDMENT_CANDIDATES_INVALID")
        slots[str(slot)] = alternatives
    corpus_version = str(amendment.get("corpus_version") or "")
    preregistered_at = str(amendment.get("preregistered_at") or "")
    if not corpus_version or not preregistered_at:
        raise ValueError("OWNER_GOLD_SOURCE_POOL_AMENDMENT_VERSION_INVALID")
    resolved["corpus_version"] = corpus_version
    resolved["preregistered_at"] = preregistered_at
    resolved["supersedes_source_pool_sha256"] = sha256(_canonical_json(base)).hexdigest()
    resolved["amendment_sha256"] = sha256(_canonical_json(amendment)).hexdigest()
    return cast(dict[str, object], resolved)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-source-pool", type=Path, required=True)
    parser.add_argument("--amendment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("OWNER_GOLD_SOURCE_POOL_ALREADY_EXISTS")
    resolved = apply_source_pool_amendment(
        json.loads(args.base_source_pool.read_text(encoding="utf-8")),
        json.loads(args.amendment.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(resolved, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OWNER_GOLD_SOURCE_POOL_RETARGETED:{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
