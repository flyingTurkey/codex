"""Append an explicit Owner override for a preserved NO_GO Owner Gold attempt."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.intelligence_v2.gold_calibration import (
    OWNER_GOLD_CORPUS_VERSION,
    CalibrationFact,
    apply_owner_override_go,
    calibrate_owner_gold,
)
from srbg_api.intelligence_v2.owner_gold_calibration_service import (
    OwnerGoldCalibrationService,
    PostgresOwnerGoldCalibrationRepository,
)
from srbg_api.intelligence_v2.owner_gold_preparation import PredictionSeal

try:
    from scripts.annotate_intelligence_v2_owner_gold import finalize_annotations
    from scripts.calibrate_intelligence_v2_owner_gold import _annotations, _predictions
    from scripts.persist_intelligence_v2_owner_gold_seal import _local_database_url
except ModuleNotFoundError:  # Direct ``python scripts/...py`` execution.
    from annotate_intelligence_v2_owner_gold import (
        finalize_annotations,  # type: ignore[import-not-found, no-redef]
    )
    from calibrate_intelligence_v2_owner_gold import (  # type: ignore[import-not-found, no-redef]
        _annotations,
        _predictions,
    )
    from persist_intelligence_v2_owner_gold_seal import (
        _local_database_url,  # type: ignore[import-not-found, no-redef]
    )

_ROOT = Path(__file__).resolve().parents[1]
_ACKNOWLEDGEMENT = "AUTHORIZE_DOT4_IMMEDIATE_PRODUCTION_AUTO_PASS"
_HISTORICAL_ACKNOWLEDGEMENT = "AUTHORIZE_EXISTING_OWNER_LABELS_AS_HISTORICAL_GO"


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    raise TypeError(type(value).__name__)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_once(path: Path, payload: object) -> None:
    content = json.dumps(
        payload,
        default=_json_default,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("OWNER_OVERRIDE_APPEND_ONLY_CONFLICT")
        return
    with path.open("xb") as stream:
        stream.write(content)


def build_historical_owner_gold_approval(
    *,
    corpus_version: str,
    rows: Sequence[dict[str, object]],
    no_go_sha256: str,
    labels_sha256: str,
    approval_timestamp: str,
) -> dict[str, object]:
    """Accept real Owner labels as historical Gold without granting production use."""

    case_ids = [str(row.get("case_id") or "") for row in rows]
    if (
        corpus_version not in {f"owner-gold-2026-07-20.{value}" for value in range(1, 5)}
        or len(rows) != 40
        or len(set(case_ids)) != 40
        or any(not case_id for case_id in case_ids)
        or any(row.get("corpus_version") != corpus_version for row in rows)
        or any(row.get("annotator_kind") != "HUMAN_OWNER" for row in rows)
        or len(no_go_sha256) != 64
        or len(labels_sha256) != 64
    ):
        raise ValueError("HISTORICAL_OWNER_LABELS_INVALID")
    distribution = Counter(str(row.get("bucket") or "") for row in rows)
    if set(distribution) - {"POSITIVE", "BOUNDARY", "NEGATIVE"}:
        raise ValueError("HISTORICAL_OWNER_LABELS_INVALID")
    return {
        "schema_version": "intelligence-v2-owner-override-go-1.0.0",
        "authority": "HUMAN_OWNER",
        "corpus_version": corpus_version,
        "approved_at": approval_timestamp,
        "decision": "GO",
        "authorization": "HISTORICAL_OWNER_LABELS_ACCEPTED",
        "production_auto_pass_eligible": False,
        "label_count": len(rows),
        "observed_distribution": {
            bucket: distribution.get(bucket, 0)
            for bucket in ("POSITIVE", "BOUNDARY", "NEGATIVE")
        },
        "preserved_no_go_sha256": no_go_sha256,
        "preserved_owner_labels_sha256": labels_sha256,
        "reason": "OWNER_EXPLICIT_OVERRIDE_EXISTING_LABEL_CONCLUSIONS",
    }


async def _persist(
    seal: PredictionSeal,
    fact: CalibrationFact,
    *,
    annotations_path: Path,
    predictions_path: Path,
    approval_sha256: str,
) -> None:
    engine = create_async_engine(_local_database_url())
    try:
        service = OwnerGoldCalibrationService(PostgresOwnerGoldCalibrationRepository(engine))
        await service.append_prediction_seal(seal)
        await service.append_calibration_fact(
            fact,
            annotations=_annotations(annotations_path),
            predictions=_predictions(predictions_path),
            owner_override_approval_sha256=approval_sha256,
        )
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--threshold-bps", type=int, default=9500)
    parser.add_argument("--acknowledgement", required=True)
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--historical-owner-labels", action="store_true")
    args = parser.parse_args(argv)
    private_root = args.private_root.resolve()
    if private_root.is_relative_to(_ROOT):
        raise ValueError("PRIVATE_OWNER_GOLD_PATH_MUST_BE_OUTSIDE_REPOSITORY")
    expected_acknowledgement = (
        _HISTORICAL_ACKNOWLEDGEMENT
        if args.historical_owner_labels
        else _ACKNOWLEDGEMENT
    )
    if args.acknowledgement != expected_acknowledgement:
        raise ValueError("OWNER_OVERRIDE_ACKNOWLEDGEMENT_INVALID")

    if args.historical_owner_labels:
        if args.persist:
            raise ValueError("HISTORICAL_OWNER_GO_CANNOT_PERSIST_PRODUCTION_FACT")
        labels_path = private_root / "attempts" / "owner-attempt-labels.jsonl"
        attempt_path = private_root / "attempts" / "owner-attempt-no-go.json"
        rows = [
            json.loads(line)
            for line in labels_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        corpus_version = str(rows[0].get("corpus_version") or "") if rows else ""
        historical_approval = build_historical_owner_gold_approval(
            corpus_version=corpus_version,
            rows=rows,
            no_go_sha256=sha256(attempt_path.read_bytes()).hexdigest(),
            labels_sha256=sha256(labels_path.read_bytes()).hexdigest(),
            approval_timestamp=datetime.now(UTC).isoformat(),
        )
        approval_sha256 = sha256(_canonical_json(historical_approval)).hexdigest()
        historical_approval["approval_sha256"] = approval_sha256
        approval_path = private_root / "authorizations" / "owner-override-go.json"
        _write_once(approval_path, historical_approval)
        print(
            "HISTORICAL_OWNER_OVERRIDE_GO_AUTHORIZED:"
            f"{corpus_version}:{approval_sha256}:{approval_path}"
        )
        return 0

    blind_path = private_root / "blind" / "blind-pack.json"
    draft_path = private_root / "annotations" / "owner-gold-draft.json"
    annotation_path = private_root / "annotations" / "owner-gold.jsonl"
    prediction_path = private_root / "predictions" / "qualification-predictions.jsonl"
    seal_path = private_root / "predictions" / "prediction-seal.json"
    corpus_path = private_root / "corpus" / "corpus-manifest.json"
    attempt_path = private_root / "attempts" / "owner-attempt-no-go.json"
    approval_path = private_root / "authorizations" / "owner-override-go.json"
    fact_path = private_root / "calibration" / "owner-override-calibration-fact.json"

    pack = json.loads(blind_path.read_text(encoding="utf-8"))
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    seal_row = json.loads(seal_path.read_text(encoding="utf-8"))
    if (
        pack.get("corpus_version") != OWNER_GOLD_CORPUS_VERSION
        or attempt.get("outcome") != "NO_GO"
        or attempt.get("production_calibration_eligible") is not False
        or seal_row.get("corpus_version") != OWNER_GOLD_CORPUS_VERSION
    ):
        raise ValueError("OWNER_OVERRIDE_SOURCE_EVIDENCE_INVALID")

    if not annotation_path.exists():
        finalize_annotations(
            pack,
            draft_path=draft_path,
            output_path=annotation_path,
            rule_version=str(seal_row["rule_version"]),
            model_id=str(seal_row["model_id"]),
            prompt_version=str(seal_row["prompt_version"]),
            annotated_at=datetime.now(UTC),
        )
    annotations = _annotations(annotation_path)
    predictions = _predictions(prediction_path)
    calibrated_at = datetime.now(UTC)
    base = calibrate_owner_gold(
        annotations,
        predictions,
        corpus_version=OWNER_GOLD_CORPUS_VERSION,
        rule_version=str(seal_row["rule_version"]),
        model_id=str(seal_row["model_id"]),
        prompt_version=str(seal_row["prompt_version"]),
        calibrated_at=calibrated_at,
        prediction_seal_sha256=str(seal_row["seal_sha256"]),
    )
    preview = apply_owner_override_go(
        base,
        annotations=annotations,
        predictions=predictions,
        approval_sha256="0" * 64,
        threshold_bps=args.threshold_bps,
    )
    approval: dict[str, object] = {
        "schema_version": "intelligence-v2-owner-override-go-1.0.0",
        "authority": "HUMAN_OWNER",
        "corpus_version": OWNER_GOLD_CORPUS_VERSION,
        "approved_at": calibrated_at,
        "authorization": "IMMEDIATE_PRODUCTION_AUTO_PASS",
        "acknowledgement": args.acknowledgement,
        "protocol_distribution": {"POSITIVE": 20, "BOUNDARY": 0, "NEGATIVE": 20},
        "threshold_bps": args.threshold_bps,
        "observed_precision_bps": preview.precision_bps,
        "observed_recall_bps": preview.recall_bps,
        "observed_locked_negative_leaks": preview.locked_negative_leaks,
        "superseded_no_go_file_sha256": sha256(attempt_path.read_bytes()).hexdigest(),
        "preserved_draft_sha256": sha256(draft_path.read_bytes()).hexdigest(),
        "corpus_manifest_file_sha256": sha256(corpus_path.read_bytes()).hexdigest(),
        "prediction_seal_file_sha256": sha256(seal_path.read_bytes()).hexdigest(),
    }
    approval_sha256 = sha256(_canonical_json(approval)).hexdigest()
    approval["approval_sha256"] = approval_sha256
    fact = apply_owner_override_go(
        base,
        annotations=annotations,
        predictions=predictions,
        approval_sha256=approval_sha256,
        threshold_bps=args.threshold_bps,
    )
    _write_once(approval_path, approval)
    _write_once(fact_path, asdict(fact))

    if args.persist:
        seal = PredictionSeal(
            **{**seal_row, "sealed_at": datetime.fromisoformat(str(seal_row["sealed_at"]))}
        )
        asyncio.run(
            _persist(
                seal,
                fact,
                annotations_path=annotation_path,
                predictions_path=prediction_path,
                approval_sha256=approval_sha256,
            )
        )
    print(
        "OWNER_OVERRIDE_GO_AUTHORIZED:"
        f"{fact.fact_sha256}:threshold={fact.auto_pass_threshold_bps}:"
        f"precision={fact.precision_bps}:recall={fact.recall_bps}:"
        f"locked_negative_leaks={fact.locked_negative_leaks}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
