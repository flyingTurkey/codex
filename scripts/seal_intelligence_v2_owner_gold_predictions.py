"""Seal a complete private prediction set and create its prediction-blind Owner pack."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from srbg_api.intelligence_v2.owner_gold_preparation import (
    FrozenCorpusCase,
    IndependentPrediction,
    PredictionSeal,
    build_blind_pack,
    seal_predictions,
)

_ROOT = Path(__file__).resolve().parents[1]


def _private(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(_ROOT):
        raise ValueError("PRIVATE_OWNER_GOLD_PATH_MUST_BE_OUTSIDE_REPOSITORY")
    return resolved


def _write_once(path: Path, value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError(f"APPEND_ONLY_ARTIFACT_CONFLICT:{path.name}") from None
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(encoded)


def seal_private_package(output_root: Path) -> PredictionSeal:
    root = _private(output_root)
    annotations_path = root / "annotations" / "owner-gold.jsonl"
    if annotations_path.exists():
        raise ValueError("OWNER_ANNOTATIONS_ALREADY_EXIST")
    manifest = json.loads((root / "corpus" / "corpus-manifest.json").read_text(encoding="utf-8"))
    cases = [
        FrozenCorpusCase(
            **{
                **row,
                "retrieved_at": datetime.fromisoformat(row["retrieved_at"]),
                "evidence_locators": tuple(row["evidence_locators"]),
            }
        )
        for row in manifest["cases"]
    ]
    prediction_rows = [
        json.loads(line)
        for line in (root / "predictions" / "qualification-predictions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    predictions = [
        IndependentPrediction(
            **{
                **row,
                "predicted_at": datetime.fromisoformat(row["predicted_at"]),
            }
        )
        for row in prediction_rows
    ]
    seal_path = root / "predictions" / "prediction-seal.json"
    sealed_at = datetime.now(UTC)
    if seal_path.exists():
        sealed_at = datetime.fromisoformat(
            json.loads(seal_path.read_text(encoding="utf-8"))["sealed_at"]
        )
    seal = seal_predictions(
        cases,
        predictions,
        corpus_version=str(manifest["corpus_version"]),
        rule_version=str(manifest["rule_version"]),
        model_id=str(manifest["model_id"]),
        prompt_version=str(manifest["prompt_version"]),
        schema_version=str(manifest["owner_gold_schema_version"]),
        sealed_at=sealed_at,
        annotations_path=annotations_path,
    )
    _write_once(seal_path, {**asdict(seal), "sealed_at": seal.sealed_at.isoformat()})
    pack = build_blind_pack(cases, seal=seal)
    serialized = json.dumps(pack, ensure_ascii=False, sort_keys=True)
    forbidden = {
        "sampling_stratum",
        "sampling_primary_type",
        "predicted_relevant",
        "confidence_bps",
        "recommended_label",
        "model_output",
    }
    if any(token in serialized for token in forbidden):
        raise ValueError("BLIND_PACK_FIELD_LEAK")
    _write_once(root / "blind" / "blind-pack.json", pack)
    return seal


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    seal = seal_private_package(args.output_root)
    print(f"OWNER_GOLD_PREDICTIONS_SEALED:{seal.case_count}:{seal.seal_sha256}")
    print(f"OWNER_GOLD_BLIND_PACK_READY:{args.output_root.resolve() / 'blind' / 'blind-pack.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
