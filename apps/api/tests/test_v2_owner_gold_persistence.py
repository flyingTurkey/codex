from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from srbg_api.intelligence_v2.gold_calibration import (
    CalibrationFact,
    CandidatePrediction,
    OwnerGoldAnnotation,
    apply_owner_override_go,
    calibrate_owner_gold,
    calibration_fact_sha256,
)
from srbg_api.intelligence_v2.owner_gold_calibration_service import (
    OwnerGoldCalibrationService,
)
from srbg_api.intelligence_v2.owner_gold_preparation import (
    PredictionSeal,
    prediction_manifest_sha256,
    prediction_seal_sha256,
)
from srbg_contracts import EngineeringObject, PrimaryIntelligenceType


class MemoryRepository:
    def __init__(self) -> None:
        self.seals: dict[str, PredictionSeal] = {}
        self.facts: list[object] = []

    async def append_prediction_seal(self, seal: PredictionSeal) -> None:
        previous = self.seals.get(seal.seal_sha256)
        if previous is not None and previous != seal:
            raise ValueError("PREDICTION_SEAL_CONFLICT")
        self.seals[seal.seal_sha256] = seal

    async def load_prediction_seal(self, seal_sha256: str) -> PredictionSeal | None:
        return self.seals.get(seal_sha256)

    async def append_calibration_fact(self, fact: object) -> None:
        self.facts.append(fact)


def _seal(*, sealed_at: datetime, prediction_manifest: str = "d" * 64) -> PredictionSeal:
    seal = PredictionSeal(
        seal_version="intelligence-v2-owner-gold-prediction-seal-1.0.0",
        corpus_version="owner-gold-2026-07-20.4",
        rule_version="intelligence-v2-qualification-1.0.0",
        model_id="deepseek-v4-flash",
        prompt_version="ai01-classify-v1",
        schema_version="classify-output-v1",
        case_count=40,
        corpus_manifest_sha256="c" * 64,
        prediction_manifest_sha256=prediction_manifest,
        sealed_at=sealed_at,
        seal_sha256="",
    )
    return replace(seal, seal_sha256=prediction_seal_sha256(seal))


def _predictions(*, predicted_at: datetime) -> list[CandidatePrediction]:
    return [
        CandidatePrediction(
            case_id=f"case-{index:02d}",
            content_sha256=f"{index + 1:064x}",
            model_id="deepseek-v4-flash",
            prompt_version="ai01-classify-v1",
            corpus_version="owner-gold-2026-07-20.4",
            rule_version="intelligence-v2-qualification-1.0.0",
            schema_version="intelligence-v2-owner-gold-2.0.0",
            predicted_at=predicted_at,
            input_sha256=f"{index + 1:064x}",
            predicted_relevant=True,
            primary_type=PrimaryIntelligenceType.DIGITAL_TRANSFORMATION,
            confidence_bps=9300,
        )
        for index in range(40)
    ]


def _annotations(*, annotated_at: datetime) -> list[OwnerGoldAnnotation]:
    values = [_annotation(f"case-{index:02d}", annotated_at=annotated_at) for index in range(40)]
    return [
        value
        if index < 20
        else replace(
            value,
            bucket="NEGATIVE",
            expected_relevant=False,
            primary_type=None,
            engineering_objects=(),
            locked_negative=True,
        )
        for index, value in enumerate(values)
    ]


def _no_go_fact(
    *,
    seal: PredictionSeal,
    annotations: list[OwnerGoldAnnotation],
    predictions: list[CandidatePrediction],
) -> CalibrationFact:
    return calibrate_owner_gold(
        annotations,
        predictions,
        corpus_version=seal.corpus_version,
        rule_version=seal.rule_version,
        model_id=seal.model_id,
        prompt_version=seal.prompt_version,
        calibrated_at=seal.sealed_at + timedelta(hours=1),
        prediction_seal_sha256=seal.seal_sha256,
    )


def _annotation(case_id: str, *, annotated_at: datetime) -> OwnerGoldAnnotation:
    return OwnerGoldAnnotation(
        case_id=case_id,
        bucket="POSITIVE",
        annotator_kind="HUMAN_OWNER",
        content_sha256="a" * 64,
        raw_object_sha256="b" * 64,
        annotated_at=annotated_at,
        rule_version="intelligence-v2-qualification-1.0.0",
        model_id="deepseek-v4-flash",
        prompt_version="ai01-classify-v1",
        corpus_version="owner-gold-2026-07-20.4",
        schema_version="intelligence-v2-owner-gold-2.0.0",
        evidence_locator="html:p:1",
        expected_relevant=True,
        primary_type=PrimaryIntelligenceType.DIGITAL_TRANSFORMATION,
        engineering_objects=(EngineeringObject.HIGHWAY,),
        specialty_facets=(),
        equipment_domains=(),
        locked_negative=False,
    )


