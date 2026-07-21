from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
import srbg_worker.app as worker
from srbg_api.ai_pipeline.content_preparation import PreparationDocument
from srbg_api.ai_pipeline.contracts import AiStep, ModelResponse
from srbg_api.ai_pipeline.preparation import DocumentBlock
from srbg_api.ai_pipeline.runtime import AttemptKind
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


def test_every_physical_model_dispatch_reauthorizes_before_budget_reservation() -> None:
    source = inspect.getsource(worker._dispatch_ai_attempt)

    assert source.index("authorize_model_call") < source.index("repository.reserve")
    assert source.index("authorize_model_call") < source.index("celery_app.send_task")


def test_success_persistence_reauthorizes_before_writing_model_content() -> None:
    append_source = inspect.getsource(PostgresAiPreparationRepository._append_step_row)
    success_source = inspect.getsource(
        PostgresAiPreparationRepository.record_approved_content_success
    )

    assert append_source.index("authorize_model_call") < append_source.index("raw_output")
    for token in (
        "raw.scan_status='CLEAN'",
        "source_admission_assessment_v2",
        "version.execution_domain IN ('TRIAL','PRODUCTION')",
        "ai_budget_policy",
    ):
        assert token in success_source

    callback_source = inspect.getsource(worker._handle_ai_content_result)
    success_branch = callback_source.rsplit('if result.get("status") == "SUCCEEDED":', 1)[1]
    assert success_branch.index("authorize_model_call") < success_branch.index(
        "repository.settle"
    )


def test_worker_validates_the_exact_owner_gold_grant_before_qualification() -> None:
    callback_source = inspect.getsource(worker._handle_ai_content_result)

    assert callback_source.index("load_auto_pass_calibration") < callback_source.index(
        "exact_auto_pass_calibration"
    )
    assert callback_source.index("exact_auto_pass_calibration") < callback_source.index(
        "qualification_reason"
    )


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
            document_version_id="019f7900-0000-7000-8000-000000000003",
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
        "needs_human_review": False,
        "review_reasons": [],
        "security": {
            "prompt_injection_detected": False,
            "prompt_injection_status": "NONE",
            "suspicious_patterns": [],
        },
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
    assert repository.failed_steps == [
        (AiStep.CLASSIFY, "AI_RUNTIME_AUTHORIZATION_DENIED")
    ]
    assert repository.failed_step_usage == [(21, 17)]
    assert repository.failures == [
        ("FAILED", "AI_RUNTIME_AUTHORIZATION_DENIED")
    ]
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
    assert repository.failed_steps == [
        (step, "AI_RUNTIME_AUTHORIZATION_DENIED")
    ]
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
    assert repository.failed_steps == [
        (AiStep.CLASSIFY, "AI_RUNTIME_AUTHORIZATION_DENIED")
    ]
