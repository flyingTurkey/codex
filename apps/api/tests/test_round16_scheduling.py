from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from srbg_api.scheduling.domain import (
    FetchFailure,
    HealthObservation,
    SchedulePolicy,
    build_fetch_message,
    classify_failure,
    evaluate_health,
    next_backoff,
)

SOURCE_ID = UUID("019b1600-0000-7000-8000-000000000001")
RUN_ID = UUID("019b1600-0000-7000-8000-000000000002")


def test_worker_message_contains_only_authoritative_ids() -> None:
    message = build_fetch_message(source_id=SOURCE_ID, run_id=RUN_ID)
    assert message == {"source_id": str(SOURCE_ID), "run_id": str(RUN_ID)}
    assert not ({"body", "url", "token", "cookie", "credential_ref"} & message.keys())


@pytest.mark.parametrize(
    ("failure", "code", "retryable", "counts_for_circuit"),
    [
        (FetchFailure(http_status=304), "NOT_MODIFIED", False, False),
        (FetchFailure(http_status=429, retry_after_seconds=90), "RATE_LIMITED", True, False),
        (FetchFailure(http_status=503), "HTTP_5XX", True, True),
        (FetchFailure(kind="TIMEOUT"), "TIMEOUT", True, True),
        (FetchFailure(kind="DNS"), "DNS", True, True),
        (FetchFailure(kind="PARSE"), "PARSE_FAILED", False, True),
        (FetchFailure(kind="OBJECT_STORAGE"), "OBJECT_STORAGE_FAILED", True, True),
        (FetchFailure(kind="DATABASE"), "DATABASE_FAILED", True, True),
    ],
)
def test_failure_classification_is_bounded(
    failure: FetchFailure, code: str, retryable: bool, counts_for_circuit: bool
) -> None:
    result = classify_failure(failure)
    assert (result.code, result.retryable, result.counts_for_circuit) == (
        code,
        retryable,
        counts_for_circuit,
    )


def test_exponential_backoff_uses_injected_full_jitter_and_caps_retry_after() -> None:
    policy = SchedulePolicy(backoff_base_seconds=30, backoff_cap_seconds=3600, max_attempts=3)
    assert next_backoff(policy, attempt=1, random_fraction=lambda: 0.5) == timedelta(seconds=15)
    assert next_backoff(policy, attempt=3, random_fraction=lambda: 1.0) == timedelta(seconds=120)
    assert next_backoff(
        policy,
        attempt=2,
        random_fraction=lambda: 0.1,
        retry_after_seconds=99999,
    ) == timedelta(seconds=3600)
    assert next_backoff(policy, attempt=4, random_fraction=lambda: 0.5) is None


def test_health_separates_transport_discovery_parse_quality_and_freshness() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    result = evaluate_health(
        HealthObservation(
            transport_succeeded=True,
            consecutive_zero_discovery=3,
            latest_published_at=now - timedelta(hours=25),
            freshness_slo_seconds=86400,
            body_length_ratio=0.4,
            required_field_ratio=0.90,
            dom_fingerprint_changed=True,
            duplicate_ratio=0.90,
            oldest_queue_age_seconds=90000,
        ),
        observed_at=now,
    )
    assert result.transport_status == "SUCCEEDED"
    assert result.discovery_status == "FALSE_SUCCESS"
    assert result.parse_status == "DEGRADED"
    assert result.quality_status == "DEGRADED"
    assert result.freshness_status == "VIOLATED"
    assert set(result.anomaly_codes) == {
        "ZERO_DISCOVERY_STREAK",
        "LATEST_PUBLICATION_STALLED",
        "BODY_LENGTH_SHIFT",
        "REQUIRED_FIELDS_MISSING",
        "DOM_FINGERPRINT_CHANGED",
        "DUPLICATE_RATIO_HIGH",
        "QUEUE_BACKLOG_STALE",
    }
