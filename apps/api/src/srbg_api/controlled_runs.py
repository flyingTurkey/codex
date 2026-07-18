"""Pure fail-closed policy for durable personal controlled runs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit


class RunStopped(RuntimeError):
    """Raised before external I/O when controlled-run authority is unavailable."""


@dataclass(frozen=True, slots=True)
class ControlledRunLimits:
    request_limit: int
    byte_limit: int
    response_limit: int
    ai_cost_limit_microusd: int
    failure_limit: int
    failure_rate_bps: int
    failure_rate_min_samples: int


@dataclass(frozen=True, slots=True)
class ControlledRunSnapshot:
    state: str
    requests_reserved: int
    bytes_reserved: int
    bytes_settled: int
    attempts_settled: int
    attempts_failed: int
    ai_cost_reserved_microusd: int
    ai_cost_settled_microusd: int
    wall_deadline: datetime


@dataclass(frozen=True, slots=True)
class AttemptReservation:
    byte_allowance: int
    snapshot: ControlledRunSnapshot


def reserve_attempt(
    snapshot: ControlledRunSnapshot,
    limits: ControlledRunLimits,
    *,
    requested_max_bytes: int,
    now: datetime | None = None,
) -> AttemptReservation:
    observed_at = now or datetime.now(UTC)
    if snapshot.state != "RUNNING":
        raise RunStopped("CONTROLLED_RUN_NOT_RUNNING")
    if observed_at >= snapshot.wall_deadline:
        raise RunStopped("CONTROLLED_RUN_WALL_DEADLINE")
    if snapshot.requests_reserved >= limits.request_limit:
        raise RunStopped("CONTROLLED_RUN_REQUEST_LIMIT")
    remaining = limits.byte_limit - snapshot.bytes_settled - snapshot.bytes_reserved
    allowance = min(requested_max_bytes, limits.response_limit, remaining)
    if allowance <= 0:
        raise RunStopped("CONTROLLED_RUN_BYTE_LIMIT")
    updated = replace(
        snapshot,
        requests_reserved=snapshot.requests_reserved + 1,
        bytes_reserved=snapshot.bytes_reserved + allowance,
    )
    return AttemptReservation(allowance, updated)


def settle_attempt(
    snapshot: ControlledRunSnapshot,
    *,
    reserved_bytes: int,
    actual_bytes: int,
    failed: bool,
    limits: ControlledRunLimits,
) -> ControlledRunSnapshot:
    if actual_bytes < 0 or actual_bytes > reserved_bytes:
        raise ValueError("CONTROLLED_RUN_INVALID_BYTE_SETTLEMENT")
    settled = snapshot.attempts_settled + 1
    failures = snapshot.attempts_failed + int(failed)
    should_stop = failures >= limits.failure_limit or (
        settled >= limits.failure_rate_min_samples
        and failures * 10_000 >= settled * limits.failure_rate_bps
    )
    return replace(
        snapshot,
        state="STOPPING" if should_stop else snapshot.state,
        bytes_reserved=snapshot.bytes_reserved - reserved_bytes,
        bytes_settled=snapshot.bytes_settled + actual_bytes,
        attempts_settled=settled,
        attempts_failed=failures,
    )


def validate_acquisition_url(
    url: str, *, expected_host: str, path_prefix: str, allow_robots: bool
) -> None:
    if any(ord(character) < 32 or ord(character) == 127 for character in unquote(url)):
        raise ValueError("CONTROLLED_RUN_URL_OUTSIDE_BOUNDARY")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").casefold()
    normalized_prefix = path_prefix if path_prefix.endswith("/") else path_prefix + "/"
    path = parsed.path or "/"
    within_prefix = path == normalized_prefix[:-1] or path.startswith(normalized_prefix)
    robots = allow_robots and path == "/robots.txt" and not parsed.query
    if (
        parsed.scheme.casefold() != "https"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or host != expected_host.casefold()
        or not (within_prefix or robots)
    ):
        raise ValueError("CONTROLLED_RUN_URL_OUTSIDE_BOUNDARY")
