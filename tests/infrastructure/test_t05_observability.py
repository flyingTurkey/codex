from inspect import getsource
from pathlib import Path

from srbg_api import observability
from srbg_api.publication.repository import PostgresPublicationRepository


def test_t05_publication_decisions_have_a_bounded_metric_and_safety_alert() -> None:
    metric = observability.INTELLIGENCE_V2_PUBLICATION_DECISIONS
    assert metric._labelnames == ("outcome",)
    source = getsource(PostgresPublicationRepository._record_v2_publication_decision)
    assert "INTELLIGENCE_V2_PUBLICATION_DECISIONS.labels(" in source
    assert "outcome=metric_outcome" in source

    rules = Path("infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")
    assert "IntelligenceV2ProjectionSafetyFailure" in rules
    assert 'outcome="SAFETY_FAILURE"' in rules
