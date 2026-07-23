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
INTELLIGENCE_QUALIFICATION_DECISIONS = Counter(
    "srbg_intelligence_qualification_decisions_total",
    "Civil-engineering qualification decisions by bounded outcome and reason.",
    ("outcome", "reason"),
)
INTELLIGENCE_QUALIFICATION_REVIEW_BACKLOG = Gauge(
    "srbg_intelligence_qualification_review_backlog",
    "Open civil-engineering qualification review cases from PostgreSQL authority.",
)
TECHNICAL_RETRY_OUTCOMES = Counter(
    "srbg_technical_retry_outcomes_total",
    "Durable technical retry transitions by bounded outcome and reason class.",
    ("outcome", "reason_class"),
)
OWNER_TECHNICAL_EXCEPTION_BACKLOG = Gauge(
    "srbg_owner_technical_exception_backlog",
    "Open Owner technical exceptions in PostgreSQL.",
)
OWNER_TECHNICAL_EXCEPTION_COMMANDS = Counter(
    "srbg_owner_technical_exception_commands_total",
    "Owner technical exception commands by bounded outcome.",
    ("outcome",),
)
OWNER_FEED_SUPPRESSION_COMMANDS = Counter(
    "srbg_owner_feed_suppression_commands_total",
    "Owner Feed suppression commands by bounded scope, action, and outcome.",
    ("scope", "action", "outcome"),
)
INTELLIGENCE_V2_PUBLICATION_DECISIONS = Counter(
    "srbg_intelligence_v2_publication_decisions_total",
    "Reader projection decisions by bounded outcome; safety failures are explicit.",
    ("outcome",),
)
INTELLIGENCE_V2_HOTSPOT_EVALUATIONS = Counter(
    "srbg_intelligence_v2_hotspot_evaluations_total",
    "Server-derived hotspot evaluations by bounded outcome.",
    ("outcome",),
)
INTELLIGENCE_V2_APPENDIX_READS = Counter(
    "srbg_intelligence_v2_appendix_reads_total",
    "ReaderAppendix reads by bounded visibility and content outcome.",
    ("outcome",),
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
PERSONAL_SOURCE_PROBES = Counter(
    "srbg_personal_source_probes_total",
    "One-shot personal source probes by bounded outcome and reason.",
    ("outcome", "reason"),
)
PERSONAL_SOURCE_PROBE_QUEUE = Gauge(
    "srbg_personal_source_probe_queue",
    "Queued one-shot personal source probe runs seen by the dispatcher.",
)
PERSONAL_DISCOVERY_RESULTS = Counter(
    "srbg_personal_discovery_results_total",
    "Personal source discoveries by bounded channel and outcome.",
    ("channel", "outcome"),
)
PERSONAL_AUTO_ENABLE_RESULTS = Counter(
    "srbg_personal_auto_enable_results_total",
    "Personal source automatic enable decisions by bounded outcome.",
    ("outcome",),
)
PERSONAL_AI_JUDGMENT_RESULTS = Counter(
    "srbg_personal_ai_judgment_results_total",
    "Personal AI judgment pipeline outcomes by bounded automatic result type.",
    ("result_type",),
)
PERSONAL_AI_REPAIR_ATTEMPTS = Counter(
    "srbg_personal_ai_repair_attempts_total",
    "Controlled JSON/schema repair attempts by bounded AI step.",
    ("step",),
)
PERSONAL_AUTOMATIC_RELATIONSHIPS = Counter(
    "srbg_personal_automatic_relationships_total",
    "Automatic relationship decisions by bounded kind and outcome.",
    ("kind", "outcome"),
)
PERSONAL_RELATIONSHIP_CORRECTIONS = Counter(
    "srbg_personal_relationship_corrections_total",
    "Local Owner relationship corrections by bounded action and outcome.",
    ("action", "outcome"),
)
SOURCE_PROFILE_QUEUE = Gauge(
    "srbg_source_profile_queue",
    "Queued automatic source profile runs seen by the dispatcher.",
)
SOURCE_PROFILE_RUNS = Counter(
    "srbg_source_profile_runs_total",
    "Automatic source profile runs by bounded outcome and reason.",
    ("outcome", "reason"),
)
SOURCE_PROFILE_MODEL_ATTEMPTS = Counter(
    "srbg_source_profile_model_attempts_total",
    "Source profile model attempts by bounded kind and outcome.",
    ("kind", "outcome"),
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
SOURCE_AUTOMATION_CANDIDATE_BACKLOG = Gauge(
    "srbg_source_automation_candidate_backlog",
    "Source candidates by bounded authoritative workflow status.",
    ("status",),
)
SOURCE_AUTOMATION_QUALIFICATION_REQUESTS = Counter(
    "srbg_source_automation_qualification_requests_total",
    "Source qualification requests by bounded trigger and outcome.",
    ("trigger", "outcome"),
)
SOURCE_AUTOMATION_CANDIDATE_DECISIONS = Counter(
    "srbg_source_automation_candidate_decisions_total",
    "Candidate decisions by bounded decision and outcome.",
    ("decision", "outcome"),
)
PERSONAL_SOURCE_UPDATES = Counter(
    "srbg_personal_source_updates_total",
    "Personal source updates by bounded action and outcome.",
    ("action", "outcome"),
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
SOURCE_STREAM_CONTROL_DECISIONS = Counter(
    "srbg_source_stream_control_decisions_total",
    "Stream-level research, intent, admission and runtime decisions by bounded outcome.",
    ("phase", "outcome"),
)
SOURCE_SHADOW_COLLECTION = Counter(
    "srbg_source_shadow_collection_total",
    "Controlled shadow collection results by bounded outcome and document kind.",
    ("outcome", "document_kind"),
)
T06_AI_RUNTIME_STATE = Gauge(
    "srbg_t06_ai_runtime_state",
    "T06 DeepSeek configured and real-content-backed availability state.",
    ("provider", "state"),
)
T06_AI_SUMMARY_STATE_TRANSITIONS = Counter(
    "srbg_t06_ai_summary_state_transitions_total",
    "Durable T06 summary state transitions by bounded state.",
    ("state",),
)
T06_AI_PROJECTION_REFRESH = Counter(
    "srbg_t06_ai_projection_refresh_total",
    "PublicationService-owned T06 projection refresh outcomes.",
    ("outcome",),
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
