"""Server-validated append-only persistence for Owner Gold calibration evidence."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.gold_calibration import (
    OWNER_GOLD_CORPUS_VERSION,
    CalibrationFact,
    CandidatePrediction,
    OwnerGoldAnnotation,
    apply_owner_override_go,
    calibrate_owner_gold,
    calibration_fact_sha256,
)
from srbg_api.intelligence_v2.owner_gold_preparation import (
    PredictionSeal,
    prediction_manifest_sha256,
    validate_prediction_seal,
)


class OwnerGoldCalibrationRepository(Protocol):
    async def append_prediction_seal(self, seal: PredictionSeal) -> None: ...

    async def load_prediction_seal(self, seal_sha256: str) -> PredictionSeal | None: ...

    async def append_calibration_fact(self, fact: CalibrationFact) -> None: ...


class OwnerGoldCalibrationService:
    def __init__(self, repository: OwnerGoldCalibrationRepository) -> None:
        self._repository = repository

    async def append_prediction_seal(self, seal: PredictionSeal) -> None:
        validate_prediction_seal(seal)
        existing = await self._repository.load_prediction_seal(seal.seal_sha256)
        if existing is not None:
            if existing != seal:
                raise ValueError("PREDICTION_SEAL_CONFLICT")
            return
        await self._repository.append_prediction_seal(seal)

    async def require_sealed_before_annotations(
        self,
        *,
        seal_sha256: str,
        annotations: list[OwnerGoldAnnotation],
    ) -> PredictionSeal:
        seal = await self._repository.load_prediction_seal(seal_sha256)
        if seal is None:
            raise ValueError("PREDICTION_SEAL_NOT_FOUND")
        if any(
            annotation.annotated_at.tzinfo is None
            or annotation.annotated_at <= seal.sealed_at
            for annotation in annotations
        ):
            raise ValueError("OWNER_ANNOTATION_PRECEDES_PREDICTION_SEAL")
        return seal

    async def append_calibration_fact(
        self,
        fact: CalibrationFact,
        *,
        annotations: list[OwnerGoldAnnotation],
        predictions: list[CandidatePrediction],
        owner_override_approval_sha256: str | None = None,
    ) -> None:
        if (
            fact.fact_version != "intelligence-v2-owner-gold-calibration-2.0.0"
            or fact.corpus_version != OWNER_GOLD_CORPUS_VERSION
            or fact.label_authority != "HUMAN_OWNER"
            or fact.calibrated_at.tzinfo is None
            or fact.fact_sha256 != calibration_fact_sha256(fact)
        ):
            raise ValueError("CALIBRATION_FACT_AUTHENTICITY_INVALID")
        seal = await self.require_sealed_before_annotations(
            seal_sha256=fact.prediction_seal_sha256,
            annotations=annotations,
        )
        if (
            any(
                prediction.predicted_at.tzinfo is None
                or prediction.predicted_at > seal.sealed_at
                for prediction in predictions
            )
            or prediction_manifest_sha256(predictions) != seal.prediction_manifest_sha256
        ):
            raise ValueError("CALIBRATION_PREDICTION_MANIFEST_INVALID")
        if (
            fact.corpus_version != seal.corpus_version
            or fact.rule_version != seal.rule_version
            or fact.model_id != seal.model_id
            or fact.prompt_version != seal.prompt_version
        ):
            raise ValueError("CALIBRATION_PREDICTION_SEAL_VERSION_MISMATCH")
        recomputed = calibrate_owner_gold(
            annotations,
            predictions,
            corpus_version=fact.corpus_version,
            rule_version=fact.rule_version,
            model_id=fact.model_id,
            prompt_version=fact.prompt_version,
            calibrated_at=fact.calibrated_at,
            prediction_seal_sha256=fact.prediction_seal_sha256,
        )
        if "OWNER_OVERRIDE_GO" in fact.reasons:
            if owner_override_approval_sha256 is None or fact.auto_pass_threshold_bps is None:
                raise ValueError("CALIBRATION_OWNER_OVERRIDE_APPROVAL_REQUIRED")
            recomputed = apply_owner_override_go(
                recomputed,
                annotations=annotations,
                predictions=predictions,
                approval_sha256=owner_override_approval_sha256,
                threshold_bps=fact.auto_pass_threshold_bps,
            )
        if recomputed != fact:
            raise ValueError("CALIBRATION_FACT_AUTHENTICITY_INVALID")
        await self._repository.append_calibration_fact(fact)


class PostgresOwnerGoldCalibrationRepository:
    """The only supported database writer for seals and calibration facts."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def append_prediction_seal(self, seal: PredictionSeal) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO owner_gold_prediction_seal_v2(
                      id,seal_version,corpus_version,rule_version,model_id,prompt_version,
                      schema_version,case_count,corpus_manifest_sha256,
                      prediction_manifest_sha256,sealed_at,prediction_seal_sha256,created_at
                    ) VALUES(
                      :id,:seal_version,:corpus_version,:rule_version,:model_id,:prompt_version,
                      :schema_version,:case_count,:corpus_manifest_sha256,
                      :prediction_manifest_sha256,:sealed_at,:prediction_seal_sha256,:created_at
                    )
                    """
                ),
                {
                    **asdict(seal),
                    "id": uuid7(),
                    "prediction_seal_sha256": seal.seal_sha256,
                    "created_at": datetime.now(UTC),
                },
            )

    async def load_prediction_seal(self, seal_sha256: str) -> PredictionSeal | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT seal_version,corpus_version,rule_version,model_id,
                                   prompt_version,schema_version,case_count,
                                   corpus_manifest_sha256,prediction_manifest_sha256,
                                   sealed_at,prediction_seal_sha256
                            FROM owner_gold_prediction_seal_v2
                            WHERE prediction_seal_sha256=:seal_sha256
                            """
                        ),
                        {"seal_sha256": seal_sha256},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return PredictionSeal(
            seal_version=str(row["seal_version"]),
            corpus_version=str(row["corpus_version"]),
            rule_version=str(row["rule_version"]),
            model_id=str(row["model_id"]),
            prompt_version=str(row["prompt_version"]),
            schema_version=str(row["schema_version"]),
            case_count=int(row["case_count"]),
            corpus_manifest_sha256=str(row["corpus_manifest_sha256"]),
            prediction_manifest_sha256=str(row["prediction_manifest_sha256"]),
            sealed_at=row["sealed_at"],
            seal_sha256=str(row["prediction_seal_sha256"]),
        )

    async def append_calibration_fact(self, fact: CalibrationFact) -> None:
        slices = {
            "primary_type": fact.primary_type_slices,
            "engineering_object": fact.engineering_object_slices,
            "specialty_facet": fact.specialty_facet_slices,
            "equipment_domain": fact.equipment_domain_slices,
        }
        encoded_slices = json.dumps(
            slices,
            default=lambda value: value.value if hasattr(value, "value") else asdict(value),
            ensure_ascii=False,
            sort_keys=True,
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO owner_gold_calibration_v2(
                      id,fact_version,corpus_version,rule_version,model_id,prompt_version,
                      calibrated_at,label_authority,decision,reasons,authorizes_auto_pass,
                      auto_pass_threshold_bps,precision_bps,recall_bps,
                      locked_negative_leaks,slice_metrics,evidence_manifest_sha256,
                      prediction_seal_sha256,fact_sha256,created_at
                    ) VALUES(
                      :id,:fact_version,:corpus_version,:rule_version,:model_id,:prompt_version,
                      :calibrated_at,:label_authority,:decision,CAST(:reasons AS jsonb),
                      :authorizes_auto_pass,:auto_pass_threshold_bps,:precision_bps,:recall_bps,
                      :locked_negative_leaks,CAST(:slice_metrics AS jsonb),
                      :evidence_manifest_sha256,:prediction_seal_sha256,:fact_sha256,:created_at
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "fact_version": fact.fact_version,
                    "corpus_version": fact.corpus_version,
                    "rule_version": fact.rule_version,
                    "model_id": fact.model_id,
                    "prompt_version": fact.prompt_version,
                    "calibrated_at": fact.calibrated_at,
                    "label_authority": fact.label_authority,
                    "decision": fact.decision,
                    "reasons": json.dumps(fact.reasons),
                    "authorizes_auto_pass": fact.authorizes_auto_pass,
                    "auto_pass_threshold_bps": fact.auto_pass_threshold_bps,
                    "precision_bps": fact.precision_bps,
                    "recall_bps": fact.recall_bps,
                    "locked_negative_leaks": fact.locked_negative_leaks,
                    "slice_metrics": encoded_slices,
                    "evidence_manifest_sha256": fact.evidence_manifest_sha256,
                    "prediction_seal_sha256": fact.prediction_seal_sha256,
                    "fact_sha256": fact.fact_sha256,
                    "created_at": datetime.now(UTC),
                },
            )
