import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from srbg_api.ai_pipeline.contracts import ClassificationOutput
from srbg_api.intelligence_v2.gold_calibration import (
    CandidatePrediction,
    OwnerGoldAnnotation,
    calibrate_owner_gold,
    calibration_grant,
    load_calibration_fact,
)
from srbg_api.intelligence_v2.qualification import QualificationReason, qualification_reason
from srbg_contracts import (
    EngineeringObject,
    EquipmentFacet,
    PrimaryIntelligenceType,
    SpecialtyFacet,
)

from scripts.calibrate_intelligence_v2_owner_gold import main

RULE_VERSION = "intelligence-v2-qualification-1.0.0"
MODEL_ID = "deepseek-chat"
PROMPT_VERSION = "qualification-v2.0.0"
ANNOTATED_AT = datetime(2026, 7, 19, tzinfo=UTC)


def _complete_owner_corpus() -> tuple[list[OwnerGoldAnnotation], list[CandidatePrediction]]:
    annotations: list[OwnerGoldAnnotation] = []
    predictions: list[CandidatePrediction] = []
    objects = tuple(EngineeringObject)
    for primary_type in PrimaryIntelligenceType:
        for index in range(60):
            case_id = f"P-{primary_type.value}-{index:03d}"
            engineering_objects = (objects[index % len(objects)],)
            specialty_facets: tuple[SpecialtyFacet, ...] = ()
            equipment_domains: tuple[EquipmentFacet, ...] = ()
            if index == 3:
                engineering_objects = (EngineeringObject.HIGHWAY, EngineeringObject.TUNNEL)
                specialty_facets = (SpecialtyFacet.TUNNEL_GAS_MONITORING,)
            if index == 4:
                equipment_domains = (EquipmentFacet.CONSTRUCTION_MACHINERY,)
            content_hash = f"{len(annotations) + 1:064x}"
            annotations.append(
                OwnerGoldAnnotation(
                    case_id=case_id,
                    bucket="POSITIVE",
                    annotator_kind="HUMAN_OWNER",
                    content_sha256=content_hash,
                    raw_object_sha256=f"{len(annotations) + 1001:064x}",
                    annotated_at=ANNOTATED_AT,
                    rule_version=RULE_VERSION,
                    model_id=MODEL_ID,
                    prompt_version=PROMPT_VERSION,
                    evidence_locator=f"html:p:{len(annotations) + 1}",
                    expected_relevant=True,
                    primary_type=primary_type,
                    engineering_objects=engineering_objects,
                    specialty_facets=specialty_facets,
                    equipment_domains=equipment_domains,
                    locked_negative=False,
                )
            )
            predictions.append(
                CandidatePrediction(
                    case_id=case_id,
                    content_sha256=content_hash,
                    model_id=MODEL_ID,
                    prompt_version=PROMPT_VERSION,
                    predicted_relevant=True,
                    primary_type=primary_type,
                    confidence_bps=9300,
                )
            )
    for bucket, count, confidence in (("BOUNDARY", 90, 9200), ("NEGATIVE", 90, 9200)):
        for index in range(count):
            case_id = f"{bucket[0]}-{index:03d}"
            content_hash = f"{len(annotations) + 1:064x}"
            annotations.append(
                OwnerGoldAnnotation(
                    case_id=case_id,
                    bucket=bucket,
                    annotator_kind="HUMAN_OWNER",
                    content_sha256=content_hash,
                    raw_object_sha256=f"{len(annotations) + 1001:064x}",
                    annotated_at=ANNOTATED_AT,
                    rule_version=RULE_VERSION,
                    model_id=MODEL_ID,
                    prompt_version=PROMPT_VERSION,
                    evidence_locator=f"html:p:{len(annotations) + 1}",
                    expected_relevant=False,
                    primary_type=None,
                    engineering_objects=(),
                    specialty_facets=(),
                    equipment_domains=(),
                    locked_negative=bucket == "NEGATIVE",
                )
            )
            predictions.append(
                CandidatePrediction(
                    case_id=case_id,
                    content_sha256=content_hash,
                    model_id=MODEL_ID,
                    prompt_version=PROMPT_VERSION,
                    predicted_relevant=True,
                    primary_type=PrimaryIntelligenceType.INDUSTRY_UPDATE,
                    confidence_bps=confidence,
                )
            )
    return annotations, predictions


