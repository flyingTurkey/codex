from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import (
    AiSummaryStatusV2,
    EventFullProjectionV2,
    EventMetadataProjectionV2,
    PrimaryIntelligenceType,
    ReviewDecisionCommandV2,
    ReviewDecisionReceiptV2,
)

EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000001")
CLAIM_ID = UUID("019f7c00-0000-7000-8000-000000000002")
DOCUMENT_VERSION_ID = UUID("019f7c00-0000-7000-8000-000000000003")
PUBLICATION_REVISION_ID = UUID("019f7c00-0000-7000-8000-000000000004")
NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _metadata() -> dict[str, object]:
    return {
        "projection_kind": "R3_METADATA",
        "event_id": EVENT_ID,
        "title": "某铁路隧道施工安全通报",
        "primary_type": PrimaryIntelligenceType.SAFETY_INTELLIGENCE,
        "official_source": True,
        "source_name": "国家铁路局",
        "source_published_at": NOW,
        "first_discovered_at": NOW,
        "original_url": "https://example.gov.cn/report/1",
        "review_state": "PENDING_OWNER_REVIEW",
    }


def test_r3_projection_rejects_full_content_fields() -> None:
    with pytest.raises(ValidationError):
        EventMetadataProjectionV2.model_validate(_metadata() | {"source_excerpt": "不得泄露"})


def test_full_projection_requires_claim_linked_excerpt_and_summary() -> None:
    projection = EventFullProjectionV2.model_validate(
        {
            "projection_kind": "FULL",
            "event_id": EVENT_ID,
            "document_version_id": DOCUMENT_VERSION_ID,
            "publication_revision_id": PUBLICATION_REVISION_ID,
            "accepted_claim_set_sha256": "a" * 64,
            "authority_epoch": 1,
            "title": "某铁路隧道施工安全通报",
            "primary_type": "SAFETY_INTELLIGENCE",
            "facets": {"engineering_objects": ["RAILWAY", "TUNNEL"]},
            "source": {"name": "国家铁路局", "official": True},
            "human_reviewed": True,
            "source_published_at": NOW,
            "first_discovered_at": NOW,
            "source_excerpt": {
                "text": "通报指出该铁路隧道正在开展安全隐患整治。",
                "claim_ids": [CLAIM_ID],
                "evidence_locators": ["html:p:12"],
            },
            "ai_summary": {
                "status": "SUCCEEDED",
                "paragraphs": [
                    {
                        "kind": "FACT",
                        "section": "WHAT_HAPPENED",
                        "text": "事实" * 50,
                        "claim_ids": [CLAIM_ID],
                    },
                    {
                        "kind": "JUDGMENT",
                        "section": "ENGINEERING_IMPACT",
                        "text": "影响" * 50,
                        "judgment_type": "ENGINEERING_SIGNIFICANCE",
                    },
                    {
                        "kind": "JUDGMENT",
                        "section": "LIMITATIONS_AND_FOLLOW_UP",
                        "text": "限制" * 50,
                        "judgment_type": "LIMITATION_AND_FOLLOW_UP",
                    },
                ],
                "claim_ids": [CLAIM_ID],
                "model": "deepseek-chat",
                "generated_at": NOW,
            },
            "original_url": "https://example.gov.cn/report/1",
            "claim_basis": ["AUTHORITY_FINDING"],
            "media": [],
            "attachments": [],
        }
    )
    assert projection.ai_summary.status is AiSummaryStatusV2.SUCCEEDED


def test_successful_summary_cannot_omit_claim_references() -> None:
    payload = {
        "status": "SUCCEEDED",
        "body": "发生了什么:已发布。工程影响与意义:待评估。限制与待跟踪:暂无。",
        "claim_ids": [],
        "judgment_paragraphs": [],
        "model": "deepseek-chat",
        "generated_at": NOW,
    }
    from srbg_contracts import AiSummaryV2

    with pytest.raises(ValidationError):
        AiSummaryV2.model_validate(payload)


def test_review_command_is_append_only_and_has_no_publication_status() -> None:
    command = ReviewDecisionCommandV2.model_validate(
        {
            "command": "CONFIRM_RELEVANCE",
            "reason": "工程对象和施工安全影响均有原文证据",
            "expected_version": 3,
        }
    )
    assert command.expected_version == 3
    with pytest.raises(ValidationError):
        ReviewDecisionCommandV2.model_validate(
            command.model_dump() | {"publication_status": "PUBLISHED"}
        )


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("CORRECT_PRIMARY_TYPE", {"primary_type": "INDUSTRY_UPDATE"}),
        (
            "CORRECT_FACETS",
            {
                "engineering_objects": ["TUNNEL"],
                "specialties": ["TUNNEL_GAS_MONITORING"],
                "equipment_domains": [],
            },
        ),
        ("ACCEPT_CLAIM", {"claim_id": str(CLAIM_ID)}),
        ("DECIDE_RISK", {"risk_tier": "R3"}),
    ],
)
def test_review_command_validates_command_specific_payload(
    command: str, payload: dict[str, object]
) -> None:
    value = ReviewDecisionCommandV2.model_validate(
        {
            "command": command,
            "reason": "Owner 已核对原文证据",
            "expected_version": 1,
            "payload": payload,
        }
    )
    assert value.command == command


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("CONFIRM_RELEVANCE", {"risk_tier": "R1"}),
        ("CORRECT_PRIMARY_TYPE", {}),
        ("ACCEPT_CLAIM", {"claim_id": "not-a-uuid"}),
        ("DECIDE_RISK", {"risk_tier": "R5"}),
        ("CORRECT_FACETS", {"engineering_objects": []}),
    ],
)
def test_review_command_rejects_irrelevant_or_invalid_payload(
    command: str, payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        ReviewDecisionCommandV2.model_validate(
            {
                "command": command,
                "reason": "Owner 已核对原文证据",
                "expected_version": 1,
                "payload": payload,
            }
        )


def test_review_receipt_exposes_durable_reprocessing_outbox() -> None:
    receipt = ReviewDecisionReceiptV2.model_validate(
        {
            "decision_id": CLAIM_ID,
            "case_id": EVENT_ID,
            "version": 4,
            "recorded_at": NOW,
            "reprocessing_outbox_id": "019f7c00-0000-7000-8000-000000000003",
            "reprocessing_state": "QUEUED",
        }
    )
    assert receipt.reprocessing_state == "QUEUED"
