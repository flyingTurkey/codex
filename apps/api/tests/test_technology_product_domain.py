from uuid import UUID

import pytest
from srbg_api.technology_products.domain import (
    CapabilityEvidence,
    ProductIdentity,
    contains_procurement_conclusion,
    determine_permit_status,
    normalize_product_identifier,
    resolve_identity,
    validate_capability,
)


def test_vendor_claim_cannot_become_verified_capability() -> None:
    evidence = CapabilityEvidence(
        attributed_vendor_id=UUID("019b0000-0000-7000-8000-000000007001"),
        source_vendor_ids=(UUID("019b0000-0000-7000-8000-000000007001"),),
        evidence_roles=("VENDOR_CLAIM",),
    )

    assert validate_capability("VERIFIED_CAPABILITY", evidence) == (
        "PRODUCT_VERIFIED_CAPABILITY_INDEPENDENT_EVIDENCE_REQUIRED",
    )
    assert validate_capability("PROMOTIONAL_CLAIM", evidence) == ()


def test_same_name_different_models_are_kept_distinct() -> None:
    existing = ProductIdentity("大疆行业应用", "机场 3", "M3D", "1.0")
    incoming = ProductIdentity("大疆行业应用", "机场 3", "M3TD", "1.0")

    result = resolve_identity(existing, incoming)

    assert result.action == "KEEP_DISTINCT"
    assert result.candidate_type == "POSSIBLE_DUPLICATE"


def test_version_update_links_new_immutable_version() -> None:
    existing = ProductIdentity("广联达", "数字项目平台", "平台版", "5.0")
    incoming = ProductIdentity("广联达", "数字项目平台", "平台版", "5.1")

    result = resolve_identity(existing, incoming)

    assert result.action == "LINK_AS_NEW_VERSION"
    assert result.candidate_type == "VERSION_SUCCESSOR"


def test_identifier_normalization_preserves_model_distinctions() -> None:
    assert normalize_product_identifier(" M3-D ") == "m3-d"
    assert normalize_product_identifier("M3/TD") == "m3/td"
    assert normalize_product_identifier(" M3-D ") != normalize_product_identifier("M3/TD")


def test_low_altitude_permit_is_unknown_without_official_evidence() -> None:
    assert determine_permit_status("LOW_ALTITUDE_EQUIPMENT", ()) == "UNKNOWN"
    assert determine_permit_status("LOW_ALTITUDE_EQUIPMENT", ("VENDOR_CLAIM",)) == "UNKNOWN"
    assert determine_permit_status(
        "LOW_ALTITUDE_EQUIPMENT", ("PRIMARY_OFFICIAL",)
    ) == "VERIFIED"


@pytest.mark.parametrize(
    "text",
    [
        "适用于四川路桥采购",
        "建议直接纳入采购短名单",
        "满足四川路桥采购要求",
    ],
)
def test_product_content_rejects_procurement_conclusions(text: str) -> None:
    assert contains_procurement_conclusion(text) is True

