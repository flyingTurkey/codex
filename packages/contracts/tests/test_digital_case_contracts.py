from datetime import UTC, datetime
from uuid import UUID

import pytest
import srbg_contracts.models as models
from pydantic import ValidationError


def _relevance() -> models.RelevanceSummary:
    return models.RelevanceSummary(
        score=100,
        rule_version="relevance-v1.0.0",
        factors=[
            models.RelevanceFactor(code="ENGINEERING_DOMAIN", label="公路/桥梁", points=70),
            models.RelevanceFactor(code="SICHUAN", label="四川实施", points=20),
            models.RelevanceFactor(code="SRBG_DIRECT", label="四川路桥直接关系", points=10),
        ],
    )


def test_digital_case_summary_keeps_source_outcome_and_relevance_dimensions_separate() -> None:
    summary = models.DigitalCaseTypeSummary(
        kind="DIGITAL_CASE",
        maturity_level="SINGLE_PROJECT_PRODUCTION",
        application_scenarios=["QUALITY_CONTROL", "PROGRESS_CONTROL"],
        source_nature="ENTERPRISE_SELF_REPORT",
        deployment_scale="沿江高速 5913 片 T 梁、98 座桥梁",
        publisher_claim_label="发布方声明/未独立验证",
        srbg_relationship="四川路桥所属单位实施项目",
        relevance=_relevance(),
        ai_short_comment=None,
    )

    payload = summary.model_dump(mode="json")

    assert payload["source_nature"] == "ENTERPRISE_SELF_REPORT"
    assert payload["publisher_claim_label"] == "发布方声明/未独立验证"
    assert payload["relevance"]["rule_version"] == "relevance-v1.0.0"
    assert "confidence" not in payload["relevance"]
    assert payload["ai_short_comment"] is None


def test_digital_detail_requires_verified_outcomes_to_have_independent_evidence() -> None:
    with pytest.raises(ValidationError, match="independent evidence"):
        models.DigitalCaseOutcome(
            id=UUID("019b0000-0000-7000-8000-000000005001"),
            statement="施工速度提升 50%",
            attribution="发布方",
            verification="VERIFIED",
            evidence_ids=[UUID("019b0000-0000-7000-8000-000000005002")],
            independent_evidence_ids=[],
        )


def test_item_detail_carries_digital_case_read_model_without_changing_item_summary_shape() -> None:
    item = models.ItemSummary(
        id=UUID("019b0000-0000-7000-8000-000000005010"),
        publication_revision_id=UUID("019b0000-0000-7000-8000-000000005011"),
        domain="DIGITAL",
        content_type="DIGITAL_CASE",
        title="智慧梁厂2.0",
        source_name="蜀道集团",
        source_published_at=datetime(2022, 3, 10, tzinfo=UTC),
        first_discovered_at=datetime(2026, 7, 14, tzinfo=UTC),
        activity_at=datetime(2026, 7, 14, tzinfo=UTC),
        original_url="https://www.shudaojt.com/example.pdf",
        review_status="APPROVED",
        type_summary=models.DigitalCaseTypeSummary(
            kind="DIGITAL_CASE",
            maturity_level="SINGLE_PROJECT_PRODUCTION",
            application_scenarios=["QUALITY_CONTROL"],
            source_nature="ENTERPRISE_SELF_REPORT",
            deployment_scale="单项目生产应用",
            publisher_claim_label="发布方声明/未独立验证",
            srbg_relationship="四川路桥所属单位实施项目",
            relevance=_relevance(),
            ai_short_comment=None,
        ),
    )
    detail = models.ItemDetail(
        item=item,
        digital_case=models.DigitalCaseDetail(
            engineering_domains=["HIGHWAY", "BRIDGE"],
            lifecycle_stages=["CONSTRUCTION"],
            technology_tags=["BIM"],
            application_scenarios=["QUALITY_CONTROL"],
            maturity_level="SINGLE_PROJECT_PRODUCTION",
            deployment_scale="单项目生产应用",
            entities=[],
            claimed_outcomes=[],
            verified_outcomes=[],
            applicability=[],
            replication_conditions=[],
            limitations=["原文未提供独立验收材料"],
            risks=[],
            recommended_actions=["READ_ORIGINAL", "TECHNICAL_RESEARCH"],
            ai_short_comment=None,
        ),
    )

    assert detail.digital_case is not None
    assert detail.digital_case.recommended_actions == [
        models.RecommendedAction.READ_ORIGINAL,
        models.RecommendedAction.TECHNICAL_RESEARCH,
    ]
