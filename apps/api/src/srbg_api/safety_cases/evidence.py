"""Evidence qualification and claim-level human decision rules."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from srbg_api.safety_cases.domain import (
    ClaimAssessment,
    ClaimCandidate,
    ClaimField,
    ClaimReviewDecision,
    EvidenceRole,
    ReportStage,
    SourceAuthority,
)

_FORMAL_FIELDS = frozenset({ClaimField.OFFICIAL_DIRECT_CAUSES, ClaimField.RESPONSIBILITY_FINDINGS})
_FORMAL_STAGES = frozenset({ReportStage.FINAL_INVESTIGATION, ReportStage.ENFORCEMENT})
_OFFICIAL_AUTHORITIES = frozenset({SourceAuthority.A0, SourceAuthority.A1})


def assess_claim_candidate(
    candidate: ClaimCandidate,
    decision: ClaimReviewDecision | None,
) -> ClaimAssessment:
    """Default-deny a protected claim unless evidence and a separated review both qualify."""

    evidence = candidate.evidence
    if candidate.field in _FORMAL_FIELDS and (
        evidence.authority not in _OFFICIAL_AUTHORITIES
        or evidence.role is not EvidenceRole.PRIMARY_OFFICIAL
        or evidence.report_stage not in _FORMAL_STAGES
    ):
        return ClaimAssessment(False, "FORMAL_OFFICIAL_EVIDENCE_REQUIRED")
    if (
        evidence.authority not in _OFFICIAL_AUTHORITIES
        or evidence.role is not EvidenceRole.PRIMARY_OFFICIAL
    ):
        return ClaimAssessment(False, "OFFICIAL_EVIDENCE_REQUIRED")
    if decision is None:
        return ClaimAssessment(False, "HUMAN_DECISION_REQUIRED")
    assert_reviewer_can_decide(decision.submitted_by, decision.reviewer_id)
    if not decision.accepted:
        return ClaimAssessment(False, "REVIEW_REJECTED")
    return ClaimAssessment(True, "ACCEPTED_BY_HUMAN_REVIEW")


def assert_reviewer_can_decide(submitted_by: UUID, reviewer_id: UUID) -> None:
    if submitted_by == reviewer_id:
        raise PermissionError("submitter cannot review their own safety case")


def findings_projection(
    *,
    formal_evidence_reviewed: bool,
    findings: Sequence[str],
) -> tuple[str, ...] | None:
    """Preserve the distinction between no basis (null) and reviewed/no findings ([])."""

    if not formal_evidence_reviewed:
        return None
    normalized = tuple(value.strip() for value in findings)
    if any(not value for value in normalized):
        raise ValueError("findings must not contain empty values")
    return normalized
