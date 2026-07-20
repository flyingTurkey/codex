from pathlib import Path


def test_t09_hotspot_rejection_alert_uses_bounded_outcome_label() -> None:
    rules = Path("infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")

    assert "IntelligenceV2HotspotEvaluationRejected" in rules
    assert (
        'srbg_intelligence_v2_hotspot_evaluations_total{outcome="REJECTED"}'
        in rules
    )
    assert "event_id" not in rules.split("IntelligenceV2HotspotEvaluationRejected", 1)[1][:300]
