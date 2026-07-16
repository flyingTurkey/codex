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
SOURCE_LIFECYCLE_STATE = Gauge(
    "srbg_source_lifecycle_state",
    "Sources by authoritative V2 lifecycle state.",
    ("state",),
)
SOURCE_RUNTIME_AUTHORIZATION_MISMATCHES = Gauge(
    "srbg_source_runtime_authorization_mismatches",
    "Stored ACTIVE sources that currently fail authoritative runtime authorization.",
)
SOURCE_POLICY_REJECTIONS = Counter(
    "srbg_source_policy_rejections_total",
    "Source policy decisions rejected by bounded reason code.",
    ("reason",),
)
SOURCE_TRIAL_RUNS = Counter(
    "srbg_source_trial_runs_total",
    "Source trial runs by bounded mode and outcome.",
    ("mode", "outcome"),
)
SOURCE_TRIAL_QUALITY_COUNT = Gauge(
    "srbg_source_trial_quality_count",
    "Database-derived bounded evidence counts for completed source trials.",
    ("mode", "status", "measure"),
)
SOURCE_TRIAL_READY_RATIO_BPS = Gauge(
    "srbg_source_trial_ready_ratio_basis_points",
    (
        "Database-derived READY ratio over distinct document-level raw objects; "
        "discovery-only responses are excluded."
    ),
    ("mode", "status"),
)
SOURCE_PRODUCTION_SCHEDULING_BLOCKED = Counter(
    "srbg_source_production_scheduling_blocked_total",
    "Round 15 production scheduling blocks by bounded server reason.",
    ("reason",),
)
CONNECTOR_CONFIG_VERSIONS = Counter(
    "srbg_connector_config_versions_total",
    "Connector configuration versions by definition and validation outcome.",
    ("definition", "outcome"),
)
SOURCE_COVERAGE_GAP_CELLS = Gauge(
    "srbg_source_coverage_gap_cells",
    "Empty cells in the current bounded source coverage profile.",
)
SCHEDULE_DISPATCH_DELAY = Histogram(
    "srbg_schedule_dispatch_delay_seconds",
    "Delay between a due schedule and durable dispatch.",
    ("outcome",),
    buckets=(1, 5, 15, 30, 60, 300, 900),
)
SOURCE_FRESHNESS = Gauge(
    "srbg_source_freshness_seconds",
    "Business freshness by bounded health status.",
    ("status",),
)
FETCH_BACKLOG_AGE = Gauge(
    "srbg_fetch_backlog_age_seconds",
    "Age of the oldest durable fetch run by bounded state.",
    ("state",),
)
FETCH_FAILURES = Counter(
    "srbg_fetch_failures_total",
    "Fetch failures by bounded classification.",
    ("kind",),
)
SOURCE_PARSE_QUALITY_BPS = Gauge(
    "srbg_source_parse_quality_basis_points",
    "Source parse quality by bounded result.",
    ("status",),
)
SOURCE_CIRCUIT_STATE = Gauge(
    "srbg_source_circuit_state",
    "Source schedules by circuit state.",
    ("state",),
)
REPLAY_RESULTS = Counter(
    "srbg_replay_results_total",
    "Safe replay results by kind and bounded outcome.",
    ("kind", "outcome"),
)
RETENTION_RESULTS = Counter(
    "srbg_retention_results_total",
    "Retention executions by bounded outcome.",
    ("outcome",),
)
SOURCE_SLO_VIOLATIONS = Counter(
    "srbg_source_slo_violations_total",
    "Source SLO violations by bounded dimension.",
    ("dimension",),
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
    INTERNAL_PROJECTION_RECONCILIATION_DIFFERENCES.set(metrics["reconciliation_differences"])
    INTERNAL_PROJECTION_LAST_SUCCESS.set(metrics["last_projection_success_timestamp"])
    AUDIT_CHAIN_ANCHOR_LAST_SUCCESS.set(metrics["last_anchor_success_timestamp"])
