from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.ai_pipeline.content_preparation import (
    AiContentPreparationService,
    PreparationDocument,
    production_policy_for,
)
from srbg_api.ai_pipeline.contracts import AiStep
from srbg_api.ai_pipeline.preparation import PreparedDocumentInput
from srbg_api.intelligence_v2.autonomous_policy import QualificationPolicyBundle
from srbg_api.intelligence_v2.policy_optimization import (
    PolicyActivation,
    PolicyEvaluationEvidence,
    PolicyGateRejected,
    PolicyHealthEvidence,
    PolicyOptimizationService,
    PolicyShadowWindowEvidence,
    _aggregate_live_health_rows,
    _aggregate_shadow_rows,
    _validate_offline_report,
)
from srbg_api.intelligence_v2.private_policy_replay import OfflineReplayReport

CHAMPION_ID = UUID("019c0000-0000-7000-8000-000000000001")
CHALLENGER_ID = UUID("019c0000-0000-7000-8000-000000000002")
OFFLINE_ID = UUID("019c0000-0000-7000-8000-000000000003")
SHADOW_ID = UUID("019c0000-0000-7000-8000-000000000004")
ACTIVATION_ID = UUID("019c0000-0000-7000-8000-000000000005")
NOW = datetime(2026, 7, 23, 1, 0, tzinfo=UTC)


def test_pipeline_document_uses_its_creation_time_policy_bundle() -> None:
    frozen = QualificationPolicyBundle.create(
        policy_version="qualification-policy-challenger-3.0.0",
        global_rule_version="global-rules-3.0.0",
        source_stream_policy_version="stream-policy-7",
        ai_provider="deepseek",
        ai_model="deepseek-v4-flash",
        prompt_version="autonomous-classify-3.0.0",
        schema_version="autonomous-classify-output-2.0.0",
        code_version="issue-46-challenger",
    )
    document = PreparationDocument(
        run_id=UUID(int=100),
        document_version_id=UUID(int=101),
        raw_object_id=UUID(int=102),
        source_stream_policy_version="stream-policy-7",
        source_code="SRC-001",
        canonical_url="https://example.invalid/item",
        title="Policy fixture",
        source_name="Fixture source",
        blocks=(),
        policy_bundle=frozen,
    )

    assert production_policy_for(document) is frozen


def test_persisted_policy_fails_closed_when_current_components_drift() -> None:
    policy = QualificationPolicyBundle.create(
        policy_version="qualification-policy-challenger-3.0.0",
        global_rule_version="global-rules-3.0.0",
        source_stream_policy_version="stream-policy-7",
        ai_provider="deepseek",
        ai_model="deepseek-v4-flash",
        prompt_version="autonomous-classify-3.0.0",
        schema_version="autonomous-classify-output-2.0.0",
        code_version="issue-46-challenger",
    )

    with pytest.raises(ValueError, match="QUALIFICATION_POLICY_BUNDLE_DIGEST_MISMATCH"):
        QualificationPolicyBundle.from_persisted(
            policy_version=policy.identity.policy_version,
            global_rule_version=policy.identity.global_rule_version,
            source_stream_policy_version=policy.identity.source_stream_policy_version,
            ai_provider=policy.identity.ai_provider,
            ai_model=policy.identity.ai_model,
            prompt_version=policy.identity.prompt_version,
            schema_version=policy.identity.schema_version,
            code_version=policy.identity.code_version,
            bundle_sha256="0" * 64,
            policy_payload={
                "source_allow_terms": [],
                "source_exclude_terms": [],
            },
        )


def test_classification_request_uses_the_frozen_bundle_model() -> None:
    policy = QualificationPolicyBundle.create(
        policy_version="qualification-policy-challenger-3.0.0",
        global_rule_version="global-rules-3.0.0",
        source_stream_policy_version="stream-policy-7",
        ai_provider="deepseek",
        ai_model="pinned-challenger-model",
        prompt_version="autonomous-classify-3.0.0",
        schema_version="autonomous-classify-output-2.0.0",
        code_version="issue-46-challenger",
    )
    prepared = PreparedDocumentInput(
        text="fixture",
        input_sha256="a" * 64,
        anchors={},
        block_ids=("block-1",),
    )

    request = AiContentPreparationService.build_request(
        AiStep.CLASSIFY,
        prepared,
        policy=policy,
    )

    assert request.model_profile == "pinned-challenger-model"


