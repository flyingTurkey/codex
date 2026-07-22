"""Durable technical retry coordination for autonomous content work."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import SystemRandom
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.ai_pipeline.content_preparation import (
    PreparationDocument,
)
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.autonomous_policy import QualificationPolicyBundle
from srbg_api.intelligence_v2.qualification_decisions import append_qualification_decision
from srbg_api.observability import TECHNICAL_RETRY_OUTCOMES
from srbg_contracts import (
    AutomatedDecisionReason,
    AutomatedDisposition,
    QualificationDecisionTrace,
)

_RETRY_BACKOFF_SECONDS = (300, 900, 2700)
logger = logging.getLogger("srbg.worker.technical_retries")
_RETRYABLE_REASON_CODES = frozenset(
    {
        "PROVIDER_TIMEOUT",
        "PROVIDER_NETWORK_ERROR",
        "TRANSIENT_UNAVAILABLE",
        "DATABASE_TEMPORARILY_UNAVAILABLE",
        "OBJECT_STORE_TEMPORARILY_UNAVAILABLE",
        "QUEUE_CONTENTION",
    }
)


@dataclass(frozen=True, slots=True)
class TechnicalRetryOutcome:
    disposition: AutomatedDisposition
    next_retry_at: datetime | None
    applied: bool = True


@dataclass(frozen=True, slots=True)
class DueTechnicalRetry:
    original_pipeline_run_id: UUID
    attempt_count: int
    next_attempt_number: int
    reason_code: str


class PostgresTechnicalRetryCoordinator:
    """Keep retry scheduling in PostgreSQL so process restarts cannot lose it."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        clock: Callable[[], datetime] | None = None,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self._engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))
        self._jitter = jitter or SystemRandom().random

    async def close(self) -> None:
        await self._engine.dispose()

    async def record_failure(
        self,
        *,
        document: PreparationDocument,
        policy: QualificationPolicyBundle,
        reason_code: str,
        attempt_number: int,
        retry_number: int | None = None,
        max_retries: int = 3,
    ) -> TechnicalRetryOutcome:
        if attempt_number < 1:
            raise ValueError("technical attempt number must be positive")
        cycle_attempt = retry_number if retry_number is not None else attempt_number
        if cycle_attempt < 1:
            raise ValueError("technical retry number must be positive")
        if not 0 <= max_retries <= len(_RETRY_BACKOFF_SECONDS):
            raise ValueError("technical retry limit must be between zero and three")
        if reason_code not in _RETRYABLE_REASON_CODES:
            outcome = await self._record_terminal_failure(
                document=document,
                policy=policy,
                reason_code=reason_code,
                attempt_number=attempt_number,
                decision_reason=AutomatedDecisionReason.TECHNICAL_EXHAUSTED,
            )
            _observe_outcome(outcome, reason_class="NON_RETRYABLE")
            return outcome
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("technical retry clock must be timezone-aware")
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"technical-retry:{document.run_id}"},
            )
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT decision.disposition,compensation.available_at "
                            "FROM automated_qualification_decision_v2 decision "
                            "JOIN qualification_policy_bundle_v2 bundle "
                            "ON bundle.id=decision.policy_bundle_id "
                            "LEFT JOIN ai_compensation_run_v2 compensation "
                            "ON compensation.original_pipeline_run_id=:run_id "
                            "WHERE decision.document_version_id=:version_id "
                            "AND bundle.bundle_sha256=:bundle_hash "
                            "AND decision.attempt_number=:attempt"
                        ),
                        {
                            "run_id": document.run_id,
                            "version_id": document.document_version_id,
                            "bundle_hash": policy.identity.bundle_sha256,
                            "attempt": attempt_number,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                existing_disposition = AutomatedDisposition(str(existing["disposition"]))
                return TechnicalRetryOutcome(
                    disposition=existing_disposition,
                    next_retry_at=(
                        existing["available_at"]
                        if existing_disposition is AutomatedDisposition.TECHNICAL_RETRY
                        else None
                    ),
                    applied=False,
                )
            retry_index = cycle_attempt - 1
            if retry_index >= max_retries:
                await connection.execute(
                    text(
                        "UPDATE ai_compensation_run_v2 SET status='DEAD_LETTER',"
                        "attempt_count=:limit,completed_at=:now "
                        "WHERE original_pipeline_run_id=:run_id"
                    ),
                    {"run_id": document.run_id, "limit": max_retries, "now": now},
                )
                disposition = AutomatedDisposition.TECHNICAL_FAILED
                decision_reason = AutomatedDecisionReason.TECHNICAL_EXHAUSTED
                next_retry_at = None
            else:
                jitter = self._jitter()
                if not 0 <= jitter <= 1:
                    raise ValueError("technical retry jitter must be between zero and one")
                delay_seconds = max(1, round(_RETRY_BACKOFF_SECONDS[retry_index] * jitter))
                next_retry_at = now + timedelta(seconds=delay_seconds)
                await connection.execute(
                    text(
                        "INSERT INTO ai_compensation_run_v2("
                        "id,original_pipeline_run_id,recovery_pipeline_run_id,reason_code,status,"
                        "attempt_count,available_at,started_at,completed_at) VALUES("
                        ":id,:run_id,NULL,:reason,'PENDING',:attempt,:available,:now,NULL) "
                        "ON CONFLICT(original_pipeline_run_id) DO UPDATE SET "
                        "reason_code=EXCLUDED.reason_code,status='PENDING',"
                        "attempt_count=EXCLUDED.attempt_count,available_at=EXCLUDED.available_at,"
                        "completed_at=NULL"
                    ),
                    {
                        "id": uuid7(),
                        "run_id": document.run_id,
                        "reason": _compensation_reason(reason_code),
                        "attempt": cycle_attempt,
                        "available": next_retry_at,
                        "now": now,
                    },
                )
                disposition = AutomatedDisposition.TECHNICAL_RETRY
                decision_reason = AutomatedDecisionReason.TECHNICAL_RETRYABLE
            await _append_decision(
                connection,
                document=document,
                policy=policy,
                reason_code=reason_code,
                decision_reason=decision_reason,
                disposition=disposition,
                attempt_number=attempt_number,
                decided_at=now,
            )
        outcome = TechnicalRetryOutcome(disposition=disposition, next_retry_at=next_retry_at)
        _observe_outcome(outcome, reason_class="RETRYABLE")
        return outcome

    async def _record_terminal_failure(
        self,
        *,
        document: PreparationDocument,
        policy: QualificationPolicyBundle,
        reason_code: str,
        attempt_number: int,
        decision_reason: AutomatedDecisionReason,
    ) -> TechnicalRetryOutcome:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("technical retry clock must be timezone-aware")
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"technical-retry:{document.run_id}"},
            )
            existing = await connection.scalar(
                text(
                    "SELECT decision.id FROM automated_qualification_decision_v2 decision "
                    "JOIN qualification_policy_bundle_v2 bundle "
                    "ON bundle.id=decision.policy_bundle_id "
                    "WHERE decision.document_version_id=:version_id "
                    "AND bundle.bundle_sha256=:bundle_hash "
                    "AND decision.attempt_number=:attempt"
                ),
                {
                    "version_id": document.document_version_id,
                    "bundle_hash": policy.identity.bundle_sha256,
                    "attempt": attempt_number,
                },
            )
            if existing is not None:
                return TechnicalRetryOutcome(
                    disposition=AutomatedDisposition.TECHNICAL_FAILED,
                    next_retry_at=None,
                    applied=False,
                )
            await connection.execute(
                text(
                    "INSERT INTO ai_compensation_run_v2("
                    "id,original_pipeline_run_id,recovery_pipeline_run_id,reason_code,status,"
                    "attempt_count,available_at,started_at,completed_at) VALUES("
                    ":id,:run_id,NULL,:reason,'DEAD_LETTER',:attempt,:now,:now,:now) "
                    "ON CONFLICT(original_pipeline_run_id) DO UPDATE SET "
                    "reason_code=EXCLUDED.reason_code,status='DEAD_LETTER',"
                    "attempt_count=EXCLUDED.attempt_count,available_at=EXCLUDED.available_at,"
                    "completed_at=EXCLUDED.completed_at"
                ),
                {
                    "id": uuid7(),
                    "run_id": document.run_id,
                    "reason": _compensation_reason(reason_code),
                    "attempt": min(attempt_number, 3),
                    "now": now,
                },
            )
            await _append_decision(
                connection,
                document=document,
                policy=policy,
                reason_code=reason_code,
                decision_reason=decision_reason,
                disposition=AutomatedDisposition.TECHNICAL_FAILED,
                attempt_number=attempt_number,
                decided_at=now,
            )
        return TechnicalRetryOutcome(
            disposition=AutomatedDisposition.TECHNICAL_FAILED,
            next_retry_at=None,
        )

    async def claim_due(self, *, limit: int) -> tuple[DueTechnicalRetry, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("technical retry claim limit must be between 1 and 100")
        now = self._clock()
        lease_until = now + timedelta(minutes=1)
        async with self._engine.begin() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "WITH due AS (SELECT id FROM ai_compensation_run_v2 "
                            "WHERE status IN ('PENDING','PROCESSING') AND available_at<=:now "
                            "ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT :limit) "
                            "UPDATE ai_compensation_run_v2 compensation SET status='PROCESSING',"
                            "available_at=:lease FROM due WHERE compensation.id=due.id RETURNING "
                            "compensation.original_pipeline_run_id,compensation.attempt_count,"
                            "compensation.reason_code,(SELECT COALESCE("
                            "MAX(decision.attempt_number),"
                            "0)+1 FROM ai_pipeline_run pipeline JOIN "
                            "automated_qualification_decision_v2 decision ON "
                            "decision.document_version_id=pipeline.document_version_id WHERE "
                            "pipeline.id=compensation.original_pipeline_run_id) next_attempt_number"
                        ),
                        {"now": now, "lease": lease_until, "limit": limit},
                    )
                ).mappings()
            )
        return tuple(
            DueTechnicalRetry(
                original_pipeline_run_id=row["original_pipeline_run_id"],
                attempt_count=int(row["attempt_count"]),
                next_attempt_number=int(row["next_attempt_number"]),
                reason_code=str(row["reason_code"]),
            )
            for row in rows
        )

    async def claim_stalled(self, *, limit: int) -> tuple[DueTechnicalRetry, ...]:
        """Find queue/database-orphaned pipeline work after its bounded lease window."""

        if not 1 <= limit <= 100:
            raise ValueError("technical stalled claim limit must be between 1 and 100")
        now = self._clock()
        stale_before = now - timedelta(minutes=15)
        async with self._engine.begin() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT pipeline.id AS original_pipeline_run_id,0 AS attempt_count,"
                            "COALESCE((SELECT MAX(decision.attempt_number)+1 FROM "
                            "automated_qualification_decision_v2 decision WHERE "
                            "decision.document_version_id=pipeline.document_version_id),1) "
                            "AS next_attempt_number,'DATABASE_TEMPORARILY_UNAVAILABLE' "
                            "AS reason_code FROM ai_pipeline_run pipeline JOIN "
                            "source_content_outbox outbox ON outbox.pipeline_run_id=pipeline.id "
                            "WHERE pipeline.status IN ('QUEUED','PREPARING','CLASSIFYING') "
                            "AND pipeline.started_at<=:stale_before "
                            "AND outbox.status='WAITING_AI' AND NOT EXISTS(SELECT 1 FROM "
                            "ai_compensation_run_v2 compensation WHERE "
                            "compensation.original_pipeline_run_id=pipeline.id AND "
                            "compensation.status IN ('PENDING','PROCESSING')) "
                            "ORDER BY pipeline.started_at,pipeline.id FOR UPDATE OF pipeline "
                            "SKIP LOCKED LIMIT :limit"
                        ),
                        {"stale_before": stale_before, "limit": limit},
                    )
                ).mappings()
            )
        return tuple(
            DueTechnicalRetry(
                original_pipeline_run_id=row["original_pipeline_run_id"],
                attempt_count=int(row["attempt_count"]),
                next_attempt_number=int(row["next_attempt_number"]),
                reason_code=str(row["reason_code"]),
            )
            for row in rows
        )

    async def retry_now(
        self,
        original_pipeline_run_id: UUID,
        *,
        retry_event_id: UUID,
        requested_at: datetime,
    ) -> bool:
        now = self._clock()
        if requested_at.tzinfo is None:
            raise ValueError("technical retry request time must be timezone-aware")
        async with self._engine.begin() as connection:
            recovery_pipeline_run_id = await connection.scalar(
                text(
                    "SELECT reopen_source_content_ai_run("
                    ":run_id,:recovery_run_id,:compensation_id,:event_id,"
                    ":requested_at,:now)"
                ),
                {
                    "run_id": original_pipeline_run_id,
                    "recovery_run_id": uuid7(),
                    "compensation_id": uuid7(),
                    "event_id": retry_event_id,
                    "now": now,
                    "requested_at": requested_at,
                },
            )
        return recovery_pipeline_run_id is not None

    async def retry_source_fetch(
        self,
        failed_run_id: UUID,
        *,
        retry_event_id: UUID,
        requested_at: datetime,
    ) -> bool:
        now = self._clock()
        if requested_at.tzinfo is None:
            raise ValueError("source retry request time must be timezone-aware")
        async with self._engine.begin() as connection:
            recovery_run_id = await connection.scalar(
                text(
                    "SELECT reopen_failed_source_fetch("
                    ":failed_run_id,:recovery_run_id,:event_id,:requested_at,:now)"
                ),
                {
                    "failed_run_id": failed_run_id,
                    "recovery_run_id": uuid7(),
                    "event_id": retry_event_id,
                    "requested_at": requested_at,
                    "now": now,
                },
            )
        return recovery_run_id is not None


