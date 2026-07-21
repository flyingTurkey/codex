import pytest
from pydantic import ValidationError
from srbg_api.ai_pipeline.contracts import ClassificationOutput
from srbg_api.ai_pipeline.gateway import _safe_validation_reason
from srbg_api.intelligence_v2.gold_calibration import AutoPassCalibrationGrant
from srbg_api.intelligence_v2.qualification import (
    QualificationReason,
    classification_allows_extraction,
    qualification_reason,
)

SECURITY = {
    "prompt_injection_detected": False,
    "prompt_injection_status": "NONE",
    "suspicious_patterns": [],
}
TEST_CALIBRATION = AutoPassCalibrationGrant(
    threshold_bps=9300,
    corpus_version="TEST_FIXTURE_ONLY",
    rule_version="intelligence-v2-qualification-1.0.0",
    model_id="protocol-equivalent-test-stub",
    prompt_version="qualification-test-v1",
    prediction_seal_sha256="e" * 64,
    fact_sha256="0" * 64,
)


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


def test_calibrated_relevant_classification_can_continue_to_fact_extraction() -> None:
    output = ClassificationOutput.model_validate(_classification())
    assert (
        classification_allows_extraction(
            output,
            document_text="铁路隧道施工安全整治",
            calibration=TEST_CALIBRATION,
        )
        is True
    )


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
    assert classification_allows_extraction(output, document_text="候选正文") is False


def test_irrelevant_classification_survives_gateway_exclude_none_round_trip() -> None:
    output = ClassificationOutput.model_validate(
        _classification(
            direct_relevance="IRRELEVANT",
            core_new_fact=None,
            primary_type=None,
            engineering_objects=[],
            evidence_locators=[],
            needs_human_review=True,
            review_reasons=["OUT_OF_SCOPE"],
        )
    )

    round_tripped = ClassificationOutput.model_validate(
        output.model_dump(mode="json", exclude_none=True)
    )

    assert round_tripped.primary_type is None


def test_gateway_reports_a_content_free_relevance_boundary_reason() -> None:
    with pytest.raises(ValidationError) as captured:
        ClassificationOutput.model_validate(
            _classification(core_new_fact=None, engineering_objects=[])
        )

    assert _safe_validation_reason(captured.value) == "[RELEVANCE_BOUNDARY]"


def test_relevant_result_requires_object_fact_type_and_evidence() -> None:
    with pytest.raises(ValidationError):
        ClassificationOutput.model_validate(_classification(engineering_objects=[]))


@pytest.mark.parametrize(
    "engineering_objects",
    [
        ["TUNNEL"],
        ["HIGHWAY", "TUNNEL", "MINING"],
        ["MINING"],
    ],
)
def test_tunnel_gas_monitoring_requires_a_highway_or_railway_tunnel(
    engineering_objects: list[str],
) -> None:
    with pytest.raises(ValidationError, match="TUNNEL_GAS_MONITORING"):
        ClassificationOutput.model_validate(
            _classification(
                engineering_objects=engineering_objects,
                specialty_facets=["TUNNEL_GAS_MONITORING"],
            )
        )


def test_tunnel_gas_monitoring_accepts_the_transport_tunnel_combinations() -> None:
    for transport_object in ("HIGHWAY", "RAILWAY"):
        output = ClassificationOutput.model_validate(
            _classification(
                engineering_objects=[transport_object, "TUNNEL"],
                specialty_facets=["TUNNEL_GAS_MONITORING"],
            )
        )
        assert output.specialty_facets == ["TUNNEL_GAS_MONITORING"]


def test_construction_machinery_requires_a_direct_engineering_lifecycle_fact() -> None:
    output = ClassificationOutput.model_validate(
        _classification(
            engineering_objects=[],
            equipment_domains=["CONSTRUCTION_MACHINERY"],
        )
    )

    assert (
        qualification_reason(output, document_text="企业发布季度经营报告")
        is QualificationReason.NO_SUBSTANTIVE_ENGINEERING_ACTIVITY
    )


def test_model_cannot_grant_hotspot_risk_review_or_publication_authority() -> None:
    for authority_field in ("hotspot_awarded", "risk_tier", "review_status", "published"):
        with pytest.raises(ValidationError):
            ClassificationOutput.model_validate(_classification(**{authority_field: True}))


@pytest.mark.parametrize(
    "document_text",
    [
        "中医药健康服务体系发布年度工作要点。",
        "旅游消费促销活动启动, 仅涉及景区营销。",
        "股票市场行情上涨, 正文没有工程项目事实。",
        "通用人工智能大模型发布, 未说明工程应用。",
        "港口企业公布营收与利润, 未披露建设运营新事实。",
    ],
)
def test_locked_negative_document_cannot_auto_pass_even_if_model_marks_relevant(
    document_text: str,
) -> None:
    output = ClassificationOutput.model_validate(_classification())

    assert classification_allows_extraction(output, document_text=document_text) is False
    assert (
        qualification_reason(output, document_text=document_text)
        is QualificationReason.LOCKED_NEGATIVE
    )


def test_manufacturing_erp_cannot_enter_construction_machinery_domain() -> None:
    output = ClassificationOutput.model_validate(
        _classification(
            core_new_fact="工程机械制造企业上线 ERP 并改造生产线",
            engineering_objects=[],
            equipment_domains=["CONSTRUCTION_MACHINERY"],
        )
    )
    text = "工程机械制造企业上线 ERP 并实施生产线工业互联网改造。"

    assert qualification_reason(output, document_text=text) is QualificationReason.LOCKED_NEGATIVE


def test_primary_type_tie_is_review_only_and_never_an_event_candidate() -> None:
    output = ClassificationOutput.model_validate(
        _classification(
            direct_relevance="LOW_CONFIDENCE",
            primary_type=None,
            needs_human_review=True,
            review_reasons=["PRIMARY_TYPE_TIE"],
        )
    )

    text = "桥梁数字监测安全通报"
    assert qualification_reason(output, document_text=text) is QualificationReason.PRIMARY_TYPE_TIE
    assert classification_allows_extraction(output, document_text=text) is False


def test_model_evidence_locator_must_refer_to_a_supplied_document_block() -> None:
    output = ClassificationOutput.model_validate(
        _classification(evidence_locators=["invented-block"])
    )

    assert (
        qualification_reason(
            output,
            document_text="铁路隧道施工安全整治",
            allowed_evidence_locators=frozenset({"block-1"}),
        )
        is QualificationReason.EVIDENCE_LOCATOR_MISMATCH
    )