def test_offline_replay_can_never_self_authorize_production() -> None:
    policy = QualificationPolicyBundle.create(
        policy_version="qualification-policy-challenger-3.0.0",
        global_rule_version="global-rules-3.0.0",
        source_stream_policy_version="stream-policy-7",
        ai_provider="deepseek",
        ai_model="deepseek-v4-flash",
        prompt_version="autonomous-classify-3.0.0",
        schema_version="autonomous-classify-output-2.0.0",
        code_version="issue-46-challenger",
    )
    report = OfflineReplayReport(
        benchmark_version="private-v5",
        corpus_manifest_sha256="a" * 64,
        policy_bundle_sha256=policy.identity.bundle_sha256,
        total_cases=20,
        auto_accepted=10,
        auto_filtered=10,
        technical_retry=0,
        technical_failed=0,
        safety_hold=0,
        owner_suppressed=0,
        precision_bps=10_000,
        recall_bps=10_000,
        locked_negative_leaks=0,
        schema_valid_bps=10_000,
        new_owner_semantic_tasks=0,
        authority_violations=0,
        evidence_violations=0,
        projection_failures=0,
        gate_passed=True,
        authorizes_production=True,
    )

    with pytest.raises(ValueError, match="OFFLINE_REPLAY_AGGREGATE_INVALID"):
        _validate_offline_report(policy, report)


class InMemoryPolicyRepository:
    def __init__(self) -> None:
        self.evaluations = {
            OFFLINE_ID: PolicyEvaluationEvidence(
                id=OFFLINE_ID,
                policy_bundle_id=CHALLENGER_ID,
                mode="OFFLINE_REPLAY",
                total_cases=40,
                terminal_cases=40,
                precision_bps=9_250,
                recall_bps=9_000,
                locked_negative_leaks=0,
                schema_valid_bps=10_000,
                authority_violations=0,
                evidence_violations=0,
                new_owner_semantic_tasks=0,
                gate_passed=True,
                authorizes_production=False,
            ),
        }
        self.shadow_windows = {
            SHADOW_ID: PolicyShadowWindowEvidence(
                id=SHADOW_ID,
                policy_bundle_id=CHALLENGER_ID,
                total_cases=24,
                terminal_cases=24,
                decision_stability_bps=9_500,
                locked_negative_leaks=0,
                schema_failures=0,
                authority_violations=0,
                evidence_violations=0,
                projection_failures=0,
                new_owner_semantic_tasks=0,
                technical_exception_bps=0,
                safety_hold_bps=0,
                suppression_bps=0,
                category_drift_bps=500,
                gate_passed=True,
                affects_production=False,
            )
        }
        self.current = PolicyActivation(
            id=ACTIVATION_ID,
            source_stream_policy_version="stream-policy-7",
            policy_bundle_id=CHAMPION_ID,
            previous_activation_id=None,
            action="BOOTSTRAP",
            reason_code="ADR_0005_PRODUCTION_BASELINE",
            activated_at=NOW,
        )
        self.activations = {ACTIVATION_ID: self.current}
        self.appended: list[PolicyActivation] = []

    async def evaluation(self, evaluation_id: UUID) -> PolicyEvaluationEvidence:
        return self.evaluations[evaluation_id]

    async def active(self, source_stream_policy_version: str) -> PolicyActivation:
        assert source_stream_policy_version == "stream-policy-7"
        return self.current

    async def activation(self, activation_id: UUID) -> PolicyActivation:
        return self.activations[activation_id]

    async def shadow_window(self, window_id: UUID) -> PolicyShadowWindowEvidence:
        return self.shadow_windows[window_id]

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
        value = PolicyActivation(
            id=UUID(int=ACTIVATION_ID.int + len(self.appended) + 1),
            source_stream_policy_version=source_stream_policy_version,
            policy_bundle_id=policy_bundle_id,
            previous_activation_id=previous_activation_id,
            action=action,
            reason_code=reason_code,
            activated_at=activated_at,
        )
        self.appended.append(value)
        self.activations[value.id] = value
        self.current = value
        return value


