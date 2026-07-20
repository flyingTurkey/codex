from datetime import UTC, datetime, timedelta

from srbg_api.intelligence_v2.ai_runtime import (
    AiAvailabilityFacts,
    project_ai_availability,
    summary_state_for_failure,
    summary_status_message,
)

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _healthy_facts(**overrides: object) -> AiAvailabilityFacts:
    values: dict[str, object] = {
        "configuration_active": True,
        "secret_configured": True,
        "provider": "deepseek",
        "configured_model": "deepseek-v4-flash",
        "worker_provider": "deepseek",
        "worker_model": "deepseek-v4-flash",
        "worker_heartbeat_at": NOW - timedelta(seconds=10),
        "queue_healthy": True,
        "budget_healthy": True,
        "last_approved_content_schema_success_at": NOW - timedelta(hours=1),
    }
    values.update(overrides)
    return AiAvailabilityFacts(**values)  # type: ignore[arg-type]


def test_configured_and_available_are_independent_and_require_real_content_success() -> None:
    configured_only = project_ai_availability(
        _healthy_facts(last_approved_content_schema_success_at=None), now=NOW
    )

    assert configured_only.configured is True
    assert configured_only.available is False
    assert configured_only.blocking_reasons == ("NO_RECENT_APPROVED_CONTENT_SCHEMA_SUCCESS",)

    available = project_ai_availability(_healthy_facts(), now=NOW)
    assert available.configured is True
    assert available.available is True
    assert available.blocking_reasons == ()


def test_availability_fails_closed_for_stale_heartbeat_config_mismatch_budget_or_queue() -> None:
    scenarios = (
        (
            {"worker_heartbeat_at": NOW - timedelta(seconds=61)},
            "WORKER_HEARTBEAT_STALE",
        ),
        ({"worker_model": "unapproved-model"}, "PROVIDER_CONFIG_MISMATCH"),
        ({"queue_healthy": False}, "QUEUE_UNAVAILABLE"),
        ({"budget_healthy": False}, "BUDGET_UNAVAILABLE"),
        (
            {"last_approved_content_schema_success_at": NOW - timedelta(hours=24, seconds=1)},
            "NO_RECENT_APPROVED_CONTENT_SCHEMA_SUCCESS",
        ),
    )

    for overrides, expected_reason in scenarios:
        view = project_ai_availability(_healthy_facts(**overrides), now=NOW)
        assert view.available is False
        assert expected_reason in view.blocking_reasons


def test_canary_or_probe_success_is_not_an_availability_input() -> None:
    facts = _healthy_facts(last_approved_content_schema_success_at=None)

    assert "canary" not in facts.__dataclass_fields__
    assert project_ai_availability(facts, now=NOW).available is False


def test_failure_mapping_and_all_seven_messages_are_deterministic() -> None:
    assert summary_state_for_failure("PROVIDER_TIMEOUT", retry_scheduled=True) == (
        "TEMPORARILY_UNAVAILABLE"
    )
    assert summary_state_for_failure("SUMMARY_SCHEMA_REJECTED", retry_scheduled=False) == (
        "SCHEMA_REJECTED"
    )
    assert summary_state_for_failure("CURRENT_ACTIVE_ACCEPTED_CLAIM_REQUIRED", False) == (
        "INSUFFICIENT_EVIDENCE"
    )
    assert summary_state_for_failure("AI_RUNTIME_AUTHORIZATION_DENIED", False) == ("NOT_GENERATED")

    states = {
        "NOT_GENERATED",
        "PROCESSING",
        "TEMPORARILY_UNAVAILABLE",
        "SCHEMA_REJECTED",
        "INSUFFICIENT_EVIDENCE",
        "SUCCEEDED",
        "STALE",
    }
    messages = {summary_status_message(state) for state in states}
    assert len(messages) == len(states)
    assert all(message.strip() for message in messages)
