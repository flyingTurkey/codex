from datetime import UTC, datetime, timedelta

from srbg_api.intelligence_v2.compensation import compensation_plan

NOW = datetime(2026, 7, 19, tzinfo=UTC)


def test_transient_failures_have_bounded_five_fifteen_forty_five_minute_backoff() -> None:
    assert compensation_plan("PROVIDER_TIMEOUT", attempt_count=0, started_at=NOW, now=NOW) == (
        "PENDING",
        NOW + timedelta(minutes=5),
    )
    assert compensation_plan(
        "PROVIDER_NETWORK_ERROR", attempt_count=1, started_at=NOW, now=NOW
    ) == ("PENDING", NOW + timedelta(minutes=15))
    assert compensation_plan(
        "TRANSIENT_UNAVAILABLE", attempt_count=2, started_at=NOW, now=NOW
    ) == ("PENDING", NOW + timedelta(minutes=45))
    assert compensation_plan(
        "PROVIDER_TIMEOUT", attempt_count=3, started_at=NOW, now=NOW
    ) == ("DEAD_LETTER", None)


def test_permanent_errors_and_two_hour_wall_clock_never_retry() -> None:
    for code in (
        "PROVIDER_BALANCE_INSUFFICIENT",
        "SCHEMA_REJECTED",
        "PROMPT_INJECTION_DETECTED",
        "MODEL_DISABLED",
        "PROVIDER_REQUEST_REJECTED",
    ):
        assert compensation_plan(code, attempt_count=0, started_at=NOW, now=NOW) == (
            "NOT_ELIGIBLE",
            None,
        )
    assert compensation_plan(
        "PROVIDER_TIMEOUT",
        attempt_count=0,
        started_at=NOW,
        now=NOW + timedelta(hours=2),
    ) == ("DEAD_LETTER", None)
