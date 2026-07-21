"""Private Owner Gold corpus freezing, prediction sealing and blind projection."""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

SamplingStratum = Literal["POSITIVE", "BOUNDARY", "NEGATIVE"]
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_PRIMARY_TYPES = {
    "DIGITAL_TRANSFORMATION",
    "SAFETY_INTELLIGENCE",
    "INDUSTRY_UPDATE",
}


@dataclass(frozen=True)
class FrozenCorpusCase:
    case_id: str
    corpus_version: str
    sampling_stratum: SamplingStratum
    sampling_primary_type: str | None
    title: str
    source_url: str
    rights_basis: str
    retrieved_at: datetime
    raw_object_path: str
    raw_object_sha256: str
    normalized_content: str
    content_sha256: str
    evidence_locators: tuple[str, ...]


@dataclass(frozen=True)
class IndependentPrediction:
    case_id: str
    corpus_version: str
    content_sha256: str
    rule_version: str
    model_id: str
    prompt_version: str
    schema_version: str
    predicted_at: datetime
    predicted_relevant: bool
    primary_type: str | None
    confidence_bps: int
    input_sha256: str


@dataclass(frozen=True)
class PredictionSeal:
    seal_version: str
    corpus_version: str
    rule_version: str
    model_id: str
    prompt_version: str
    schema_version: str
    case_count: int
    corpus_manifest_sha256: str
    prediction_manifest_sha256: str
    sealed_at: datetime
    seal_sha256: str


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        default=lambda item: item.isoformat() if isinstance(item, datetime) else item,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _manifest_sha256(values: list[object]) -> str:
    return sha256(_canonical_json(values)).hexdigest()


def prediction_manifest_sha256(predictions: Sequence[object]) -> str:
    """Recompute the canonical prediction-manifest hash for persistence checks."""

    return _manifest_sha256([vars(value) for value in predictions])


def prediction_seal_sha256(seal: PredictionSeal) -> str:
    """Recompute the seal hash from every immutable server-owned field."""

    payload = asdict(seal)
    payload.pop("seal_sha256")
    return sha256(_canonical_json(payload)).hexdigest()


def validate_prediction_seal(seal: PredictionSeal) -> None:
    """Fail closed when a caller-supplied seal is incomplete or has been altered."""

    if (
        seal.seal_version != "intelligence-v2-owner-gold-prediction-seal-1.0.0"
        or not all(
            value.strip()
            for value in (
                seal.corpus_version,
                seal.rule_version,
                seal.model_id,
                seal.prompt_version,
                seal.schema_version,
            )
        )
        or seal.case_count != 40
        or seal.sealed_at.tzinfo is None
        or not _SHA256.fullmatch(seal.corpus_manifest_sha256)
        or not _SHA256.fullmatch(seal.prediction_manifest_sha256)
        or not _SHA256.fullmatch(seal.seal_sha256)
        or seal.seal_sha256 != prediction_seal_sha256(seal)
    ):
        raise ValueError("PREDICTION_SEAL_AUTHENTICITY_INVALID")


def _validate_corpus(cases: list[FrozenCorpusCase], *, corpus_version: str) -> None:
    ids = [case.case_id for case in cases]
    distribution = Counter(case.sampling_stratum for case in cases)
    positive_types = Counter(
        case.sampling_primary_type for case in cases if case.sampling_stratum == "POSITIVE"
    )
    if len(cases) != 40 or distribution != {
        "POSITIVE": 20,
        "NEGATIVE": 20,
    }:
        raise ValueError("OWNER_GOLD_CORPUS_DISTRIBUTION_INVALID")
    if positive_types != {
        "DIGITAL_TRANSFORMATION": 7,
        "SAFETY_INTELLIGENCE": 7,
        "INDUSTRY_UPDATE": 6,
    }:
        raise ValueError("OWNER_GOLD_CORPUS_PRIMARY_TYPE_DISTRIBUTION_INVALID")
    if len(set(ids)) != 40 or any(not value for value in ids):
        raise ValueError("OWNER_GOLD_CORPUS_CASE_ID_INVALID")
    if any(
        case.corpus_version != corpus_version
        or not case.title.strip()
        or not case.source_url.startswith("https://")
        or not case.rights_basis.strip()
        or case.retrieved_at.tzinfo is None
        or not _SHA256.fullmatch(case.raw_object_sha256)
        or not _SHA256.fullmatch(case.content_sha256)
        or not case.normalized_content.strip()
        or not case.evidence_locators
        or any(not locator.strip() for locator in case.evidence_locators)
        or (
            case.sampling_stratum == "POSITIVE" and case.sampling_primary_type not in _PRIMARY_TYPES
        )
        or (case.sampling_stratum != "POSITIVE" and case.sampling_primary_type is not None)
        for case in cases
    ):
        raise ValueError("OWNER_GOLD_CORPUS_PROVENANCE_INVALID")


