from pathlib import Path


def test_t11_appendix_metric_has_only_a_bounded_outcome_label() -> None:
    source = Path("apps/api/src/srbg_api/observability.py").read_text(encoding="utf-8")

    metric = source.split("INTELLIGENCE_V2_APPENDIX_READS = Counter(", 1)[1][:300]
    assert '"srbg_intelligence_v2_appendix_reads_total"' in metric
    assert '("outcome",)' in metric
    assert "event_id" not in metric
