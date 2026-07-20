"""T04 application service from active AcceptedClaims to review-only candidates."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from srbg_api.ai_pipeline.security import PromptInjectionScanner
from srbg_api.intelligence_v2.content_candidates import (
    AcceptedClaimInput,
    ContentCandidateRejected,
    ContentPreparationCandidate,
    StructuredSummaryCandidate,
    build_content_candidate,
    build_minimal_summary_payload,
)


class ContentSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_version_id: UUID
    model: str = Field(default="protocol-equivalent-stub", min_length=1, max_length=100)
    prompt_version: str = Field(default="t04-structured-summary-v1", min_length=1, max_length=100)
    schema_version: str = Field(default="t04-structured-summary-v1", min_length=1, max_length=100)
    payload: dict[str, Any]
    response_schema: dict[str, Any]
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def model_input(self) -> str:
        return json.dumps(
            self.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class ContentCandidateRepository(Protocol):
    async def load_active_claims(
        self, document_version_id: UUID
    ) -> list[AcceptedClaimInput]: ...

    async def append_candidate(
        self,
        candidate: ContentPreparationCandidate,
        request: ContentSummaryRequest,
    ) -> UUID: ...

    async def append_invalidation(self, candidate_id: UUID, reason: str) -> None: ...


class ContentSummaryModel(Protocol):
    async def generate(self, request: ContentSummaryRequest) -> dict[str, Any]: ...


class ContentCandidatePreparationService:
    """Build candidates only; it has no publication dependency or status capability."""

    def __init__(
        self,
        *,
        repository: ContentCandidateRepository,
        model: ContentSummaryModel,
        scanner: PromptInjectionScanner | None = None,
    ) -> None:
        self._repository = repository
        self._model = model
        self._scanner = scanner or PromptInjectionScanner()

    async def prepare(self, document_version_id: UUID) -> UUID:
        claims = await self._repository.load_active_claims(document_version_id)
        payload = build_minimal_summary_payload(
            claims, current_document_version_id=document_version_id
        )
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if self._scanner.scan(serialized).detected:
            raise ContentCandidateRejected("PROMPT_INJECTION_UNRESOLVED")
        request = ContentSummaryRequest(
            document_version_id=document_version_id,
            payload=payload,
            response_schema=_summary_schema(),
            input_sha256=sha256(serialized.encode()).hexdigest(),
        )
        raw_output = await self._model.generate(request)
        try:
            Draft202012Validator(request.response_schema).validate(raw_output)
            summary = StructuredSummaryCandidate.model_validate(raw_output)
        except (ValidationError, JsonSchemaValidationError) as exc:
            raise ContentCandidateRejected("SUMMARY_SCHEMA_REJECTED") from exc
        candidate = build_content_candidate(
            claims=claims,
            current_document_version_id=document_version_id,
            summary=summary,
        )
        return await self._repository.append_candidate(candidate, request)

    async def invalidate(
        self,
        candidate_id: UUID,
        reason: Literal[
            "DOCUMENT_VERSION_CHANGED",
            "ACCEPTED_CLAIMS_CHANGED",
            "SOURCE_WITHDRAWN",
            "SOURCE_CORRECTED",
        ],
    ) -> None:
        await self._repository.append_invalidation(candidate_id, reason)


def _summary_schema() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[5]
    path = root / "docs" / "codex-kit" / "assets" / "schemas" / "summarize-v2-output.schema.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
