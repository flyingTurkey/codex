from datetime import UTC, datetime, timedelta

import pytest
from srbg_api.source_registry.domain import (
    GateEvidence,
    InvalidSourceTransition,
    SourceGate,
    transition_source,
)
from srbg_contracts import SourceState


def _gate(**overrides: object) -> SourceGate:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "policy_valid": True,
        "policy_valid_until": now + timedelta(days=30),
        "onboarding_valid": True,
        "onboarding_valid_until": now + timedelta(days=30),
        "onboarding_policy_matches": True,
        "fixture_count": 30,
        "required_checks_complete": True,
    }
    values.update(overrides)
    return SourceGate(**values)  # type: ignore[arg-type]


def test_source_state_machine_allows_only_the_next_state() -> None:
    assert transition_source(SourceState.CANDIDATE, SourceState.COMPLIANCE_REVIEW, _gate()) == (
        SourceState.COMPLIANCE_REVIEW
    )
    assert (
        transition_source(SourceState.COMPLIANCE_REVIEW, SourceState.FIXTURE_TEST, _gate())
        == SourceState.FIXTURE_TEST
    )
    assert transition_source(SourceState.FIXTURE_TEST, SourceState.APPROVED, _gate()) == (
        SourceState.APPROVED
    )

    with pytest.raises(InvalidSourceTransition):
        transition_source(SourceState.CANDIDATE, SourceState.ACTIVE, _gate())


@pytest.mark.parametrize(
    "gate",
    [
        _gate(policy_valid=False),
        _gate(onboarding_valid=False),
        _gate(onboarding_policy_matches=False),
        _gate(fixture_count=29),
        _gate(required_checks_complete=False),
    ],
)
def test_approval_is_default_deny_when_any_evidence_is_missing(gate: SourceGate) -> None:
    with pytest.raises(InvalidSourceTransition):
        transition_source(SourceState.FIXTURE_TEST, SourceState.APPROVED, gate)


def test_effective_active_recomputes_gate_instead_of_trusting_database_flags() -> None:
    tampered_row = GateEvidence(
        state=SourceState.ACTIVE,
        enabled=True,
        gate=_gate(policy_valid=False),
    )
    assert tampered_row.is_effectively_active() is False
