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
from srbg_api.intelligence_v2.gold_calibration import AutoPassCalibrationGrant

RUN_ID = UUID("019d0000-0000-7000-8000-000000002021")
PILOT_URL = (
    "https://xxgk.mot.gov.cn/2020/jigou/glj/202311/"
    "P020250514396309964949.pdf"
)


@dataclass
class FakeRepository:
    statuses: list[str] = field(default_factory=list)
    steps: list[tuple[AiStep, str]] = field(default_factory=list)
    reservations: list[AiStep] = field(default_factory=list)
    materialized: int = 0
    judgment_type: str | None = None
    review_payloads: list[dict[str, Any]] = field(default_factory=list)

    async def begin(self, run_id: UUID) -> PreparationDocument:
        self.statuses.append("PREPARING")
        return PreparationDocument(
            run_id=run_id,
            document_version_id="document-v1",
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
        return document.document_version_id == "document-v1"

    async def load_auto_pass_calibration(
        self, *, corpus_version: str, rule_version: str, model_id: str, prompt_version: str
    ) -> AutoPassCalibrationGrant | None:
        return AutoPassCalibrationGrant(
            threshold_bps=9300,
            corpus_version=corpus_version,
            rule_version=rule_version,
            model_id=model_id,
            prompt_version=prompt_version,
            prediction_seal_sha256="e" * 64,
            fact_sha256="0" * 64,
        )

    async def record_security(self, document: PreparationDocument, detected: bool) -> None:
        assert detected is False

    async def transition(self, run_id: UUID, status: str) -> None:
        self.statuses.append(status)

    async def reserve(self, run_id: UUID, step: AiStep, attempt: int) -> object:
        self.reservations.append(step)
        return (step, attempt)

    async def settle(self, reservation: object, response: ModelResponse | None) -> None:
        assert response is not None

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
        assert extraction["claims"][0]["claim_status"] == "UNVERIFIED"
        self.materialized = 1
        return 1

    async def load_judgment_facts(
        self, document: PreparationDocument
    ) -> list[EvidenceFactInput]:
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
                "needs_human_review": False,
                "review_reasons": [],
                "security": {
                    "prompt_injection_detected": False,
                    "prompt_injection_status": "NONE",
                    "suspicious_patterns": [],
                },
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
    assert sha256(result.input_text.encode()).hexdigest() == result.input_sha256


def test_ai01_scope_is_authorized_by_server_facts_not_a_pinned_url() -> None:
    source = AiContentPreparationService.run.__code__.co_consts
    assert PILOT_URL not in source


def test_locked_negative_only_creates_a_qualification_review_case() -> None:
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
    assert len(repository.review_payloads) == 1
    assert repository.review_payloads[0]["review_reasons"] == ["LOCKED_NEGATIVE"]
    assert repository.statuses == ["PREPARING", "CLASSIFYING", "WAITING_CLAIM_REVIEW"]


def test_stale_calibration_grant_is_treated_as_unavailable() -> None:
    class StaleCalibrationRepository(FakeRepository):
        async def load_auto_pass_calibration(
            self,
            *,
            corpus_version: str,
            rule_version: str,
            model_id: str,
            prompt_version: str,
        ) -> AutoPassCalibrationGrant | None:
            grant = await super().load_auto_pass_calibration(
                corpus_version=corpus_version,
                rule_version=rule_version,
                model_id=model_id,
                prompt_version=prompt_version,
            )
            assert grant is not None
            return replace(grant, corpus_version="owner-gold-2026-07-20.3")

    repository = StaleCalibrationRepository()
    service = AiContentPreparationService(
        repository=repository,
        model=FakeModel(),
        scanner=PromptInjectionScanner(),
    )

    result = asyncio.run(service.run(RUN_ID))

    assert result.candidate_count == 0
    assert repository.materialized == 0
    assert repository.review_payloads[0]["review_reasons"] == ["CALIBRATION_UNAVAILABLE"]
