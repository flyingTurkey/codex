import asyncio
import json
from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import Any
from uuid import UUID

from srbg_api.ai_pipeline.ai_judgments import EvidenceFactInput, EvidenceSnippet
from srbg_api.ai_pipeline.content_preparation import (
    AiContentPreparationService,
    PreparationDocument,
)
from srbg_api.ai_pipeline.contracts import AiStep, ModelRequest, ModelResponse, ModelUsage
from srbg_api.ai_pipeline.preparation import DocumentBlock
from srbg_api.ai_pipeline.security import PromptInjectionScanner
from srbg_api.intelligence_v2.autonomous_policy import QualificationPolicyBundle
from srbg_contracts import QualificationDecisionTrace

RUN_ID = UUID("019d0000-0000-7000-8000-000000002021")
DOCUMENT_VERSION_ID = UUID("019d0000-0000-7000-8000-000000002022")
RAW_OBJECT_ID = UUID("019d0000-0000-7000-8000-000000002023")
PILOT_URL = "https://xxgk.mot.gov.cn/2020/jigou/glj/202311/P020250514396309964949.pdf"


@dataclass
class FakeRepository:
    statuses: list[str] = field(default_factory=list)
    steps: list[tuple[AiStep, str]] = field(default_factory=list)
    reservations: list[AiStep] = field(default_factory=list)
    reservation_keys: list[tuple[AiStep, int]] = field(default_factory=list)
    materialized: int = 0
    judgment_type: str | None = None
    review_payloads: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[QualificationDecisionTrace] = field(default_factory=list)
    materialized_classifications: list[dict[str, Any]] = field(default_factory=list)
    calibration_reads: int = 0

    async def begin(self, run_id: UUID) -> PreparationDocument:
        self.statuses.append("PREPARING")
        return PreparationDocument(
            run_id=run_id,
            document_version_id=DOCUMENT_VERSION_ID,
            raw_object_id=RAW_OBJECT_ID,
            source_stream_policy_version="stream-policy-7",
            source_code="GOV-003",
            canonical_url=PILOT_URL,
            title="典型案例",
            source_name="交通运输部",
            blocks=(
                DocumentBlock(
                    block_id="block-1",
                    page_number=1,
                    text="交通运输部发布公路养护数字化典型案例。",
                    locator_value="page=1&box=1,2,3,4",
                ),
            ),
        )

    async def authorize_real_run(self, document: PreparationDocument) -> bool:
        return document.document_version_id == DOCUMENT_VERSION_ID

    async def append_automated_decision(
        self, trace: QualificationDecisionTrace, policy: QualificationPolicyBundle
    ) -> None:
        assert trace.policy == policy.identity
        self.decisions.append(trace)

    async def record_security(self, document: PreparationDocument, detected: bool) -> None:
        assert detected is False

    async def transition(self, run_id: UUID, status: str) -> None:
        self.statuses.append(status)

    async def reserve(self, run_id: UUID, step: AiStep, attempt: int) -> object:
        assert (step, attempt) not in self.reservation_keys
        self.reservation_keys.append((step, attempt))
        self.reservations.append(step)
        return (step, attempt)

    async def settle(self, reservation: object, response: ModelResponse | None) -> None:
        assert reservation in self.reservation_keys

    async def append_step(
        self,
        run_id: UUID,
        step: AiStep,
        attempt: int,
        kind: str,
        response: ModelResponse,
        input_sha256: str,
    ) -> None:
        self.steps.append((step, kind))
        assert len(input_sha256) == 64

    async def materialize(
        self,
        document: PreparationDocument,
        classification: dict[str, Any],
        extraction: dict[str, Any],
    ) -> int:
        assert classification["primary_type"] == "DIGITAL_TRANSFORMATION"
        self.materialized_classifications.append(classification)
        assert extraction["claims"][0]["claim_status"] == "UNVERIFIED"
        self.materialized = 1
        return 1

    async def load_judgment_facts(self, document: PreparationDocument) -> list[EvidenceFactInput]:
        return [
            EvidenceFactInput(
                claim_id=UUID("019b0000-0000-7000-8000-000000000101"),
                field_name="title",
                value="公路养护数字化典型案例",
                evidence=[
                    EvidenceSnippet(
                        evidence_id=UUID("019b0000-0000-7000-8000-000000000201"),
                        excerpt="公路养护数字化典型案例",
                    )
                ],
            )
        ]

    async def materialize_judgment(
        self,
        document: PreparationDocument,
        summary: dict[str, Any] | None,
        verification: dict[str, Any] | None,
        result_type: str,
        reason_codes: tuple[str, ...],
    ) -> None:
        assert summary is not None
        assert verification is not None
        assert reason_codes == ()
        self.judgment_type = result_type

    async def fail(self, run_id: UUID, status: str, code: str) -> None:
        self.statuses.append(status)

    async def queue_qualification_review(
        self, document: PreparationDocument, classification: dict[str, Any]
    ) -> UUID:
        self.review_payloads.append(classification)
        self.statuses.append("WAITING_CLAIM_REVIEW")
        return UUID("019d0000-0000-7000-8000-000000002099")


