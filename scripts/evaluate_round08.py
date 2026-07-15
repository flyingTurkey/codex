"""Print Round 08 offline metrics as JSON and human-readable text."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from srbg_api.intelligence_resolution.evaluation import evaluate_fixture_files


def main() -> None:
    root = Path("apps/api/tests/fixtures/round08")
    result = evaluate_fixture_files(root / "dedup_pairs.v1.jsonl", root / "event_clusters.v1.jsonl")
    payload = asdict(result)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    print(
        "Round08 internal evaluation: "
        f"precision={result.precision_bps / 100:.2f}% "
        f"recall={result.recall_bps / 100:.2f}% "
        f"cluster_purity={result.cluster_purity_bps / 100:.2f}% "
        f"pairs={result.pair_count} events={result.event_count} "
        "auto_merge_enabled=false"
    )
    if (
        result.precision_bps < 9_800
        or result.recall_bps < 9_300
        or result.cluster_purity_bps < 9_500
    ):
        raise SystemExit("Round08 internal evaluation thresholds were not met")


if __name__ == "__main__":
    main()
