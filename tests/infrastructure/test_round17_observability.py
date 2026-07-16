from pathlib import Path


def test_round17_has_low_cardinality_metrics_alerts_and_runbook() -> None:
    observability = Path("apps/api/src/srbg_api/observability.py").read_text(encoding="utf-8")
    service = Path("apps/api/src/srbg_api/operations/service.py").read_text(encoding="utf-8")
    rules = Path("infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")
    runbook = Path("docs/operations/runbooks.md").read_text(encoding="utf-8")

    for metric in (
        "ROUND17_WINDOW_STATE",
        "ROUND17_SOURCE_SEGMENT_STATE",
        "ROUND17_CONTAMINATED_RUNS",
        "ROUND17_STALE_WORK_TIMERS",
    ):
        assert metric in observability
    assert "round17_observability" in service
    assert "source_code" not in observability.split("ROUND17_WINDOW_STATE", 1)[1]
    for alert in (
        "Round17PilotSourcePaused",
        "Round17PilotEvidenceContamination",
        "Round17OperatorTimerStale",
    ):
        assert alert in rules
    for procedure in (
        "round17_source_pause",
        "round17_evidence_contamination",
        "round17_operator_timer",
    ):
        assert procedure in runbook
