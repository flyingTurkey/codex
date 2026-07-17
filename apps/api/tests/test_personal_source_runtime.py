from datetime import UTC, datetime, timedelta

from srbg_api.scheduling.domain import (
    AdaptiveScheduleInput,
    calculate_adaptive_interval,
)

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def test_new_stream_defaults_to_one_hour_with_neutral_jitter() -> None:
    result = calculate_adaptive_interval(
        AdaptiveScheduleInput(
            content_update_times=(),
            current_interval_seconds=3600,
            new_content_count=0,
            zero_update_streak=0,
        ),
        random_fraction=lambda: 0.5,
    )

    assert result.interval_seconds == 5400
    assert result.zero_update_streak == 1


def test_recent_twenty_updates_use_median_quarter_and_accelerate() -> None:
    updates = tuple(NOW - timedelta(hours=hour) for hour in range(0, 40, 2))

    result = calculate_adaptive_interval(
        AdaptiveScheduleInput(
            content_update_times=updates,
            current_interval_seconds=3600,
            new_content_count=1,
            zero_update_streak=4,
        ),
        random_fraction=lambda: 0.5,
    )

    assert result.interval_seconds == 1440
    assert result.zero_update_streak == 0


def test_adaptive_interval_enforces_final_bounds_after_jitter() -> None:
    fast = calculate_adaptive_interval(
        AdaptiveScheduleInput(
            content_update_times=(NOW, NOW - timedelta(minutes=1)),
            current_interval_seconds=900,
            new_content_count=1,
            zero_update_streak=0,
        ),
        random_fraction=lambda: 0.0,
    )
    slow = calculate_adaptive_interval(
        AdaptiveScheduleInput(
            content_update_times=(NOW, NOW - timedelta(days=100)),
            current_interval_seconds=86400,
            new_content_count=0,
            zero_update_streak=10,
        ),
        random_fraction=lambda: 1.0,
    )

    assert fast.interval_seconds == 900
    assert slow.interval_seconds == 86400
