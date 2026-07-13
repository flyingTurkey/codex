"""Pure source lifecycle and activation gate rules."""

from dataclasses import dataclass
from datetime import UTC, datetime

from srbg_contracts import SourceState


class InvalidSourceTransition(ValueError):
    """Raised when a transition skips state or lacks authoritative evidence."""


@dataclass(frozen=True, slots=True)
class SourceGate:
    policy_valid: bool
    policy_valid_until: datetime | None
    onboarding_valid: bool
    onboarding_valid_until: datetime | None
    onboarding_policy_matches: bool
    fixture_count: int
    required_checks_complete: bool

    def allows_fixture_test(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return (
            self.policy_valid
            and self.policy_valid_until is not None
            and self.policy_valid_until > current
        )

    def allows_approval(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return (
            self.allows_fixture_test(current)
            and self.onboarding_valid
            and self.onboarding_valid_until is not None
            and self.onboarding_valid_until > current
            and self.onboarding_policy_matches
            and self.fixture_count >= 30
            and self.required_checks_complete
        )


@dataclass(frozen=True, slots=True)
class GateEvidence:
    state: SourceState
    enabled: bool
    gate: SourceGate

    def is_effectively_active(self, now: datetime | None = None) -> bool:
        return self.state is SourceState.ACTIVE and self.enabled and self.gate.allows_approval(now)


_NEXT_STATE = {
    SourceState.CANDIDATE: SourceState.COMPLIANCE_REVIEW,
    SourceState.COMPLIANCE_REVIEW: SourceState.FIXTURE_TEST,
    SourceState.FIXTURE_TEST: SourceState.APPROVED,
    SourceState.APPROVED: SourceState.ACTIVE,
}


def transition_source(
    current: SourceState,
    target: SourceState,
    gate: SourceGate,
    now: datetime | None = None,
) -> SourceState:
    if _NEXT_STATE.get(current) is not target:
        raise InvalidSourceTransition(f"invalid transition: {current.value} -> {target.value}")
    if target is SourceState.FIXTURE_TEST and not gate.allows_fixture_test(now):
        raise InvalidSourceTransition("a current valid source policy is required")
    if target in {SourceState.APPROVED, SourceState.ACTIVE} and not gate.allows_approval(now):
        raise InvalidSourceTransition("all onboarding evidence and 30 fixtures are required")
    return target
