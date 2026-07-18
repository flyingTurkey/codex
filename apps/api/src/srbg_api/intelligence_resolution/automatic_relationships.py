"""Conservative PERS-08 automatic relationship decisions.

The module is persistence-free so API and worker calculations cannot drift. Model
scores are inputs only; deterministic hard constraints remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

AUTOMATIC_RELATIONSHIP_ALGORITHM_VERSION = "pers08-relations-v1"
HIGH_CONFIDENCE_BPS = 9_500
RELATED_CONTENT_BPS = 9_000


class RelationshipKind(StrEnum):
    DUPLICATE = "DUPLICATE"
    SAME_EVENT = "SAME_EVENT"
    FOLLOW_UP_OF = "FOLLOW_UP_OF"
    INVESTIGATES = "INVESTIGATES"
    MODEL_ALIAS = "MODEL_ALIAS"
    VERSION_SUCCESSOR = "VERSION_SUCCESSOR"
    TOPIC = "TOPIC"
    RELATED_CONTENT = "RELATED_CONTENT"


@dataclass(frozen=True, slots=True)
class AutomaticRelationshipInput:
    left_item_id: UUID
    right_item_id: UUID
    left_document_version_id: UUID
    right_document_version_id: UUID
    left_content_sha256: str
    right_content_sha256: str
    score_bps: int
    hard_conflicts: tuple[str, ...]
    exact_identity: bool
    relation_hint: str | None
    left_report_stage: str | None
    right_report_stage: str | None
    left_source_role: str | None
    right_source_role: str | None
    algorithm_version: str = AUTOMATIC_RELATIONSHIP_ALGORITHM_VERSION
    model_version: str | None = None


@dataclass(frozen=True, slots=True)
class AutomaticRelationshipDecision:
    kind: RelationshipKind
    source_item_id: UUID
    target_item_id: UUID
    score_bps: int
    reason_codes: tuple[str, ...]
    input_fingerprint_sha256: str


@dataclass(frozen=True, slots=True)
class RelationshipSuppression:
    kind: RelationshipKind
    member_ids: frozenset[UUID]
    input_fingerprint_sha256: str


_SYMMETRIC_KINDS = {
    RelationshipKind.DUPLICATE,
    RelationshipKind.SAME_EVENT,
    RelationshipKind.MODEL_ALIAS,
    RelationshipKind.TOPIC,
    RelationshipKind.RELATED_CONTENT,
}
_INITIAL_STAGES = {"INITIAL", "INITIAL_OFFICIAL_REPORT"}
_FOLLOW_UP_STAGES = {"FOLLOW_UP", "UNDER_INVESTIGATION", "RECTIFICATION_FOLLOW_UP"}
_FINAL_STAGES = {"FINAL", "FINAL_INVESTIGATION_REPORT", "CLOSED"}
_DISTINCT_SOURCE_ROLES = {"VENDOR_STATEMENT", "MEDIA_REPORT", "INDEPENDENT_VERIFICATION"}


def input_fingerprint(value: AutomaticRelationshipInput, kind: RelationshipKind) -> str:
    members = [
        {
            "item_id": str(value.left_item_id),
            "document_version_id": str(value.left_document_version_id),
            "content_sha256": value.left_content_sha256,
            "source_role": value.left_source_role,
        },
        {
            "item_id": str(value.right_item_id),
            "document_version_id": str(value.right_document_version_id),
            "content_sha256": value.right_content_sha256,
            "source_role": value.right_source_role,
        },
    ]
    if kind in _SYMMETRIC_KINDS:
        members.sort(key=lambda member: str(member["item_id"]))
    payload = {
        "kind": kind.value,
        "members": members,
        "algorithm_version": value.algorithm_version,
        "model_version": value.model_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _lifecycle_kind(value: AutomaticRelationshipInput) -> RelationshipKind | None:
    left = value.left_report_stage
    right = value.right_report_stage
    if left in _INITIAL_STAGES and right in _FOLLOW_UP_STAGES:
        return RelationshipKind.FOLLOW_UP_OF
    if left in _FOLLOW_UP_STAGES and right in _FINAL_STAGES:
        return RelationshipKind.INVESTIGATES
    if left in _INITIAL_STAGES and right in _FINAL_STAGES:
        return RelationshipKind.INVESTIGATES
    return None


def _hint_kind(hint: str | None) -> RelationshipKind | None:
    mapping = {
        "SAME_EVENT": RelationshipKind.SAME_EVENT,
        "MODEL_ALIAS": RelationshipKind.MODEL_ALIAS,
        "VERSION_SUCCESSOR": RelationshipKind.VERSION_SUCCESSOR,
        "TOPIC": RelationshipKind.TOPIC,
        "RELATED_CONTENT": RelationshipKind.RELATED_CONTENT,
    }
    return mapping.get(hint or "")


def decide_automatic_relationship(
    value: AutomaticRelationshipInput,
    *,
    suppressions: tuple[RelationshipSuppression, ...] = (),
) -> AutomaticRelationshipDecision | None:
    if value.left_item_id == value.right_item_id or value.hard_conflicts:
        return None
    if not 0 <= value.score_bps <= 10_000:
        raise ValueError("score_bps must be between 0 and 10000")

    lifecycle = _lifecycle_kind(value)
    hinted = _hint_kind(value.relation_hint)
    distinct_roles = {
        role
        for role in (value.left_source_role, value.right_source_role)
        if role in _DISTINCT_SOURCE_ROLES
    }
    reasons: tuple[str, ...]
    if lifecycle is not None:
        kind = lifecycle
        source, target = value.right_item_id, value.left_item_id
        reasons = ("REPORT_LIFECYCLE", "NO_DEDUPLICATION")
    elif hinted is not None:
        required = (
            HIGH_CONFIDENCE_BPS
            if hinted is not RelationshipKind.RELATED_CONTENT
            else RELATED_CONTENT_BPS
        )
        if not value.exact_identity and value.score_bps < required:
            return None
        kind = hinted
        source, target = value.left_item_id, value.right_item_id
        reasons = ("EXPLICIT_RELATION_KEY",)
    elif len(distinct_roles) > 1:
        if not value.exact_identity and value.score_bps < RELATED_CONTENT_BPS:
            return None
        kind = RelationshipKind.RELATED_CONTENT
        source, target = value.left_item_id, value.right_item_id
        reasons = ("SOURCE_ROLES_PRESERVED",)
    elif value.exact_identity or value.score_bps >= HIGH_CONFIDENCE_BPS:
        kind = RelationshipKind.DUPLICATE
        source, target = sorted((value.left_item_id, value.right_item_id), key=str)
        reasons = ("EXACT_IDENTITY",) if value.exact_identity else ("HIGH_CONFIDENCE",)
    else:
        return None

    fingerprint = input_fingerprint(value, kind)
    members = frozenset((value.left_item_id, value.right_item_id))
    if any(
        suppression.kind is kind
        and suppression.member_ids == members
        and suppression.input_fingerprint_sha256 == fingerprint
        for suppression in suppressions
    ):
        return None
    return AutomaticRelationshipDecision(
        kind=kind,
        source_item_id=source,
        target_item_id=target,
        score_bps=value.score_bps,
        reason_codes=reasons,
        input_fingerprint_sha256=fingerprint,
    )
