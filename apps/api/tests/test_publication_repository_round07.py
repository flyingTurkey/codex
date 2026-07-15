from __future__ import annotations

from pathlib import Path

REPOSITORY = Path("apps/api/src/srbg_api/publication/repository.py")


def test_round07_authoritative_context_is_loaded_for_all_product_types() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")

    assert "async def _round07_gate_facts(" in source
    assert 'policy_version in {"2.1.0", "7.0.0"} and round07 is not None' in source
    assert 'context["server"])["round07"] = round07' in source
    for item_type in (
        "SOFTWARE_PRODUCT",
        "IOT_PRODUCT",
        "LOW_ALTITUDE_EQUIPMENT",
        "AI_EQUIPMENT",
    ):
        assert item_type in source


def test_round07_context_checks_identity_claim_separation_images_and_permits() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")

    for fact in (
        '"identity_safe"',
        '"capability_groups_separated"',
        '"verified_capabilities_have_independent_evidence"',
        '"promotional_claims_vendor_attributed"',
        '"procurement_conclusion_count"',
        '"vendor_image_download_count"',
        '"permit_evidence_authorized"',
    ):
        assert fact in source
    assert "INDEPENDENT_CONFIRMATION" in source
    assert "document.source_id <> :product_source_id" in source
