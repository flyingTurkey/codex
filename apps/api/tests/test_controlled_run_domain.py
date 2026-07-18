from datetime import UTC, datetime, timedelta

import pytest
from srbg_api.controlled_runs import (
    ControlledRunLimits,
    ControlledRunSnapshot,
    RunStopped,
    reserve_attempt,
    settle_attempt,
    validate_acquisition_url,
)

LIMITS = ControlledRunLimits(
    request_limit=80,
    byte_limit=150 * 1024 * 1024,
    response_limit=50 * 1024 * 1024,
    ai_cost_limit_microusd=1_250_000,
    failure_limit=10,
    failure_rate_bps=3_000,
    failure_rate_min_samples=10,
)


def _snapshot(**overrides: object) -> ControlledRunSnapshot:
    values: dict[str, object] = {
        "state": "RUNNING",
        "requests_reserved": 0,
        "bytes_reserved": 0,
        "bytes_settled": 0,
        "attempts_settled": 0,
        "attempts_failed": 0,
        "ai_cost_reserved_microusd": 0,
        "ai_cost_settled_microusd": 0,
        "wall_deadline": datetime.now(UTC) + timedelta(hours=4),
    }
    values.update(overrides)
    return ControlledRunSnapshot(**values)  # type: ignore[arg-type]


def test_request_81_is_rejected_before_transport() -> None:
    with pytest.raises(RunStopped, match="REQUEST_LIMIT"):
        reserve_attempt(_snapshot(requests_reserved=80), LIMITS, requested_max_bytes=1)


def test_byte_allowance_is_reserved_and_unused_capacity_is_released() -> None:
    reservation = reserve_attempt(_snapshot(), LIMITS, requested_max_bytes=60 * 1024 * 1024)
    assert reservation.byte_allowance == 50 * 1024 * 1024
    settled = settle_attempt(
        reservation.snapshot,
        reserved_bytes=reservation.byte_allowance,
        actual_bytes=1024,
        failed=False,
        limits=LIMITS,
    )
    assert settled.bytes_reserved == 0
    assert settled.bytes_settled == 1024


def test_failure_rate_only_stops_from_tenth_settled_attempt() -> None:
    ninth = _snapshot(attempts_settled=8, attempts_failed=2)
    assert (
        settle_attempt(ninth, reserved_bytes=0, actual_bytes=0, failed=True, limits=LIMITS).state
        == "RUNNING"
    )
    tenth = _snapshot(attempts_settled=9, attempts_failed=2)
    assert (
        settle_attempt(tenth, reserved_bytes=0, actual_bytes=0, failed=True, limits=LIMITS).state
        == "STOPPING"
    )


def test_exact_path_prefix_allows_robots_but_rejects_sibling_content() -> None:
    validate_acquisition_url(
        "https://www.mem.gov.cn/robots.txt",
        expected_host="www.mem.gov.cn",
        path_prefix="/gk/sgcc/tbzdsgdcbg/",
        allow_robots=True,
    )
    with pytest.raises(ValueError, match="CONTROLLED_RUN_URL_OUTSIDE_BOUNDARY"):
        validate_acquisition_url(
            "https://www.mem.gov.cn/gk/other/page.html",
            expected_host="www.mem.gov.cn",
            path_prefix="/gk/sgcc/tbzdsgdcbg/",
            allow_robots=False,
        )
