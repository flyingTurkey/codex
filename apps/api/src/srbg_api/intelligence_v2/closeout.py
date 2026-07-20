"""Pure, fail-closed evaluation rules for intelligence v2 acceptance evidence."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Literal

BalanceState = Literal["SUFFICIENT_AT_LAST_REAL_CALL", "INSUFFICIENT", "UNKNOWN"]
AcceptanceProfile = Literal["engineering", "production"]


@dataclass(frozen=True)
class RuntimeObservation:
    observed_at: datetime
    worker_heartbeat_at: datetime
    queue_healthy: bool
    budget_healthy: bool
    last_real_schema_success_at: datetime | None
    external_balance_state: BalanceState


@dataclass(frozen=True)
class RuntimeWindowResult:
    passed: bool
    reasons: tuple[str, ...]
    duration_seconds: int
    real_schema_success_count: int


def evaluate_runtime_window(
    values: list[RuntimeObservation], *, acceptance_profile: AcceptanceProfile
) -> RuntimeWindowResult:
    if not values:
        return RuntimeWindowResult(False, ("AI_RUNTIME_WINDOW_INCOMPLETE",), 0, 0)
    ordered = sorted(values, key=lambda value: value.observed_at)
    reasons: list[str] = []
    duration = ordered[-1].observed_at - ordered[0].observed_at
    minimum_duration = timedelta(hours=1 if acceptance_profile == "engineering" else 24)
    minimum_successes = 1 if acceptance_profile == "engineering" else 5
    if duration < minimum_duration:
        reasons.append("AI_RUNTIME_WINDOW_INCOMPLETE")
    if any(
        right.observed_at - left.observed_at > timedelta(seconds=90)
        for left, right in pairwise(ordered)
    ):
        reasons.append("AI_RUNTIME_OBSERVATION_GAP")
    if any(
        value.observed_at - value.worker_heartbeat_at > timedelta(seconds=60)
        or value.worker_heartbeat_at > value.observed_at
        for value in ordered
    ):
        reasons.append("AI_WORKER_HEARTBEAT_STALE")
    if any(not value.queue_healthy for value in ordered):
        reasons.append("AI_QUEUE_UNAVAILABLE")
    if any(not value.budget_healthy for value in ordered):
        reasons.append("AI_BUDGET_UNAVAILABLE")
    if any(value.external_balance_state == "INSUFFICIENT" for value in ordered):
        reasons.append("AI_EXTERNAL_BALANCE_INSUFFICIENT")
    if any(value.external_balance_state == "UNKNOWN" for value in ordered):
        reasons.append("AI_EXTERNAL_BALANCE_UNKNOWN")
    successes = {
        value.last_real_schema_success_at
        for value in ordered
        if value.last_real_schema_success_at is not None
    }
    if len(successes) < minimum_successes:
        reasons.append("AI_REAL_SCHEMA_SUCCESS_INSUFFICIENT")
    if any(
        value.last_real_schema_success_at is None
        or value.observed_at - value.last_real_schema_success_at >= timedelta(hours=24)
        or value.last_real_schema_success_at > value.observed_at
        for value in ordered
    ):
        reasons.append("AI_REAL_SCHEMA_SUCCESS_STALE")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return RuntimeWindowResult(
        not unique_reasons,
        unique_reasons,
        max(0, int(duration.total_seconds())),
        len(successes),
    )


@dataclass(frozen=True)
class QualificationInspection:
    case_id: str
    bucket: Literal["POSITIVE", "BOUNDARY", "NEGATIVE"]
    expected_relevant: bool
    predicted_relevant: bool
    locked_negative: bool


@dataclass(frozen=True)
class QualificationResult:
    passed: bool
    reasons: tuple[str, ...]
    precision_bps: int
    recall_bps: int
    locked_negative_leaks: int


def _basis_points(numerator: int, denominator: int) -> int:
    return 0 if denominator == 0 else numerator * 10_000 // denominator


def evaluate_qualification(values: list[QualificationInspection]) -> QualificationResult:
    identifiers = [value.case_id for value in values]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate qualification case")
    true_positive = sum(value.expected_relevant and value.predicted_relevant for value in values)
    predicted_positive = sum(value.predicted_relevant for value in values)
    expected_positive = sum(value.expected_relevant for value in values)
    precision = _basis_points(true_positive, predicted_positive)
    recall = _basis_points(true_positive, expected_positive)
    leaks = sum(
        value.locked_negative and value.predicted_relevant
        for value in values
    )
    reasons: list[str] = []
    if precision < 9_000:
        reasons.append("QUALIFICATION_PRECISION_FAILED")
    if recall < 9_000:
        reasons.append("QUALIFICATION_RECALL_FAILED")
    if leaks:
        reasons.append("LOCKED_NEGATIVE_LEAKAGE")
    return QualificationResult(not reasons, tuple(reasons), precision, recall, leaks)


@dataclass(frozen=True)
class FeedInspection:
    projection_id: str
    owner_relevant: bool | None
    risk_tier: Literal["R1", "R2", "R3", "R4"]
    unaccepted_claims: int
    unsupported_facts: int


@dataclass(frozen=True)
class FeedResult:
    passed: bool
    reasons: tuple[str, ...]
    precision_bps: int | None


def evaluate_feed(
    values: list[FeedInspection], *, acceptance_profile: AcceptanceProfile
) -> FeedResult:
    if len(values) < 200:
        return FeedResult(False, ("FEED_SAMPLE_INSUFFICIENT",), None)
    identifiers = [value.projection_id for value in values]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate feed projection")
    precision = (
        _basis_points(sum(value.owner_relevant is True for value in values), len(values))
        if acceptance_profile == "production"
        else None
    )
    reasons: list[str] = []
    if precision is not None and precision < 9_800:
        reasons.append("FEED_PRECISION_FAILED")
    if any(value.risk_tier == "R4" for value in values):
        reasons.append("FEED_R4_LEAKAGE")
    if any(value.unaccepted_claims for value in values):
        reasons.append("FEED_UNACCEPTED_CLAIM_LEAKAGE")
    if any(value.unsupported_facts for value in values):
        reasons.append("FEED_UNSUPPORTED_FACT_LEAKAGE")
    return FeedResult(not reasons, tuple(reasons), precision)


@dataclass(frozen=True)
class CompensationInspection:
    injected_transient_count: int
    recovered_count: int
    injected_permanent_count: int
    permanent_error_observed_count: int
    duplicate_side_effects: int
    stale_version_recoveries: int
    permanent_error_retries: int


@dataclass(frozen=True)
class CompensationResult:
    passed: bool
    reasons: tuple[str, ...]


def evaluate_compensation(value: CompensationInspection) -> CompensationResult:
    reasons: list[str] = []
    if value.injected_transient_count < 1 or value.injected_permanent_count < 1:
        reasons.append("AI_COMPENSATION_NOT_EXERCISED")
    if value.recovered_count != value.injected_transient_count:
        reasons.append("AI_COMPENSATION_BACKLOG_INCOMPLETE")
    if value.permanent_error_observed_count != value.injected_permanent_count:
        reasons.append("AI_PERMANENT_ERROR_EVIDENCE_INCOMPLETE")
    if value.duplicate_side_effects:
        reasons.append("AI_COMPENSATION_DUPLICATE_SIDE_EFFECT")
    if value.stale_version_recoveries:
        reasons.append("AI_COMPENSATION_STALE_VERSION_RECOVERY")
    if value.permanent_error_retries:
        reasons.append("AI_PERMANENT_ERROR_RETRIED")
    return CompensationResult(not reasons, tuple(reasons))
