from pathlib import Path


def test_feed_suppression_failure_has_bounded_alert_and_runbook() -> None:
    rules = Path("infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")
    runbook = Path("docs/operations/runbooks.md").read_text(encoding="utf-8")

    assert "FeedSuppressionCommandFailed" in rules
    assert 'srbg_owner_feed_suppression_commands_total{outcome="failed"}' in rules
    assert "feed_suppression_failure" in runbook
