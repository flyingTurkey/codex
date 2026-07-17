"""Isolated AI worker: queue input in, controlled model gateway output out.

This process intentionally has no database, object-storage, command-execution, or tool client.
"""

import asyncio
import re
from pathlib import Path
from typing import Any

import httpx2 as httpx
from celery import Celery
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from srbg_api.ai_pipeline.catalog import ProviderCode, provider_capability
from srbg_api.ai_pipeline.contracts import AiStep, ModelRequest
from srbg_api.ai_pipeline.gateway import (
    ControlledModelGateway,
    DeepSeekProvider,
    HttpResponse,
    MockProvider,
    ModelOutputRejected,
    TransientProviderError,
)


class AiWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SRBG_AI_", extra="ignore")

    broker_url: str = "redis://redis:6379/0"
    provider: str = "mock"
    api_key: SecretStr | None = None
    api_key_file: Path | None = None
    timeout_seconds: float = 30.0


settings = AiWorkerSettings()
celery_app = Celery("srbg-ai-worker", broker=settings.broker_url, backend=settings.broker_url)
celery_app.conf.update(
    enable_utc=True,
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_routes={
        "srbg.ai.generate": {"queue": "ai"},
        "srbg.ai.generate_attempt": {"queue": "ai"},
    },
)


class _HttpxClientAdapter:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def post(self, path: str, **kwargs: Any) -> HttpResponse:
        return await self._client.post(path, **kwargs)


@celery_app.task(name="srbg.ai.generate")  # type: ignore[untyped-decorator]
def generate(payload: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_generate(payload))


@celery_app.task(name="srbg.ai.generate_attempt")  # type: ignore[untyped-decorator]
def generate_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute exactly one physical request; orchestration owns retries and budget."""
    return asyncio.run(_generate_attempt(payload))


async def _generate_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = ModelRequest.model_validate(payload)
        response = await _physical_generate(request)
        return {"status": "SUCCEEDED", "response": response.model_dump(mode="json")}
    except (TimeoutError, httpx.TimeoutException):
        return _safe_failure("PROVIDER_TIMEOUT", retryable=True)
    except httpx.NetworkError:
        return _safe_failure("PROVIDER_NETWORK_ERROR", retryable=True)
    except TransientProviderError as exc:
        return _safe_failure(str(exc), retryable=True)
    except ModelOutputRejected as exc:
        return _safe_failure(str(exc), repairable=True)
    except (ValueError, RuntimeError) as exc:
        code = str(exc)
        if code not in {"MODEL_DISABLED", "AI provider is not approved"}:
            code = "PROVIDER_REQUEST_REJECTED"
        return _safe_failure(code)


async def _generate(payload: dict[str, Any]) -> dict[str, Any]:
    request = ModelRequest.model_validate(payload)
    if settings.provider == "mock":
        mock_provider = MockProvider({request.step: _mock_output(request)})
        return (await ControlledModelGateway(mock_provider).generate(request)).model_dump(
            mode="json"
        )
    raise ValueError("budgeted real calls require srbg.ai.generate_attempt")


async def _physical_generate(request: ModelRequest) -> Any:
    if settings.provider == "mock":
        mock_provider = MockProvider({request.step: _mock_output(request)})
        return await ControlledModelGateway(mock_provider).generate(request)
    if settings.provider != ProviderCode.DEEPSEEK.value:
        raise ValueError("AI provider is not approved")
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("MODEL_DISABLED")
    capability = provider_capability(ProviderCode.DEEPSEEK)
    async with httpx.AsyncClient(
        base_url=capability.base_url,
        follow_redirects=False,
    ) as client:
        deepseek_provider = DeepSeekProvider(
            client=_HttpxClientAdapter(client),
            api_key=api_key,
            timeout_seconds=settings.timeout_seconds,
        )
        return await ControlledModelGateway(deepseek_provider).generate(request)


def _safe_failure(
    code: str,
    *,
    retryable: bool = False,
    repairable: bool = False,
) -> dict[str, object]:
    return {
        "status": "FAILED",
        "error_code": code[:80],
        "retryable": retryable,
        "repairable": repairable,
    }


def _api_key() -> str | None:
    if settings.api_key_file is not None:
        if not settings.api_key_file.is_file():
            return settings.api_key.get_secret_value() if settings.api_key else None
        key = settings.api_key_file.read_text(encoding="utf-8")
        if not key or len(key) > 4096 or any(character in key for character in "\r\n\x00"):
            raise ValueError("AI key file is invalid")
        return key
    return settings.api_key.get_secret_value() if settings.api_key else None


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
            "claims": [
                {
                    "claim_id": "mock-claim-1",
                    "field": "title",
                    "value": excerpt,
                    "claim_status": "UNVERIFIED",
                    "confidence": 0,
                    "evidence_ids": [evidence_id],
                }
            ],
            "evidence": [
                {
                    "evidence_id": evidence_id,
                    "document_block_id": anchor.document_block_id,
                    "locator": {"type": "TEXT_RANGE", "value": f"0:{len(excerpt)}"},
                    "excerpt": excerpt,
                    "supports": ["mock-claim-1"],
                }
            ],
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
