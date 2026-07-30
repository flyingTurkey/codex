from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
import srbg_worker.app as worker
from srbg_api.ai_pipeline.content_preparation import (
    PreparationDocument,
    production_policy_for_stream,
)
from srbg_api.ai_pipeline.contracts import AiStep, ModelResponse
from srbg_api.ai_pipeline.preparation import DocumentBlock
from srbg_api.ai_pipeline.runtime import AttemptKind
from srbg_api.intelligence_v2.qualification_decisions import (
    append_qualification_decision,
    persist_qualification_policy_bundle,
)
from srbg_worker.ai_content_preparation import PostgresAiPreparationRepository

RUN_ID = UUID("019f7900-0000-7000-8000-000000000001")
RESERVATION_ID = UUID("019f7900-0000-7000-8000-000000000002")


def test_runtime_probe_budget_query_pins_postgres_timestamp_type() -> None:
    source = inspect.getsource(PostgresAiPreparationRepository.record_runtime_observation)

    assert "CAST(:now AS timestamptz)" in source


def test_runtime_probe_projects_the_catalog_model_name() -> None:
    source = inspect.getsource(worker._record_ai_runtime_observation)

    assert 'model="deepseek-v4-flash"' in source


def test_fixed_canary_orders_versions_by_the_real_acquisition_column() -> None:
    source = inspect.getsource(PostgresAiPreparationRepository.create_fixed_canary_run)

    assert "version.acquired_at" in source
    assert "version.created_at" not in source
    assert "policy_bundle_id" in source
    assert "active_qualification_policy_v2" in source
    assert "OFFLINE_REPLAY" in source
    assert "challenger.policy_bundle_id" in source
    assert "bundle.ai_provider='deepseek'" in source
    assert "bundle.ai_model='deepseek-v4-flash'" in source
    assert "bundle.prompt_version='autonomous-classify-2.7.0'" in source
    assert "bundle.schema_version='autonomous-classify-output-2.0.0'" in source


def test_fixed_canary_terminal_state_accepts_real_document_preparation() -> None:
    source = inspect.getsource(PostgresAiPreparationRepository.complete_fixed_canary)

    assert "status IN ('QUEUED','PREPARING')" in source


def test_fixed_canary_dispatch_and_callback_use_the_run_bound_bundle() -> None:
    dispatch_source = inspect.getsource(worker._dispatch_ai_v2_canary)
    callback_source = inspect.getsource(worker._record_ai_v2_canary_result)

    assert "policy_bundle" in dispatch_source
    assert "policy=policy_bundle" in dispatch_source
    assert "_prepare_ai_inputs_for_document(document)" in dispatch_source
    assert "bind_shadow_input" in dispatch_source
    assert "production_policy_for(document)" in callback_source
    assert "policy=policy_bundle" in callback_source
    assert "_prepare_ai_inputs_for_document(document)" in callback_source
    assert "fixed_canary_input" not in callback_source
    assert "runtime_model" in callback_source
    assert "prompt_version=request.prompt_version" in callback_source
    assert "schema_version=request.schema_version" in callback_source
    assert "append_shadow_decision(trace, policy_bundle)" in callback_source


def test_policy_health_monitor_is_scheduled_and_can_auto_rollback() -> None:
    schedule = worker.celery_app.conf.beat_schedule
    source = inspect.getsource(worker._monitor_policy_health)

    assert schedule["monitor-policy-health"]["schedule"] == 60.0
    assert "promotion_candidates" in source
    assert "aggregate_shadow_window" in source
    assert ".promote(" in source
    assert "record_live_health" in source
    assert "rollback_if_regressed" in source


def test_every_physical_model_dispatch_reauthorizes_before_budget_reservation() -> None:
    source = inspect.getsource(worker._dispatch_ai_attempt)

    assert source.index("authorize_model_call") < source.index("repository.reserve")
    assert source.index("authorize_model_call") < source.index("celery_app.send_task")


