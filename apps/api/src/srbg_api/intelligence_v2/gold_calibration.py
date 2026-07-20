"""Versioned Owner-gold calibration facts for qualification auto-pass policy."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Literal

from srbg_contracts import (
    EngineeringObject,
    EquipmentFacet,
    PrimaryIntelligenceType,
    SpecialtyFacet,
)

Bucket = Literal["POSITIVE", "BOUNDARY", "NEGATIVE"]
Decision = Literal["GO", "NO_GO"]
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class OwnerGoldAnnotation:
    case_id: str
    bucket: Bucket
    annotator_kind: Literal["HUMAN_OWNER"]
    content_sha256: str
    raw_object_sha256: str
    annotated_at: datetime
    rule_version: str
    model_id: str
    prompt_version: str
    evidence_locator: str
    expected_relevant: bool
    primary_type: PrimaryIntelligenceType | None
    engineering_objects: tuple[EngineeringObject, ...]
    specialty_facets: tuple[SpecialtyFacet, ...]
    equipment_domains: tuple[EquipmentFacet, ...]
    locked_negative: bool


@dataclass(frozen=True)
class CandidatePrediction:
    case_id: str
    content_sha256: str
    model_id: str
    prompt_version: str
    predicted_relevant: bool
    primary_type: PrimaryIntelligenceType | None
    confidence_bps: int


@dataclass(frozen=True)
class SliceMetrics:
    sample_count: int
    precision_bps: int
    recall_bps: int


@dataclass(frozen=True)
class CalibrationFact:
    fact_version: str
    corpus_version: str
    rule_version: str
    model_id: str
    prompt_version: str
    calibrated_at: datetime
    label_authority: Literal["HUMAN_OWNER"]
    decision: Decision
    reasons: tuple[str, ...]
    authorizes_auto_pass: bool
    auto_pass_threshold_bps: int | None
    precision_bps: int
    recall_bps: int
    locked_negative_leaks: int
    primary_type_slices: dict[PrimaryIntelligenceType, SliceMetrics]
    engineering_object_slices: dict[EngineeringObject, SliceMetrics]
    specialty_facet_slices: dict[SpecialtyFacet, SliceMetrics]
    equipment_domain_slices: dict[EquipmentFacet, SliceMetrics]
    evidence_manifest_sha256: str
    fact_sha256: str


@dataclass(frozen=True)
class AutoPassCalibrationGrant:
    threshold_bps: int
    corpus_version: str
    rule_version: str
    model_id: str
    prompt_version: str
    fact_sha256: str


def calibration_grant(
    fact: CalibrationFact,
    *,
    rule_version: str,
    model_id: str,
    prompt_version: str,
) -> AutoPassCalibrationGrant | None:
    """Return a usable grant only for an exact, successful version tuple."""

    if (
        fact.fact_sha256 != calibration_fact_sha256(fact)
        or fact.decision != "GO"
        or not fact.authorizes_auto_pass
        or fact.auto_pass_threshold_bps is None
        or fact.rule_version != rule_version
        or fact.model_id != model_id
        or fact.prompt_version != prompt_version
    ):
        return None
    return AutoPassCalibrationGrant(
        threshold_bps=fact.auto_pass_threshold_bps,
        corpus_version=fact.corpus_version,
        rule_version=fact.rule_version,
        model_id=fact.model_id,
        prompt_version=fact.prompt_version,
        fact_sha256=fact.fact_sha256,
    )


def calibration_fact_sha256(fact: CalibrationFact) -> str:
    payload = asdict(fact)
    payload.pop("fact_sha256")
    return sha256(_canonical_json(payload)).hexdigest()


def _load_slices[
    SliceKey: (EngineeringObject, PrimaryIntelligenceType, SpecialtyFacet, EquipmentFacet)
](
    value: object,
    enum_type: type[SliceKey],
) -> dict[SliceKey, SliceMetrics]:
    if not isinstance(value, dict):
        raise ValueError("calibration slice metrics must be an object")
    loaded: dict[SliceKey, SliceMetrics] = {}
    for raw_key, raw_metrics in value.items():
        if not isinstance(raw_metrics, dict):
            raise ValueError("calibration slice entry must be an object")
        loaded[enum_type(str(raw_key))] = SliceMetrics(
            sample_count=int(raw_metrics["sample_count"]),
            precision_bps=int(raw_metrics["precision_bps"]),
            recall_bps=int(raw_metrics["recall_bps"]),
        )
    return loaded


def load_calibration_fact(path: Path) -> CalibrationFact:
    """Load and authenticate one CLI-produced calibration fact."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("calibration fact must be an object")
    fact = CalibrationFact(
        fact_version=str(value["fact_version"]),
        corpus_version=str(value["corpus_version"]),
        rule_version=str(value["rule_version"]),
        model_id=str(value["model_id"]),
        prompt_version=str(value["prompt_version"]),
        calibrated_at=datetime.fromisoformat(str(value["calibrated_at"])),
        label_authority=value["label_authority"],
        decision=value["decision"],
        reasons=tuple(str(reason) for reason in value["reasons"]),
        authorizes_auto_pass=value["authorizes_auto_pass"] is True,
        auto_pass_threshold_bps=(
            int(value["auto_pass_threshold_bps"])
            if value.get("auto_pass_threshold_bps") is not None
            else None
        ),
        precision_bps=int(value["precision_bps"]),
        recall_bps=int(value["recall_bps"]),
        locked_negative_leaks=int(value["locked_negative_leaks"]),
        primary_type_slices=_load_slices(
            value["primary_type_slices"], PrimaryIntelligenceType
        ),
        engineering_object_slices=_load_slices(
            value["engineering_object_slices"], EngineeringObject
        ),
        specialty_facet_slices=_load_slices(
            value["specialty_facet_slices"], SpecialtyFacet
        ),
        equipment_domain_slices=_load_slices(
            value["equipment_domain_slices"], EquipmentFacet
        ),
        evidence_manifest_sha256=str(value["evidence_manifest_sha256"]),
        fact_sha256=str(value["fact_sha256"]),
    )
    if (
        fact.fact_version != "intelligence-v2-owner-gold-calibration-1.0.0"
        or fact.label_authority != "HUMAN_OWNER"
        or fact.calibrated_at.tzinfo is None
        or not _SHA256.fullmatch(fact.evidence_manifest_sha256)
        or not _SHA256.fullmatch(fact.fact_sha256)
        or fact.fact_sha256 != calibration_fact_sha256(fact)
    ):
        raise ValueError("calibration fact authenticity validation failed")
    return fact


