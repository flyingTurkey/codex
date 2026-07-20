"""Evidence-bound SourceExcerpt and structured AISummary candidate rules for v2."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContentCandidateRejected(ValueError):
    """The candidate escaped the current accepted-evidence boundary."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ClaimBasis = Literal[
    "MANUFACTURER_CLAIM",
    "RESEARCH_CONCLUSION",
    "PROJECT_FIRST_PARTY_RECORD",
    "INDEPENDENT_VERIFICATION",
    "AUTHORITY_FINDING",
]

_AUTHORITY_RESERVED_FIELDS = frozenset(
    {
        "regulation_status",
        "incident_cause",
        "responsibility",
        "penalty",
        "corrective_action",
        "final_rectification",
    }
)
_SENSITIVE_PATTERN = re.compile(
    r"(?:authorization\s*:|bearer\s+|api[_-]?key|client[_-]?secret|password|cookie|token)",
    re.IGNORECASE,
)


class ClaimEvidenceInput(_StrictModel):
    evidence_id: UUID
    document_version_id: UUID
    document_block_id: UUID
    locator: str = Field(min_length=1, max_length=500)
    excerpt: str = Field(min_length=1, max_length=500)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    authority_original: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> ClaimEvidenceInput:
        if self.char_end <= self.char_start:
            raise ValueError("evidence range must be positive")
        return self


class AcceptedClaimInput(_StrictModel):
    claim_id: UUID
    document_version_id: UUID
    field_name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=2000)
    basis: ClaimBasis
    active: bool
    evidence: tuple[ClaimEvidenceInput, ...] = Field(min_length=1, max_length=20)


class SourceExcerptCandidate(_StrictModel):
    text: str = Field(min_length=1, max_length=500)
    claim_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    evidence_locators: tuple[str, ...] = Field(min_length=1, max_length=100)


class CandidateClaimReference(_StrictModel):
    claim_id: UUID
    basis: ClaimBasis
    evidence_locators: tuple[str, ...] = Field(min_length=1, max_length=100)


class SummaryFactParagraph(_StrictModel):
    kind: Literal["FACT"] = "FACT"
    section: Literal["WHAT_HAPPENED"]
    text: str = Field(min_length=1, max_length=500)
    claim_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    judgment_type: None = None


class SummaryJudgmentParagraph(_StrictModel):
    kind: Literal["JUDGMENT"] = "JUDGMENT"
    section: Literal["ENGINEERING_IMPACT", "LIMITATIONS_AND_FOLLOW_UP"]
    text: str = Field(min_length=1, max_length=500)
    claim_ids: tuple[()] = ()
    judgment_type: Literal["ENGINEERING_SIGNIFICANCE", "LIMITATION_AND_FOLLOW_UP"]


SummaryParagraph = Annotated[
    SummaryFactParagraph | SummaryJudgmentParagraph,
    Field(discriminator="kind"),
]


class StructuredSummaryCandidate(_StrictModel):
    paragraphs: tuple[SummaryParagraph, ...] = Field(min_length=3, max_length=12)

    @property
    def visible_character_count(self) -> int:
        return sum(len(paragraph.text) for paragraph in self.paragraphs)

    @model_validator(mode="after")
    def validate_coverage(self) -> StructuredSummaryCandidate:
        sections = {paragraph.section for paragraph in self.paragraphs}
        required = {
            "WHAT_HAPPENED",
            "ENGINEERING_IMPACT",
            "LIMITATIONS_AND_FOLLOW_UP",
        }
        if not required.issubset(sections):
            raise ValueError("structured summary is missing a required section")
        if not 300 <= self.visible_character_count <= 500:
            raise ValueError("structured summary must contain 300-500 visible characters")
        return self


class ContentPreparationCandidate(_StrictModel):
    document_version_id: UUID
    accepted_claim_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["CURRENT", "STALE"]
    claim_references: tuple[CandidateClaimReference, ...] = Field(
        min_length=1, max_length=100
    )
    source_excerpt: SourceExcerptCandidate
    summary: StructuredSummaryCandidate
    invalidation_reason: Literal[
        "DOCUMENT_VERSION_CHANGED",
        "ACCEPTED_CLAIMS_CHANGED",
        "SOURCE_WITHDRAWN",
        "SOURCE_CORRECTED",
    ] | None = None

    @property
    def current_source_excerpt(self) -> SourceExcerptCandidate | None:
        return self.source_excerpt if self.status == "CURRENT" else None

    @property
    def current_summary(self) -> StructuredSummaryCandidate | None:
        return self.summary if self.status == "CURRENT" else None

    def invalidate(
        self,
        reason: Literal[
            "DOCUMENT_VERSION_CHANGED",
            "ACCEPTED_CLAIMS_CHANGED",
            "SOURCE_WITHDRAWN",
            "SOURCE_CORRECTED",
        ],
    ) -> ContentPreparationCandidate:
        return self.model_copy(update={"status": "STALE", "invalidation_reason": reason})


