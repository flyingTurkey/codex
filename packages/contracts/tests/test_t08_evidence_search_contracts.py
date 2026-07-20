from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import EventFullProjectionV2, EventMetadataProjectionV2

EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000801")
CLAIM_ID = UUID("019f7c00-0000-7000-8000-000000000802")


def _full_projection() -> dict[str, object]:
    return {
        "projection_kind": "FULL",
        "event_id": EVENT_ID,
        "title": "铁路隧道安全监测更新",
        "primary_type": "SAFETY_INTELLIGENCE",
        "facets": {"engineering_objects": ["RAILWAY", "TUNNEL"]},
        "source": {"name": "国家铁路局", "official": True},
        "human_reviewed": True,
        "source_published_at": None,
        "first_discovered_at": None,
        "source_excerpt": {
            "text": "原文说明铁路隧道安全监测系统完成更新。",
            "claim_ids": [CLAIM_ID],
            "evidence_locators": ["html:p:8"],
        },
        "ai_summary": {"status": "NOT_GENERATED"},
        "original_url": "https://example.gov.cn/tunnel/1",
        "claim_basis": ["AUTHORITY_FINDING"],
        "search_explanation": {
            "matched_evidence_fields": ["TITLE", "ACCEPTED_CLAIMS", "SOURCE_EXCERPT"],
            "ai_summary_assisted": False,
        },
    }


def test_full_search_result_explains_evidence_and_low_weight_ai_matches() -> None:
    evidence_match = EventFullProjectionV2.model_validate(_full_projection())
    assert evidence_match.search_explanation is not None
    assert evidence_match.search_explanation.matched_evidence_fields == [
        "TITLE",
        "ACCEPTED_CLAIMS",
        "SOURCE_EXCERPT",
    ]
    assert evidence_match.search_explanation.ai_summary_assisted is False

    ai_assisted = EventFullProjectionV2.model_validate(
        _full_projection()
        | {
            "search_explanation": {
                "matched_evidence_fields": ["SOURCE"],
                "ai_summary_assisted": True,
            }
        }
    )
    assert ai_assisted.search_explanation.ai_summary_assisted is True


def test_r3_metadata_rejects_search_explanations_and_ai_match_details() -> None:
    metadata = {
        "projection_kind": "R3_METADATA",
        "event_id": EVENT_ID,
        "title": "待审核铁路隧道信息",
        "primary_type": "SAFETY_INTELLIGENCE",
        "official_source": True,
        "source_name": "国家铁路局",
        "source_published_at": None,
        "first_discovered_at": None,
        "original_url": "https://example.gov.cn/tunnel/pending",
        "review_state": "PENDING_OWNER_REVIEW",
    }
    with pytest.raises(ValidationError):
        EventMetadataProjectionV2.model_validate(
            metadata
            | {
                "search_explanation": {
                    "matched_evidence_fields": ["TITLE"],
                    "ai_summary_assisted": True,
                }
            }
        )
