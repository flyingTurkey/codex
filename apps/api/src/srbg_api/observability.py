"""Low-cardinality metrics and privacy-safe error reporting."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sentry_sdk import init as init_sentry
from srbg_contracts import MetricSample

from srbg_api.config import Settings

API_REQUESTS = Counter(
    "srbg_api_requests_total",
    "API requests by normalized route, method, and status.",
    ("route", "method", "status"),
)
API_DURATION = Histogram(
    "srbg_api_request_duration_seconds",
    "API request duration by normalized route and method.",
    ("route", "method"),
    buckets=(0.05, 0.1, 0.25, 0.5, 0.8, 1, 2, 5),
)
SEARCH_DURATION = Histogram(
    "srbg_search_duration_seconds",
    "Search duration.",
    buckets=(0.05, 0.1, 0.25, 0.5, 0.8, 1, 2),
)
OPERATIONS_METRIC = Gauge(
    "srbg_operations_metric",
    "Bounded operational metric values from PostgreSQL authority",
    ["code", "unit", "status"],
)
INTERNAL_PROJECTION_RUNS = Counter(
    "srbg_internal_projection_runs_total",
    "Internal shadow projection runs by bounded outcome.",
    ("outcome",),
)
INTERNAL_PROJECTION_RECORDS = Counter(
    "srbg_internal_projection_records_total",
    "Internal shadow projection records by policy level.",
    ("level",),
)
INTERNAL_PROJECTION_RECONCILIATION_DIFFERENCES = Gauge(
    "srbg_internal_projection_reconciliation_differences",
    "Differences in the latest completed internal shadow projection generation.",
)
INTERNAL_PROJECTION_LAST_SUCCESS = Gauge(
    "srbg_internal_projection_last_success_timestamp_seconds",
    "Unix timestamp of the latest completed internal shadow projection generation.",
)
AUDIT_CHAIN_ANCHOR_LAST_SUCCESS = Gauge(
    "srbg_audit_chain_anchor_last_success_timestamp_seconds",
    "Unix timestamp of the latest independently persisted audit chain anchor.",
)
AUTHORIZATION_DENIALS = Counter(
    "srbg_authorization_denials_total",
    "Authorization denials by bounded policy reason.",
    ("reason",),
)
EVENT_MIGRATION_RECORDS = Gauge(
    "srbg_event_migration_records",
    "Latest Event migration records by bounded outcome.",
    ("outcome",),
)
EVENT_CONSUMER_PARITY_DIFFERENCES = Gauge(
    "srbg_event_consumer_parity_differences",
    "Latest Item-to-Event consumer parity differences.",
)
EVENT_ALIAS_RESOLUTIONS = Counter(
    "srbg_event_alias_resolutions_total",
    "Item/Event alias resolution outcomes.",
    ("outcome",),
)
EVENT_IDENTITY_CANDIDATE_BACKLOG = Gauge(
    "srbg_event_identity_candidate_backlog",
    "Fuzzy identity candidates awaiting a human decision.",
)
EVENT_IDENTITY_ROLLBACKS = Counter(
    "srbg_event_identity_rollbacks_total",
    "Reviewed Event merge/split rollbacks.",
)


def configure_observability(settings: Settings) -> None:
    if settings.sentry_dsn is None or not settings.sentry_dsn.get_secret_value().strip():
        return
    init_sentry(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        send_default_pii=False,
        traces_sample_rate=0.1,
        max_request_body_size="never",
    )


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def set_operations_metrics(metrics: list[MetricSample]) -> None:
    for metric in metrics:
        code = metric.code
        unit = metric.unit
        status = metric.status
        value = float(metric.value)
        OPERATIONS_METRIC.labels(code, unit, status).set(value)


def set_internal_projection_metrics(metrics: dict[str, float]) -> None:
    INTERNAL_PROJECTION_RECONCILIATION_DIFFERENCES.set(
        metrics["reconciliation_differences"]
    )
    INTERNAL_PROJECTION_LAST_SUCCESS.set(metrics["last_projection_success_timestamp"])
    AUDIT_CHAIN_ANCHOR_LAST_SUCCESS.set(metrics["last_anchor_success_timestamp"])
