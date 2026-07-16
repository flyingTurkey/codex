from datetime import UTC, datetime, timedelta

from srbg_api.operations.round17 import (
    PilotReadinessFacts,
    PilotSourceReadiness,
    WindowChangeKind,
    evaluate_window_readiness,
    reset_scope_for_change,
)


def _source(index: int, now: datetime) -> PilotSourceReadiness:
    return PilotSourceReadiness(
        source_code=f"GOV-{index:03d}",
        lifecycle_state="ACTIVE",
        policy_approved=True,
        approval_valid_until=now + timedelta(days=30),
        connector_current=True,
        live_trial_succeeded=True,
        production_approval_current=True,
        schedule_active=True,
        eventization_pipeline_ready=True,
        execution_domain="PRODUCTION",
    )


def test_t0_requires_server_authoritative_twenty_source_facts() -> None:
    now = datetime(2026, 7, 16, 9, tzinfo=UTC)
    facts = PilotReadinessFacts(
        sources=tuple(_source(index, now) for index in range(1, 21)),
        controlled_oidc_actor_count=3,
        local_identity_count=0,
        gold_release_frozen=True,
        metric_definition_frozen=True,
        ai_enabled=False,
        semantic_search_enabled=False,
        external_notifications_enabled=False,
    )

    result = evaluate_window_readiness(facts, starts_at=now, duration_hours=168)

    assert result.blocker_codes == ()
    assert result.ends_at == now + timedelta(hours=168)


def test_t0_fails_closed_for_missing_expired_or_nonproduction_evidence() -> None:
    now = datetime(2026, 7, 16, 9, tzinfo=UTC)
    sources = [_source(index, now) for index in range(1, 21)]
    sources[0] = PilotSourceReadiness(
        **(
            sources[0].as_dict()
            | {"approval_valid_until": now + timedelta(hours=167)}
        )
    )
    sources[1] = PilotSourceReadiness(
        **(sources[1].as_dict() | {"execution_domain": "TRIAL"})
    )
    sources[2] = PilotSourceReadiness(
        **(sources[2].as_dict() | {"eventization_pipeline_ready": False})
    )
    facts = PilotReadinessFacts(
        sources=tuple(sources),
        controlled_oidc_actor_count=2,
        local_identity_count=1,
        gold_release_frozen=False,
        metric_definition_frozen=True,
        ai_enabled=True,
        semantic_search_enabled=False,
        external_notifications_enabled=False,
    )

    result = evaluate_window_readiness(facts, starts_at=now, duration_hours=168)

    assert set(result.blocker_codes) >= {
        "SOURCE_APPROVAL_DOES_NOT_COVER_WINDOW",
        "NON_PRODUCTION_SOURCE_EVIDENCE",
        "SOURCE_EVENTIZATION_PIPELINE_NOT_READY",
        "CONTROLLED_OIDC_IDENTITIES_MISSING",
        "LOCAL_IDENTITY_PRESENT",
        "GOLD_RELEASE_NOT_FROZEN",
        "MODEL_EXECUTION_ENABLED",
    }


def test_t0_requires_eventization_readiness_for_each_of_exactly_twenty_sources() -> None:
    now = datetime(2026, 7, 16, 9, tzinfo=UTC)
    sources = [_source(index, now) for index in range(1, 21)]
    sources[-1] = PilotSourceReadiness(
        **(sources[-1].as_dict() | {"eventization_pipeline_ready": False})
    )
    facts = PilotReadinessFacts(
        sources=tuple(sources),
        controlled_oidc_actor_count=3,
        local_identity_count=0,
        gold_release_frozen=True,
        metric_definition_frozen=True,
        ai_enabled=False,
        semantic_search_enabled=False,
        external_notifications_enabled=False,
    )

    result = evaluate_window_readiness(facts, starts_at=now, duration_hours=168)

    assert "SOURCE_EVENTIZATION_PIPELINE_NOT_READY" in result.blocker_codes


def test_window_reset_scope_is_versioned_and_never_silent() -> None:
    assert reset_scope_for_change(WindowChangeKind.ROSTER) == "FULL_WINDOW"
    assert reset_scope_for_change(WindowChangeKind.METRIC_DEFINITION) == "FULL_WINDOW"
    assert reset_scope_for_change(WindowChangeKind.PUBLICATION_ACL) == "FULL_WINDOW"
    assert reset_scope_for_change(WindowChangeKind.SHARED_EXECUTOR) == "FULL_WINDOW"
    assert reset_scope_for_change(WindowChangeKind.SOURCE_CONNECTOR) == "SOURCE_WINDOW"
    assert reset_scope_for_change(WindowChangeKind.SOURCE_DOM) == "SOURCE_WINDOW"
    assert reset_scope_for_change(WindowChangeKind.RUNTIME_FAILURE) == "NO_RESET"
    assert reset_scope_for_change(WindowChangeKind.DOCUMENTATION) == "NO_RESET"