class FakeModel:
    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.step is AiStep.CLASSIFY:
            output: dict[str, Any] = {
                "direct_relevance": "RELEVANT",
                "core_new_fact": "公路养护采用数字化系统",
                "primary_type": "DIGITAL_TRANSFORMATION",
                "engineering_objects": ["HIGHWAY"],
                "specialty_facets": [],
                "equipment_domains": [],
                "content_form": "PROJECT_RECORD",
                "evidence_locators": ["block-1"],
                "confidence": 0.95,
                "ambiguity_indicators": [],
                "security_signals": [],
            }
        elif request.step is AiStep.EXTRACT:
            evidence_id, anchor = next(iter(request.evidence_anchors.items()))
            output = {
                "claims": [
                    {
                        "claim_id": "model-claim-1",
                        "field": "title",
                        "value": "公路养护数字化典型案例",
                        "claim_status": "UNVERIFIED",
                        "confidence": 0.8,
                        "evidence_ids": [evidence_id],
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": evidence_id,
                        "document_block_id": anchor.document_block_id,
                        "locator": {"type": "PDF_PAGE", "value": anchor.locator_value},
                        "excerpt": "公路养护数字化典型案例",
                        "supports": ["model-claim-1"],
                    }
                ],
                "security": {
                    "prompt_injection_detected": False,
                    "prompt_injection_status": "NONE",
                    "suspicious_patterns": [],
                },
            }
        elif request.step is AiStep.SUMMARIZE:
            output = {
                "why_worth_attention": "值得跟踪公路养护数字化应用。",
                "potential_industry_impacts": ["提升巡检效率"],
                "potential_engineering_scenarios": ["公路养护"],
                "current_limitations": ["仅有单一案例"],
                "questions_to_verify": ["能否规模复制"],
                "used_claim_ids": ["019b0000-0000-7000-8000-000000000101"],
            }
        else:
            output = {
                "unsupported_claims": [],
                "number_or_date_conflicts": [],
                "legal_responsibility_or_causal_overreach": [],
                "enterprise_claims_missing_attribution": [],
                "stale_or_superseded_evidence": False,
                "prompt_injection_risk": False,
                "candidate_decision": "PASS_TO_SERVER_GATE",
            }
        raw = json.dumps(output, ensure_ascii=False)
        return ModelResponse(
            raw_output=raw,
            output=output,
            usage=ModelUsage(input_tokens=10, output_tokens=5),
            cost_microusd=3,
            latency_ms=1,
            provider_request_id=f"request-{request.step.value.lower()}",
            finish_reason="stop",
        )


