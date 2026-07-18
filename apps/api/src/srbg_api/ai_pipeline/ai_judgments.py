"""Strict PERS-07 judgment contracts and deterministic server decisions."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AiJudgmentInputRejected(ValueError):
    """The model input or output escaped the current evidence-fact boundary."""


class AiJudgmentResultType(StrEnum):
    EVIDENCE_FACT = "EVIDENCE_FACT"
    AI_JUDGMENT = "AI_JUDGMENT"
    UNVERIFIED_AI = "UNVERIFIED_AI"
    AI_PROCESSING_FAILED = "AI_PROCESSING_FAILED"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceSnippet(_StrictModel):
    evidence_id: UUID
    excerpt: str = Field(min_length=1, max_length=500)
    attribution: str | None = Field(default=None, min_length=1, max_length=200)


class EvidenceFactInput(_StrictModel):
    claim_id: UUID
    field_name: str = Field(min_length=1, max_length=100)
    value: Any
    evidence: list[EvidenceSnippet] = Field(min_length=1, max_length=20)


class SummarizeOutput(_StrictModel):
    why_worth_attention: str = Field(min_length=1, max_length=500)
    potential_industry_impacts: list[str] = Field(default_factory=list, max_length=10)
    potential_engineering_scenarios: list[str] = Field(default_factory=list, max_length=10)
    current_limitations: list[str] = Field(default_factory=list, max_length=10)
    questions_to_verify: list[str] = Field(default_factory=list, max_length=10)
    used_claim_ids: list[UUID] = Field(min_length=1, max_length=100)


class VerificationOutput(_StrictModel):
    unsupported_claims: list[str] = Field(default_factory=list, max_length=50)
    number_or_date_conflicts: list[str] = Field(default_factory=list, max_length=50)
    legal_responsibility_or_causal_overreach: list[str] = Field(default_factory=list, max_length=50)
    enterprise_claims_missing_attribution: list[str] = Field(default_factory=list, max_length=50)
    stale_or_superseded_evidence: bool = False
    prompt_injection_risk: bool = False
    candidate_decision: Literal["PASS_TO_SERVER_GATE", "UNVERIFIED", "REJECT"]


def build_summarize_prompt(facts: list[EvidenceFactInput]) -> str:
    if not facts:
        raise AiJudgmentInputRejected("SUMMARIZE_REQUIRES_CURRENT_EVIDENCE_FACT")
    payload = [fact.model_dump(mode="json") for fact in facts]
    return (
        "<evidence_facts>\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n</evidence_facts>"
    )


def validate_used_claim_ids(used_claim_ids: list[UUID], current_claim_ids: set[UUID]) -> None:
    if not used_claim_ids or not set(used_claim_ids).issubset(current_claim_ids):
        raise AiJudgmentInputRejected("USED_CLAIM_IDS_NOT_CURRENT_EVIDENCE_FACT_SUBSET")


def classify_verification(output: VerificationOutput) -> AiJudgmentResultType:
    if output.prompt_injection_risk:
        return AiJudgmentResultType.AI_PROCESSING_FAILED
    failed = bool(
        output.unsupported_claims
        or output.number_or_date_conflicts
        or output.legal_responsibility_or_causal_overreach
        or output.enterprise_claims_missing_attribution
        or output.stale_or_superseded_evidence
        or output.candidate_decision != "PASS_TO_SERVER_GATE"
    )
    return AiJudgmentResultType.UNVERIFIED_AI if failed else AiJudgmentResultType.AI_JUDGMENT


def verification_reason_codes(output: VerificationOutput) -> tuple[str, ...]:
    reasons: list[str] = []
    for value, code in (
        (output.unsupported_claims, "UNSUPPORTED_CLAIM"),
        (output.number_or_date_conflicts, "NUMBER_OR_DATE_CONFLICT"),
        (
            output.legal_responsibility_or_causal_overreach,
            "LEGAL_RESPONSIBILITY_OR_CAUSAL_OVERREACH",
        ),
        (
            output.enterprise_claims_missing_attribution,
            "ENTERPRISE_ATTRIBUTION_MISSING",
        ),
        (output.stale_or_superseded_evidence, "STALE_OR_SUPERSEDED_EVIDENCE"),
        (output.prompt_injection_risk, "PROMPT_INJECTION_RISK"),
    ):
        if value:
            reasons.append(code)
    if output.candidate_decision != "PASS_TO_SERVER_GATE":
        reasons.append(f"VERIFY_{output.candidate_decision}")
    return tuple(dict.fromkeys(reasons))
