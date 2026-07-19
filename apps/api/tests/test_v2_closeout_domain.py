from datetime import UTC, datetime, timedelta

import pytest
from srbg_api.intelligence_v2.closeout import (
    FeedInspection,
    QualificationInspection,
    RuntimeObservation,
    evaluate_feed,
    evaluate_qualification,
    evaluate_runtime_window,
)

START = datetime(2026, 7, 19, tzinfo=UTC)


def _runtime_observations() -> list[RuntimeObservation]:
    observations: list[RuntimeObservation] = []
    for minute in range(24 * 60 + 1):
        observed_at = START + timedelta(minutes=minute)
        observations.append(
            RuntimeObservation(
                observed_at=observed_at,
                worker_heartbeat_at=observed_at,
                queue_healthy=True,
                budget_healthy=True,
                last_real_schema_success_at=START + timedelta(hours=(minute // 360) * 6),
                external_balance_state="SUFFICIENT_AT_LAST_REAL_CALL",
            )
        )
    return observations


def test_runtime_window_requires_24_hours_five_real_successes_and_no_health_gap() -> None:
    result = evaluate_runtime_window(_runtime_observations(), acceptance_profile="production")
    assert result.passed is True
    assert result.real_schema_success_count == 5


def test_runtime_window_fails_closed_on_gap_or_unknown_balance() -> None:
    observations = _runtime_observations()
    observations.pop(100)
    assert "AI_RUNTIME_OBSERVATION_GAP" in evaluate_runtime_window(
        observations, acceptance_profile="production"
    ).reasons
    observations = _runtime_observations()
    observations[5] = observations[5].__class__(
        **(observations[5].__dict__ | {"external_balance_state": "UNKNOWN"})
    )
    assert "AI_EXTERNAL_BALANCE_UNKNOWN" in evaluate_runtime_window(
        observations, acceptance_profile="production"
    ).reasons


def test_engineering_runtime_requires_one_hour_and_one_real_schema_success() -> None:
    observations = _runtime_observations()[:61]
    result = evaluate_runtime_window(observations, acceptance_profile="engineering")
    assert result.passed is True
    assert result.real_schema_success_count == 1
    assert evaluate_runtime_window(
        observations, acceptance_profile="production"
    ).passed is False


def test_owner_gold_gates_precision_recall_and_locked_negative_leakage() -> None:
    values = [
        QualificationInspection(
            case_id=f"p-{index}",
            bucket="POSITIVE",
            expected_relevant=True,
            predicted_relevant=index < 90,
            locked_negative=False,
        )
        for index in range(100)
    ] + [
        QualificationInspection(
            case_id=f"n-{index}",
            bucket="NEGATIVE",
            expected_relevant=False,
            predicted_relevant=False,
            locked_negative=True,
        )
        for index in range(100)
    ]
    result = evaluate_qualification(values)
    assert result.precision_bps == 10_000
    assert result.recall_bps == 9_000
    assert result.passed is True
    values[-1] = values[-1].__class__(**(values[-1].__dict__ | {"predicted_relevant": True}))
    assert evaluate_qualification(values).passed is False


def test_feed_requires_200_items_98_percent_precision_and_zero_leakage() -> None:
    values = [
        FeedInspection(
            projection_id=f"event-{index}",
            owner_relevant=index < 196,
            risk_tier="R1",
            unaccepted_claims=0,
            unsupported_facts=0,
        )
        for index in range(200)
    ]
    assert evaluate_feed(values, acceptance_profile="production").passed is True
    assert evaluate_feed(values[:-1], acceptance_profile="production").reasons == (
        "FEED_SAMPLE_INSUFFICIENT",
    )
    values[0] = values[0].__class__(**(values[0].__dict__ | {"risk_tier": "R4"}))
    assert "FEED_R4_LEAKAGE" in evaluate_feed(
        values, acceptance_profile="production"
    ).reasons


def test_engineering_feed_uses_only_automatic_safety_invariants() -> None:
    values = [
        FeedInspection(
            projection_id=f"event-{index}",
            owner_relevant=None,
            risk_tier="R1",
            unaccepted_claims=0,
            unsupported_facts=0,
        )
        for index in range(200)
    ]
    result = evaluate_feed(values, acceptance_profile="engineering")
    assert result.passed is True
    assert result.precision_bps is None
    values[0] = values[0].__class__(
        **(values[0].__dict__ | {"unsupported_facts": 1})
    )
    assert "FEED_UNSUPPORTED_FACT_LEAKAGE" in evaluate_feed(
        values, acceptance_profile="engineering"
    ).reasons


def test_closeout_inputs_reject_duplicates() -> None:
    duplicate = QualificationInspection(
        case_id="same",
        bucket="BOUNDARY",
        expected_relevant=True,
        predicted_relevant=True,
        locked_negative=False,
    )
    with pytest.raises(ValueError, match="duplicate qualification case"):
        evaluate_qualification([duplicate, duplicate])
