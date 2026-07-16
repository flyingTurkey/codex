import re
from pathlib import Path

from srbg_api.observability import render_metrics

ROOT = Path(__file__).parents[2]


def test_round15_source_governance_metrics_have_actionable_alerts() -> None:
    metrics = render_metrics()[0].decode()
    rules = (ROOT / "infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")
    expected = {
        "srbg_source_runtime_authorization_mismatches": (
            "SourceLifecycleAuthorizationMismatch"
        ),
        "srbg_source_policy_rejections_total": "SourcePolicyRejectionSpike",
        "srbg_source_trial_runs_total": "SourceTrialSecurityFailure",
        "srbg_source_trial_quality_count": "SourceTrialQualityDegraded",
        "srbg_source_trial_ready_ratio_basis_points": "SourceTrialQualityDegraded",
        "srbg_connector_config_versions_total": "ConnectorConfigValidationFailure",
        "srbg_source_coverage_gap_cells": "SourceCoverageGapDetected",
        "srbg_source_production_scheduling_blocked_total": (
            "SourceProductionSchedulingBlocked"
        ),
    }
    for metric, alert in expected.items():
        assert metric in metrics
        block = re.search(
            rf"- alert: {alert}\n(?P<body>(?:        .+\n)+)", rules
        )
        assert block is not None
        assert metric in block.group("body")
    assert "srbg_source_lifecycle_state" in metrics
    assert (
        'srbg_source_trial_ready_ratio_basis_points{status="succeeded"} < 8000'
        in rules
    )


def test_round15_source_governance_runbook_is_fail_closed_and_redacted() -> None:
    runbook = (ROOT / "docs/operations/runbooks.md").read_text(encoding="utf-8")
    for required in (
        "source_governance_v2",
        "runtime authorization mismatch",
        "policy rejection",
        "trial security failure",
        "trial quality degradation",
        "connector config validation",
        "coverage gap",
        "SourceProductionSchedulingBlocked",
        "CONFIG_ROLLBACK_BY_NEW_VERSION",
        "source_admin",
        "platform_admin",
        "make phase2-round15-test",
        "do not log URLs, credentials, or response bodies",
    ):
        assert required in runbook


def test_round15_source_health_dashboard_exposes_governance_signals() -> None:
    dashboard = (
        ROOT / "infra/observability/grafana/dashboards/source-health.json"
    ).read_text(encoding="utf-8")

    for metric in (
        "srbg_source_lifecycle_state",
        "srbg_source_runtime_authorization_mismatches",
        "srbg_source_policy_rejections_total",
        "srbg_source_trial_runs_total",
        "srbg_source_trial_quality_count",
        "srbg_source_trial_ready_ratio_basis_points",
        "srbg_connector_config_versions_total",
        "srbg_source_coverage_gap_cells",
        "srbg_source_production_scheduling_blocked_total",
    ):
        assert metric in dashboard
