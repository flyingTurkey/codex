"""Fail-closed AI availability and reader summary-state policy for T06."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from srbg_contracts import AI_SUMMARY_STATUS_MESSAGES_V2, AiSummaryStatusV2

SummaryState = Literal[
    "NOT_GENERATED",
    "PROCESSING",
    "TEMPORARILY_UNAVAILABLE",
    "SCHEMA_REJECTED",
    "INSUFFICIENT_EVIDENCE",
    "SUCCEEDED",
    "STALE",
]


@dataclass(frozen=True, slots=True)
class AiAvailabilityFacts:
    configuration_active: bool
    secret_configured: bool
    provider: str
    configured_model: str
    worker_provider: str | None
    worker_model: str | None
    worker_heartbeat_at: datetime | None
    queue_healthy: bool
    budget_healthy: bool
    last_approved_content_schema_success_at: datetime | None


@dataclass(frozen=True, slots=True)
class AiAvailabilityView:
    configured: bool
    available: bool
    blocking_reasons: tuple[str, ...]


_TRANSIENT_FAILURES = frozenset(
    {
        "PROVIDER_TIMEOUT",
        "PROVIDER_NETWORK_ERROR",
        "NETWORK_ERROR",
        "TRANSIENT_UNAVAILABLE",
    }
)
_SCHEMA_FAILURES = frozenset(
    {
        "SUMMARY_SCHEMA_REJECTED",
        "SCHEMA_REJECTED",
        "MODELOUTPUTREJECTED",
        "NON_REPAIRABLE_OUTPUT",
    }
)
_EVIDENCE_FAILURES = frozenset(
    {
        "CURRENT_ACTIVE_ACCEPTED_CLAIM_REQUIRED",
        "NO_VALID_CANDIDATES",
        "INSUFFICIENT_EVIDENCE",
    }
)


def project_ai_availability(facts: AiAvailabilityFacts, *, now: datetime) -> AiAvailabilityView:
    """Project configuration separately from current, real-content-backed capability."""

    if now.tzinfo is None:
        raise ValueError("availability time must include a timezone")
    configured = facts.configuration_active and facts.secret_configured
    reasons: list[str] = []
    if not facts.secret_configured:
        reasons.append("SECRET_NOT_CONFIGURED")
    if not facts.configuration_active:
        reasons.append("CONFIGURATION_NOT_ACTIVE")
    if facts.worker_heartbeat_at is None or facts.worker_heartbeat_at < now - timedelta(seconds=60):
        reasons.append("WORKER_HEARTBEAT_STALE")
    if facts.worker_provider != facts.provider or facts.worker_model != facts.configured_model:
        reasons.append("PROVIDER_CONFIG_MISMATCH")
    if not facts.queue_healthy:
        reasons.append("QUEUE_UNAVAILABLE")
    if not facts.budget_healthy:
        reasons.append("BUDGET_UNAVAILABLE")
    if (
        facts.last_approved_content_schema_success_at is None
        or facts.last_approved_content_schema_success_at < now - timedelta(hours=24)
    ):
        reasons.append("NO_RECENT_APPROVED_CONTENT_SCHEMA_SUCCESS")
    return AiAvailabilityView(
        configured=configured,
        available=configured and not reasons,
        blocking_reasons=tuple(reasons),
    )


def summary_state_for_failure(reason_code: str, retry_scheduled: bool) -> SummaryState:
    """Map a durable terminal or compensation fact to one stable reader state."""

    normalized = reason_code.strip().upper()
    if normalized in _TRANSIENT_FAILURES or retry_scheduled:
        return "TEMPORARILY_UNAVAILABLE"
    if normalized in _SCHEMA_FAILURES:
        return "SCHEMA_REJECTED"
    if normalized in _EVIDENCE_FAILURES:
        return "INSUFFICIENT_EVIDENCE"
    return "NOT_GENERATED"


def summary_status_message(state: SummaryState) -> str:
    return AI_SUMMARY_STATUS_MESSAGES_V2[AiSummaryStatusV2(state)]