def test_owner_retry_separates_bounded_physical_and_immutable_decision_attempts() -> None:
    source = inspect.getsource(worker._dispatch_due_technical_retries)

    assert "attempt=due.attempt_count + 1" in source
    assert "decision_attempt=due.next_attempt_number" in source


def test_success_persistence_reauthorizes_before_writing_model_content() -> None:
    append_source = inspect.getsource(PostgresAiPreparationRepository._append_step_row)
    append_connection_source = inspect.getsource(
        PostgresAiPreparationRepository._append_step_row_in_connection
    )
    success_source = inspect.getsource(
        PostgresAiPreparationRepository.record_approved_content_success
    )

    assert "authorize_model_call" in append_source
    assert append_source.index("authorize_model_call") < append_source.index(
        "_append_step_row_in_connection"
    )
    assert "raw_output" in append_connection_source
    for token in (
        "raw.scan_status='CLEAN'",
        "source_admission_assessment_v2",
        "version.execution_domain IN ('TRIAL','PRODUCTION')",
        "ai_budget_policy",
    ):
        assert token in success_source

    callback_source = inspect.getsource(worker._handle_ai_content_result)
    success_branch = callback_source.split('if result.get("status") == "SUCCEEDED":', 1)[1]
    assert success_branch.index("authorize_model_call") < success_branch.index("repository.settle")


def test_worker_uses_versioned_autonomous_decision_without_owner_gold() -> None:
    callback_source = inspect.getsource(worker._handle_ai_content_result)

    assert "load_auto_pass_calibration" not in callback_source
    assert "OWNER_OVERRIDE_GO" not in callback_source
    assert "append_automated_decision" in callback_source
    assert "adjudicate_candidates" in callback_source
    assert "if semantic_recheck" in callback_source
    assert "successful_output_before_attempt" in callback_source
    assert "attempt=attempt + 1" in callback_source


def test_semantic_recheck_flag_survives_every_failure_redispatch() -> None:
    callback_source = inspect.getsource(worker._handle_ai_content_result)
    failure_tail = callback_source.split("await repository.settle(reservation_id, None)", 1)[1]

    assert failure_tail.count("semantic_recheck=semantic_recheck") == 3


def test_repository_persists_policy_identity_and_decision_append_only() -> None:
    repository_source = inspect.getsource(PostgresAiPreparationRepository.append_automated_decision)
    source = inspect.getsource(append_qualification_decision)
    bundle_source = inspect.getsource(persist_qualification_policy_bundle)

    assert "append_qualification_decision" in repository_source
    assert "qualification_policy_bundle_v2" in bundle_source
    assert "automated_qualification_decision_v2" in source
    assert "ON CONFLICT (bundle_sha256) DO NOTHING" in bundle_source
    assert "owner_gold" not in (source + bundle_source).casefold()


def test_live_safety_hold_projects_through_server_owned_exception_function() -> None:
    source = inspect.getsource(append_qualification_decision)

    assert "classify_safety_signals" in source
    assert "record_safety_exception_v2" in source
    assert "SafetyOverrideability" not in source


def test_prompt_injection_prescan_enters_the_same_safety_hold_lifecycle() -> None:
    source = inspect.getsource(worker._start_ai_content_preparation)
    detected_branch = source.split("if scan.detected:", 1)[1].split(
        "deterministic_trace = try_deterministic_adjudication", 1
    )[0]

    assert "SAFETY_HOLD" in detected_branch
    assert "append_automated_decision" in detected_branch
    assert "PROMPT_INJECTION_R4" not in detected_branch
    assert "extract_input.input_sha256" in detected_branch
    assert "list(extract_input.block_ids)" in detected_branch
    assert 'transition(run_id, "SUCCEEDED")' not in detected_branch
    assert 'transition(run_id, "CLASSIFYING")' in detected_branch
    assert "_dispatch_ai_attempt" in source


