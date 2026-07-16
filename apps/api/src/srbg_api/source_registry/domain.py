"""Pure source lifecycle and activation gate rules."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from srbg_contracts import (
    RuntimeAuthorization,
    SourceLifecycleState,
    SourceState,
    SourceTrialKind,
)


class InvalidSourceTransition(ValueError):
    """Raised when a transition skips state or lacks authoritative evidence."""


class InvalidLifecycleCommand(ValueError):
    """Raised when a V2 command cannot pass the server-owned governance gate."""


class LifecycleCommand(StrEnum):
    SUBMIT_COMPLIANCE = "SUBMIT_COMPLIANCE"
    START_FIXTURE_TRIAL = "START_FIXTURE_TRIAL"
    START_LIVE_TRIAL = "START_LIVE_TRIAL"
    APPROVE_PRODUCTION = "APPROVE_PRODUCTION"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    RETIRE = "RETIRE"


@dataclass(frozen=True, slots=True)
class LifecycleGate:
    """Only authoritative, persisted facts used to calculate source authorization."""

    policy_valid: bool
    policy_valid_until: datetime | None
    robots_allowed: bool
    terms_allowed: bool
    copyright_allowed: bool
    governance_owner_present: bool
    compliance_approved: bool
    connector_config_current: bool
    trial_kind: SourceTrialKind | None
    live_trial_succeeded: bool
    production_approval_current: bool
    separation_actor_ids: frozenset[UUID]
    current_trial_pending: bool = False

    def policy_is_current(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return bool(
            self.policy_valid
            and self.policy_valid_until is not None
            and self.policy_valid_until > current
            and self.robots_allowed
            and self.terms_allowed
            and self.copyright_allowed
        )

    def allows_trial(self, now: datetime | None = None) -> bool:
        return bool(
            self.policy_is_current(now)
            and self.governance_owner_present
            and self.compliance_approved
            and self.connector_config_current
        )

    def allows_production(self, now: datetime | None = None) -> bool:
        return bool(
            self.allows_trial(now)
            and self.trial_kind is SourceTrialKind.LIVE_TRIAL
            and self.live_trial_succeeded
            and self.production_approval_current
        )


_LIFECYCLE_TARGETS: dict[
    tuple[SourceLifecycleState, LifecycleCommand], SourceLifecycleState
] = {
    (
        SourceLifecycleState.CANDIDATE,
        LifecycleCommand.SUBMIT_COMPLIANCE,
    ): SourceLifecycleState.COMPLIANCE_REVIEW,
    (
        SourceLifecycleState.COMPLIANCE_REVIEW,
        LifecycleCommand.START_FIXTURE_TRIAL,
    ): SourceLifecycleState.TRIAL,
    (
        SourceLifecycleState.COMPLIANCE_REVIEW,
        LifecycleCommand.START_LIVE_TRIAL,
    ): SourceLifecycleState.TRIAL,
    (
        SourceLifecycleState.TRIAL,
        LifecycleCommand.START_FIXTURE_TRIAL,
    ): SourceLifecycleState.TRIAL,
    (
        SourceLifecycleState.TRIAL,
        LifecycleCommand.START_LIVE_TRIAL,
    ): SourceLifecycleState.TRIAL,
    (
        SourceLifecycleState.PAUSED,
        LifecycleCommand.START_FIXTURE_TRIAL,
    ): SourceLifecycleState.TRIAL,
    (
        SourceLifecycleState.PAUSED,
        LifecycleCommand.START_LIVE_TRIAL,
    ): SourceLifecycleState.TRIAL,
    (
        SourceLifecycleState.TRIAL,
        LifecycleCommand.APPROVE_PRODUCTION,
    ): SourceLifecycleState.ACTIVE,
    (SourceLifecycleState.ACTIVE, LifecycleCommand.PAUSE): SourceLifecycleState.PAUSED,
    (SourceLifecycleState.PAUSED, LifecycleCommand.RESUME): SourceLifecycleState.ACTIVE,
    (SourceLifecycleState.CANDIDATE, LifecycleCommand.RETIRE): SourceLifecycleState.RETIRED,
    (
        SourceLifecycleState.COMPLIANCE_REVIEW,
        LifecycleCommand.RETIRE,
    ): SourceLifecycleState.RETIRED,
    (SourceLifecycleState.TRIAL, LifecycleCommand.RETIRE): SourceLifecycleState.RETIRED,
    (SourceLifecycleState.PAUSED, LifecycleCommand.RETIRE): SourceLifecycleState.RETIRED,
}


def lifecycle_transition(
    current: SourceLifecycleState,
    command: LifecycleCommand,
    gate: LifecycleGate,
    *,
    actor_id: UUID,
    now: datetime | None = None,
) -> SourceLifecycleState:
    """Calculate a lifecycle transition without trusting a client-provided target state."""

    target = _LIFECYCLE_TARGETS.get((current, command))
    if target is None:
        raise InvalidLifecycleCommand(
            f"invalid lifecycle command: {command.value} from {current.value}"
        )
    if command in {LifecycleCommand.START_FIXTURE_TRIAL, LifecycleCommand.START_LIVE_TRIAL}:
        if current is SourceLifecycleState.TRIAL and gate.current_trial_pending:
            raise InvalidLifecycleCommand("the current source trial is still pending")
        if not gate.allows_trial(now):
            raise InvalidLifecycleCommand("current policy and compliance approval are required")
    if command in {LifecycleCommand.APPROVE_PRODUCTION, LifecycleCommand.RESUME}:
        if gate.trial_kind is not SourceTrialKind.LIVE_TRIAL:
            raise InvalidLifecycleCommand("a successful live trial is required")
        if not gate.allows_production(now):
            raise InvalidLifecycleCommand("production governance evidence is incomplete or expired")
    if command is LifecycleCommand.APPROVE_PRODUCTION and actor_id in gate.separation_actor_ids:
        raise InvalidLifecycleCommand("approval violates separation of duties")
    return target


def runtime_authorization(
    state: SourceLifecycleState,
    gate: LifecycleGate,
    now: datetime | None = None,
) -> RuntimeAuthorization:
    """Derive runtime authorization exclusively from lifecycle plus current evidence."""

    if state is SourceLifecycleState.ACTIVE and gate.allows_production(now):
        return RuntimeAuthorization.PRODUCTION
    if (
        state is SourceLifecycleState.TRIAL
        and gate.trial_kind in {SourceTrialKind.FIXTURE_REPLAY, SourceTrialKind.LIVE_TRIAL}
        and gate.allows_trial(now)
    ):
        return RuntimeAuthorization.TRIAL_ONLY
    return RuntimeAuthorization.DENIED


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
