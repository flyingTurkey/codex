"""State transitions for the resumable engineering closeout campaign."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CampaignAction(StrEnum):
    PREPARE = "prepare"
    START = "start"
    STATUS = "status"
    FINALIZE = "finalize"


class CampaignPhase(StrEnum):
    PREPARED = "PREPARED"
    STARTED = "STARTED"
    FINALIZED = "FINALIZED"
    RESTORED = "RESTORED"


@dataclass(frozen=True)
class CampaignSnapshot:
    phase: CampaignPhase
    occurred_at: datetime


def decide_transition(
    current: CampaignSnapshot | None,
    action: CampaignAction,
    occurred_at: datetime,
) -> CampaignSnapshot | None:
    """Return the fact to append, or ``None`` for an idempotent/read-only action."""

    if occurred_at.tzinfo is None:
        raise ValueError("CAMPAIGN_TIMEZONE_REQUIRED")
    if action is CampaignAction.STATUS:
        return None
    if current is None:
        if action is not CampaignAction.PREPARE:
            raise ValueError("CAMPAIGN_NOT_PREPARED")
        return CampaignSnapshot(CampaignPhase.PREPARED, occurred_at)
    if action is CampaignAction.PREPARE:
        return None
    if action is CampaignAction.START:
        if current.phase is CampaignPhase.PREPARED:
            return CampaignSnapshot(CampaignPhase.STARTED, occurred_at)
        if current.phase is CampaignPhase.STARTED:
            return None
        raise ValueError("CAMPAIGN_ALREADY_FINALIZED")
    if action is CampaignAction.FINALIZE:
        if current.phase is CampaignPhase.STARTED:
            return CampaignSnapshot(CampaignPhase.FINALIZED, occurred_at)
        if current.phase in {CampaignPhase.FINALIZED, CampaignPhase.RESTORED}:
            return None
        raise ValueError("CAMPAIGN_NOT_STARTED")
    raise ValueError("CAMPAIGN_ACTION_INVALID")
