from pathlib import Path

from srbg_api.observability import render_metrics

ROOT = Path(__file__).parents[2]


def test_round14_metrics_have_actionable_alerts() -> None:
    metrics = render_metrics()[0].decode()
    rules = (ROOT / "infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")
    expected = {
        "srbg_event_migration_records": "EventMigrationBlocked",
        "srbg_event_consumer_parity_differences": "EventConsumerParityMismatch",
        "srbg_event_alias_resolutions_total": "EventAliasResolutionFailure",
        "srbg_event_identity_candidate_backlog": "EventIdentityCandidateBacklog",
        "srbg_event_identity_rollbacks_total": "EventIdentityRollbackDetected",
    }
    for metric, alert in expected.items():
        assert metric in metrics
        assert f"alert: {alert}" in rules


def test_round14_runbook_covers_switch_failure_alias_loops_and_backlog() -> None:
    runbook = (ROOT / "docs/operations/runbooks.md").read_text(encoding="utf-8")
    for required in (
        "event_identity_migration",
        "consumer parity",
        "alias loop",
        "candidate backlog",
        "application rollback",
    ):
        assert required in runbook
