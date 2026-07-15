"""Isolated AI worker: queue input in, controlled model gateway output out.

This process intentionally has no database, object-storage, command-execution, or tool client.
"""

import asyncio
import re
from typing import Any

import httpx2 as httpx
from celery import Celery
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from srbg_api.ai_pipeline.contracts import AiStep, ModelRequest
from srbg_api.ai_pipeline.gateway import (
    ControlledModelGateway,
    HttpResponse,
    MockProvider,
    OpenAICompatibleProvider,
)


class AiWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SRBG_AI_", extra="ignore")

    broker_url: str = "redis://redis:6379/0"
    provider: str = "mock"
    base_url: str = "http://model-gateway.invalid"
    request_path: str = "/v1/chat/completions"
    api_key: SecretStr | None = None
    timeout_seconds: float = 30.0


settings = AiWorkerSettings()
celery_app = Celery("srbg-ai-worker", broker=settings.broker_url, backend=settings.broker_url)
celery_app.conf.update(
    enable_utc=True,
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_routes={"srbg.ai.generate": {"queue": "ai"}},
)


class _HttpxClientAdapter:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def post(self, path: str, **kwargs: Any) -> HttpResponse:
        return await self._client.post(path, **kwargs)


@celery_app.task(name="srbg.ai.generate")  # type: ignore[untyped-decorator]
def generate(payload: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_generate(payload))


async def _generate(payload: dict[str, Any]) -> dict[str, Any]:
    request = ModelRequest.model_validate(payload)
    if settings.provider == "mock":
        mock_provider = MockProvider({request.step: _mock_output(request)})
        return (await ControlledModelGateway(mock_provider).generate(request)).model_dump(
            mode="json"
        )
    if settings.provider != "openai-compatible":
        raise ValueError("AI provider is not approved")
    async with httpx.AsyncClient(base_url=settings.base_url) as client:
        openai_provider = OpenAICompatibleProvider(
            client=_HttpxClientAdapter(client),
            request_path=settings.request_path,
            api_key=settings.api_key.get_secret_value() if settings.api_key else None,
            timeout_seconds=settings.timeout_seconds,
        )
        return (await ControlledModelGateway(openai_provider).generate(request)).model_dump(
            mode="json"
        )


def _mock_output(request: ModelRequest) -> dict[str, Any]:
    if request.step is AiStep.CLASSIFY:
        return {
            "channel": "UNKNOWN",
            "item_type": "UNKNOWN",
            "engineering_domains": [],
            "lifecycle_stages": [],
            "technology_tags": [],
            "application_scenarios": [],
            "confidence": 0,
            "needs_human_review": True,
            "review_reasons": ["MOCK_PROVIDER"],
            "security": _safe_security(),
        }
    if request.step is AiStep.EXTRACT:
        if not request.evidence_anchors:
            raise ValueError("mock extraction requires a server evidence anchor")
        evidence_id, anchor = next(iter(request.evidence_anchors.items()))
        excerpt = anchor.normalized_text[:500]
        return {
            "claims": [{
                "claim_id": "mock-claim-1",
                "field": "title",
                "value": excerpt,
                "claim_status": "UNVERIFIED",
                "confidence": 0,
                "evidence_ids": [evidence_id],
            }],
            "evidence": [{
                "evidence_id": evidence_id,
                "document_block_id": anchor.document_block_id,
                "locator": {"type": "TEXT_RANGE", "value": f"0:{len(excerpt)}"},
                "excerpt": excerpt,
                "supports": ["mock-claim-1"],
            }],
            "security": _safe_security(),
        }
    if request.step is AiStep.SUMMARIZE:
        claim_ids = re.findall(r'"claim_id":"([^"]+)"', request.user_prompt)
        if not claim_ids:
            raise ValueError("mock summary requires accepted claims")
        return {
            "one_sentence": "题录与已接受事实摘要。",
            "why_it_matters": "供内部专业人员继续核验。",
            "key_points": [],
            "applicable_scenarios": [],
            "limitations": ["Mock provider output"],
            "recommended_actions": ["READ_ORIGINAL"],
            "used_claim_ids": list(dict.fromkeys(claim_ids)),
        }
    return {
        "unsupported_claims": [],
        "evidence_mismatches": [],
        "number_or_date_conflicts": [],
        "legal_or_causal_overreach": [],
        "enterprise_claims_missing_attribution": [],
        "stale_or_superseded_risk": False,
        "prompt_injection_risk": False,
        "candidate_decision": "HUMAN_REVIEW",
    }


def _safe_security() -> dict[str, object]:
    return {
        "prompt_injection_detected": False,
        "prompt_injection_status": "NONE",
        "suspicious_patterns": [],
    }
