from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError
from srbg_contracts import (
    EventFullProjectionV2,
    EventMetadataProjectionV2,
    EventProjectionV2,
    QuarantineProjectionV2,
)

EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000601")
CASE_ID = UUID("019f7c00-0000-7000-8000-000000000602")
CLAIM_ID = UUID("019f7c00-0000-7000-8000-000000000603")
DOCUMENT_VERSION_ID = UUID("019f7c00-0000-7000-8000-000000000604")
PUBLICATION_REVISION_ID = UUID("019f7c00-0000-7000-8000-000000000605")


def test_r3_is_an_exact_metadata_whitelist_with_nullable_times() -> None:
    projection = EventMetadataProjectionV2.model_validate(
        {
            "projection_kind": "R3_METADATA",
            "event_id": EVENT_ID,
            "title": "某铁路隧道施工安全通报",
            "primary_type": "SAFETY_INTELLIGENCE",
            "official_source": True,
            "source_name": "国家铁路局",
            "source_published_at": None,
            "first_discovered_at": None,
            "original_url": "https://example.gov.cn/report/1",
            "review_state": "PENDING_OWNER_REVIEW",
        }
    )

    assert set(projection.model_dump(mode="json")) == {
        "projection_kind",
        "event_id",
        "title",
        "primary_type",
        "official_source",
        "source_name",
        "source_published_at",
        "first_discovered_at",
        "original_url",
        "review_state",
    }
    with pytest.raises(ValidationError):
        EventMetadataProjectionV2.model_validate(
            projection.model_dump() | {"source_excerpt": {"text": "不得泄漏"}}
        )


def test_full_separates_official_source_from_human_review_and_uses_structured_summary() -> None:
    projection = EventFullProjectionV2.model_validate(
        {
            "projection_kind": "FULL",
            "event_id": EVENT_ID,
            "document_version_id": DOCUMENT_VERSION_ID,
            "publication_revision_id": PUBLICATION_REVISION_ID,
            "accepted_claim_set_sha256": "a" * 64,
            "authority_epoch": 1,
            "title": "某铁路隧道开展隐患整治",
            "primary_type": "SAFETY_INTELLIGENCE",
            "facets": {"engineering_objects": ["RAILWAY", "TUNNEL"]},
            "source": {"name": "国家铁路局", "official": True},
            "human_reviewed": False,
            "source_published_at": None,
            "first_discovered_at": None,
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
                "generated_at": "2026-07-20T00:00:00Z",
            },
            "original_url": "https://example.gov.cn/report/1",
            "claim_basis": ["AUTHORITY_FINDING"],
            "media": [],
            "attachments": [],
        }
    )

    assert projection.source.official is True
    assert projection.human_reviewed is False
    assert projection.publication_revision_id == PUBLICATION_REVISION_ID
    assert projection.accepted_claim_set_sha256 == "a" * 64
    assert projection.ai_summary.paragraphs[0].kind == "FACT"


def test_all_summary_states_project_distinct_deterministic_reader_copy() -> None:
    from srbg_contracts import AiSummaryStatusV2, AiSummaryV2

    messages = {
        AiSummaryV2(status=status).status_message
        for status in AiSummaryStatusV2
        if status != AiSummaryStatusV2.SUCCEEDED
    }

    assert len(messages) == 6
    assert None not in messages


def test_r4_has_a_separate_owner_safe_quarantine_contract() -> None:
    quarantine = QuarantineProjectionV2.model_validate(
        {
            "projection_kind": "QUARANTINE",
            "case_id": CASE_ID,
            "event_id": EVENT_ID,
            "title": "隔离内容",
            "primary_type": "SAFETY_INTELLIGENCE",
            "official_source": False,
            "source_published_at": None,
            "first_discovered_at": None,
            "original_url": "https://example.com/source/1",
            "isolation_reason": "UNRESOLVED_PROMPT_INJECTION",
        }
    )

    assert quarantine.projection_kind == "QUARANTINE"
    assert "source_excerpt" not in quarantine.model_dump(mode="json")
    with pytest.raises(ValidationError):
        TypeAdapter(EventProjectionV2).validate_python(quarantine.model_dump())