def test_one_document_reaches_automatic_evidence_gate_without_claim_review() -> None:
    repository = FakeRepository()
    service = AiContentPreparationService(
        repository=repository,
        model=FakeModel(),
        scanner=PromptInjectionScanner(),
    )
    result = asyncio.run(service.run(RUN_ID))
    assert result.candidate_count == 1
    assert repository.statuses == [
        "PREPARING",
        "CLASSIFYING",
        "EXTRACTING",
        "EVIDENCE_GATING",
        "SUMMARIZING",
        "VERIFYING",
        "SUCCEEDED",
    ]
    assert [step for step, _ in repository.steps] == [
        AiStep.CLASSIFY,
        AiStep.EXTRACT,
        AiStep.SUMMARIZE,
        AiStep.VERIFY,
    ]
    assert repository.reservations == [
        AiStep.CLASSIFY,
        AiStep.EXTRACT,
        AiStep.SUMMARIZE,
        AiStep.VERIFY,
    ]
    assert repository.judgment_type == "AI_JUDGMENT"
    assert [decision.disposition.value for decision in repository.decisions] == ["AUTO_ACCEPTED"]
    assert sha256(result.input_text.encode()).hexdigest() == result.input_sha256


def test_ai01_scope_is_authorized_by_server_facts_not_a_pinned_url() -> None:
    source = AiContentPreparationService.run.__code__.co_consts
    assert PILOT_URL not in source


def test_locked_negative_is_durably_filtered_without_owner_review_or_model_call() -> None:
    class LockedNegativeRepository(FakeRepository):
        async def begin(self, run_id: UUID) -> PreparationDocument:
            document = await super().begin(run_id)
            return replace(
                document,
                blocks=(
                    DocumentBlock(
                        block_id="block-1",
                        page_number=1,
                        text="旅游消费促销活动启动, 仅涉及景区营销。",
                        locator_value="page=1&box=1,2,3,4",
                    ),
                ),
            )

    repository = LockedNegativeRepository()
    service = AiContentPreparationService(
        repository=repository,
        model=FakeModel(),
        scanner=PromptInjectionScanner(),
    )

    result = asyncio.run(service.run(RUN_ID))

    assert result.candidate_count == 0
    assert repository.materialized == 0
    assert repository.judgment_type is None
    assert repository.review_payloads == []
    assert [decision.disposition.value for decision in repository.decisions] == ["AUTO_FILTERED"]
    assert repository.reservations == []
    assert repository.statuses == ["PREPARING", "CLASSIFYING", "SUCCEEDED"]


def test_new_autonomous_path_has_no_owner_gold_or_override_authorization_seam() -> None:
    repository = FakeRepository()
    service = AiContentPreparationService(
        repository=repository,
        model=FakeModel(),
        scanner=PromptInjectionScanner(),
    )

    result = asyncio.run(service.run(RUN_ID))

    assert result.candidate_count == 1
    assert repository.calibration_reads == 0
    source = AiContentPreparationService.run.__code__.co_names
    assert "load_auto_pass_calibration" not in source
    assert "OWNER_OVERRIDE_GO" not in str(AiContentPreparationService.run.__code__.co_consts)


def test_schema_repair_then_semantic_recheck_uses_a_fresh_attempt_number() -> None:
    class RepairThenRecheckModel(FakeModel):
        classification_calls = 0

        async def generate(self, request: ModelRequest) -> ModelResponse:
            if request.step is not AiStep.CLASSIFY:
                return await super().generate(request)
            self.classification_calls += 1
            if self.classification_calls == 1:
                return ModelResponse(
                    raw_output="{}",
                    output={},
                    usage=ModelUsage(input_tokens=1, output_tokens=1),
                    cost_microusd=1,
                    latency_ms=1,
                    provider_request_id="classification-schema-invalid",
                    finish_reason="stop",
                )
            response = await super().generate(request)
            if self.classification_calls == 2:
                response.output["evidence_locators"] = ["missing-block"]
            return response

    repository = FakeRepository()
    service = AiContentPreparationService(
        repository=repository,
        model=RepairThenRecheckModel(),
        scanner=PromptInjectionScanner(),
    )

    result = asyncio.run(service.run(RUN_ID))

    assert result.candidate_count == 1
    assert [
        attempt for step, attempt in repository.reservation_keys if step is AiStep.CLASSIFY
    ] == [1, 2, 3]
    assert repository.decisions[0].semantic_recheck_count == 1
    assert repository.materialized_classifications[0]["evidence_locators"] == ["block-1"]