def _current_claims(
    claims: list[AcceptedClaimInput], *, current_document_version_id: UUID
) -> list[AcceptedClaimInput]:
    current = [
        claim
        for claim in claims
        if claim.active
        and claim.document_version_id == current_document_version_id
        and claim.evidence
        and all(
            evidence.document_version_id == current_document_version_id
            for evidence in claim.evidence
        )
    ]
    if not current or len(current) != len(claims):
        raise ContentCandidateRejected("CURRENT_ACTIVE_ACCEPTED_CLAIM_REQUIRED")
    for claim in current:
        if claim.field_name in _AUTHORITY_RESERVED_FIELDS and (
            claim.basis != "AUTHORITY_FINDING"
            or not all(evidence.authority_original for evidence in claim.evidence)
        ):
            raise ContentCandidateRejected("AUTHORITY_ORIGINAL_REQUIRED")
    return current


def build_source_excerpt(
    claims: list[AcceptedClaimInput], *, current_document_version_id: UUID
) -> SourceExcerptCandidate:
    """Select one source passage; never stitch discontinuous evidence text."""

    current = _current_claims(
        claims, current_document_version_id=current_document_version_id
    )
    selected_claim = current[0]
    selected_evidence = selected_claim.evidence[0]
    text = " ".join(selected_evidence.excerpt.split())
    if not text or len(text) > 500:
        raise ContentCandidateRejected("SOURCE_EXCERPT_LENGTH_INVALID")
    return SourceExcerptCandidate(
        text=text,
        claim_ids=(selected_claim.claim_id,),
        evidence_locators=(selected_evidence.locator,),
    )


def build_content_candidate(
    *,
    claims: list[AcceptedClaimInput],
    current_document_version_id: UUID,
    summary: StructuredSummaryCandidate,
) -> ContentPreparationCandidate:
    current = _current_claims(
        claims, current_document_version_id=current_document_version_id
    )
    if any(_SENSITIVE_PATTERN.search(claim.value) for claim in current):
        raise ContentCandidateRejected("SENSITIVE_MODEL_INPUT")
    current_ids = {claim.claim_id for claim in current}
    for paragraph in summary.paragraphs:
        if isinstance(paragraph, SummaryFactParagraph) and not set(
            paragraph.claim_ids
        ).issubset(current_ids):
            raise ContentCandidateRejected("FACT_CLAIM_NOT_CURRENT")
    excerpt = build_source_excerpt(
        current, current_document_version_id=current_document_version_id
    )
    fingerprint = accepted_claim_set_sha256(current)
    return ContentPreparationCandidate(
        document_version_id=current_document_version_id,
        accepted_claim_set_sha256=fingerprint,
        status="CURRENT",
        claim_references=tuple(
            CandidateClaimReference(
                claim_id=claim.claim_id,
                basis=claim.basis,
                evidence_locators=tuple(
                    evidence.locator for evidence in claim.evidence
                ),
            )
            for claim in current
        ),
        source_excerpt=excerpt,
        summary=summary,
    )


def accepted_claim_set_sha256(claims: list[AcceptedClaimInput]) -> str:
    """Fingerprint the exact accepted-claim and evidence dependencies."""

    fingerprint_payload = [
        {
            "claim_id": str(claim.claim_id),
            "basis": claim.basis,
            "evidence": [
                {
                    "evidence_id": str(evidence.evidence_id),
                    "locator": evidence.locator,
                    "excerpt": evidence.excerpt,
                }
                for evidence in claim.evidence
            ],
        }
        for claim in sorted(claims, key=lambda value: value.claim_id.int)
    ]
    return sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
def build_minimal_summary_payload(
    claims: list[AcceptedClaimInput], *, current_document_version_id: UUID
) -> dict[str, Any]:
    """Return only accepted facts and one source passage for a model request."""

    current = _current_claims(
        claims, current_document_version_id=current_document_version_id
    )
    if any(_SENSITIVE_PATTERN.search(claim.value) for claim in current):
        raise ContentCandidateRejected("SENSITIVE_MODEL_INPUT")
    excerpt = build_source_excerpt(
        current, current_document_version_id=current_document_version_id
    )
    return {
        "accepted_claims": [
            {
                "claim_id": str(claim.claim_id),
                "field_name": claim.field_name,
                "value": claim.value,
                "basis": claim.basis,
                "evidence_locators": [evidence.locator for evidence in claim.evidence],
            }
            for claim in current
        ],
        "source_excerpt": excerpt.model_dump(mode="json"),
    }
