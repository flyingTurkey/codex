from datetime import UTC, datetime
from uuid import UUID

import srbg_contracts.models as models

ITEM_ID = UUID("019b0000-0000-7000-8000-000000002001")
REVISION_ID = UUID("019b0000-0000-7000-8000-000000002002")


def _common_item() -> dict[str, object]:
    return {
        "id": ITEM_ID,
        "domain": "SAFETY",
        "content_type": "SAFETY_REGULATION",
        "title": "生产安全事故应急预案管理办法",
        "source_name": "应急管理部",
        "source_published_at": datetime(2016, 6, 3, 10, 28, tzinfo=UTC),
        "first_discovered_at": datetime(2026, 7, 14, 1, 9, 4, tzinfo=UTC),
        "activity_at": datetime(2026, 7, 14, 1, 9, 4, tzinfo=UTC),
        "original_url": (
            "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/201606/t20160603_405633.shtml"
        ),
    }


def test_r3_pending_item_serializes_only_server_whitelist_and_null_revision() -> None:
    item = models.ItemSummary(
        **_common_item(),
        publication_revision_id=None,
        review_status="PENDING",
    )

    payload = item.model_dump(mode="json", exclude_unset=True)

    assert payload["publication_revision_id"] is None
    assert set(payload) == {
        "id",
        "publication_revision_id",
        "domain",
        "content_type",
        "title",
        "source_name",
        "source_published_at",
        "first_discovered_at",
        "activity_at",
        "original_url",
        "review_status",
    }
    assert "one_sentence_fact" not in payload
    assert "evidence_count" not in payload
    assert "type_summary" not in payload
    assert "scores" not in payload


def test_published_safety_item_binds_immutable_revision_and_typed_summary() -> None:
    item = models.ItemSummary(
        **_common_item(),
        publication_revision_id=REVISION_ID,
        review_status="APPROVED",
        publication_status="PUBLISHED",
        evidence_status="VERIFIED",
        evidence_count=4,
        type_summary=models.SafetyRegulationTypeSummary(
            kind="SAFETY_REGULATION",
            document_number="国家安全生产监督管理总局令第88号",
            issuing_authority="应急管理部",
            regulation_status="UNKNOWN",
            classification="DEPARTMENT_RULE",
        ),
        detail_available=True,
    )

    payload = item.model_dump(mode="json", exclude_unset=True)

    assert payload["publication_revision_id"] == str(REVISION_ID)
    assert payload["type_summary"] == {
        "kind": "SAFETY_REGULATION",
        "document_number": "国家安全生产监督管理总局令第88号",
        "issuing_authority": "应急管理部",
        "regulation_status": "UNKNOWN",
        "classification": "DEPARTMENT_RULE",
    }
    assert "scores" not in payload


def test_feed_page_is_flat_cursor_contract_with_notices_and_no_total() -> None:
    item = models.ItemSummary(
        **_common_item(),
        publication_revision_id=None,
        review_status="PENDING",
    )
    page = models.FeedPage(
        items=[item],
        next_cursor=None,
        fingerprint="sha256:fixture",
        generated_at=datetime(2026, 7, 14, 2, 0, tzinfo=UTC),
        freshness="fresh",
        notices=[
            models.FeedNotice(
                code="R3_RESTRICTED",
                level="info",
                message="待人工审核; 暂不展示敏感字段。",
            )
        ],
    )

    payload = page.model_dump(mode="json", exclude_unset=True)

    assert payload["next_cursor"] is None
    assert payload["notices"][0]["code"] == "R3_RESTRICTED"
    assert "total" not in payload