def _basis_points(numerator: int, denominator: int) -> int:
    return 0 if denominator == 0 else numerator * 10_000 // denominator


def _canonical_json(value: object) -> bytes:
    def encode(item: object) -> object:
        if isinstance(item, datetime):
            return item.isoformat()
        if is_dataclass(item) and not isinstance(item, type):
            return asdict(item)
        if isinstance(item, StrEnum):
            return item.value
        raise TypeError(f"unsupported canonical JSON value: {type(item).__name__}")

    return json.dumps(
        value,
        default=encode,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _metrics(
    annotations: list[OwnerGoldAnnotation],
    predictions: dict[str, CandidatePrediction],
    threshold_bps: int,
) -> tuple[int, int, int]:
    passed = [
        (annotation, predictions[annotation.case_id])
        for annotation in annotations
        if predictions[annotation.case_id].predicted_relevant
        and predictions[annotation.case_id].confidence_bps >= threshold_bps
    ]
    true_positive = sum(
        annotation.expected_relevant and prediction.primary_type == annotation.primary_type
        for annotation, prediction in passed
    )
    expected_positive = sum(annotation.expected_relevant for annotation in annotations)
    leaks = sum(annotation.locked_negative for annotation, _prediction in passed)
    return (
        _basis_points(true_positive, len(passed)),
        _basis_points(true_positive, expected_positive),
        leaks,
    )


def _slice_metrics(
    annotations: list[OwnerGoldAnnotation],
    predictions: dict[str, CandidatePrediction],
    threshold_bps: int,
) -> SliceMetrics:
    precision, recall, _leaks = _metrics(annotations, predictions, threshold_bps)
    return SliceMetrics(len(annotations), precision, recall)


def _validation_reasons(
    annotations: list[OwnerGoldAnnotation],
    predictions: list[CandidatePrediction],
    *,
    rule_version: str,
    model_id: str,
    prompt_version: str,
) -> list[str]:
    reasons: list[str] = []
    annotation_ids = [annotation.case_id for annotation in annotations]
    prediction_ids = [prediction.case_id for prediction in predictions]
    if len(set(annotation_ids)) != len(annotation_ids) or any(
        not value for value in annotation_ids
    ):
        reasons.append("OWNER_GOLD_CASE_ID_INVALID")
    if len(set(prediction_ids)) != len(prediction_ids) or set(annotation_ids) != set(
        prediction_ids
    ):
        reasons.append("OWNER_GOLD_PREDICTIONS_INCOMPLETE")
    distribution = Counter(annotation.bucket for annotation in annotations)
    if len(annotations) != 360 or distribution != {
        "POSITIVE": 180,
        "BOUNDARY": 90,
        "NEGATIVE": 90,
    }:
        reasons.append("OWNER_GOLD_DISTRIBUTION_INVALID")
    positive_types = Counter(
        annotation.primary_type
        for annotation in annotations
        if annotation.bucket == "POSITIVE" and annotation.expected_relevant
    )
    if any(positive_types[value] < 60 for value in PrimaryIntelligenceType):
        reasons.append("OWNER_GOLD_PRIMARY_TYPE_COVERAGE_INVALID")
    covered_objects = {
        value for annotation in annotations for value in annotation.engineering_objects
    }
    if covered_objects != set(EngineeringObject):
        reasons.append("OWNER_GOLD_ENGINEERING_OBJECT_COVERAGE_INVALID")
    if not any(
        SpecialtyFacet.TUNNEL_GAS_MONITORING in annotation.specialty_facets
        and EngineeringObject.TUNNEL in annotation.engineering_objects
        and bool(
            {EngineeringObject.HIGHWAY, EngineeringObject.RAILWAY}
            & set(annotation.engineering_objects)
        )
        for annotation in annotations
    ):
        reasons.append("OWNER_GOLD_TUNNEL_GAS_COVERAGE_INVALID")
    if not any(
        EquipmentFacet.CONSTRUCTION_MACHINERY in annotation.equipment_domains
        for annotation in annotations
    ):
        reasons.append("OWNER_GOLD_EQUIPMENT_COVERAGE_INVALID")
    if any(
        annotation.annotator_kind != "HUMAN_OWNER"
        or not _SHA256.fullmatch(annotation.content_sha256)
        or not _SHA256.fullmatch(annotation.raw_object_sha256)
        or annotation.annotated_at.tzinfo is None
        or not annotation.evidence_locator.strip()
        for annotation in annotations
    ):
        reasons.append("OWNER_GOLD_PROVENANCE_INVALID")
    if any(
        annotation.rule_version != rule_version
        or annotation.model_id != model_id
        or annotation.prompt_version != prompt_version
        for annotation in annotations
    ):
        reasons.append("OWNER_GOLD_VERSION_MISMATCH")
    if any(
        (annotation.bucket == "POSITIVE" and not annotation.expected_relevant)
        or (annotation.bucket == "NEGATIVE" and annotation.expected_relevant)
        or (
            annotation.expected_relevant
            and (annotation.primary_type is None or not annotation.engineering_objects)
        )
        or (
            not annotation.expected_relevant
            and (annotation.primary_type is not None or bool(annotation.specialty_facets))
        )
        for annotation in annotations
    ):
        reasons.append("OWNER_GOLD_LABEL_SEMANTICS_INVALID")
    if any(
        annotation.bucket == "NEGATIVE" and not annotation.locked_negative
        for annotation in annotations
    ):
        reasons.append("OWNER_GOLD_LOCKED_NEGATIVE_INVALID")
    by_id = {annotation.case_id: annotation for annotation in annotations}
    if any(
        prediction.confidence_bps < 0
        or prediction.confidence_bps > 10_000
        or prediction.model_id != model_id
        or prediction.prompt_version != prompt_version
        or (
            prediction.case_id in by_id
            and prediction.content_sha256 != by_id[prediction.case_id].content_sha256
        )
        for prediction in predictions
    ):
        reasons.append("OWNER_GOLD_PREDICTION_VERSION_OR_HASH_MISMATCH")
    if any(
        not prediction.predicted_relevant and prediction.primary_type is not None
        for prediction in predictions
    ):
        reasons.append("OWNER_GOLD_PREDICTION_SEMANTICS_INVALID")
    return reasons


def calibrate_owner_gold(
    annotations: list[OwnerGoldAnnotation],
    predictions: list[CandidatePrediction],
    *,
    corpus_version: str,
    rule_version: str,
    model_id: str,
    prompt_version: str,
    calibrated_at: datetime,
) -> CalibrationFact:
    """Calibrate a threshold only from complete, version-matched HUMAN_OWNER evidence."""

    reasons = _validation_reasons(
        annotations,
        predictions,
        rule_version=rule_version,
        model_id=model_id,
        prompt_version=prompt_version,
    )
    if calibrated_at.tzinfo is None:
        reasons.append("OWNER_GOLD_CALIBRATION_TIMESTAMP_INVALID")
    if not all(value.strip() for value in (corpus_version, rule_version, model_id, prompt_version)):
        reasons.append("OWNER_GOLD_CALIBRATION_VERSION_INVALID")
    by_id = {prediction.case_id: prediction for prediction in predictions}
    threshold: int | None = None
    precision = recall = leaks = 0
    if not reasons:
        for candidate in sorted({prediction.confidence_bps for prediction in predictions}):
            candidate_precision, candidate_recall, candidate_leaks = _metrics(
                annotations, by_id, candidate
            )
            if candidate_precision >= 9_000 and candidate_recall >= 9_000 and not candidate_leaks:
                threshold = candidate
                precision, recall, leaks = candidate_precision, candidate_recall, candidate_leaks
                break
        if threshold is None:
            reasons.append("OWNER_GOLD_QUALITY_THRESHOLD_NOT_MET")
    decision: Decision = "NO_GO" if reasons else "GO"
    effective_threshold = threshold if threshold is not None else 10_001
    type_slices = (
        {
            value: _slice_metrics(
                [annotation for annotation in annotations if annotation.primary_type == value],
                by_id,
                effective_threshold,
            )
            for value in PrimaryIntelligenceType
        }
        if not reasons
        else {}
    )
    object_slices = (
        {
            value: _slice_metrics(
                [
                    annotation
                    for annotation in annotations
                    if value in annotation.engineering_objects
                ],
                by_id,
                effective_threshold,
            )
            for value in EngineeringObject
        }
        if not reasons
        else {}
    )
    specialty_slices = (
        {
            value: _slice_metrics(
                [annotation for annotation in annotations if value in annotation.specialty_facets],
                by_id,
                effective_threshold,
            )
            for value in SpecialtyFacet
        }
        if not reasons
        else {}
    )
    equipment_slices = (
        {
            value: _slice_metrics(
                [annotation for annotation in annotations if value in annotation.equipment_domains],
                by_id,
                effective_threshold,
            )
            for value in EquipmentFacet
        }
        if not reasons
        else {}
    )
    evidence_hash = sha256(
        _canonical_json(
            {
                "annotations": [asdict(value) for value in annotations],
                "predictions": [asdict(value) for value in predictions],
            }
        )
    ).hexdigest()
    fact = CalibrationFact(
        fact_version="intelligence-v2-owner-gold-calibration-1.0.0",
        corpus_version=corpus_version,
        rule_version=rule_version,
        model_id=model_id,
        prompt_version=prompt_version,
        calibrated_at=calibrated_at,
        label_authority="HUMAN_OWNER",
        decision=decision,
        reasons=tuple(dict.fromkeys(reasons)),
        authorizes_auto_pass=decision == "GO",
        auto_pass_threshold_bps=threshold,
        precision_bps=precision,
        recall_bps=recall,
        locked_negative_leaks=leaks,
        primary_type_slices=type_slices,
        engineering_object_slices=object_slices,
        specialty_facet_slices=specialty_slices,
        equipment_domain_slices=equipment_slices,
        evidence_manifest_sha256=evidence_hash,
        fact_sha256="",
    )
    return replace(fact, fact_sha256=calibration_fact_sha256(fact))