def _compensation_reason(reason_code: str) -> str:
    if reason_code in {"PROVIDER_TIMEOUT", "PROVIDER_NETWORK_ERROR"}:
        return reason_code
    return "TRANSIENT_UNAVAILABLE"


def _observe_outcome(outcome: TechnicalRetryOutcome, *, reason_class: str) -> None:
    TECHNICAL_RETRY_OUTCOMES.labels(
        outcome=outcome.disposition.value,
        reason_class=reason_class,
    ).inc()
    logger.info(
        "technical_retry_transition",
        extra={
            "outcome": outcome.disposition.value,
            "reason_class": reason_class,
            "retry_scheduled": outcome.next_retry_at is not None,
        },
    )


async def _append_decision(
    connection: Any,
    *,
    document: PreparationDocument,
    policy: QualificationPolicyBundle,
    reason_code: str,
    decision_reason: AutomatedDecisionReason,
    disposition: AutomatedDisposition,
    attempt_number: int,
    decided_at: datetime,
) -> None:
    trace = QualificationDecisionTrace(
        decision_id=uuid7(),
        document_version_id=document.document_version_id,
        raw_object_id=document.raw_object_id,
        normalized_input_sha256=await connection.scalar(
            text("SELECT content_hash FROM document_version WHERE id=:id"),
            {"id": document.document_version_id},
        ),
        policy=policy.identity,
        disposition=disposition,
        reason_codes=[decision_reason],
        rule_signals=[f"TECHNICAL_REASON:{reason_code}"],
        semantic_recheck_count=0,
        attempt_number=attempt_number,
        decided_at=decided_at,
    )
    await append_qualification_decision(connection, trace=trace, policy=policy)