@pytest.mark.asyncio
async def test_service_rejects_owner_labels_that_predate_the_prediction_seal() -> None:
    repository = MemoryRepository()
    service = OwnerGoldCalibrationService(repository)
    sealed_at = datetime(2026, 7, 20, 2, tzinfo=UTC)
    seal = _seal(sealed_at=sealed_at)
    await repository.append_prediction_seal(seal)

    with pytest.raises(ValueError, match="OWNER_ANNOTATION_PRECEDES_PREDICTION_SEAL"):
        await service.require_sealed_before_annotations(
            seal_sha256=seal.seal_sha256,
            annotations=[_annotation("case-1", annotated_at=sealed_at - timedelta(seconds=1))],
        )


@pytest.mark.asyncio
async def test_service_accepts_an_exact_idempotent_prediction_seal() -> None:
    repository = MemoryRepository()
    service = OwnerGoldCalibrationService(repository)
    seal = _seal(sealed_at=datetime(2026, 7, 20, 2, tzinfo=UTC))

    await service.append_prediction_seal(seal)
    await service.append_prediction_seal(replace(seal))

    assert repository.seals == {seal.seal_sha256: seal}


@pytest.mark.asyncio
async def test_service_recomputes_and_rejects_a_tampered_prediction_seal() -> None:
    repository = MemoryRepository()
    service = OwnerGoldCalibrationService(repository)
    seal = _seal(sealed_at=datetime(2026, 7, 20, 2, tzinfo=UTC))

    with pytest.raises(ValueError, match="PREDICTION_SEAL_AUTHENTICITY_INVALID"):
        await service.append_prediction_seal(replace(seal, case_count=39))

    assert repository.seals == {}


@pytest.mark.asyncio
async def test_service_recomputes_and_rejects_a_tampered_calibration_fact() -> None:
    repository = MemoryRepository()
    service = OwnerGoldCalibrationService(repository)
    sealed_at = datetime(2026, 7, 20, 2, tzinfo=UTC)
    predictions = _predictions(predicted_at=sealed_at - timedelta(minutes=1))
    seal = _seal(
        sealed_at=sealed_at,
        prediction_manifest=prediction_manifest_sha256(predictions),
    )
    await service.append_prediction_seal(seal)
    annotations = _annotations(annotated_at=sealed_at + timedelta(minutes=1))
    fact = _no_go_fact(seal=seal, annotations=annotations, predictions=predictions)
    tampered = replace(fact, evidence_manifest_sha256="b" * 64, fact_sha256="")
    tampered = replace(tampered, fact_sha256=calibration_fact_sha256(tampered))

    with pytest.raises(ValueError, match="CALIBRATION_FACT_AUTHENTICITY_INVALID"):
        await service.append_calibration_fact(
            tampered,
            annotations=annotations,
            predictions=predictions,
        )

    assert repository.facts == []


@pytest.mark.asyncio
async def test_service_recomputes_the_complete_fact_from_annotations_and_predictions() -> None:
    repository = MemoryRepository()
    service = OwnerGoldCalibrationService(repository)
    sealed_at = datetime(2026, 7, 20, 2, tzinfo=UTC)
    predictions = _predictions(predicted_at=sealed_at - timedelta(minutes=1))
    seal = _seal(
        sealed_at=sealed_at,
        prediction_manifest=prediction_manifest_sha256(predictions),
    )
    await service.append_prediction_seal(seal)
    annotations = _annotations(annotated_at=sealed_at + timedelta(minutes=1))
    fact = _no_go_fact(seal=seal, annotations=annotations, predictions=predictions)

    await service.append_calibration_fact(
        fact, annotations=annotations, predictions=predictions
    )

    assert repository.facts == [fact]


@pytest.mark.asyncio
async def test_service_requires_and_verifies_explicit_owner_override_approval() -> None:
    repository = MemoryRepository()
    service = OwnerGoldCalibrationService(repository)
    sealed_at = datetime(2026, 7, 20, 2, tzinfo=UTC)
    predictions = _predictions(predicted_at=sealed_at - timedelta(minutes=1))
    seal = _seal(
        sealed_at=sealed_at,
        prediction_manifest=prediction_manifest_sha256(predictions),
    )
    await service.append_prediction_seal(seal)
    annotations = _annotations(annotated_at=sealed_at + timedelta(minutes=1))
    base = _no_go_fact(seal=seal, annotations=annotations, predictions=predictions)
    approval_sha256 = "e" * 64
    fact = apply_owner_override_go(
        base,
        annotations=annotations,
        predictions=predictions,
        approval_sha256=approval_sha256,
        threshold_bps=9300,
    )

    with pytest.raises(ValueError, match="CALIBRATION_OWNER_OVERRIDE_APPROVAL_REQUIRED"):
        await service.append_calibration_fact(
            fact,
            annotations=annotations,
            predictions=predictions,
        )

    await service.append_calibration_fact(
        fact,
        annotations=annotations,
        predictions=predictions,
        owner_override_approval_sha256=approval_sha256,
    )
    assert repository.facts == [fact]