def seal_predictions(
    cases: list[FrozenCorpusCase],
    predictions: list[IndependentPrediction],
    *,
    corpus_version: str,
    rule_version: str,
    model_id: str,
    prompt_version: str,
    schema_version: str,
    sealed_at: datetime,
    annotations_path: Path,
) -> PredictionSeal:
    """Authenticate a complete prediction set before any Owner annotation exists."""

    if annotations_path.exists():
        raise ValueError("OWNER_ANNOTATIONS_ALREADY_EXIST")
    if sealed_at.tzinfo is None:
        raise ValueError("PREDICTION_SEAL_TIMESTAMP_INVALID")
    _validate_corpus(cases, corpus_version=corpus_version)
    case_by_id = {case.case_id: case for case in cases}
    prediction_ids = [prediction.case_id for prediction in predictions]
    if (
        len(predictions) != 40
        or len(set(prediction_ids)) != 40
        or set(prediction_ids) != set(case_by_id)
    ):
        raise ValueError("PREDICTIONS_INCOMPLETE")
    if any(
        prediction.predicted_at.tzinfo is None or prediction.predicted_at > sealed_at
        for prediction in predictions
    ):
        raise ValueError("PREDICTION_TIMESTAMP_INVALID")
    if any(
        prediction.corpus_version != corpus_version
        or prediction.rule_version != rule_version
        or prediction.model_id != model_id
        or prediction.prompt_version != prompt_version
        or prediction.schema_version != schema_version
        or prediction.content_sha256 != case_by_id[prediction.case_id].content_sha256
        or prediction.input_sha256 != prediction.content_sha256
        or not 0 <= prediction.confidence_bps <= 10_000
        or (prediction.predicted_relevant and prediction.primary_type not in _PRIMARY_TYPES)
        or (not prediction.predicted_relevant and prediction.primary_type is not None)
        for prediction in predictions
    ):
        raise ValueError("PREDICTION_VERSION_OR_HASH_INVALID")
    corpus_hash = _manifest_sha256([asdict(case) for case in cases])
    prediction_hash = prediction_manifest_sha256(predictions)
    seal = PredictionSeal(
        seal_version="intelligence-v2-owner-gold-prediction-seal-1.0.0",
        corpus_version=corpus_version,
        rule_version=rule_version,
        model_id=model_id,
        prompt_version=prompt_version,
        schema_version=schema_version,
        case_count=40,
        corpus_manifest_sha256=corpus_hash,
        prediction_manifest_sha256=prediction_hash,
        sealed_at=sealed_at,
        seal_sha256="",
    )
    return replace(seal, seal_sha256=prediction_seal_sha256(seal))


def build_blind_pack(cases: list[FrozenCorpusCase], *, seal: PredictionSeal) -> dict[str, object]:
    """Project corpus evidence without sampling targets or model predictions."""

    _validate_corpus(cases, corpus_version=seal.corpus_version)
    if _manifest_sha256([asdict(case) for case in cases]) != seal.corpus_manifest_sha256:
        raise ValueError("CORPUS_MANIFEST_HASH_MISMATCH")
    seed = int(sha256(f"{seal.corpus_version}:{seal.seal_sha256}".encode()).hexdigest(), 16)
    ordered = list(cases)
    random.Random(seed).shuffle(ordered)  # noqa: S311 - reproducible blinding, not security
    return {
        "schema_version": "intelligence-v2-owner-gold-blind-pack-1.0.0",
        "corpus_version": seal.corpus_version,
        "prediction_seal_sha256": seal.seal_sha256,
        "cases": [
            {
                "case_id": case.case_id,
                "title": case.title,
                "source_url": case.source_url,
                "rights_basis": case.rights_basis,
                "retrieved_at": case.retrieved_at.isoformat(),
                "raw_object_path": case.raw_object_path,
                "raw_object_sha256": case.raw_object_sha256,
                "normalized_content": case.normalized_content,
                "content_sha256": case.content_sha256,
                "evidence_locators": list(case.evidence_locators),
            }
            for case in ordered
        ],
    }
