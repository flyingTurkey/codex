import pytest
from srbg_api.intelligence_v2.domain import (
    HotspotComponents,
    RelevanceDecision,
    calculate_hotspot_award,
    decide_projection,
)


def test_uncertain_relevance_never_projects() -> None:
    assert decide_projection(RelevanceDecision.LOW_CONFIDENCE, "R1") == "REVIEW_ONLY"
    assert decide_projection(RelevanceDecision.RELEVANT, "R4") == "QUARANTINE_ONLY"
    assert decide_projection(RelevanceDecision.RELEVANT, "R3") == "R3_METADATA"
    assert decide_projection(RelevanceDecision.RELEVANT, "R2") == "FULL"


def test_hotspot_is_derived_by_server_rule() -> None:
    components = HotspotComponents(
        impact_scope=20,
        engineering_materiality=20,
        novelty=15,
        urgency=10,
        evidence_authority=10,
    )
    result = calculate_hotspot_award(
        components=components,
        independent_source_count=1,
        authoritative_first_party=True,
    )
    assert result.awarded is True
    assert result.score == 75
    assert result.rule_version == "hotspot-v2.0.0"


@pytest.mark.parametrize("field,value", [("impact_scope", 26), ("novelty", 21)])
def test_hotspot_component_caps_are_enforced(field: str, value: int) -> None:
    payload = {
        "impact_scope": 0,
        "engineering_materiality": 0,
        "novelty": 0,
        "urgency": 0,
        "evidence_authority": 0,
        field: value,
    }
    with pytest.raises(ValueError):
        HotspotComponents(**payload)
