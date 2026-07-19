"""Bounded compensation policy for transient real-provider failures."""

from datetime import datetime, timedelta
from typing import Literal

CompensationState = Literal["PENDING", "DEAD_LETTER", "NOT_ELIGIBLE"]

_TRANSIENT_CODES = {
    "PROVIDER_TIMEOUT",
    "PROVIDER_NETWORK_ERROR",
    "NETWORK_ERROR",
    "TRANSIENT_UNAVAILABLE",
}
_BACKOFF = (timedelta(minutes=5), timedelta(minutes=15), timedelta(minutes=45))
_MAX_WALL_CLOCK = timedelta(hours=2)


def compensation_plan(
    reason_code: str,
    *,
    attempt_count: int,
    started_at: datetime,
    now: datetime,
) -> tuple[CompensationState, datetime | None]:
    """Return a deterministic retry decision without mutating pipeline facts."""

    if started_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("compensation timestamps must include timezone")
    if attempt_count < 0:
        raise ValueError("compensation attempt_count cannot be negative")
    if reason_code not in _TRANSIENT_CODES:
        return "NOT_ELIGIBLE", None
    if attempt_count >= len(_BACKOFF) or now - started_at >= _MAX_WALL_CLOCK:
        return "DEAD_LETTER", None
    available_at = now + _BACKOFF[attempt_count]
    if available_at - started_at > _MAX_WALL_CLOCK:
        return "DEAD_LETTER", None
    return "PENDING", available_at