def test_complete_owner_gold_derives_threshold_from_observed_predictions() -> None:
    annotations, predictions = _complete_owner_corpus()

    fact = calibrate_owner_gold(
        annotations,
        predictions,
        corpus_version="owner-gold-2026-07-19.1",
        rule_version=RULE_VERSION,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        calibrated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    assert fact.decision == "GO"
    assert fact.authorizes_auto_pass is True
    assert fact.auto_pass_threshold_bps == 9300
    assert fact.auto_pass_threshold_bps != 9000
    assert fact.precision_bps == 10_000
    assert fact.recall_bps == 10_000
    assert fact.locked_negative_leaks == 0
    assert set(fact.primary_type_slices) == set(PrimaryIntelligenceType)
    assert set(fact.engineering_object_slices) == set(EngineeringObject)


def test_incomplete_owner_gold_fails_closed_without_a_threshold() -> None:
    annotations, predictions = _complete_owner_corpus()

    fact = calibrate_owner_gold(
        annotations[:-1],
        predictions,
        corpus_version="owner-gold-2026-07-19.1",
        rule_version=RULE_VERSION,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        calibrated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    assert fact.decision == "NO_GO"
    assert fact.authorizes_auto_pass is False
    assert fact.auto_pass_threshold_bps is None
    assert "OWNER_GOLD_DISTRIBUTION_INVALID" in fact.reasons
    assert "OWNER_GOLD_PREDICTIONS_INCOMPLETE" in fact.reasons


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value.value


def _write_jsonl(path: Path, values: list[object]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(asdict(value), default=_json_default, sort_keys=True) for value in values
        )
        + "\n",
        encoding="utf-8",
    )


def test_cli_writes_one_versioned_calibration_fact(tmp_path: Path) -> None:
    annotations, predictions = _complete_owner_corpus()
    annotation_path = tmp_path / "owner-gold.jsonl"
    prediction_path = tmp_path / "predictions.jsonl"
    output_path = tmp_path / "calibration.json"
    _write_jsonl(annotation_path, annotations)
    _write_jsonl(prediction_path, predictions)

    exit_code = main(
        [
            "--annotations",
            str(annotation_path),
            "--predictions",
            str(prediction_path),
            "--output",
            str(output_path),
            "--corpus-version",
            "owner-gold-2026-07-19.1",
            "--rule-version",
            RULE_VERSION,
            "--model-id",
            MODEL_ID,
            "--prompt-version",
            PROMPT_VERSION,
            "--calibrated-at",
            "2026-07-20T00:00:00+00:00",
        ]
    )

    fact = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert fact["fact_version"] == "intelligence-v2-owner-gold-calibration-1.0.0"
    assert fact["label_authority"] == "HUMAN_OWNER"
    assert fact["decision"] == "GO"
    assert fact["auto_pass_threshold_bps"] == 9300
    assert len(fact["evidence_manifest_sha256"]) == 64
    assert len(fact["fact_sha256"]) == 64
    loaded = load_calibration_fact(output_path)
    assert loaded.fact_sha256 == fact["fact_sha256"]
    assert (
        calibration_grant(
            loaded,
            rule_version=RULE_VERSION,
            model_id=MODEL_ID,
            prompt_version=PROMPT_VERSION,
        )
        is not None
    )


def test_high_confidence_classification_fails_closed_without_calibration() -> None:
    output = ClassificationOutput.model_validate(
        {
            "direct_relevance": "RELEVANT",
            "core_new_fact": "发布铁路隧道施工安全整治要求",
            "primary_type": "SAFETY_INTELLIGENCE",
            "engineering_objects": ["RAILWAY", "TUNNEL"],
            "specialty_facets": [],
            "equipment_domains": [],
            "content_form": "AUTHORITY_NOTICE",
            "evidence_locators": ["html:p:8"],
            "confidence": 0.99,
            "needs_human_review": False,
            "review_reasons": [],
            "security": {
                "prompt_injection_detected": False,
                "prompt_injection_status": "NONE",
                "suspicious_patterns": [],
            },
        }
    )

    assert (
        qualification_reason(output, document_text="铁路隧道施工安全整治")
        is QualificationReason.CALIBRATION_UNAVAILABLE
    )


def test_tampered_calibration_fact_cannot_issue_a_grant() -> None:
    annotations, predictions = _complete_owner_corpus()
    fact = calibrate_owner_gold(
        annotations,
        predictions,
        corpus_version="owner-gold-2026-07-19.1",
        rule_version=RULE_VERSION,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        calibrated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    assert (
        calibration_grant(
            replace(fact, auto_pass_threshold_bps=9000),
            rule_version=RULE_VERSION,
            model_id=MODEL_ID,
            prompt_version=PROMPT_VERSION,
        )
        is None
    )


def test_cli_reports_deterministic_no_go_for_invalid_private_input(tmp_path: Path) -> None:
    annotations, predictions = _complete_owner_corpus()
    annotation_path = tmp_path / "owner-gold.jsonl"
    prediction_path = tmp_path / "predictions.jsonl"
    output_path = tmp_path / "calibration.json"
    _write_jsonl(annotation_path, annotations)
    prediction_rows = [asdict(value) for value in predictions]
    prediction_rows[0]["predicted_relevant"] = "true"
    prediction_path.write_text(
        "\n".join(
            json.dumps(value, default=_json_default, sort_keys=True)
            for value in prediction_rows
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--annotations",
            str(annotation_path),
            "--predictions",
            str(prediction_path),
            "--output",
            str(output_path),
            "--corpus-version",
            "owner-gold-2026-07-19.1",
            "--rule-version",
            RULE_VERSION,
            "--model-id",
            MODEL_ID,
            "--prompt-version",
            PROMPT_VERSION,
            "--calibrated-at",
            "2026-07-20T00:00:00+00:00",
        ]
    )

    attempt = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert attempt["decision"] == "NO_GO"
    assert attempt["label_authority"] == "UNVERIFIED"
    assert attempt["reasons"] == ["OWNER_GOLD_INPUT_INVALID"]
    assert attempt["authorizes_auto_pass"] is False
    assert attempt["auto_pass_threshold_bps"] is None
