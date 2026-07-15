"""Offline evaluation for the versioned Round 08 internal fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from srbg_api.intelligence_resolution.domain import DeduplicationDocument, assess_duplicate


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    pair_count: int
    event_count: int
    precision_bps: int
    recall_bps: int
    cluster_purity_bps: int
    evaluation_tier: str = "INTERNAL_TEST_FIXTURE"
    auto_merge_enabled: bool = False
    rule_version: str = "dedup-v1.0.0"


def _document(payload: dict[str, Any]) -> DeduplicationDocument:
    occurred_at = payload.get("occurred_at")
    return DeduplicationDocument(
        **(payload | {"occurred_at": datetime.fromisoformat(occurred_at) if occurred_at else None})
    )


def evaluate_fixture_files(pair_path: Path, event_path: Path) -> EvaluationResult:
    true_positive = false_positive = false_negative = 0
    pair_count = 0
    with pair_path.open(encoding="utf-8") as stream:
        for line in stream:
            pair_count += 1
            row = json.loads(line)
            assessment = assess_duplicate(_document(row["left"]), _document(row["right"]))
            predicted = assessment.recommendation in {"EXACT_DUPLICATE", "POSSIBLE_DUPLICATE"}
            expected = bool(row["expected_duplicate"])
            true_positive += int(predicted and expected)
            false_positive += int(predicted and not expected)
            false_negative += int(not predicted and expected)

    precision_bps = true_positive * 10_000 // max(1, true_positive + false_positive)
    recall_bps = true_positive * 10_000 // max(1, true_positive + false_negative)

    event_count = correct_members = total_members = 0
    with event_path.open(encoding="utf-8") as stream:
        for line in stream:
            event_count += 1
            row = json.loads(line)
            gold = row["gold_cluster"]
            labels = row["predicted_clusters"]
            counts: dict[str, int] = {}
            for label in labels:
                counts[label] = counts.get(label, 0) + 1
            correct_members += max(counts.values()) if counts and gold else 0
            total_members += len(labels)
    purity_bps = correct_members * 10_000 // max(1, total_members)
    return EvaluationResult(
        pair_count=pair_count,
        event_count=event_count,
        precision_bps=precision_bps,
        recall_bps=recall_bps,
        cluster_purity_bps=purity_bps,
    )
