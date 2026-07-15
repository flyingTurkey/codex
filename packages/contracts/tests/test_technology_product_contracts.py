from datetime import UTC, datetime
from uuid import UUID

import pytest
import srbg_contracts.models as models
from pydantic import ValidationError


def _capability(kind: str = "PROMOTIONAL_CLAIM") -> models.ProductCapability:
    return models.ProductCapability(
        claim_id=UUID("019b0000-0000-7000-8000-000000007101"),
        statement="支持桥梁监测数据接入",
        attribution="厂商声明" if kind == "PROMOTIONAL_CLAIM" else "独立项目材料",
        kind=kind,
        evidence_ids=[UUID("019b0000-0000-7000-8000-000000007102")],
        independent_evidence_ids=(
            [] if kind == "PROMOTIONAL_CLAIM" else [UUID("019b0000-0000-7000-8000-000000007103")]
        ),
    )


def test_four_product_type_summaries_are_discriminated_union_members() -> None:
    summaries = [
        models.SoftwareProductTypeSummary(
            kind="SOFTWARE_PRODUCT",
            vendor_name="广联达",
            product_name="数字项目平台",
            product_kind="PROJECT_MANAGEMENT_PLATFORM",
            model_no=None,
            version="5.0",
            evidence_level="VENDOR_CLAIM_ONLY",
            promotional_claim_count=1,
            verified_capability_count=0,
            interfaces=["REST API"],
            deployment_modes=["PRIVATE_CLOUD"],
        ),
        models.IotProductTypeSummary(
            kind="IOT_PRODUCT",
            vendor_name="演示厂商",
            product_name="位移监测终端",
            product_kind="MONITORING_TERMINAL",
            model_no="S-100",
            version="1.0",
            evidence_level="PROJECT_EVIDENCE",
            promotional_claim_count=1,
            verified_capability_count=1,
            connectivity=["4G", "LoRa"],
            maturity_level="PILOT",
        ),
        models.LowAltitudeEquipmentTypeSummary(
            kind="LOW_ALTITUDE_EQUIPMENT",
            vendor_name="大疆行业应用",
            product_name="机场 3",
            product_kind="UAV_DOCK",
            model_no="M3D",
            version="1.0",
            evidence_level="VENDOR_CLAIM_ONLY",
            promotional_claim_count=2,
            verified_capability_count=0,
            platform_type="UAV_DOCK",
            payload_types=["CAMERA"],
            permit_status="UNKNOWN",
        ),
        models.AiEquipmentTypeSummary(
            kind="AI_EQUIPMENT",
            vendor_name="演示科研机构",
            product_name="巡检机器人",
            product_kind="INSPECTION_ROBOT",
            model_no="R1",
            version="0.9",
            evidence_level="RESEARCH_EVIDENCE",
            promotional_claim_count=0,
            verified_capability_count=1,
            equipment_form="ROBOT",
            ai_tasks=["DEFECT_DETECTION"],
            maturity_level="LAB_PROTOTYPE",
            production_validation=False,
        ),
    ]

    assert [summary.kind for summary in summaries] == [
        "SOFTWARE_PRODUCT",
        "IOT_PRODUCT",
        "LOW_ALTITUDE_EQUIPMENT",
        "AI_EQUIPMENT",
    ]


def test_verified_capability_requires_independent_evidence() -> None:
    with pytest.raises(ValidationError, match="independent evidence"):
        models.ProductCapability(
            claim_id=UUID("019b0000-0000-7000-8000-000000007111"),
            statement="已验证能力",
            attribution="厂商",
            kind="VERIFIED_CAPABILITY",
            evidence_ids=[UUID("019b0000-0000-7000-8000-000000007112")],
            independent_evidence_ids=[],
        )


def test_item_detail_exposes_three_product_sections_without_procurement_result() -> None:
    item = models.ItemSummary(
        id=UUID("019b0000-0000-7000-8000-000000007120"),
        publication_revision_id=None,
        domain="DIGITAL",
        content_type="LOW_ALTITUDE_EQUIPMENT",
        title="无人机桥梁巡检载荷",
        source_name="大疆行业应用",
        source_published_at=None,
        first_discovered_at=datetime(2026, 7, 15, tzinfo=UTC),
        activity_at=datetime(2026, 7, 15, tzinfo=UTC),
        original_url="https://enterprise.dji.com/cn",
        review_status="PENDING",
        type_summary=models.LowAltitudeEquipmentTypeSummary(
            kind="LOW_ALTITUDE_EQUIPMENT",
            vendor_name="大疆行业应用",
            product_name="机场 3",
            product_kind="UAV_DOCK",
            model_no="M3D",
            version="1.0",
            evidence_level="VENDOR_CLAIM_ONLY",
            promotional_claim_count=1,
            verified_capability_count=0,
            platform_type="UAV_DOCK",
            payload_types=["CAMERA"],
            permit_status="UNKNOWN",
        ),
    )
    detail = models.ItemDetail(
        item=item,
        technology_product=models.TechnologyProductDetail(
            vendor=models.ProductEntity(
                id=UUID("019b0000-0000-7000-8000-000000007121"), name="大疆行业应用"
            ),
            product=models.ProductEntity(
                id=UUID("019b0000-0000-7000-8000-000000007122"), name="机场 3"
            ),
            model=models.ProductEntity(id=UUID("019b0000-0000-7000-8000-000000007123"), name="M3D"),
            current_version="1.0",
            version_history=["1.0"],
            product_kind="UAV_DOCK",
            promotional_claims=[_capability()],
            verified_capabilities=[],
            interfaces=[],
            deployment_modes=[],
            application_scenarios=["INSPECTION"],
            engineering_cases=[],
            evidence_level="VENDOR_CLAIM_ONLY",
            permit_status="UNKNOWN",
            limitations=["需按项目核验许可"],
            procurement_notice="仅供技术调研，不构成采购建议",  # noqa: RUF001
            low_altitude_notice="产品发布不代表空域、适航、飞手和项目许可。",
        ),
    )

    assert detail.technology_product is not None
    assert detail.technology_product.permit_status is models.ProductPermitStatus.UNKNOWN
    assert "适用于四川路桥采购" not in detail.model_dump_json()
