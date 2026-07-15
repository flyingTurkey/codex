"""Shared API/worker application service for governed resolution candidates and scores."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Protocol, TypedDict, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.identifiers import uuid7
from srbg_api.intelligence_resolution.domain import (
    DeduplicationDocument,
    ScoreValue,
    assess_duplicate,
    calculate_scores,
)


class ScoringInput(TypedDict):
    relevance_features: tuple[int, ...] | None
    authority_level: str | None
    impact_features: tuple[int, ...] | None
    novelty_similarity_bps: int | None
    published_at: datetime | None
    content_type: str
    accepted_claim_coverage_bps: int | None
    locator_integrity: bool | None
    primary_evidence: bool | None
    extraction_confidence_bps: int | None
    cross_source_agreement_bps: int | None
    human_reviewed: bool | None
    unresolved_conflicts: int
    independent_source_count: int
    event_activity_count: int


class ResolutionStore(Protocol):
    async def save_duplicate_candidate(
        self,
        *,
        left_item_id: UUID,
        right_item_id: UUID,
        score_bps: int,
        features: tuple[tuple[str, int], ...],
        hard_conflicts: tuple[str, ...],
        recall_methods: tuple[str, ...],
        requires_human_review: bool,
        rule_version: str,
        created_at: datetime,
    ) -> UUID: ...

    async def save_score_set(
        self,
        *,
        item_id: UUID,
        scores: Mapping[str, ScoreValue],
        calculated_at: datetime,
    ) -> UUID: ...


class ResolutionService:
    def __init__(
        self,
        *,
        store: ResolutionStore,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(UTC))

    async def evaluate_pair(
        self,
        *,
        left_item_id: UUID,
        left: DeduplicationDocument,
        right_item_id: UUID,
        right: DeduplicationDocument,
        recall_methods: tuple[str, ...],
        vector_similarity_bps: int | None = None,
    ) -> UUID | None:
        assessment = assess_duplicate(left, right, vector_similarity_bps=vector_similarity_bps)
        if (
            assessment.recommendation in {"KEEP_DISTINCT", "LINK_RELATION"}
            and not assessment.blocked
        ):
            return None
        first_id, second_id = sorted((left_item_id, right_item_id), key=str)
        return await self._store.save_duplicate_candidate(
            left_item_id=first_id,
            right_item_id=second_id,
            score_bps=assessment.similarity_bps,
            features=assessment.features,
            hard_conflicts=assessment.hard_conflicts,
            recall_methods=recall_methods,
            requires_human_review=True,
            rule_version=assessment.rule_version,
            created_at=self._now(),
        )

    async def score_item(self, *, item_id: UUID, scoring_input: ScoringInput) -> UUID | None:
        scores = calculate_scores(**scoring_input, now=self._now())
        if not scores:
            return None
        return await self._store.save_score_set(
            item_id=item_id,
            scores=scores,
            calculated_at=self._now(),
        )


class PostgresResolutionStore:
    """Runtime writer for candidates and raw score calculations, never review decisions."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def save_duplicate_candidate(
        self,
        *,
        left_item_id: UUID,
        right_item_id: UUID,
        score_bps: int,
        features: tuple[tuple[str, int], ...],
        hard_conflicts: tuple[str, ...],
        recall_methods: tuple[str, ...],
        requires_human_review: bool,
        rule_version: str,
        created_at: datetime,
    ) -> UUID:
        if not requires_human_review:
            raise ValueError("Round08 item resolution candidates always require human review")
        candidate_id = uuid7()
        feature_payload = [{"code": code, "similarity_bps": value} for code, value in features]
        async with self._engine.begin() as connection:
            resolved = await connection.scalar(
                text(
                    """
                    INSERT INTO duplicate_candidate (
                        id, left_item_id, right_item_id, score_bps, features,
                        hard_conflicts, recall_methods, status, rule_version, created_at
                    ) VALUES (
                        :id, :left_item_id, :right_item_id, :score_bps,
                        CAST(:features AS jsonb), :hard_conflicts, :recall_methods,
                        'PENDING_REVIEW', :rule_version, :created_at
                    )
                    ON CONFLICT (left_item_id, right_item_id, rule_version) DO UPDATE
                      SET score_bps = EXCLUDED.score_bps,
                          features = EXCLUDED.features,
                          hard_conflicts = EXCLUDED.hard_conflicts,
                          recall_methods = EXCLUDED.recall_methods
                      WHERE duplicate_candidate.status = 'PENDING_REVIEW'
                    RETURNING id
                    """
                ),
                {
                    "id": candidate_id,
                    "left_item_id": left_item_id,
                    "right_item_id": right_item_id,
                    "score_bps": score_bps,
                    "features": json.dumps(feature_payload, ensure_ascii=False),
                    "hard_conflicts": list(hard_conflicts),
                    "recall_methods": list(recall_methods),
                    "rule_version": rule_version,
                    "created_at": created_at,
                },
            )
        if resolved is None:
            raise RuntimeError("a terminal duplicate decision cannot be overwritten")
        return cast(UUID, resolved)

    async def save_score_set(
        self,
        *,
        item_id: UUID,
        scores: Mapping[str, ScoreValue],
        calculated_at: datetime,
    ) -> UUID:
        score_set_id = uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE score_set SET is_current = false "
                    "WHERE item_id = :item_id AND is_current"
                ),
                {"item_id": item_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO score_set (
                        id, item_id, rule_version, calculated_at, is_current
                    ) VALUES (:id, :item_id, 'scoring-v1.0.0', :calculated_at, true)
                    """
                ),
                {"id": score_set_id, "item_id": item_id, "calculated_at": calculated_at},
            )
            for dimension, score in scores.items():
                features = [
                    {
                        "code": code,
                        "label": code.replace("_", " ").title(),
                        "points": points,
                        "explanation": explanation,
                    }
                    for code, points, explanation in score.features
                ]
                await connection.execute(
                    text(
                        """
                        INSERT INTO score_dimension (
                            id, score_set_id, dimension, raw_score, features
                        ) VALUES (
                            :id, :score_set_id, :dimension, :raw_score,
                            CAST(:features AS jsonb)
                        )
                        """
                    ),
                    {
                        "id": uuid7(),
                        "score_set_id": score_set_id,
                        "dimension": dimension,
                        "raw_score": score.score,
                        "features": json.dumps(features, ensure_ascii=False),
                    },
                )
        return score_set_id
