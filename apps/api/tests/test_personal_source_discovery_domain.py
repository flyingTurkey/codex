from datetime import UTC, datetime, timedelta

import pytest
from srbg_api.personal_source_discovery import (
    AUTO_SCORE_RULE_VERSION,
    AutoEnableGate,
    AutoScoreComponents,
    ScoringInput,
    calculate_auto_score,
    evaluate_auto_enable,
    validate_discovery_depth,
)


def _gate(**updates: bool) -> AutoEnableGate:
    values = {
        "public_network": True,
        "ssrf_safe": True,
        "robots_permitted": True,
        "access_open": True,
        "terms_permitted": True,
        "copyright_permitted": True,
        "connector_executable": True,
        "sample_parsed": True,
        "evidence_current": True,
        "sticky_disabled": False,
    }
    values.update(updates)
    return AutoEnableGate(**values)


def test_auto_enable_threshold_is_inclusive_at_70() -> None:
    denied = evaluate_auto_enable(AutoScoreComponents(35, 25, 0, 4, 5), _gate())
    allowed = evaluate_auto_enable(AutoScoreComponents(35, 25, 0, 5, 5), _gate())

    assert denied.total == 69
    assert denied.eligible is False
    assert denied.reason_codes == ("SCORE_BELOW_70",)
    assert allowed.total == 70
    assert allowed.eligible is True
    assert allowed.reason_codes == ()


def test_hard_gate_and_sticky_disable_override_a_passing_score() -> None:
    score = AutoScoreComponents(35, 25, 20, 10, 10)

    blocked = evaluate_auto_enable(
        score,
        _gate(ssrf_safe=False, robots_permitted=False, sticky_disabled=True),
    )

    assert blocked.eligible is False
    assert blocked.reason_codes == (
        "SSRF_GATE_FAILED",
        "ROBOTS_NOT_PERMITTED",
        "OWNER_STICKY_DISABLED",
    )


def test_rule_scoring_uses_ratios_and_ignores_authority_and_independence() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    facts = ScoringInput(
        successful_sample_count=4,
        relevant_sample_count=3,
        stability_checks_passed=4,
        complete_field_count=16,
        possible_field_count=20,
        profile_confidences=(80, 60, 40, 20),
        valid_sample_count=3,
        latest_published_at=now - timedelta(days=40),
    )

    first = calculate_auto_score(facts, now=now)
    second = calculate_auto_score(facts, now=now)

    assert first == AutoScoreComponents(26, 20, 16, 5, 6)
    assert second == first
    assert first.total == 73
    assert AUTO_SCORE_RULE_VERSION == "personal-source-auto-score-v1"


@pytest.mark.parametrize("depth", [-1, 2, 99])
def test_outbound_link_depth_is_fixed_to_one(depth: int) -> None:
    with pytest.raises(ValueError, match="depth"):
        validate_discovery_depth(depth)


@pytest.mark.parametrize("depth", [0, 1])
def test_root_and_first_level_discovery_depths_are_valid(depth: int) -> None:
    assert validate_discovery_depth(depth) == depth


def test_deepseek_unavailable_does_not_block_rule_score_at_seventy() -> None:
    rule_only = AutoScoreComponents(25, 20, 15, 5, 5)
    gate = AutoEnableGate(True, True, True, True, True, True, True, True, True, False)

    decision = evaluate_auto_enable(rule_only, gate)

    assert decision.total == 70
    assert decision.eligible is True
