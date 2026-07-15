"""A tool-free model gateway with local schema and evidence enforcement."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, ClassVar, Protocol, cast

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource

from srbg_api.ai_pipeline.contracts import (
    STEP_OUTPUT_MODELS,
    AiStep,
    ExtractionOutput,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)


class ModelOutputRejected(ValueError):
    """Provider response failed a non-bypassable local check."""


@dataclass(frozen=True, slots=True)
class ProviderResult:
    content: str
    input_tokens: int
    output_tokens: int
    provider_request_id: str | None = None
    tool_calls_present: bool = False


class ModelProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ProviderResult: ...


class HttpResponse(Protocol):
    def raise_for_status(self) -> object: ...

    def json(self) -> object: ...


class AsyncHttpClient(Protocol):
    async def post(self, path: str, **kwargs: Any) -> HttpResponse: ...


class ControlledModelGateway:
    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def generate(self, request: ModelRequest) -> ModelResponse:
        started = perf_counter()
        result = await self._provider.complete(request)
        latency_ms = max(0, int((perf_counter() - started) * 1_000))
        if result.tool_calls_present:
            raise ModelOutputRejected("provider returned tool calls")
        try:
            decoded = json.loads(result.content)
        except json.JSONDecodeError as exc:
            raise ModelOutputRejected("provider returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ModelOutputRejected("provider output must be a JSON object")

        self._validate_json_schema(decoded, request.response_schema)
        try:
            validated = STEP_OUTPUT_MODELS[request.step].model_validate(decoded)
        except ValidationError as exc:
            raise ModelOutputRejected("provider output violates step contract") from exc
        if isinstance(validated, ExtractionOutput):
            self._validate_evidence(validated, request)

        usage = ModelUsage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        numerator = (
            usage.input_tokens * request.input_price_microusd_per_million
            + usage.output_tokens * request.output_price_microusd_per_million
        )
        cost = (numerator + 999_999) // 1_000_000 if numerator else 0
        return ModelResponse(
            raw_output=result.content,
            output=validated.model_dump(mode="json", exclude_none=True),
            usage=usage,
            cost_microusd=cost,
            latency_ms=latency_ms,
            provider_request_id=result.provider_request_id,
        )

    @staticmethod
    def _validate_json_schema(output: dict[str, Any], schema: dict[str, Any]) -> None:
        registry = Registry()
        classify_schema = MockProvider.schema_for(AiStep.CLASSIFY)
        if "$id" in classify_schema:
            registry = registry.with_resource(
                str(classify_schema["$id"]), Resource.from_contents(classify_schema)
            )
        try:
            Draft202012Validator(schema, registry=registry).validate(output)
        except Exception as exc:
            raise ModelOutputRejected("provider output violates JSON Schema") from exc

    @staticmethod
    def _validate_evidence(output: ExtractionOutput, request: ModelRequest) -> None:
        claim_ids = {claim.claim_id for claim in output.claims}
        evidence_ids = {evidence.evidence_id for evidence in output.evidence}
        for evidence in output.evidence:
            anchor = request.evidence_anchors.get(evidence.evidence_id)
            if anchor is None:
                raise ModelOutputRejected("evidence id was not issued by the server")
            if evidence.document_block_id != anchor.document_block_id:
                raise ModelOutputRejected("evidence block does not match server anchor")
            if evidence.excerpt not in anchor.normalized_text:
                raise ModelOutputRejected("evidence excerpt is not present in source block")
            if not set(evidence.supports).issubset(claim_ids):
                raise ModelOutputRejected("evidence supports an unknown claim")
        for claim in output.claims:
            if not set(claim.evidence_ids).issubset(evidence_ids):
                raise ModelOutputRejected("claim references unknown evidence")
            for evidence_id in claim.evidence_ids:
                evidence = next(item for item in output.evidence if item.evidence_id == evidence_id)
                if claim.claim_id not in evidence.supports:
                    raise ModelOutputRejected("claim and evidence links are not bidirectional")


class MockProvider:
    """Deterministic provider used by tests, replay and local demonstrations."""

    _SCHEMA_FILES: ClassVar[dict[AiStep, str]] = {
        AiStep.CLASSIFY: "classify-output.schema.json",
        AiStep.EXTRACT: "extract-output.schema.json",
        AiStep.SUMMARIZE: "summarize-output.schema.json",
        AiStep.VERIFY: "verify-output.schema.json",
    }

    def __init__(
        self,
        outputs: Mapping[AiStep, dict[str, Any]],
        *,
        result: ProviderResult | None = None,
    ) -> None:
        self._outputs = dict(outputs)
        self._result = result
        self.requests: list[ModelRequest] = []
        self.request_payloads: list[dict[str, Any]] = []

    @classmethod
    def schema_for(cls, step: AiStep) -> dict[str, Any]:
        root = Path(__file__).resolve().parents[5]
        path = root / "docs" / "codex-kit" / "assets" / "schemas" / cls._SCHEMA_FILES[step]
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    async def complete(self, request: ModelRequest) -> ProviderResult:
        self.requests.append(request)
        self.request_payloads.append(
            {
                "model": request.model_profile,
                "messages": [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"strict": True, "schema": request.response_schema},
                },
                **request.parameters,
            }
        )
        if self._result is not None:
            return self._result
        return ProviderResult(
            content=json.dumps(self._outputs[request.step], ensure_ascii=False),
            input_tokens=100,
            output_tokens=50,
            provider_request_id=f"mock-{request.step.value.lower()}",
        )


class OpenAICompatibleProvider:
    """OpenAI-compatible chat-completions transport without tool capability."""

    def __init__(
        self,
        *,
        client: AsyncHttpClient,
        request_path: str = "/v1/chat/completions",
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not request_path.startswith("/"):
            raise ValueError("OpenAI-compatible request path must be absolute")
        if timeout_seconds <= 0:
            raise ValueError("provider timeout must be positive")
        self._client = client
        self._request_path = request_path
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def complete(self, request: ModelRequest) -> ProviderResult:
        payload: dict[str, Any] = {
            "model": request.model_profile,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.step.value.lower(),
                    "strict": True,
                    "schema": request.response_schema,
                },
            },
            **request.parameters,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        response = await self._client.post(
            self._request_path,
            json=payload,
            headers=headers,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        raw = response.json()
        if not isinstance(raw, dict):
            raise ModelOutputRejected("provider response must be an object")
        choices = raw.get("choices")
        usage = raw.get("usage")
        if not isinstance(choices, list) or not choices or not isinstance(usage, dict):
            raise ModelOutputRejected("provider response is missing choices or usage")
        choice = choices[0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise ModelOutputRejected("provider response has invalid message shape")
        message = cast(dict[str, Any], choice["message"])
        content = message.get("content")
        if not isinstance(content, str):
            raise ModelOutputRejected("provider response content is not text")
        return ProviderResult(
            content=content,
            input_tokens=_nonnegative_int(usage.get("prompt_tokens"), "prompt_tokens"),
            output_tokens=_nonnegative_int(usage.get("completion_tokens"), "completion_tokens"),
            provider_request_id=str(raw["id"]) if raw.get("id") is not None else None,
            tool_calls_present=bool(message.get("tool_calls")),
        )


def _nonnegative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ModelOutputRejected(f"provider usage {field} is invalid")
    return value
