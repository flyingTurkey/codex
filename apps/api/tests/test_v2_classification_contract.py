import pytest
from pydantic import ValidationError
from srbg_api.ai_pipeline.contracts import ClassificationOutput
from srbg_api.intelligence_v2.qualification import classification_allows_extraction

SECURITY = {
    "prompt_injection_detected": False,
    "prompt_injection_status": "NONE",
    "suspicious_patterns": [],
}


def _classification(**overrides: object) -> dict[str, object]:
    return {
        "direct_relevance": "RELEVANT",
        "core_new_fact": "发布铁路隧道施工安全整治要求",
        "primary_type": "SAFETY_INTELLIGENCE",
        "engineering_objects": ["RAILWAY", "TUNNEL"],
        "specialty_facets": [],
        "equipment_domains": [],
        "content_form": "AUTHORITY_NOTICE",
        "evidence_locators": ["html:p:8"],
        "confidence": 0.96,
        "needs_human_review": False,
        "review_reasons": [],
        "security": SECURITY,
    } | overrides


def test_relevant_classification_can_continue_to_fact_extraction() -> None:
    output = ClassificationOutput.model_validate(_classification())
    assert classification_allows_extraction(output) is True


@pytest.mark.parametrize("decision", ["IRRELEVANT", "LOW_CONFIDENCE", "FAILED"])
def test_non_relevant_or_uncertain_classification_stops_before_extraction(decision: str) -> None:
    output = ClassificationOutput.model_validate(
        _classification(
            direct_relevance=decision,
            primary_type=None,
            engineering_objects=[],
            needs_human_review=True,
            review_reasons=[decision],
        )
    )
    assert classification_allows_extraction(output) is False


def test_relevant_result_requires_object_fact_type_and_evidence() -> None:
    with pytest.raises(ValidationError):
        ClassificationOutput.model_validate(_classification(engineering_objects=[]))
