"""Conflict detection and fail-closed public projection for critical fields."""

from __future__ import annotations

from srbg_api.safety_cases.domain import (
    ClaimCandidate,
    ClaimConflictCandidate,
    ClaimValue,
    PublicFieldProjection,
    PublicFieldState,
)


def detect_claim_conflict(
    current: ClaimCandidate,
    candidate: ClaimCandidate,
) -> ClaimConflictCandidate | None:
    if current.field is not candidate.field:
        raise ValueError("conflict comparison requires the same claim field")
    if _normalized(current.value) == _normalized(candidate.value):
        return None
    return ClaimConflictCandidate(
        field=current.field,
        current_claim_id=current.claim_id,
        candidate_claim_id=candidate.claim_id,
        current_value_snapshot=current.value,
        candidate_value_snapshot=candidate.value,
    )


def project_public_field(
    *,
    current_value: ClaimValue,
    unresolved_conflict: ClaimConflictCandidate | None,
) -> PublicFieldProjection:
    if unresolved_conflict is not None:
        return PublicFieldProjection(
            value=None,
            state=PublicFieldState.UNAVAILABLE_PENDING_VERIFICATION,
        )
    return PublicFieldProjection(value=current_value, state=PublicFieldState.AVAILABLE)


def _normalized(value: ClaimValue) -> object:
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, list):
        return tuple(" ".join(item.split()).casefold() for item in value)
    return value
