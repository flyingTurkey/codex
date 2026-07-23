"""Server-owned Champion/Challenger promotion and rollback rules."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.autonomous_policy import QualificationPolicyBundle
from srbg_api.intelligence_v2.private_policy_replay import OfflineReplayReport
from srbg_api.intelligence_v2.qualification_decisions import (
    persist_qualification_policy_bundle,
)

PolicyEvaluationMode = Literal["OFFLINE_REPLAY", "SHADOW"]
PolicyActivationAction = Literal["BOOTSTRAP", "PROMOTE", "ROLLBACK"]


class PolicyGateRejected(RuntimeError):
    """Raised when immutable aggregate evidence cannot authorize an activation."""


@dataclass(frozen=True, slots=True)
class PolicyEvaluationEvidence:
    id: UUID
    policy_bundle_id: UUID
    mode: PolicyEvaluationMode
    total_cases: int
    terminal_cases: int
    precision_bps: int | None
    recall_bps: int | None
    locked_negative_leaks: int
    schema_valid_bps: int
    authority_violations: int
    evidence_violations: int
    new_owner_semantic_tasks: int
    gate_passed: bool
    authorizes_production: bool


@dataclass(frozen=True, slots=True)
class PolicyActivation:
    id: UUID
    source_stream_policy_version: str
    policy_bundle_id: UUID
    previous_activation_id: UUID | None
    action: PolicyActivationAction
    reason_code: str
    activated_at: datetime


@dataclass(frozen=True, slots=True)
class PolicyHealthEvidence:
    activation_id: UUID
    total_runs: int
    feed_yield_bps: int
    technical_exception_bps: int
    safety_hold_bps: int
    suppression_bps: int
    schema_failures: int
    projection_failures: int
    hard_negative_leaks: int
    cost_budget_exceeded: bool
    category_drift_bps: int


@dataclass(frozen=True, slots=True)
class PolicyShadowWindowEvidence:
    id: UUID
    policy_bundle_id: UUID
    total_cases: int
    terminal_cases: int
    decision_stability_bps: int
    locked_negative_leaks: int
    schema_failures: int
    authority_violations: int
    evidence_violations: int
    projection_failures: int
    new_owner_semantic_tasks: int
    technical_exception_bps: int
    safety_hold_bps: int
    suppression_bps: int
    category_drift_bps: int
    gate_passed: bool
    affects_production: bool


@dataclass(frozen=True, slots=True)
class PolicyPromotionCandidate:
    source_stream_policy_version: str
    challenger_policy_bundle_id: UUID
    champion_policy_bundle_id: UUID
    offline_evaluation_id: UUID
    window_started_at: datetime


class PolicyOptimizationRepository(Protocol):
    async def evaluation(self, evaluation_id: UUID) -> PolicyEvaluationEvidence: ...

    async def active(self, source_stream_policy_version: str) -> PolicyActivation: ...

    async def activation(self, activation_id: UUID) -> PolicyActivation: ...

    async def shadow_window(self, window_id: UUID) -> PolicyShadowWindowEvidence: ...

    async def append_activation(
        self,
        *,
        source_stream_policy_version: str,
        policy_bundle_id: UUID,
        previous_activation_id: UUID,
        action: str,
        reason_code: str,
        offline_evaluation_id: UUID | None,
        shadow_window_id: UUID | None,
        activated_at: datetime,
    ) -> PolicyActivation: ...


class PolicyOptimizationService:
    """Apply hard aggregate gates without mutating evaluation or decision facts."""

    _MINIMUM_SHADOW_CASES = 20

    def __init__(self, *, repository: PolicyOptimizationRepository) -> None:
        self._repository = repository

    async def promote(
        self,
        *,
        source_stream_policy_version: str,
        challenger_policy_bundle_id: UUID,
        offline_evaluation_id: UUID,
        shadow_window_id: UUID,
        now: datetime,
    ) -> PolicyActivation:
        offline = await self._repository.evaluation(offline_evaluation_id)
        shadow = await self._repository.shadow_window(shadow_window_id)
        self._require_offline_gate(offline, challenger_policy_bundle_id)
        self._require_shadow_gate(shadow, challenger_policy_bundle_id)
        current = await self._repository.active(source_stream_policy_version)
        if current.policy_bundle_id == challenger_policy_bundle_id:
            return current
        return await self._repository.append_activation(
            source_stream_policy_version=source_stream_policy_version,
            policy_bundle_id=challenger_policy_bundle_id,
            previous_activation_id=current.id,
            action="PROMOTE",
            reason_code="CHALLENGER_AGGREGATE_GATES_PASSED",
            offline_evaluation_id=offline.id,
            shadow_window_id=shadow.id,
            activated_at=now,
        )

    async def rollback_if_regressed(
        self, *, health: PolicyHealthEvidence, now: datetime
    ) -> PolicyActivation | None:
        activation = await self._repository.activation(health.activation_id)
        current = await self._repository.active(activation.source_stream_policy_version)
        if current.id != activation.id:
            if current.action == "ROLLBACK" and current.previous_activation_id == activation.id:
                return current
            return None
        reason = self.regression_reason(health)
        if reason is None or activation.previous_activation_id is None:
            return None
        previous = await self._repository.activation(activation.previous_activation_id)
        return await self._repository.append_activation(
            source_stream_policy_version=activation.source_stream_policy_version,
            policy_bundle_id=previous.policy_bundle_id,
            previous_activation_id=activation.id,
            action="ROLLBACK",
            reason_code=reason,
            offline_evaluation_id=None,
            shadow_window_id=None,
            activated_at=now,
        )

    @classmethod
    def _require_offline_gate(
        cls, evaluation: PolicyEvaluationEvidence, challenger_id: UUID
    ) -> None:
        if (
            evaluation.mode != "OFFLINE_REPLAY"
            or evaluation.policy_bundle_id != challenger_id
            or evaluation.total_cases <= 0
            or evaluation.terminal_cases != evaluation.total_cases
            or evaluation.precision_bps is None
            or evaluation.precision_bps < 9_000
            or evaluation.recall_bps is None
            or evaluation.recall_bps < 9_000
            or evaluation.locked_negative_leaks != 0
            or evaluation.schema_valid_bps != 10_000
            or evaluation.authority_violations != 0
            or evaluation.evidence_violations != 0
            or evaluation.new_owner_semantic_tasks != 0
            or not evaluation.gate_passed
            or evaluation.authorizes_production
        ):
            raise PolicyGateRejected("OFFLINE_REPLAY_GATE_FAILED")

    @classmethod
    def _require_shadow_gate(
        cls, evaluation: PolicyShadowWindowEvidence, challenger_id: UUID
    ) -> None:
        if (
            evaluation.policy_bundle_id != challenger_id
            or evaluation.total_cases < cls._MINIMUM_SHADOW_CASES
            or evaluation.terminal_cases != evaluation.total_cases
        ):
            raise PolicyGateRejected("SHADOW_AGGREGATE_WINDOW_REQUIRED")
        if (
            evaluation.decision_stability_bps < 9_000
            or evaluation.locked_negative_leaks != 0
            or evaluation.schema_failures != 0
            or evaluation.authority_violations != 0
            or evaluation.evidence_violations != 0
            or evaluation.projection_failures != 0
            or evaluation.new_owner_semantic_tasks != 0
            or evaluation.technical_exception_bps > 2_000
            or evaluation.safety_hold_bps > 2_000
            or evaluation.suppression_bps > 2_000
            or evaluation.category_drift_bps > 2_000
            or not evaluation.gate_passed
            or evaluation.affects_production
        ):
            raise PolicyGateRejected("SHADOW_AGGREGATE_GATE_FAILED")

    @staticmethod
    def regression_reason(health: PolicyHealthEvidence) -> str | None:
        if health.total_runs < 20:
            return None
        if health.hard_negative_leaks:
            return "HARD_NEGATIVE_LEAKAGE"
        if health.schema_failures:
            return "SCHEMA_FAILURE"
        if health.projection_failures:
            return "PROJECTION_FAILURE"
        if health.cost_budget_exceeded:
            return "COST_BUDGET_EXCEEDED"
        if health.feed_yield_bps < 2_000:
            return "FEED_YIELD_COLLAPSE"
        if health.technical_exception_bps > 2_000:
            return "TECHNICAL_EXCEPTION_SPIKE"
        if health.safety_hold_bps > 2_000:
            return "SAFETY_HOLD_SPIKE"
        if health.suppression_bps > 2_000:
            return "SUPPRESSION_SPIKE"
        if health.category_drift_bps > 2_000:
            return "CATEGORY_DRIFT"
        return None


class PostgresPolicyOptimizationRepository:
    """Authoritative append-only policy lifecycle repository."""

    def __init__(self, *, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record_offline_replay(
        self,
        *,
        policy: QualificationPolicyBundle,
        report: OfflineReplayReport,
        evaluated_at: datetime,
    ) -> UUID:
        """Append a private aggregate replay without granting it production authority."""

        _validate_offline_report(policy, report)
        evaluation_id = uuid7()
        async with self._engine.begin() as connection:
            bundle_id = await persist_qualification_policy_bundle(
                connection,
                policy=policy,
                created_at=evaluated_at,
            )
            await connection.execute(
                text(
                    "INSERT INTO qualification_policy_evaluation_v2("
                    "id,policy_bundle_id,mode,benchmark_version,corpus_manifest_sha256,"
                    "total_cases,auto_accepted_count,auto_filtered_count,"
                    "technical_retry_count,technical_failed_count,safety_hold_count,"
                    "owner_suppressed_count,precision_bps,recall_bps,"
                    "locked_negative_leaks,schema_valid_bps,new_owner_semantic_tasks,"
                    "gate_passed,authorizes_production,evaluated_at) VALUES("
                    ":id,:bundle,'OFFLINE_REPLAY',:benchmark,:manifest,:total,:accepted,"
                    ":filtered,:retry,:failed,:safety,:suppressed,:precision,:recall,"
                    ":leaks,:schema,:owner_tasks,:gate,false,:now)"
                ),
                {
                    "id": evaluation_id,
                    "bundle": bundle_id,
                    "benchmark": report.benchmark_version,
                    "manifest": report.corpus_manifest_sha256,
                    "total": report.total_cases,
                    "accepted": report.auto_accepted,
                    "filtered": report.auto_filtered,
                    "retry": report.technical_retry,
                    "failed": report.technical_failed,
                    "safety": report.safety_hold,
                    "suppressed": report.owner_suppressed,
                    "precision": report.precision_bps,
                    "recall": report.recall_bps,
                    "leaks": report.locked_negative_leaks,
                    "schema": report.schema_valid_bps,
                    "owner_tasks": report.new_owner_semantic_tasks,
                    "gate": report.gate_passed,
                    "now": evaluated_at,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO qualification_policy_evaluation_invariant_v2("
                    "evaluation_id,terminal_cases,authority_violations,"
                    "evidence_violations,projection_failures,recorded_at) VALUES("
                    ":evaluation,:terminal,:authority,:evidence,:projection,:now)"
                ),
                {
                    "evaluation": evaluation_id,
                    "terminal": report.total_cases,
                    "authority": report.authority_violations,
                    "evidence": report.evidence_violations,
                    "projection": report.projection_failures,
                    "now": evaluated_at,
                },
            )
        return evaluation_id

    async def evaluation(self, evaluation_id: UUID) -> PolicyEvaluationEvidence:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT evaluation.*,invariant.terminal_cases,"
                            "invariant.authority_violations,invariant.evidence_violations "
                            "FROM qualification_policy_evaluation_v2 evaluation "
                            "JOIN qualification_policy_evaluation_invariant_v2 invariant "
                            "ON invariant.evaluation_id=evaluation.id "
                            "WHERE evaluation.id=:id"
                        ),
                        {"id": evaluation_id},
                    )
                )
                .mappings()
                .one()
            )
        mode = str(row["mode"])
        if mode not in {"OFFLINE_REPLAY", "SHADOW"}:
            raise RuntimeError("POLICY_EVALUATION_MODE_INVALID")
        return PolicyEvaluationEvidence(
            id=cast(UUID, row["id"]),
            policy_bundle_id=cast(UUID, row["policy_bundle_id"]),
            mode=cast(PolicyEvaluationMode, mode),
            total_cases=int(row["total_cases"]),
            terminal_cases=int(row["terminal_cases"]),
            precision_bps=int(row["precision_bps"]),
            recall_bps=int(row["recall_bps"]),
            locked_negative_leaks=int(row["locked_negative_leaks"]),
            schema_valid_bps=int(row["schema_valid_bps"]),
            authority_violations=int(row["authority_violations"]),
            evidence_violations=int(row["evidence_violations"]),
            new_owner_semantic_tasks=int(row["new_owner_semantic_tasks"]),
            gate_passed=bool(row["gate_passed"]),
            authorizes_production=bool(row["authorizes_production"]),
        )

    async def shadow_window(self, window_id: UUID) -> PolicyShadowWindowEvidence:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM qualification_policy_shadow_window_v2 "
                            "WHERE id=:id"
                        ),
                        {"id": window_id},
                    )
                )
                .mappings()
                .one()
            )
        return _shadow_window_from_row(row)

    async def active(self, source_stream_policy_version: str) -> PolicyActivation:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT activation.* FROM active_qualification_policy_v2 active "
                            "JOIN qualification_policy_activation_v2 activation "
                            "ON activation.id=active.activation_id "
                            "WHERE active.source_stream_policy_version=:stream_version"
                        ),
                        {"stream_version": source_stream_policy_version},
                    )
                )
                .mappings()
                .one()
            )
        return _activation_from_row(row)

    async def activation(self, activation_id: UUID) -> PolicyActivation:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM qualification_policy_activation_v2 WHERE id=:id"
                        ),
                        {"id": activation_id},
                    )
                )
                .mappings()
                .one()
            )
        return _activation_from_row(row)

    async def active_promotions(self) -> tuple[PolicyActivation, ...]:
        """Return only active challengers that have a rollback predecessor."""

        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT activation.* FROM active_qualification_policy_v2 active "
                            "JOIN qualification_policy_activation_v2 activation "
                            "ON activation.id=active.activation_id "
                            "WHERE activation.action='PROMOTE' "
                            "ORDER BY activation.activated_at,activation.id"
                        )
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_activation_from_row(row) for row in rows)

    async def promotion_candidates(
        self, *, observed_at: datetime
    ) -> tuple[PolicyPromotionCandidate, ...]:
        """Find offline-qualified challengers with one new aggregate shadow window."""

        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "WITH candidates AS("
                            "SELECT bundle.source_stream_policy_version AS stream_version,"
                            "evaluation.policy_bundle_id AS challenger_bundle_id,"
                            "active.policy_bundle_id AS champion_bundle_id,"
                            "evaluation.id AS offline_evaluation_id,"
                            "min(shadow.decided_at) AS window_started_at,"
                            "max(shadow.decided_at) AS last_shadow_at,"
                            "count(DISTINCT shadow.document_version_id) AS shadow_count "
                            "FROM qualification_policy_evaluation_v2 evaluation "
                            "JOIN qualification_policy_evaluation_invariant_v2 invariant "
                            "ON invariant.evaluation_id=evaluation.id "
                            "JOIN qualification_policy_bundle_v2 bundle "
                            "ON bundle.id=evaluation.policy_bundle_id "
                            "JOIN active_qualification_policy_v2 active "
                            "ON active.source_stream_policy_version="
                            "bundle.source_stream_policy_version "
                            "JOIN qualification_shadow_decision_v2 shadow "
                            "ON shadow.policy_bundle_id=evaluation.policy_bundle_id "
                            "AND shadow.affects_production=false "
                            "WHERE evaluation.mode='OFFLINE_REPLAY' "
                            "AND evaluation.gate_passed "
                            "AND evaluation.authorizes_production=false "
                            "AND evaluation.total_cases>0 "
                            "AND invariant.terminal_cases=evaluation.total_cases "
                            "AND evaluation.precision_bps>=9000 "
                            "AND evaluation.recall_bps>=9000 "
                            "AND evaluation.locked_negative_leaks=0 "
                            "AND evaluation.schema_valid_bps=10000 "
                            "AND evaluation.new_owner_semantic_tasks=0 "
                            "AND invariant.authority_violations=0 "
                            "AND invariant.evidence_violations=0 "
                            "AND invariant.projection_failures=0 "
                            "AND active.policy_bundle_id<>evaluation.policy_bundle_id "
                            "AND shadow.decided_at<:observed "
                            "GROUP BY bundle.source_stream_policy_version,"
                            "evaluation.policy_bundle_id,active.policy_bundle_id,evaluation.id "
                            "HAVING count(*)>=20) "
                            "SELECT * FROM candidates candidate WHERE NOT EXISTS("
                            "SELECT 1 FROM qualification_policy_shadow_window_v2 shadow_window "
                            "WHERE shadow_window.policy_bundle_id="
                            "candidate.challenger_bundle_id "
                            "AND shadow_window.window_started_at<=candidate.window_started_at "
                            "AND shadow_window.window_ended_at>candidate.last_shadow_at) "
                            "ORDER BY candidate.stream_version,candidate.offline_evaluation_id"
                        ),
                        {"observed": observed_at},
                    )
                )
                .mappings()
                .all()
            )
        return tuple(
            PolicyPromotionCandidate(
                source_stream_policy_version=str(row["stream_version"]),
                challenger_policy_bundle_id=cast(UUID, row["challenger_bundle_id"]),
                champion_policy_bundle_id=cast(UUID, row["champion_bundle_id"]),
                offline_evaluation_id=cast(UUID, row["offline_evaluation_id"]),
                window_started_at=cast(datetime, row["window_started_at"]),
            )
            for row in rows
        )

    async def append_activation(
        self,
        *,
        source_stream_policy_version: str,
        policy_bundle_id: UUID,
        previous_activation_id: UUID,
        action: str,
        reason_code: str,
        offline_evaluation_id: UUID | None,
        shadow_window_id: UUID | None,
        activated_at: datetime,
    ) -> PolicyActivation:
        async with self._engine.begin() as connection:
            activation_id = await connection.scalar(
                text(
                    "SELECT append_qualification_policy_activation_v2("
                    ":id,:stream,:bundle,:previous,:action,:reason,:offline,:shadow,:now)"
                ),
                {
                    "id": uuid7(),
                    "stream": source_stream_policy_version,
                    "bundle": policy_bundle_id,
                    "previous": previous_activation_id,
                    "action": action,
                    "reason": reason_code,
                    "offline": offline_evaluation_id,
                    "shadow": shadow_window_id,
                    "now": activated_at,
                },
            )
        if not isinstance(activation_id, UUID):
            raise RuntimeError("POLICY_ACTIVATION_NOT_PERSISTED")
        return await self.activation(activation_id)

    async def record_evaluation_invariants(
        self,
        *,
        evaluation_id: UUID,
        terminal_cases: int,
        authority_violations: int,
        evidence_violations: int,
        projection_failures: int,
        recorded_at: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO qualification_policy_evaluation_invariant_v2("
                    "evaluation_id,terminal_cases,authority_violations,evidence_violations,"
                    "projection_failures,recorded_at) VALUES("
                    ":evaluation,:terminal,:authority,:evidence,:projection,:now) "
                    "ON CONFLICT(evaluation_id) DO NOTHING"
                ),
                {
                    "evaluation": evaluation_id,
                    "terminal": terminal_cases,
                    "authority": authority_violations,
                    "evidence": evidence_violations,
                    "projection": projection_failures,
                    "now": recorded_at,
                },
            )

    async def aggregate_shadow_window(
        self,
        *,
        challenger_policy_bundle_id: UUID,
        champion_policy_bundle_id: UUID,
        window_started_at: datetime,
        window_ended_at: datetime,
        recorded_at: datetime,
    ) -> PolicyShadowWindowEvidence:
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT DISTINCT ON (shadow.document_version_id) "
                            "shadow.disposition,shadow.reason_codes,"
                            "shadow.decision_trace,champion.disposition AS champion_disposition,"
                            "champion.model_candidate AS champion_candidate,"
                            "EXISTS(SELECT 1 FROM event_suppression_match_v2 match "
                            "JOIN feed_suppression_effective_v2 suppression "
                            "ON suppression.scope=match.scope "
                            "AND suppression.target_key=match.target_key "
                            "WHERE match.document_version_id=shadow.document_version_id "
                            "AND suppression.feedback_reason='CLASSIFICATION_ERROR' "
                            "AND suppression.effective_at<=:ended "
                            "AND (suppression.revoked_at IS NULL "
                            "OR suppression.revoked_at>:ended)) "
                            "AS classification_error_suppressed "
                            "FROM qualification_shadow_decision_v2 shadow "
                            "LEFT JOIN LATERAL("
                            "SELECT decision.disposition,decision.model_candidate "
                            "FROM automated_qualification_decision_v2 decision "
                            "WHERE decision.document_version_id=shadow.document_version_id "
                            "AND decision.policy_bundle_id=:champion "
                            "ORDER BY decision.attempt_number DESC,decision.decided_at DESC "
                            "LIMIT 1) champion ON true "
                            "WHERE shadow.policy_bundle_id=:challenger "
                            "AND shadow.decided_at>=:started AND shadow.decided_at<:ended "
                            "AND shadow.affects_production=false "
                            "ORDER BY shadow.document_version_id,"
                            "shadow.decided_at DESC,shadow.id DESC"
                        ),
                        {
                            "champion": champion_policy_bundle_id,
                            "challenger": challenger_policy_bundle_id,
                            "started": window_started_at,
                            "ended": window_ended_at,
                        },
                    )
                )
                .mappings()
                .all()
            )
            values = _aggregate_shadow_rows(rows)
            projection_failures = int(
                await connection.scalar(
                    text(
                        "SELECT count(DISTINCT shadow.document_version_id) "
                        "FROM qualification_shadow_decision_v2 shadow "
                        "JOIN automated_qualification_decision_v2 production "
                        "ON production.document_version_id=shadow.document_version_id "
                        "AND production.policy_bundle_id=shadow.policy_bundle_id "
                        "AND production.normalized_input_sha256="
                        "shadow.decision_trace->>'normalized_input_sha256' "
                        "AND production.decided_at>=:started "
                        "AND production.decided_at<:ended "
                        "WHERE shadow.policy_bundle_id=:challenger "
                        "AND shadow.decided_at>=:started AND shadow.decided_at<:ended"
                    ),
                    {
                        "challenger": challenger_policy_bundle_id,
                        "started": window_started_at,
                        "ended": window_ended_at,
                    },
                )
                or 0
            )
            values["projection_failures"] = projection_failures
            values["gate_passed"] = bool(values["gate_passed"]) and projection_failures == 0
            window_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO qualification_policy_shadow_window_v2("
                    "id,policy_bundle_id,window_started_at,window_ended_at,total_cases,"
                    "terminal_cases,decision_stability_bps,auto_accepted_count,"
                    "auto_filtered_count,technical_retry_count,technical_failed_count,"
                    "safety_hold_count,owner_suppressed_count,category_distribution,"
                    "ai_cost_microusd,p95_latency_ms,locked_negative_leaks,schema_failures,"
                    "authority_violations,evidence_violations,projection_failures,"
                    "new_owner_semantic_tasks,technical_exception_bps,safety_hold_bps,"
                    "suppression_bps,category_drift_bps,gate_passed,affects_production,"
                    "created_at) VALUES("
                    ":id,:bundle,:started,:ended,:total,:terminal,:stability,:accepted,"
                    ":filtered,:retry,:failed,:safety,:suppressed,CAST(:categories AS jsonb),"
                    ":cost,:latency,:leaks,:schema,:authority,:evidence,:projection,:owner_tasks,"
                    ":technical_bps,:safety_bps,"
                    ":suppression_bps,:drift,:gate,false,:now) "
                    "ON CONFLICT(policy_bundle_id,window_started_at,window_ended_at) DO NOTHING"
                ),
                {
                    "id": window_id,
                    "bundle": challenger_policy_bundle_id,
                    "started": window_started_at,
                    "ended": window_ended_at,
                    "total": values["total_cases"],
                    "terminal": values["terminal_cases"],
                    "stability": values["decision_stability_bps"],
                    "accepted": values["AUTO_ACCEPTED"],
                    "filtered": values["AUTO_FILTERED"],
                    "retry": values["TECHNICAL_RETRY"],
                    "failed": values["TECHNICAL_FAILED"],
                    "safety": values["SAFETY_HOLD"],
                    "suppressed": values["OWNER_SUPPRESSED"],
                    "categories": json.dumps(values["category_distribution"], sort_keys=True),
                    "cost": values["ai_cost_microusd"],
                    "latency": values["p95_latency_ms"],
                    "leaks": values["locked_negative_leaks"],
                    "schema": values["schema_failures"],
                    "authority": values["authority_violations"],
                    "evidence": values["evidence_violations"],
                    "projection": values["projection_failures"],
                    "owner_tasks": values["new_owner_semantic_tasks"],
                    "technical_bps": values["technical_exception_bps"],
                    "safety_bps": values["safety_hold_bps"],
                    "suppression_bps": values["suppression_bps"],
                    "drift": values["category_drift_bps"],
                    "gate": values["gate_passed"],
                    "now": recorded_at,
                },
            )
            persisted_id = await connection.scalar(
                text(
                    "SELECT id FROM qualification_policy_shadow_window_v2 "
                    "WHERE policy_bundle_id=:bundle AND window_started_at=:started "
                    "AND window_ended_at=:ended"
                ),
                {
                    "bundle": challenger_policy_bundle_id,
                    "started": window_started_at,
                    "ended": window_ended_at,
                },
            )
        if not isinstance(persisted_id, UUID):
            raise RuntimeError("POLICY_SHADOW_WINDOW_NOT_PERSISTED")
        return await self.shadow_window(persisted_id)

    async def record_live_health(
        self,
        *,
        activation: PolicyActivation,
        window_started_at: datetime,
        window_ended_at: datetime,
        recorded_at: datetime,
    ) -> PolicyHealthEvidence:
        """Append one production health window for an active challenger."""

        if activation.previous_activation_id is None:
            raise ValueError("live challenger health requires a predecessor")
        previous = await self.activation(activation.previous_activation_id)
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT DISTINCT ON (decision.document_version_id) "
                            "decision.disposition,decision.reason_codes,"
                            "decision.model_candidate,run.failure_code,"
                            "champion.model_candidate AS champion_candidate,"
                            "publication.outcome AS publication_outcome,"
                            "EXISTS(SELECT 1 FROM event_suppression_match_v2 match "
                            "JOIN feed_suppression_effective_v2 suppression "
                            "ON suppression.scope=match.scope "
                            "AND suppression.target_key=match.target_key "
                            "WHERE match.document_version_id=decision.document_version_id "
                            "AND suppression.effective_at<=:ended "
                            "AND (suppression.revoked_at IS NULL "
                            "OR suppression.revoked_at>:ended)) AS actively_suppressed,"
                            "EXISTS(SELECT 1 FROM event_suppression_match_v2 match "
                            "JOIN feed_suppression_effective_v2 suppression "
                            "ON suppression.scope=match.scope "
                            "AND suppression.target_key=match.target_key "
                            "WHERE match.document_version_id=decision.document_version_id "
                            "AND suppression.feedback_reason='CLASSIFICATION_ERROR' "
                            "AND suppression.effective_at<=:ended "
                            "AND (suppression.revoked_at IS NULL "
                            "OR suppression.revoked_at>:ended)) "
                            "AS classification_error_suppressed,"
                            "EXISTS(SELECT 1 FROM ai_budget_reservation budget "
                            "WHERE budget.pipeline_run_id=run.id "
                            "AND budget.billing_status='UNKNOWN') OR EXISTS("
                            "SELECT 1 FROM ai_budget_policy budget_policy "
                            "JOIN ai_budget_month budget_month "
                            "ON budget_month.policy_id=budget_policy.id "
                            "WHERE budget_policy.active "
                            "AND budget_month.month_start=date_trunc('month',:ended)::date "
                            "AND budget_month.reserved_points+budget_month.settled_points"
                            ">=budget_policy.monthly_points) AS budget_failed "
                            "FROM automated_qualification_decision_v2 decision "
                            "JOIN LATERAL(SELECT pipeline.id,pipeline.failure_code "
                            "FROM ai_pipeline_run pipeline "
                            "WHERE pipeline.document_version_id=decision.document_version_id "
                            "AND pipeline.policy_bundle_id=decision.policy_bundle_id "
                            "ORDER BY pipeline.started_at DESC,pipeline.id DESC LIMIT 1) run "
                            "ON true LEFT JOIN LATERAL(SELECT prior.model_candidate "
                            "FROM automated_qualification_decision_v2 prior "
                            "WHERE prior.document_version_id=decision.document_version_id "
                            "AND prior.policy_bundle_id=:champion "
                            "ORDER BY prior.attempt_number DESC,prior.decided_at DESC LIMIT 1) "
                            "champion ON true LEFT JOIN LATERAL("
                            "SELECT published.outcome FROM publication_decision_v2 published "
                            "WHERE published.document_version_id=decision.document_version_id "
                            "ORDER BY published.created_at DESC,published.id DESC LIMIT 1"
                            ") publication ON true "
                            "WHERE decision.policy_bundle_id=:challenger "
                            "AND decision.decided_at>=:started AND decision.decided_at<:ended "
                            "ORDER BY decision.document_version_id,"
                            "decision.attempt_number DESC,decision.decided_at DESC"
                        ),
                        {
                            "champion": previous.policy_bundle_id,
                            "challenger": activation.policy_bundle_id,
                            "started": window_started_at,
                            "ended": window_ended_at,
                        },
                    )
                )
                .mappings()
                .all()
            )
            baseline_categories = await connection.scalar(
                text(
                    "SELECT shadow.category_distribution "
                    "FROM qualification_policy_activation_v2 policy_activation "
                    "JOIN qualification_policy_shadow_window_v2 shadow "
                    "ON shadow.id=policy_activation.shadow_window_id "
                    "WHERE policy_activation.id=:activation"
                ),
                {"activation": activation.id},
            )
            values = _aggregate_live_health_rows(
                rows,
                baseline_categories=(
                    cast(dict[str, int], baseline_categories)
                    if isinstance(baseline_categories, dict)
                    else {}
                ),
            )
            reason_codes = _live_regression_reason_codes(values)
            await connection.execute(
                text(
                    "INSERT INTO qualification_policy_health_v2("
                    "id,activation_id,window_started_at,window_ended_at,total_runs,"
                    "feed_yield_bps,technical_exception_bps,safety_hold_bps,"
                    "suppression_bps,schema_failures,projection_failures,"
                    "hard_negative_leaks,cost_budget_exceeded,category_drift_bps,"
                    "regression_reason_codes,recorded_at) VALUES("
                    ":id,:activation,:started,:ended,:total,:feed,:technical,:safety,"
                    ":suppression,:schema,:projection,:leaks,:cost,:drift,:reasons,:now) "
                    "ON CONFLICT(activation_id,window_started_at,window_ended_at) DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "activation": activation.id,
                    "started": window_started_at,
                    "ended": window_ended_at,
                    "total": values["total_runs"],
                    "feed": values["feed_yield_bps"],
                    "technical": values["technical_exception_bps"],
                    "safety": values["safety_hold_bps"],
                    "suppression": values["suppression_bps"],
                    "schema": values["schema_failures"],
                    "projection": values["projection_failures"],
                    "leaks": values["hard_negative_leaks"],
                    "cost": values["cost_budget_exceeded"],
                    "drift": values["category_drift_bps"],
                    "reasons": reason_codes,
                    "now": recorded_at,
                },
            )
        return PolicyHealthEvidence(
            activation_id=activation.id,
            total_runs=int(values["total_runs"]),
            feed_yield_bps=int(values["feed_yield_bps"]),
            technical_exception_bps=int(values["technical_exception_bps"]),
            safety_hold_bps=int(values["safety_hold_bps"]),
            suppression_bps=int(values["suppression_bps"]),
            schema_failures=int(values["schema_failures"]),
            projection_failures=int(values["projection_failures"]),
            hard_negative_leaks=int(values["hard_negative_leaks"]),
            cost_budget_exceeded=bool(values["cost_budget_exceeded"]),
            category_drift_bps=int(values["category_drift_bps"]),
        )

    async def close(self) -> None:
        await self._engine.dispose()


def _activation_from_row(row: RowMapping) -> PolicyActivation:
    action = str(row["action"])
    if action not in {"BOOTSTRAP", "PROMOTE", "ROLLBACK"}:
        raise RuntimeError("POLICY_ACTIVATION_ACTION_INVALID")
    return PolicyActivation(
        id=cast(UUID, row["id"]),
        source_stream_policy_version=str(row["source_stream_policy_version"]),
        policy_bundle_id=cast(UUID, row["policy_bundle_id"]),
        previous_activation_id=cast(UUID | None, row["previous_activation_id"]),
        action=cast(PolicyActivationAction, action),
        reason_code=str(row["reason_code"]),
        activated_at=cast(datetime, row["activated_at"]),
    )


def _validate_offline_report(
    policy: QualificationPolicyBundle, report: OfflineReplayReport
) -> None:
    dispositions = (
        report.auto_accepted
        + report.auto_filtered
        + report.technical_retry
        + report.technical_failed
        + report.safety_hold
        + report.owner_suppressed
    )
    if (
        report.policy_bundle_sha256 != policy.identity.bundle_sha256
        or report.authorizes_production
        or report.new_owner_semantic_tasks != 0
        or report.total_cases < 0
        or dispositions != report.total_cases
    ):
        raise ValueError("OFFLINE_REPLAY_AGGREGATE_INVALID")


def _shadow_window_from_row(row: RowMapping) -> PolicyShadowWindowEvidence:
    return PolicyShadowWindowEvidence(
        id=cast(UUID, row["id"]),
        policy_bundle_id=cast(UUID, row["policy_bundle_id"]),
        total_cases=int(row["total_cases"]),
        terminal_cases=int(row["terminal_cases"]),
        decision_stability_bps=int(row["decision_stability_bps"]),
        locked_negative_leaks=int(row["locked_negative_leaks"]),
        schema_failures=int(row["schema_failures"]),
        authority_violations=int(row["authority_violations"]),
        evidence_violations=int(row["evidence_violations"]),
        projection_failures=int(row["projection_failures"]),
        new_owner_semantic_tasks=int(row["new_owner_semantic_tasks"]),
        technical_exception_bps=int(row["technical_exception_bps"]),
        safety_hold_bps=int(row["safety_hold_bps"]),
        suppression_bps=int(row["suppression_bps"]),
        category_drift_bps=int(row["category_drift_bps"]),
        gate_passed=bool(row["gate_passed"]),
        affects_production=bool(row["affects_production"]),
    )


def _aggregate_shadow_rows(rows: Sequence[RowMapping]) -> dict[str, Any]:
    dispositions = {
        value: 0
        for value in (
            "AUTO_ACCEPTED",
            "AUTO_FILTERED",
            "TECHNICAL_RETRY",
            "TECHNICAL_FAILED",
            "SAFETY_HOLD",
            "OWNER_SUPPRESSED",
        )
    }
    categories: dict[str, int] = {}
    champion_categories: dict[str, int] = {}
    stable = 0
    schema_failures = 0
    locked_negative_leaks = 0
    authority_violations = 0
    evidence_violations = 0
    owner_semantic_tasks = 0
    latencies: list[int] = []
    cost = 0
    for row in rows:
        disposition = str(row["disposition"])
        if disposition not in dispositions:
            raise RuntimeError("POLICY_SHADOW_DISPOSITION_INVALID")
        dispositions[disposition] += 1
        if row.get("champion_disposition") == disposition:
            stable += 1
        reasons = {str(value) for value in cast(list[object], row["reason_codes"])}
        schema_failures += int("AI_SCHEMA_INVALID" in reasons)
        evidence_violations += int(
            bool(reasons & {"EVIDENCE_MISSING", "EVIDENCE_LOCATOR_INVALID"})
        )
        owner_semantic_tasks += int("OWNER_CLASSIFICATION_ERROR" in reasons)
        locked_negative_leaks += int(
            disposition == "AUTO_ACCEPTED"
            and (
                "RULE_LOCKED_NEGATIVE" in reasons
                or bool(row.get("classification_error_suppressed"))
            )
        )
        trace = cast(dict[str, Any], row["decision_trace"])
        candidate = trace.get("model_candidate")
        if isinstance(candidate, dict) and isinstance(candidate.get("primary_type"), str):
            category = str(candidate["primary_type"])
            categories[category] = categories.get(category, 0) + 1
        champion_candidate = row.get("champion_candidate")
        if isinstance(champion_candidate, dict) and isinstance(
            champion_candidate.get("primary_type"), str
        ):
            champion_category = str(champion_candidate["primary_type"])
            champion_categories[champion_category] = (
                champion_categories.get(champion_category, 0) + 1
            )
        latency = trace.get("model_latency_ms")
        if isinstance(latency, int) and latency >= 0:
            latencies.append(latency)
        candidate_cost = trace.get("model_cost_microusd")
        if isinstance(candidate_cost, int) and candidate_cost >= 0:
            cost += candidate_cost
    total = len(rows)
    stability = _bps(stable, total)
    technical = dispositions["TECHNICAL_RETRY"] + dispositions["TECHNICAL_FAILED"]
    category_drift = _category_drift_bps(categories, champion_categories)
    p95_latency = 0
    if latencies:
        ordered = sorted(latencies)
        p95_latency = ordered[min(len(ordered) - 1, (len(ordered) * 95 - 1) // 100)]
    gate = (
        total >= 20
        and stability >= 9_000
        and schema_failures == 0
        and locked_negative_leaks == 0
        and authority_violations == 0
        and evidence_violations == 0
        and owner_semantic_tasks == 0
        and _bps(technical, total) <= 2_000
        and _bps(dispositions["SAFETY_HOLD"], total) <= 2_000
        and _bps(dispositions["OWNER_SUPPRESSED"], total) <= 2_000
        and category_drift <= 2_000
    )
    return {
        **dispositions,
        "total_cases": total,
        "terminal_cases": total,
        "decision_stability_bps": stability,
        "category_distribution": categories,
        "ai_cost_microusd": cost,
        "p95_latency_ms": p95_latency,
        "locked_negative_leaks": locked_negative_leaks,
        "schema_failures": schema_failures,
        "authority_violations": authority_violations,
        "evidence_violations": evidence_violations,
        "new_owner_semantic_tasks": owner_semantic_tasks,
        "technical_exception_bps": _bps(technical, total),
        "safety_hold_bps": _bps(dispositions["SAFETY_HOLD"], total),
        "suppression_bps": _bps(dispositions["OWNER_SUPPRESSED"], total),
        "category_drift_bps": category_drift,
        "gate_passed": gate,
        "window_manifest_sha256": sha256(
            json.dumps(dispositions, sort_keys=True).encode()
        ).hexdigest(),
    }


def _aggregate_live_health_rows(
    rows: Sequence[RowMapping], *, baseline_categories: dict[str, int] | None = None
) -> dict[str, int | bool]:
    total = len(rows)
    accepted = 0
    technical = 0
    safety = 0
    suppressed = 0
    schema_failures = 0
    projection_failures = 0
    hard_negative_leaks = 0
    cost_budget_exceeded = False
    categories: dict[str, int] = {}
    champion_categories: dict[str, int] = {}
    for row in rows:
        disposition = str(row["disposition"])
        reasons = {str(value) for value in cast(list[object], row["reason_codes"])}
        failure_code = str(row.get("failure_code") or "")
        accepted += int(
            disposition == "AUTO_ACCEPTED" and row.get("publication_outcome") == "FULL"
        )
        technical += int(disposition in {"TECHNICAL_RETRY", "TECHNICAL_FAILED"})
        safety += int(disposition == "SAFETY_HOLD")
        suppressed += int(bool(row.get("actively_suppressed")))
        schema_failures += int(
            "AI_SCHEMA_INVALID" in reasons or failure_code == "SCHEMA_REJECTED"
        )
        projection_failures += int(
            disposition == "AUTO_ACCEPTED"
            and row.get("publication_outcome") not in {"FULL", "R3_METADATA"}
        )
        hard_negative_leaks += int(
            disposition == "AUTO_ACCEPTED"
            and (
                "RULE_LOCKED_NEGATIVE" in reasons
                or bool(row.get("classification_error_suppressed"))
            )
        )
        cost_budget_exceeded = cost_budget_exceeded or bool(row.get("budget_failed")) or bool(
            reasons
            & {
                "AI_BUDGET_EXHAUSTED",
                "BUDGET_EXCEEDED",
                "COST_BUDGET_EXCEEDED",
            }
        )
        _increment_candidate_category(categories, row.get("model_candidate"))
        _increment_candidate_category(champion_categories, row.get("champion_candidate"))
    return {
        "total_runs": total,
        "feed_yield_bps": _bps(accepted, total),
        "technical_exception_bps": _bps(technical, total),
        "safety_hold_bps": _bps(safety, total),
        "suppression_bps": _bps(suppressed, total),
        "schema_failures": schema_failures,
        "projection_failures": projection_failures,
        "hard_negative_leaks": hard_negative_leaks,
        "cost_budget_exceeded": cost_budget_exceeded,
        "category_drift_bps": _category_drift_bps(
            categories,
            champion_categories or (baseline_categories or {}),
        ),
    }


def _increment_candidate_category(target: dict[str, int], candidate: object) -> None:
    if isinstance(candidate, dict) and isinstance(candidate.get("primary_type"), str):
        category = str(candidate["primary_type"])
        target[category] = target.get(category, 0) + 1


def _live_regression_reason_codes(values: dict[str, int | bool]) -> list[str]:
    health = PolicyHealthEvidence(
        activation_id=UUID(int=0),
        total_runs=int(values["total_runs"]),
        feed_yield_bps=int(values["feed_yield_bps"]),
        technical_exception_bps=int(values["technical_exception_bps"]),
        safety_hold_bps=int(values["safety_hold_bps"]),
        suppression_bps=int(values["suppression_bps"]),
        schema_failures=int(values["schema_failures"]),
        projection_failures=int(values["projection_failures"]),
        hard_negative_leaks=int(values["hard_negative_leaks"]),
        cost_budget_exceeded=bool(values["cost_budget_exceeded"]),
        category_drift_bps=int(values["category_drift_bps"]),
    )
    reason = PolicyOptimizationService.regression_reason(health)
    return [] if reason is None else [reason]


def _bps(count: int, total: int) -> int:
    return 0 if total == 0 else min(10_000, count * 10_000 // total)


def _category_drift_bps(candidate: dict[str, int], champion: dict[str, int]) -> int:
    candidate_total = sum(candidate.values())
    champion_total = sum(champion.values())
    if candidate_total == 0 and champion_total == 0:
        return 0
    if candidate_total == 0 or champion_total == 0:
        return 10_000
    keys = set(candidate) | set(champion)
    absolute_delta = sum(
        abs(
            candidate.get(key, 0) * champion_total
            - champion.get(key, 0) * candidate_total
        )
        for key in keys
    )
    return min(
        10_000,
        absolute_delta * 5_000 // (candidate_total * champion_total),
    )
