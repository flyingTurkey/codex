from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_personal_source_probe_has_queue_and_failure_observability() -> None:
    metrics = (ROOT / "apps/api/src/srbg_api/observability.py").read_text(encoding="utf-8")
    rules = (ROOT / "infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")

    assert "srbg_personal_source_probe_queue" in metrics
    assert "srbg_personal_source_probes_total" in metrics
    assert "PersonalSourceProbeQueueStalled" in rules
    assert "srbg_personal_source_probe_queue > 0" in rules