@pytest.mark.asyncio
async def test_challenger_requires_offline_and_aggregate_shadow_gates() -> None:
    repository = InMemoryPolicyRepository()
    service = PolicyOptimizationService(repository=repository)

    promoted = await service.promote(
        source_stream_policy_version="stream-policy-7",
        challenger_policy_bundle_id=CHALLENGER_ID,
        offline_evaluation_id=OFFLINE_ID,
        shadow_window_id=SHADOW_ID,
        now=NOW,
    )

    assert promoted.policy_bundle_id == CHALLENGER_ID
    assert promoted.previous_activation_id == ACTIVATION_ID
    assert promoted.action == "PROMOTE"
    assert len(repository.appended) == 1

    repository.evaluations[OFFLINE_ID] = replace(
        repository.evaluations[OFFLINE_ID],
        precision_bps=7_000,
        recall_bps=7_000,
        locked_negative_leaks=5,
        gate_passed=False,
    )
    with pytest.raises(PolicyGateRejected, match="OFFLINE_REPLAY_GATE_FAILED"):
        await service.promote(
            source_stream_policy_version="stream-policy-7",
            challenger_policy_bundle_id=CHALLENGER_ID,
            offline_evaluation_id=OFFLINE_ID,
            shadow_window_id=SHADOW_ID,
            now=NOW,
        )


@pytest.mark.asyncio
async def test_single_document_shadow_cannot_promote() -> None:
    repository = InMemoryPolicyRepository()
    repository.shadow_windows[SHADOW_ID] = replace(
        repository.shadow_windows[SHADOW_ID], total_cases=1, terminal_cases=1
    )

    with pytest.raises(PolicyGateRejected, match="SHADOW_AGGREGATE_WINDOW_REQUIRED"):
        await PolicyOptimizationService(repository=repository).promote(
            source_stream_policy_version="stream-policy-7",
            challenger_policy_bundle_id=CHALLENGER_ID,
            offline_evaluation_id=OFFLINE_ID,
            shadow_window_id=SHADOW_ID,
            now=NOW,
        )


@pytest.mark.asyncio
async def test_live_regression_rolls_back_once_to_the_previous_champion() -> None:
    repository = InMemoryPolicyRepository()
    promoted = await PolicyOptimizationService(repository=repository).promote(
        source_stream_policy_version="stream-policy-7",
        challenger_policy_bundle_id=CHALLENGER_ID,
        offline_evaluation_id=OFFLINE_ID,
        shadow_window_id=SHADOW_ID,
        now=NOW,
    )
    service = PolicyOptimizationService(repository=repository)
    health = PolicyHealthEvidence(
        activation_id=promoted.id,
        total_runs=30,
        feed_yield_bps=1_000,
        technical_exception_bps=2_500,
        safety_hold_bps=0,
        suppression_bps=0,
        schema_failures=0,
        projection_failures=0,
        hard_negative_leaks=0,
        cost_budget_exceeded=False,
        category_drift_bps=0,
    )

    rolled_back = await service.rollback_if_regressed(health=health, now=NOW)
    replay = await service.rollback_if_regressed(health=health, now=NOW)

    assert rolled_back is not None
    assert rolled_back.policy_bundle_id == CHAMPION_ID
    assert rolled_back.action == "ROLLBACK"
    assert rolled_back.reason_code == "FEED_YIELD_COLLAPSE"
    assert replay == rolled_back
    assert [value.action for value in repository.appended] == ["PROMOTE", "ROLLBACK"]


def test_live_health_aggregation_detects_schema_and_feed_regression() -> None:
    rows = [
        {
            "disposition": "AUTO_FILTERED",
            "reason_codes": ["AI_SCHEMA_INVALID"],
            "model_candidate": None,
            "champion_candidate": None,
            "failure_code": "SCHEMA_REJECTED",
        }
        for _ in range(20)
    ]

    health = _aggregate_live_health_rows(rows)

    assert health["total_runs"] == 20
    assert health["feed_yield_bps"] == 0
    assert health["schema_failures"] == 20
    assert health["cost_budget_exceeded"] is False


def test_live_health_treats_owner_classification_error_as_hard_negative_leak() -> None:
    health = _aggregate_live_health_rows(
        [
            {
                "disposition": "AUTO_ACCEPTED",
                "reason_codes": [],
                "model_candidate": None,
                "champion_candidate": None,
                "failure_code": None,
                "publication_outcome": "FULL",
                "classification_error_suppressed": True,
            }
        ]
    )

    assert health["hard_negative_leaks"] == 1


def test_shadow_treats_owner_classification_error_as_hard_negative_leak() -> None:
    rows = [
        {
            "disposition": "AUTO_ACCEPTED",
            "reason_codes": ["MODEL_RELEVANT"],
            "decision_trace": {"model_candidate": None},
            "champion_disposition": "AUTO_ACCEPTED",
            "champion_candidate": None,
            "classification_error_suppressed": index == 0,
        }
        for index in range(20)
    ]

    health = _aggregate_shadow_rows(rows)

    assert health["locked_negative_leaks"] == 1
    assert health["gate_passed"] is False
