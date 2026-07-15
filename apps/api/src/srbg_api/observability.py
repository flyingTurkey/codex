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
AUTHORIZATION_DENIALS = Counter(
    "srbg_authorization_denials_total",
    "Authorization denials by bounded policy reason.",
    ("reason",),
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
