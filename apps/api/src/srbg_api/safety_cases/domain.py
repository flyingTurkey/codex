"""Core value objects for the safety-case lifecycle.

The module deliberately contains no database or HTTP dependencies.  Parser output remains a
candidate; only explicit reviewer decisions may turn protected safety-case fields into accepted
facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

type ClaimValue = int | str | list[str] | None


class ReportStage(StrEnum):
    INITIAL_REPORT = "INITIAL_REPORT"
    FOLLOW_UP_REPORT = "FOLLOW_UP_REPORT"
    FINAL_INVESTIGATION = "FINAL_INVESTIGATION"
    ENFORCEMENT = "ENFORCEMENT"
    RECTIFICATION = "RECTIFICATION"


class IncidentStatus(StrEnum):
    UNVERIFIED_LEAD = "UNVERIFIED_LEAD"
    INITIAL_OFFICIAL_REPORT = "INITIAL_OFFICIAL_REPORT"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    FINAL_INVESTIGATION_REPORT = "FINAL_INVESTIGATION_REPORT"
    ENFORCEMENT_DECISION = "ENFORCEMENT_DECISION"
    RECTIFICATION_FOLLOW_UP = "RECTIFICATION_FOLLOW_UP"
    CLOSED = "CLOSED"
    CORRECTED = "CORRECTED"
    WITHDRAWN = "WITHDRAWN"


class EventRelationType(StrEnum):
    FOLLOW_UP = "FOLLOW_UP"
    INVESTIGATES = "INVESTIGATES"
    PENALIZES = "PENALIZES"
    RECTIFIES = "RECTIFIES"
    CORRECTS = "CORRECTS"


class ClaimConflictStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    RESOLVED = "RESOLVED"


class ClaimConflictAction(StrEnum):
    ACCEPT_CANDIDATE = "ACCEPT_CANDIDATE"
    KEEP_CURRENT = "KEEP_CURRENT"
    MARK_UNRESOLVED = "MARK_UNRESOLVED"


class ClaimField(StrEnum):
    DEATHS = "deaths"
    INJURIES = "injuries"
    LOSS_AMOUNT_MINOR = "loss_amount_minor"
    OFFICIAL_DIRECT_CAUSES = "official_direct_causes"
    RESPONSIBILITY_FINDINGS = "responsibility_findings"


class SourceAuthority(StrEnum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C = "C"


class EvidenceRole(StrEnum):
    PRIMARY_OFFICIAL = "PRIMARY_OFFICIAL"
    PRIMARY_AUTHOR = "PRIMARY_AUTHOR"
    VENDOR_CLAIM = "VENDOR_CLAIM"
    INDEPENDENT_CONFIRMATION = "INDEPENDENT_CONFIRMATION"
    SECONDARY_REPORT = "SECONDARY_REPORT"
    CONTRADICTING = "CONTRADICTING"


class DedupDisposition(StrEnum):
    EXACT_RAW_DUPLICATE = "EXACT_RAW_DUPLICATE"
    PRESERVE_AND_LINK = "PRESERVE_AND_LINK"
    PRESERVE_AS_DISTINCT = "PRESERVE_AS_DISTINCT"


class PublicFieldState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE_PENDING_VERIFICATION = "UNAVAILABLE_PENDING_VERIFICATION"


@dataclass(frozen=True, slots=True)
class EventIdentity:
    occurred_on: date | None
    region: str | None
    project: str | None
    subjects: tuple[str, ...]
    accident_type: str | None


@dataclass(frozen=True, slots=True)
class EventMatchResult:
    total: int
    dimension_scores: dict[str, int]
    forms_candidate: bool
    requires_human_review: bool
    algorithm_version: str


@dataclass(frozen=True, slots=True)
class EvidenceDescriptor:
    evidence_id: UUID
    report_stage: ReportStage
    authority: SourceAuthority
    role: EvidenceRole


@dataclass(frozen=True, slots=True)
class ClaimCandidate:
    claim_id: UUID
    field: ClaimField
    value: ClaimValue
    evidence: EvidenceDescriptor

    def __post_init__(self) -> None:
        if self.field in {
            ClaimField.DEATHS,
            ClaimField.INJURIES,
            ClaimField.LOSS_AMOUNT_MINOR,
        } and (not isinstance(self.value, int) or isinstance(self.value, bool) or self.value < 0):
            raise ValueError(f"{self.field.value} must be a non-negative integer")
        if self.field in {
            ClaimField.OFFICIAL_DIRECT_CAUSES,
            ClaimField.RESPONSIBILITY_FINDINGS,
        } and (
            not isinstance(self.value, list)
            or any(not isinstance(item, str) or not item.strip() for item in self.value)
        ):
            raise ValueError(f"{self.field.value} must be a list of non-empty strings")


@dataclass(frozen=True, slots=True)
class ClaimReviewDecision:
    accepted: bool
    reviewer_id: UUID
    submitted_by: UUID


@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ClaimConflictCandidate:
    field: ClaimField
    current_claim_id: UUID
    candidate_claim_id: UUID
    current_value_snapshot: ClaimValue
    candidate_value_snapshot: ClaimValue
    status: ClaimConflictStatus = ClaimConflictStatus.PENDING_REVIEW
    requires_human_review: bool = True


@dataclass(frozen=True, slots=True)
class PublicFieldProjection:
    value: ClaimValue
    state: PublicFieldState
