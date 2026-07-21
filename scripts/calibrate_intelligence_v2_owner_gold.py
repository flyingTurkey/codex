"""Calibrate a versioned auto-pass fact from private Owner labels and predictions."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from srbg_api.intelligence_v2.gold_calibration import (
    Bucket,
    CandidatePrediction,
    OwnerGoldAnnotation,
    calibrate_owner_gold,
)
from srbg_contracts import (
    EngineeringObject,
    EquipmentFacet,
    PrimaryIntelligenceType,
    SpecialtyFacet,
)

_ROOT = Path(__file__).resolve().parents[1]
_ANNOTATION_SCHEMA = (
    _ROOT
    / "docs/codex-kit/assets/validation/intelligence_v2_owner_gold_annotation.schema.json"
)
_PREDICTION_SCHEMA = (
    _ROOT
    / "docs/codex-kit/assets/validation/intelligence_v2_qualification_prediction.schema.json"
)


def _read_jsonl(path: Path, *, schema_path: Path) -> list[dict[str, Any]]:
    validator = Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number} must contain one JSON object")
        validator.validate(value)
        values.append(value)
    return values


def _annotations(path: Path) -> list[OwnerGoldAnnotation]:
    values: list[OwnerGoldAnnotation] = []
    for row in _read_jsonl(path, schema_path=_ANNOTATION_SCHEMA):
        values.append(
            OwnerGoldAnnotation(
                case_id=str(row["case_id"]),
                bucket=cast(Bucket, str(row["bucket"])),
                annotator_kind=cast("Any", row["annotator_kind"]),
                content_sha256=str(row["content_sha256"]),
                raw_object_sha256=str(row["raw_object_sha256"]),
                annotated_at=datetime.fromisoformat(str(row["annotated_at"])),
                rule_version=str(row["rule_version"]),
                model_id=str(row["model_id"]),
                prompt_version=str(row["prompt_version"]),
                corpus_version=str(row["corpus_version"]),
                schema_version=str(row["schema_version"]),
                evidence_locator=str(row["evidence_locator"]),
                expected_relevant=row["expected_relevant"] is True,
                primary_type=(
                    PrimaryIntelligenceType(str(row["primary_type"]))
                    if row.get("primary_type") is not None
                    else None
                ),
                engineering_objects=tuple(
                    EngineeringObject(str(value)) for value in row["engineering_objects"]
                ),
                specialty_facets=tuple(
                    SpecialtyFacet(str(value)) for value in row["specialty_facets"]
                ),
                equipment_domains=tuple(
                    EquipmentFacet(str(value)) for value in row["equipment_domains"]
                ),
                locked_negative=row["locked_negative"] is True,
            )
        )
    return values


def _predictions(path: Path) -> list[CandidatePrediction]:
    values: list[CandidatePrediction] = []
    for row in _read_jsonl(path, schema_path=_PREDICTION_SCHEMA):
        values.append(
            CandidatePrediction(
                case_id=str(row["case_id"]),
                content_sha256=str(row["content_sha256"]),
                model_id=str(row["model_id"]),
                prompt_version=str(row["prompt_version"]),
                corpus_version=str(row["corpus_version"]),
                rule_version=str(row["rule_version"]),
                schema_version=str(row["schema_version"]),
                predicted_at=datetime.fromisoformat(str(row["predicted_at"])),
                input_sha256=str(row["input_sha256"]),
                predicted_relevant=row["predicted_relevant"] is True,
                primary_type=(
                    PrimaryIntelligenceType(str(row["primary_type"]))
                    if row.get("primary_type") is not None
                    else None
                ),
                confidence_bps=int(row["confidence_bps"]),
            )
        )
    return values


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corpus-version", required=True)
    parser.add_argument("--rule-version", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--calibrated-at", required=True)
    parser.add_argument("--prediction-seal-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        fact = calibrate_owner_gold(
            _annotations(args.annotations),
            _predictions(args.predictions),
            corpus_version=args.corpus_version,
            rule_version=args.rule_version,
            model_id=args.model_id,
            prompt_version=args.prompt_version,
            calibrated_at=datetime.fromisoformat(args.calibrated_at),
            prediction_seal_sha256=args.prediction_seal_sha256,
        )
        result: dict[str, object] = asdict(fact)
        exit_code = 0 if fact.authorizes_auto_pass else 1
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError):
        result = {
            "schema_version": "intelligence-v2-owner-gold-calibration-attempt-1.0.0",
            "corpus_version": args.corpus_version,
            "rule_version": args.rule_version,
            "model_id": args.model_id,
            "prompt_version": args.prompt_version,
            "calibrated_at": args.calibrated_at,
            "prediction_seal_sha256": args.prediction_seal_sha256,
            "label_authority": "UNVERIFIED",
            "decision": "NO_GO",
            "reasons": ["OWNER_GOLD_INPUT_INVALID"],
            "authorizes_auto_pass": False,
            "auto_pass_threshold_bps": None,
        }
        exit_code = 1
    rendered = json.dumps(
        result, default=_json_default, ensure_ascii=False, indent=2, sort_keys=True
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
