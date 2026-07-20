"""Isolated AI worker: queue input in, controlled model gateway output out.

This process intentionally has no database, object-storage, command-execution, or tool client.
"""

import asyncio
import re
from datetime import UTC, datetime
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
    provider: str = "deepseek"
    environment: str = "production"
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
        "srbg.ai.runtime_probe": {"queue": "ai"},
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


@celery_app.task(name="srbg.ai.runtime_probe")  # type: ignore[untyped-decorator]
def runtime_probe() -> dict[str, str]:
    """Prove that the isolated queue runtime is alive without using the network."""

    return {
        "status": "READY",
        "provider": settings.provider,
        "environment": settings.environment,
        "observed_at": datetime.now(UTC).isoformat(),
    }


async def _generate_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = ModelRequest.model_validate(payload)
        response = await _physical_generate(request)
        return {
            "status": "SUCCEEDED",
            "response": response.model_dump(mode="json"),
            "runtime_provider": settings.provider,
            "runtime_model": provider_capability(ProviderCode.DEEPSEEK).models[0],
        }
    except (TimeoutError, httpx.TimeoutException):
        return _safe_failure("PROVIDER_TIMEOUT", retryable=True)
    except httpx.NetworkError:
        return _safe_failure("PROVIDER_NETWORK_ERROR", retryable=True)
    except TransientProviderError:
        return _safe_failure("TRANSIENT_UNAVAILABLE", retryable=True)
    except ModelOutputRejected as exc:
        if request.schema_version == "summarize-v2-output-1.0.0":
            return _safe_failure("SUMMARY_SCHEMA_REJECTED")
        return _safe_failure(str(exc), repairable=True)
    except (ValueError, RuntimeError) as exc:
        code = str(exc)
        if code not in {
            "MODEL_DISABLED",
            "PROVIDER_BALANCE_INSUFFICIENT",
            "AI provider is not approved",
        }:
            code = "PROVIDER_REQUEST_REJECTED"
        return _safe_failure(code)


async def _generate(payload: dict[str, Any]) -> dict[str, Any]:
    request = ModelRequest.model_validate(payload)
    if settings.provider == "mock":
        if settings.environment != "test":
            raise RuntimeError("MOCK_PROVIDER_FORBIDDEN")
        mock_provider = MockProvider({request.step: _mock_output(request)})
        return (await ControlledModelGateway(mock_provider).generate(request)).model_dump(
            mode="json"
        )
    raise ValueError("budgeted real calls require srbg.ai.generate_attempt")


async def _physical_generate(request: ModelRequest) -> Any:
    if settings.provider == "mock":
        if settings.environment != "test":
            raise RuntimeError("MOCK_PROVIDER_FORBIDDEN")
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
    if request.step is AiStep.SOURCE_PROFILE:
        return {
            "industry_candidates": [],
            "content_domain_candidates": [],
            "language_candidates": [],
            "country_candidates": [],
            "region_candidates": [],
            "declared_role_candidates": [],
            "organization_clues": [],
            "ownership_clues": [],
        }
    if request.step is AiStep.CLASSIFY:
        return {
            "direct_relevance": "LOW_CONFIDENCE",
            "core_new_fact": None,
            "primary_type": None,
            "engineering_objects": [],
            "specialty_facets": [],
            "equipment_domains": [],
            "content_form": "OTHER",
            "evidence_locators": [],
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
            "why_worth_attention": "供 Owner 继续跟踪。",
            "potential_industry_impacts": [],
            "potential_engineering_scenarios": [],
            "current_limitations": ["Mock provider output"],
            "questions_to_verify": [],
            "used_claim_ids": list(dict.fromkeys(claim_ids)),
        }
    return {
        "unsupported_claims": [],
        "number_or_date_conflicts": [],
        "legal_responsibility_or_causal_overreach": [],
        "enterprise_claims_missing_attribution": [],
        "stale_or_superseded_evidence": False,
        "prompt_injection_risk": False,
        "candidate_decision": "PASS_TO_SERVER_GATE",
    }


def _safe_security() -> dict[str, object]:
    return {
        "prompt_injection_detected": False,
        "prompt_injection_status": "NONE",
        "suspicious_patterns": [],
    }
