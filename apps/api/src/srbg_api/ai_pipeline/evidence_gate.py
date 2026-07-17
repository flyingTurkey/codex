"""Deterministic PERS-06 evidence acceptance; model confidence never grants authority."""

from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AUTOMATIC_EVIDENCE_RULE_VERSION = "automatic-evidence-gate-v1"
_LEGAL_CAUSAL_FIELDS = frozenset(
    {
        "legal_effect",
        "legal_liability",
        "regulation_status",
        "incident_cause",
        "responsibility",
    }
)
_ATTRIBUTED_FIELDS = frozenset({"claimed_outcome"})
_SCALAR_FIELDS = frozenset(
    {
        "published_at",
        "effective_at",
        "occurred_at",
        "publication_year",
        "death_count",
        "injury_count",
        "direct_loss",
    }
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceGateEvidence(_StrictModel):
    document_version_id: UUID
    excerpt: str = Field(min_length=1, max_length=2000)
    active: bool


class AutomaticEvidenceCandidate(_StrictModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    field: str = Field(min_length=1, max_length=100)
    value: Any
    confidence_bps: int = Field(ge=0, le=10_000)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)
    attribution: str | None = Field(default=None, min_length=1, max_length=500)
    origin: Literal["MODEL", "LOCAL_RULE"]


class AutomaticEvidenceContext(_StrictModel):
    document_version_id: UUID
    evidence: dict[UUID, EvidenceGateEvidence]
    official_first_party: bool
    unresolved_conflict_fields: frozenset[str]
    prompt_injection_risk: bool
    evaluated_at: datetime


class EvidenceFact(_StrictModel):
    kind: Literal["EVIDENCE_FACT"] = "EVIDENCE_FACT"
    candidate: AutomaticEvidenceCandidate
    acceptance_method: Literal["AUTOMATED_EVIDENCE_GATE"] = "AUTOMATED_EVIDENCE_GATE"
    rule_version: str = AUTOMATIC_EVIDENCE_RULE_VERSION
    input_document_version_id: UUID
    evidence_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AiJudgment(_StrictModel):
    kind: Literal["AI_JUDGMENT"] = "AI_JUDGMENT"
    candidate: AutomaticEvidenceCandidate
    reason_codes: tuple[str, ...]
    rule_version: str = AUTOMATIC_EVIDENCE_RULE_VERSION
    input_document_version_id: UUID


GateResult = EvidenceFact | AiJudgment


class AutomaticEvidenceGate:
    """Fail closed using only current server-authoritative evidence facts."""

    def evaluate(
        self,
        candidate: AutomaticEvidenceCandidate,
        context: AutomaticEvidenceContext,
    ) -> GateResult:
        reasons: list[str] = []
        evidence_rows: list[EvidenceGateEvidence] = []
        for evidence_id in candidate.evidence_ids:
            evidence = context.evidence.get(evidence_id)
            if evidence is None:
                _append_once(reasons, "EVIDENCE_ID_NOT_FOUND")
                continue
            evidence_rows.append(evidence)
            if evidence.document_version_id != context.document_version_id:
                _append_once(reasons, "EVIDENCE_DOCUMENT_VERSION_MISMATCH")
            if not evidence.active:
                _append_once(reasons, "EVIDENCE_INACTIVE")
        if context.prompt_injection_risk:
            reasons.append("PROMPT_INJECTION_RISK")
        if candidate.field in context.unresolved_conflict_fields:
            reasons.append("UNRESOLVED_CONFLICT")
        excerpts = "\n".join(row.excerpt for row in evidence_rows)
        if candidate.field in _ATTRIBUTED_FIELDS:
            if not candidate.attribution or not _contains(excerpts, candidate.attribution):
                reasons.append("ENTERPRISE_ATTRIBUTION_REQUIRED")
        if candidate.field in _LEGAL_CAUSAL_FIELDS and not context.official_first_party:
            reasons.append("OFFICIAL_DIRECT_SUPPORT_REQUIRED")
        if evidence_rows and not _directly_supported(candidate, excerpts):
            reasons.append(
                "SCALAR_EVIDENCE_MISMATCH"
                if candidate.field in _SCALAR_FIELDS
                else "DIRECT_TEXT_SUPPORT_REQUIRED"
            )
        if reasons:
            return AiJudgment(
                candidate=candidate,
                reason_codes=tuple(dict.fromkeys(reasons)),
                input_document_version_id=context.document_version_id,
            )
        digest_payload = [
            {
                "id": str(evidence_id),
                "excerpt_sha256": sha256(
                    context.evidence[evidence_id].excerpt.encode()
                ).hexdigest(),
            }
            for evidence_id in sorted(candidate.evidence_ids, key=str)
        ]
        digest = sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return EvidenceFact(
            candidate=candidate,
            input_document_version_id=context.document_version_id,
            evidence_set_sha256=digest,
        )


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _contains(text: str, value: object) -> bool:
    return _normalize_text(str(value)) in _normalize_text(text)


def _directly_supported(candidate: AutomaticEvidenceCandidate, excerpts: str) -> bool:
    value = candidate.value
    if candidate.field in {"published_at", "effective_at", "occurred_at"}:
        wanted_match = re.search(r"(20\d{2})\D*(\d{1,2})\D*(\d{1,2})", str(value))
        if wanted_match is None:
            return False
        wanted = tuple(int(part) for part in wanted_match.groups())
        dates = re.findall(
            r"(20\d{2})\D{0,3}(1[0-2]|0?[1-9])\D{0,3}(3[01]|[12]\d|0?[1-9])",
            excerpts,
        )
        return any(tuple(int(part) for part in date) == wanted for date in dates)
    if candidate.field == "publication_year":
        return bool(re.search(rf"(?<!\d){re.escape(str(value))}(?!\d)", excerpts))
    if candidate.field in {"death_count", "injury_count"}:
        return bool(re.search(rf"(?<!\d){int(value)}\s*(?:人|名)(?!\d)", excerpts))
    if candidate.field == "direct_loss":
        return _contains(excerpts, value)
    return _contains(excerpts, value)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()
