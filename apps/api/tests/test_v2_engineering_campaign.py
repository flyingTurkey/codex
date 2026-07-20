from datetime import UTC, datetime

import pytest
from srbg_api.intelligence_v2.campaign import (
    CampaignAction,
    CampaignPhase,
    CampaignSnapshot,
    decide_transition,
)

NOW = datetime(2026, 7, 19, tzinfo=UTC)


def test_campaign_requires_prepare_before_start() -> None:
    with pytest.raises(ValueError, match="CAMPAIGN_NOT_PREPARED"):
        decide_transition(None, CampaignAction.START, NOW)


def test_campaign_transitions_are_append_only_and_idempotent() -> None:
    prepared = decide_transition(None, CampaignAction.PREPARE, NOW)
    assert prepared is not None
    assert prepared.phase is CampaignPhase.PREPARED

    started = decide_transition(prepared, CampaignAction.START, NOW)
    assert started is not None
    assert started.phase is CampaignPhase.STARTED
    assert decide_transition(started, CampaignAction.START, NOW) is None

    finalized = decide_transition(started, CampaignAction.FINALIZE, NOW)
    assert finalized is not None
    assert finalized.phase is CampaignPhase.FINALIZED
    restored = CampaignSnapshot(CampaignPhase.RESTORED, NOW)
    assert decide_transition(restored, CampaignAction.FINALIZE, NOW) is None


def test_status_is_read_only() -> None:
    prepared = CampaignSnapshot(CampaignPhase.PREPARED, NOW)
    assert decide_transition(prepared, CampaignAction.STATUS, NOW) is None
