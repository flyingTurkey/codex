from srbg_api.safety_regulations.query import _render_technology_product_metrics


def test_product_metrics_distinguish_type_evidence_capabilities_and_review_queue() -> None:
    rendered = _render_technology_product_metrics(
        profiles=[
            {
                "item_type": "LOW_ALTITUDE_EQUIPMENT",
                "evidence_level": "VENDOR_CLAIM_ONLY",
                "permit_status": "UNKNOWN",
                "count": 1,
            }
        ],
        capabilities={"PROMOTIONAL_CLAIM": 3, "VERIFIED_CAPABILITY": 0},
        pending_normalization=2,
    )

    assert 'item_type="LOW_ALTITUDE_EQUIPMENT"' in rendered
    assert 'permit_status="UNKNOWN"' in rendered
    assert 'kind="PROMOTIONAL_CLAIM"} 3' in rendered
    assert 'kind="VERIFIED_CAPABILITY"} 0' in rendered
    assert "srbg_product_normalization_pending 2" in rendered
