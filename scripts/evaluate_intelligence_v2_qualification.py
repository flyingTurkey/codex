"""Evaluate externally supplied predictions against non-human structural replay cases."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from srbg_api.intelligence_v2.structural_corpus import (
    CORPUS_VERSION,
    STRUCTURAL_REPLAY_CORPUS,
    StructuralPrediction,
    evaluate_structural_replay,
)
from srbg_contracts import PrimaryIntelligenceType


def _predictions(path: Path) -> dict[str, StructuralPrediction]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"corpus_version", "predictions"}:
        raise ValueError("prediction input must contain only corpus_version and predictions")
    if payload["corpus_version"] != CORPUS_VERSION:
        raise ValueError("prediction corpus_version does not match the structural replay")
    rows = payload["predictions"]
    if not isinstance(rows, list):
        raise ValueError("predictions must be a list")
    known_ids = {case.case_id for case in STRUCTURAL_REPLAY_CORPUS}
    predictions: dict[str, StructuralPrediction] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "case_id",
            "directly_relevant",
            "primary_type",
        }:
            raise ValueError("each prediction must use the frozen prediction fields")
        case_id = str(row["case_id"])
        if case_id not in known_ids or case_id in predictions:
            raise ValueError("prediction case_id is unknown or duplicated")
        directly_relevant = row["directly_relevant"]
        if not isinstance(directly_relevant, bool):
            raise ValueError("directly_relevant must be boolean")
        raw_type = row["primary_type"]
        primary_type = None if raw_type is None else PrimaryIntelligenceType(str(raw_type))
        if not directly_relevant and primary_type is not None:
            raise ValueError("an irrelevant prediction cannot carry a primary type")
        predictions[case_id] = StructuralPrediction(
            directly_relevant=directly_relevant,
            primary_type=primary_type,
        )
    return predictions


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    report = evaluate_structural_replay(_predictions(args.input))
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 1 if report.failed_case_ids or report.locked_negative_leaks else 0


if __name__ == "__main__":
    raise SystemExit(main())