def test_model_safety_hold_continues_to_prepare_gated_publication_context() -> None:
    source = " ".join(inspect.getsource(worker._handle_ai_content_result).split())

    branch = source.split("trace.disposition not in", 1)[1].split(
        "await repository.transition(run_id, \"EXTRACTING\")", 1
    )[0]
    assert "AutomatedDisposition.AUTO_ACCEPTED" in branch
    assert "AutomatedDisposition.SAFETY_HOLD" in branch
    assert "trace.model_candidate is None" in branch
    assert '"projection_eligible": False' in branch


@dataclass
class RevokedAuthorizationRepository:
    settled: list[ModelResponse | None] = field(default_factory=list)
    failed_steps: list[tuple[AiStep, str]] = field(default_factory=list)
    failed_step_usage: list[tuple[int, int]] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    closed: bool = False
    require_billing_response: bool = True

    async def begin(self, run_id: UUID) -> PreparationDocument:
        assert run_id == RUN_ID
        return PreparationDocument(
            run_id=run_id,
            document_version_id=UUID("019f7900-0000-7000-8000-000000000003"),
            raw_object_id=UUID("019f7900-0000-7000-8000-000000000004"),
            source_stream_policy_version="stream-policy-7",
            source_code="GOV-002",
            canonical_url="https://example.invalid/public-record",
            title="公开工程记录",
            source_name="权威来源",
            blocks=(
                DocumentBlock(
                    block_id="block-1",
                    page_number=1,
                    text="公开记录包含一项工程事实。",
                    locator_value="page=1",
                ),
            ),
            policy_bundle=production_policy_for_stream("stream-policy-7"),
        )

    async def authorize_real_run(self, document: PreparationDocument) -> bool:
        assert document.run_id == RUN_ID
        return False

    async def settle(self, reservation_id: UUID, response: ModelResponse | None) -> None:
        assert reservation_id == RESERVATION_ID
        self.settled.append(response)

    async def append_failed_step(
        self,
        run_id: UUID,
        step: AiStep,
        attempt: int,
        kind: str,
        code: str,
        input_sha256: str | None,
        billing_response: ModelResponse | None = None,
    ) -> None:
        assert run_id == RUN_ID
        assert attempt == 1
        assert kind == AttemptKind.PRIMARY.value
        assert input_sha256 is None
        self.failed_steps.append((step, code))
        if self.require_billing_response:
            assert billing_response is not None
        if billing_response is not None:
            self.failed_step_usage.append(
                (billing_response.usage.input_tokens, billing_response.cost_microusd)
            )

    async def fail(self, run_id: UUID, status: str, code: str) -> None:
        assert run_id == RUN_ID
        self.failures.append((status, code))

    async def close(self) -> None:
        self.closed = True

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"revoked callback must not call repository.{name}")


@dataclass
class RevokedBeforeReadRepository(RevokedAuthorizationRepository):
    async def begin(self, run_id: UUID) -> PreparationDocument:
        assert run_id == RUN_ID
        raise RuntimeError("AI01_SHADOW_AUTHORITY_INVALID")


def _successful_classification_result() -> dict[str, object]:
    output = {
        "direct_relevance": "RELEVANT",
        "core_new_fact": "工程记录包含一项新事实",
        "primary_type": "INDUSTRY_UPDATE",
        "engineering_objects": ["HIGHWAY"],
        "specialty_facets": [],
        "equipment_domains": [],
        "content_form": "PROJECT_RECORD",
        "evidence_locators": ["page=1"],
        "confidence": 0.96,
        "ambiguity_indicators": [],
        "security_signals": [],
    }
    return {
        "status": "SUCCEEDED",
        "runtime_provider": "deepseek",
        "runtime_model": "deepseek-v4-flash",
        "response": {
            "raw_output": json.dumps(output, ensure_ascii=False),
            "output": output,
            "usage": {
                "input_tokens": 21,
                "output_tokens": 8,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 21,
            },
            "cost_microusd": 17,
            "latency_ms": 42,
            "provider_request_id": "redacted-request-id",
            "finish_reason": "stop",
        },
    }


