"""Pure Round 17 readiness and observation-window versioning rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal


@dataclass(frozen=True, slots=True)
class PilotSourceReadiness:
    source_code: str
    lifecycle_state: str
    policy_approved: bool
    approval_valid_until: datetime | None
    connector_current: bool
    live_trial_succeeded: bool
    production_approval_current: bool
    schedule_active: bool
    eventization_pipeline_ready: bool
    execution_domain: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PilotReadinessFacts:
    sources: tuple[PilotSourceReadiness, ...]
    controlled_oidc_actor_count: int
    local_identity_count: int
    gold_release_frozen: bool
    metric_definition_frozen: bool
    ai_enabled: bool
    semantic_search_enabled: bool
    external_notifications_enabled: bool


@dataclass(frozen=True, slots=True)
class PilotReadinessResult:
    blocker_codes: tuple[str, ...]
    ends_at: datetime


class WindowChangeKind(StrEnum):
    ROSTER = "ROSTER"
    METRIC_DEFINITION = "METRIC_DEFINITION"
    EVENT_IDENTITY = "EVENT_IDENTITY"
    PUBLICATION_ACL = "PUBLICATION_ACL"
    SHARED_EXECUTOR = "SHARED_EXECUTOR"
    SOURCE_CONNECTOR = "SOURCE_CONNECTOR"
    SOURCE_DOM = "SOURCE_DOM"
    SOURCE_SLO = "SOURCE_SLO"
    RUNTIME_FAILURE = "RUNTIME_FAILURE"
    DOCUMENTATION = "DOCUMENTATION"


ResetScope = Literal["FULL_WINDOW", "SOURCE_WINDOW", "NO_RESET"]


def reset_scope_for_change(change: WindowChangeKind) -> ResetScope:
    if change in {
        WindowChangeKind.ROSTER,
        WindowChangeKind.METRIC_DEFINITION,
        WindowChangeKind.EVENT_IDENTITY,
        WindowChangeKind.PUBLICATION_ACL,
        WindowChangeKind.SHARED_EXECUTOR,
    }:
        return "FULL_WINDOW"
    if change in {
        WindowChangeKind.SOURCE_CONNECTOR,
        WindowChangeKind.SOURCE_DOM,
        WindowChangeKind.SOURCE_SLO,
    }:
        return "SOURCE_WINDOW"
    return "NO_RESET"


def evaluate_window_readiness(
    facts: PilotReadinessFacts,
    *,
    starts_at: datetime,
    duration_hours: int,
) -> PilotReadinessResult:
    blockers: set[str] = set()
    ends_at = starts_at + timedelta(hours=duration_hours)
    source_codes = [source.source_code for source in facts.sources]
    if len(source_codes) != 20 or len(set(source_codes)) != 20:
        blockers.add("SOURCE_COHORT_NOT_EXACTLY_20")
    for source in facts.sources:
        if source.lifecycle_state != "ACTIVE":
            blockers.add("SOURCE_NOT_ACTIVE")
        if not source.policy_approved:
            blockers.add("SOURCE_POLICY_NOT_APPROVED")
        if source.approval_valid_until is None or source.approval_valid_until < ends_at:
            blockers.add("SOURCE_APPROVAL_DOES_NOT_COVER_WINDOW")
        if not source.connector_current:
            blockers.add("SOURCE_CONNECTOR_NOT_CURRENT")
        if not source.live_trial_succeeded:
            blockers.add("LIVE_TRIAL_NOT_SUCCEEDED")
        if not source.production_approval_current:
            blockers.add("PRODUCTION_APPROVAL_NOT_CURRENT")
        if not source.schedule_active:
            blockers.add("SOURCE_SCHEDULE_NOT_ACTIVE")
        if not source.eventization_pipeline_ready:
            blockers.add("SOURCE_EVENTIZATION_PIPELINE_NOT_READY")
        if source.execution_domain != "PRODUCTION":
            blockers.add("NON_PRODUCTION_SOURCE_EVIDENCE")
    if duration_hours != 168:
        blockers.add("WINDOW_DURATION_NOT_168_HOURS")
    if facts.controlled_oidc_actor_count < 3:
        blockers.add("CONTROLLED_OIDC_IDENTITIES_MISSING")
    if facts.local_identity_count:
        blockers.add("LOCAL_IDENTITY_PRESENT")
    if not facts.gold_release_frozen:
        blockers.add("GOLD_RELEASE_NOT_FROZEN")
    if not facts.metric_definition_frozen:
        blockers.add("METRIC_DEFINITION_NOT_FROZEN")
    if facts.ai_enabled:
        blockers.add("MODEL_EXECUTION_ENABLED")
    if facts.semantic_search_enabled:
        blockers.add("SEMANTIC_SEARCH_ENABLED")
    if facts.external_notifications_enabled:
        blockers.add("EXTERNAL_NOTIFICATIONS_ENABLED")
    return PilotReadinessResult(blocker_codes=tuple(sorted(blockers)), ends_at=ends_at)
