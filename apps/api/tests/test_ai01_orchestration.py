import asyncio
import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from uuid import UUID

from srbg_api.ai_pipeline.content_preparation import (
    AiContentPreparationService,
    PreparationDocument,
)
from srbg_api.ai_pipeline.contracts import AiStep, ModelRequest, ModelResponse, ModelUsage
from srbg_api.ai_pipeline.preparation import DocumentBlock
from srbg_api.ai_pipeline.security import PromptInjectionScanner

RUN_ID = UUID("019d0000-0000-7000-8000-000000002021")


@dataclass
class FakeRepository:
    statuses: list[str] = field(default_factory=list)
    steps: list[tuple[AiStep, str]] = field(default_factory=list)
    reservations: list[AiStep] = field(default_factory=list)
    materialized: int = 0

    async def begin(self, run_id: UUID) -> PreparationDocument:
        self.statuses.append("PREPARING")
        return PreparationDocument(
            run_id=run_id,
            document_version_id="document-v1",
            source_code="GOV-003",
            canonical_url=(
                "https://zizhan.mot.gov.cn/sj2019/gongluj/sihaoncl/dianxingal/202311/"
                "P020250627753815314372.pdf"
            ),
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
        assert classification["item_type"] == "DIGITAL_CASE"
        assert extraction["claims"][0]["claim_status"] == "UNVERIFIED"
        self.materialized = 1
        return 1

    async def fail(self, run_id: UUID, status: str, code: str) -> None:
        self.statuses.append(status)


class FakeModel:
    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.step is AiStep.CLASSIFY:
            output: dict[str, Any] = {
                "channel": "DIGITAL",
                "item_type": "DIGITAL_CASE",
                "engineering_domains": ["HIGHWAY"],
                "lifecycle_stages": ["OPERATION"],
                "technology_tags": ["DIGITALIZATION"],
                "application_scenarios": ["MAINTENANCE"],
                "confidence": 0.9,
                "needs_human_review": True,
                "review_reasons": ["SHADOW"],
                "security": {
                    "prompt_injection_detected": False,
                    "prompt_injection_status": "NONE",
                    "suspicious_patterns": [],
                },
            }
        else:
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


def test_one_document_reaches_waiting_claim_review_without_summary_or_publication() -> None:
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
        "WAITING_CLAIM_REVIEW",
    ]
    assert [step for step, _ in repository.steps] == [AiStep.CLASSIFY, AiStep.EXTRACT]
    assert AiStep.SUMMARIZE not in [step for step, _ in repository.steps]
    assert repository.reservations == [AiStep.CLASSIFY, AiStep.EXTRACT]
    assert sha256(result.input_text.encode()).hexdigest() == result.input_sha256