@pytest.mark.asyncio
async def test_revoked_authorization_settles_real_usage_and_terminalizes_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = RevokedAuthorizationRepository()
    monkeypatch.setattr(worker, "_ai_repository", lambda: repository)

    result = await worker._handle_ai_content_result(
        result=_successful_classification_result(),
        run_id=RUN_ID,
        step=AiStep.CLASSIFY,
        attempt=1,
        kind=AttemptKind.PRIMARY,
        network_retries=0,
        repair_used=False,
        reservation_id=RESERVATION_ID,
    )

    assert result == {
        "run_id": str(RUN_ID),
        "status": "FAILED",
        "failure_code": "AI_RUNTIME_AUTHORIZATION_DENIED",
    }
    assert len(repository.settled) == 1
    assert repository.settled[0] is not None
    assert repository.settled[0].usage.input_tokens == 21
    assert repository.settled[0].cost_microusd == 17
    assert repository.failed_steps == [(AiStep.CLASSIFY, "AI_RUNTIME_AUTHORIZATION_DENIED")]
    assert repository.failed_step_usage == [(21, 17)]
    assert repository.failures == [("FAILED", "AI_RUNTIME_AUTHORIZATION_DENIED")]
    assert repository.closed is True


@pytest.mark.asyncio
async def test_revoked_before_source_read_only_settles_verifiable_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = RevokedBeforeReadRepository()
    monkeypatch.setattr(worker, "_ai_repository", lambda: repository)

    result = await worker._handle_ai_content_result(
        result=_successful_classification_result(),
        run_id=RUN_ID,
        step=AiStep.CLASSIFY,
        attempt=1,
        kind=AttemptKind.PRIMARY,
        network_retries=0,
        repair_used=False,
        reservation_id=RESERVATION_ID,
    )

    assert result["failure_code"] == "AI_RUNTIME_AUTHORIZATION_DENIED"
    assert repository.failed_step_usage == [(21, 17)]
    assert repository.failures == [("FAILED", "AI_RUNTIME_AUTHORIZATION_DENIED")]


@pytest.mark.asyncio
@pytest.mark.parametrize("step", [AiStep.SUMMARIZE, AiStep.VERIFY])
async def test_revoked_later_step_callback_does_not_load_prior_ai_results(
    monkeypatch: pytest.MonkeyPatch,
    step: AiStep,
) -> None:
    repository = RevokedAuthorizationRepository()
    monkeypatch.setattr(worker, "_ai_repository", lambda: repository)

    result = await worker._handle_ai_content_result(
        result=_successful_classification_result(),
        run_id=RUN_ID,
        step=step,
        attempt=1,
        kind=AttemptKind.PRIMARY,
        network_retries=0,
        repair_used=False,
        reservation_id=RESERVATION_ID,
    )

    assert result["failure_code"] == "AI_RUNTIME_AUTHORIZATION_DENIED"
    assert repository.failed_steps == [(step, "AI_RUNTIME_AUTHORIZATION_DENIED")]
    assert repository.failures == [("FAILED", "AI_RUNTIME_AUTHORIZATION_DENIED")]


@pytest.mark.asyncio
async def test_revoked_callback_with_malformed_success_never_dispatches_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = RevokedAuthorizationRepository(require_billing_response=False)
    monkeypatch.setattr(worker, "_ai_repository", lambda: repository)

    result = await worker._handle_ai_content_result(
        result={"status": "SUCCEEDED", "response": {"invalid": True}},
        run_id=RUN_ID,
        step=AiStep.CLASSIFY,
        attempt=1,
        kind=AttemptKind.PRIMARY,
        network_retries=0,
        repair_used=False,
        reservation_id=RESERVATION_ID,
    )

    assert result["failure_code"] == "AI_RUNTIME_AUTHORIZATION_DENIED"
    assert repository.settled == [None]
    assert repository.failed_steps == [(AiStep.CLASSIFY, "AI_RUNTIME_AUTHORIZATION_DENIED")]
