from datetime import UTC, datetime
from uuid import UUID

from srbg_api.safety_regulations.query import _item_summary


def test_pending_r2_low_altitude_product_gets_full_vendor_claim_projection() -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    item = _item_summary(  # type: ignore[arg-type]
        {
            "id": UUID("019b0000-0000-7000-8000-000000007201"),
            "item_type": "LOW_ALTITUDE_EQUIPMENT",
            "title": "无人机桥梁巡检载荷",
            "original_url": "https://enterprise.dji.com/cn",
            "source_published_at": None,
            "first_discovered_at": now,
            "activity_at": now,
            "updated_at": now,
            "review_status": "PENDING",
            "source_name": "大疆行业应用",
            "publication_status": None,
            "publication_revision_id": None,
            "vendor_name": "大疆行业应用",
            "product_name": "机场 3",
            "product_kind": "UAV_DOCK",
            "model_no": "M3D",
            "version": "1.0",
            "evidence_level": "VENDOR_CLAIM_ONLY",
            "permit_status": "UNKNOWN",
            "platform_type": "UAV_DOCK",
            "payload_types": ["CAMERA"],
            "promotional_claim_count": 1,
            "verified_capability_count": 0,
            "application_scenarios": ["INSPECTION"],
            "version_count": 1,
            "latest_change_type": None,
            "latest_change_review_state": None,
            "source_unavailable": False,
            "evidence_count": 1,
        }
    )

    assert item.domain == "DIGITAL"
    assert item.type_summary is not None
    assert item.type_summary.kind == "LOW_ALTITUDE_EQUIPMENT"
    assert item.type_summary.permit_status == "UNKNOWN"
    assert item.source_role == "厂商一手来源"

