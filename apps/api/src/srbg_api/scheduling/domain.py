"""Pure scheduling, retry and source-health rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SchedulePolicy:
    backoff_base_seconds: int = 30
    backoff_cap_seconds: int = 21600
    max_attempts: int = 3


@dataclass(frozen=True, slots=True)
class FetchFailure:
    kind: str | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class FailureClassification:
    code: str
    retryable: bool
    counts_for_circuit: bool


@dataclass(frozen=True, slots=True)
class HealthObservation:
    transport_succeeded: bool
    consecutive_zero_discovery: int = 0
    latest_published_at: datetime | None = None
    freshness_slo_seconds: int = 86400
    body_length_ratio: float | None = None
    required_field_ratio: float = 1.0
    dom_fingerprint_changed: bool = False
    duplicate_ratio: float = 0.0
    oldest_queue_age_seconds: int = 0
    discovery_body_bytes: int = 0
    structure_fingerprint_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class HealthEvaluation:
    transport_status: str
    discovery_status: str
    parse_status: str
    quality_status: str
    freshness_status: str
    anomaly_codes: tuple[str, ...]


def build_fetch_message(*, source_id: UUID, run_id: UUID) -> dict[str, str]:
    return {"source_id": str(source_id), "run_id": str(run_id)}


def classify_failure(failure: FetchFailure) -> FailureClassification:
    if failure.http_status == 304:
        return FailureClassification("NOT_MODIFIED", False, False)
    if failure.http_status == 429:
        return FailureClassification("RATE_LIMITED", True, False)
    if failure.http_status is not None and 500 <= failure.http_status <= 599:
        return FailureClassification("HTTP_5XX", True, True)
    kinds = {
        "TIMEOUT": "TIMEOUT",
        "DNS": "DNS",
        "PARSE": "PARSE_FAILED",
        "OBJECT_STORAGE": "OBJECT_STORAGE_FAILED",
        "DATABASE": "DATABASE_FAILED",
    }
    code = kinds.get(failure.kind or "", "UNKNOWN")
    return FailureClassification(code, code != "UNKNOWN", code != "UNKNOWN")


def next_backoff(
    policy: SchedulePolicy,
    *,
    attempt: int,
    random_fraction: Callable[[], float],
    retry_after_seconds: int | None = None,
) -> timedelta | None:
    if attempt > policy.max_attempts:
        return None
    if retry_after_seconds is not None:
        seconds = min(max(0, retry_after_seconds), policy.backoff_cap_seconds)
    else:
        ceiling = min(
            policy.backoff_cap_seconds,
            policy.backoff_base_seconds * (2 ** max(0, attempt - 1)),
        )
        seconds = int(ceiling * min(1.0, max(0.0, random_fraction())))
    return timedelta(seconds=seconds)


def evaluate_health(observation: HealthObservation, *, observed_at: datetime) -> HealthEvaluation:
    anomalies: list[str] = []
    if observation.consecutive_zero_discovery >= 3:
        anomalies.append("ZERO_DISCOVERY_STREAK")
    freshness_violated = (
        observation.latest_published_at is not None
        and (observed_at - observation.latest_published_at).total_seconds()
        > observation.freshness_slo_seconds
    )
    if freshness_violated:
        anomalies.append("LATEST_PUBLICATION_STALLED")
    if observation.body_length_ratio is not None and not 0.5 <= observation.body_length_ratio <= 2:
        anomalies.append("BODY_LENGTH_SHIFT")
    if observation.required_field_ratio < 0.95:
        anomalies.append("REQUIRED_FIELDS_MISSING")
    if observation.dom_fingerprint_changed:
        anomalies.append("DOM_FINGERPRINT_CHANGED")
    if observation.duplicate_ratio > 0.8:
        anomalies.append("DUPLICATE_RATIO_HIGH")
    if observation.oldest_queue_age_seconds > observation.freshness_slo_seconds:
        anomalies.append("QUEUE_BACKLOG_STALE")
    parse_degraded = bool(
        {"BODY_LENGTH_SHIFT", "REQUIRED_FIELDS_MISSING", "DOM_FINGERPRINT_CHANGED"} & set(anomalies)
    )
    quality_degraded = bool({"REQUIRED_FIELDS_MISSING", "DUPLICATE_RATIO_HIGH"} & set(anomalies))
    return HealthEvaluation(
        transport_status="SUCCEEDED" if observation.transport_succeeded else "FAILED",
        discovery_status=("FALSE_SUCCESS" if "ZERO_DISCOVERY_STREAK" in anomalies else "SUCCEEDED"),
        parse_status="DEGRADED" if parse_degraded else "SUCCEEDED",
        quality_status="DEGRADED" if quality_degraded else "SUCCEEDED",
        freshness_status="VIOLATED" if freshness_violated else "WITHIN_SLO",
        anomaly_codes=tuple(anomalies),
    )
