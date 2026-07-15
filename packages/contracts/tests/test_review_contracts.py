from datetime import UTC, datetime
from uuid import UUID

import srbg_contracts.models as models


def test_restricted_item_detail_omits_claims_and_evidence() -> None:
    item = models.ItemSummary(
        id=UUID("019b0000-0000-7000-8000-000000004001"),
        publication_revision_id=None,
        domain="SAFETY",
        content_type="SAFETY_REGULATION",
        title="生产安全事故应急预案管理办法",
        source_name="应急管理部",
        source_published_at=datetime(2016, 6, 3, 10, 28, tzinfo=UTC),
        first_discovered_at=datetime(2026, 7, 14, 1, 9, 4, tzinfo=UTC),
        activity_at=datetime(2026, 7, 14, 1, 9, 4, tzinfo=UTC),
        original_url="https://www.mem.gov.cn/example.shtml",
        review_status="PENDING",
    )
    detail = models.ItemDetail(
        item=item,
        notice=models.FeedNotice(
            code="R3_RESTRICTED",
            level="info",
            message="待人工审核; 暂不展示敏感字段。",
        ),
    )

    payload = detail.model_dump(mode="json", exclude_unset=True)

    assert payload["item"]["publication_revision_id"] is None
    assert "claims" not in payload
    assert "evidence" not in payload


def test_review_contract_exposes_bidirectional_claim_evidence_and_decision_shape() -> None:
    evidence_id = UUID("019b0000-0000-7000-8000-000000004011")
    claim = models.ClaimView(
        id=UUID("019b0000-0000-7000-8000-000000004010"),
        claim_type="document_number",
        label="文号",
        value="国家安全生产监督管理总局令第88号",
        evidence_ids=[evidence_id],
    )
    evidence = models.EvidenceView(
        id=evidence_id,
        claim_ids=[claim.id],
        paragraph_id="html-p-0002",
        char_start=18,
        char_end=38,
        excerpt="国家安全生产监督管理总局令第88号",
        excerpt_sha256="a" * 64,
        original_url="https://www.mem.gov.cn/example.shtml",
    )
    request = models.ReviewDecisionRequest(action="APPROVE", reason="字段与证据一致")

    assert claim.evidence_ids == [evidence.id]
    assert evidence.claim_ids == [claim.id]
    assert request.model_dump() == {
        "action": "APPROVE",
        "reason": "字段与证据一致",
        "digital_case_patch": None,
    }
