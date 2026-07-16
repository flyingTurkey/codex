from pathlib import Path


def test_round16_metrics_are_low_cardinality_and_alerted() -> None:
    observability = Path("apps/api/src/srbg_api/observability.py").read_text(encoding="utf-8")
    rules = Path("infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")
    dashboard = Path("infra/observability/grafana/dashboards/source-health.json").read_text(
        encoding="utf-8"
    )
    metrics = (
        "srbg_schedule_dispatch_delay_seconds",
        "srbg_source_freshness_seconds",
        "srbg_fetch_backlog_age_seconds",
        "srbg_fetch_failures_total",
        "srbg_source_parse_quality_basis_points",
        "srbg_source_circuit_state",
        "srbg_replay_results_total",
        "srbg_retention_results_total",
        "srbg_source_slo_violations_total",
    )
    for metric in metrics:
        assert metric in observability
        assert metric in dashboard
    for alert in (
        "SourceFalseSuccess",
        "SourceFreshnessSLOViolation",
        "FetchQueueBacklog",
        "SafeReplayBlocked",
        "RetentionExecutionFailure",
    ):
        assert alert in rules
    assert 'labelnames=("source_id"' not in observability
    assert 'labelnames=("url"' not in observability
