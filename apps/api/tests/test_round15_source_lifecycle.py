from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from srbg_api.source_registry.domain import (
    InvalidLifecycleCommand,
    LifecycleCommand,
    LifecycleGate,
    lifecycle_transition,
    runtime_authorization,
)
from srbg_api.source_registry.service import _available_actions
from srbg_contracts import (
    RuntimeAuthorization,
    SourceLifecycleAction,
    SourceLifecycleState,
    SourceTrialKind,
)

ACTOR = UUID("019b1500-0000-7000-8000-000000009001")
CREATOR = UUID("019b1500-0000-7000-8000-000000009002")


def _gate(**overrides: object) -> LifecycleGate:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "policy_valid": True,
        "policy_valid_until": now + timedelta(days=30),
        "robots_allowed": True,
        "terms_allowed": True,
        "copyright_allowed": True,
        "governance_owner_present": True,
        "compliance_approved": True,
        "connector_config_current": True,
        "trial_kind": SourceTrialKind.LIVE_TRIAL,
        "live_trial_succeeded": True,
        "production_approval_current": True,
        "separation_actor_ids": frozenset({CREATOR}),
    }
    values.update(overrides)
    return LifecycleGate(**values)  # type: ignore[arg-type]


def test_round15_state_machine_exposes_only_command_transitions() -> None:
    assert lifecycle_transition(
        SourceLifecycleState.CANDIDATE,
        LifecycleCommand.SUBMIT_COMPLIANCE,
        _gate(),
        actor_id=ACTOR,
    ) is SourceLifecycleState.COMPLIANCE_REVIEW
    assert lifecycle_transition(
        SourceLifecycleState.COMPLIANCE_REVIEW,
        LifecycleCommand.START_LIVE_TRIAL,
        _gate(),
        actor_id=ACTOR,
    ) is SourceLifecycleState.TRIAL
    assert lifecycle_transition(
        SourceLifecycleState.TRIAL,
        LifecycleCommand.START_LIVE_TRIAL,
        _gate(),
        actor_id=ACTOR,
    ) is SourceLifecycleState.TRIAL
    assert lifecycle_transition(
        SourceLifecycleState.TRIAL,
        LifecycleCommand.APPROVE_PRODUCTION,
        _gate(),
        actor_id=ACTOR,
    ) is SourceLifecycleState.ACTIVE
    assert lifecycle_transition(
        SourceLifecycleState.ACTIVE,
        LifecycleCommand.PAUSE,
        _gate(),
        actor_id=ACTOR,
    ) is SourceLifecycleState.PAUSED
    assert lifecycle_transition(
        SourceLifecycleState.PAUSED,
        LifecycleCommand.RESUME,
        _gate(),
        actor_id=ACTOR,
    ) is SourceLifecycleState.ACTIVE
    assert lifecycle_transition(
        SourceLifecycleState.PAUSED,
        LifecycleCommand.RETIRE,
        _gate(),
        actor_id=ACTOR,
    ) is SourceLifecycleState.RETIRED


@pytest.mark.parametrize(
    ("state", "command"),
    [
        (SourceLifecycleState.CANDIDATE, LifecycleCommand.APPROVE_PRODUCTION),
        (SourceLifecycleState.ACTIVE, LifecycleCommand.RETIRE),
        (SourceLifecycleState.RETIRED, LifecycleCommand.RESUME),
        (SourceLifecycleState.TRIAL, LifecycleCommand.SUBMIT_COMPLIANCE),
    ],
)
def test_illegal_or_terminal_transitions_are_rejected(
    state: SourceLifecycleState, command: LifecycleCommand
) -> None:
    with pytest.raises(InvalidLifecycleCommand):
        lifecycle_transition(state, command, _gate(), actor_id=ACTOR)


@pytest.mark.parametrize(
    "override",
    [
        {"policy_valid": False},
        {"policy_valid_until": datetime.now(UTC) - timedelta(seconds=1)},
        {"robots_allowed": False},
        {"terms_allowed": False},
        {"copyright_allowed": False},
        {"governance_owner_present": False},
        {"compliance_approved": False},
        {"connector_config_current": False},
        {"live_trial_succeeded": False},
        {"production_approval_current": False},
    ],
)
def test_production_approval_is_default_deny(override: dict[str, object]) -> None:
    with pytest.raises(InvalidLifecycleCommand):
        lifecycle_transition(
            SourceLifecycleState.TRIAL,
            LifecycleCommand.APPROVE_PRODUCTION,
            _gate(**override),
            actor_id=ACTOR,
        )


def test_fixture_trial_and_self_approval_never_grant_production() -> None:
    fixture = _gate(trial_kind=SourceTrialKind.FIXTURE_REPLAY)
    with pytest.raises(InvalidLifecycleCommand, match="live trial"):
        lifecycle_transition(
            SourceLifecycleState.TRIAL,
            LifecycleCommand.APPROVE_PRODUCTION,
            fixture,
            actor_id=ACTOR,
        )

    with pytest.raises(InvalidLifecycleCommand, match="separation"):
        lifecycle_transition(
            SourceLifecycleState.TRIAL,
            LifecycleCommand.APPROVE_PRODUCTION,
            _gate(),
            actor_id=CREATOR,
        )


def test_runtime_authorization_is_server_derived_and_expires_closed() -> None:
    assert (
        runtime_authorization(SourceLifecycleState.TRIAL, _gate())
        is RuntimeAuthorization.TRIAL_ONLY
    )
    assert (
        runtime_authorization(SourceLifecycleState.ACTIVE, _gate())
        is RuntimeAuthorization.PRODUCTION
    )
    assert (
        runtime_authorization(SourceLifecycleState.ACTIVE, _gate(policy_valid=False))
        is RuntimeAuthorization.DENIED
    )
    assert (
        runtime_authorization(SourceLifecycleState.PAUSED, _gate())
        is RuntimeAuthorization.DENIED
    )
    assert (
        runtime_authorization(SourceLifecycleState.TRIAL, _gate(trial_kind=None))
        is RuntimeAuthorization.DENIED
    )


def test_trial_state_keeps_server_authorized_retry_actions_after_fixture_completion() -> None:
    actions = _available_actions(
        SourceLifecycleState.TRIAL,
        _gate(
            trial_kind=SourceTrialKind.FIXTURE_REPLAY,
            live_trial_succeeded=False,
            production_approval_current=False,
        ),
    )

    assert SourceLifecycleAction.START_FIXTURE_TRIAL in actions
    assert SourceLifecycleAction.START_LIVE_TRIAL in actions
    assert SourceLifecycleAction.APPROVE_PRODUCTION not in actions


def test_pending_trial_cannot_be_silently_replaced_by_another_run() -> None:
    gate = _gate(
        current_trial_pending=True,
        trial_kind=SourceTrialKind.FIXTURE_REPLAY,
        live_trial_succeeded=False,
        production_approval_current=False,
    )

    actions = _available_actions(SourceLifecycleState.TRIAL, gate)
    assert SourceLifecycleAction.START_FIXTURE_TRIAL not in actions
    assert SourceLifecycleAction.START_LIVE_TRIAL not in actions
    with pytest.raises(InvalidLifecycleCommand, match="pending"):
        lifecycle_transition(
            SourceLifecycleState.TRIAL,
            LifecycleCommand.START_FIXTURE_TRIAL,
            gate,
            actor_id=ACTOR,
        )
