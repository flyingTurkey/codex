from pathlib import Path

from srbg_api.observability import render_metrics

ROOT = Path(__file__).parents[2]


def test_round13_metrics_expose_actionable_current_state() -> None:
    metrics = render_metrics()[0].decode()
    for name in (
        "srbg_internal_projection_reconciliation_differences",
        "srbg_internal_projection_last_success_timestamp_seconds",
        "srbg_audit_chain_anchor_last_success_timestamp_seconds",
    ):
        assert name in metrics


def test_round13_alerts_cover_reconciliation_staleness_and_audit_anchor() -> None:
    rules = (ROOT / "infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")
    for alert in (
        "InternalProjectionReconciliationMismatch",
        "InternalProjectionStale",
        "AuditChainAnchorStale",
    ):
        assert f"alert: {alert}" in rules


def test_audit_anchor_is_periodically_scheduled_on_controlled_publisher() -> None:
    worker = (ROOT / "apps/worker/src/srbg_worker/app.py").read_text(encoding="utf-8")
    assert '"task": "srbg.audit.anchor"' in worker
    assert '@celery_app.task(name="srbg.audit.anchor")' in worker
    assert '"srbg.audit.anchor": {"queue": "publisher"}' in worker


def test_round13_runbook_has_fail_closed_recovery_without_consumer_switch() -> None:
    runbook = (ROOT / "docs/operations/runbooks.md").read_text(encoding="utf-8")
    for required in (
        "internal_projection_shadow",
        "audit_anchor_failure",
        "不得切换第14轮消费者",
        "srbg_projection_reader_login",
    ):
        assert required in runbook
