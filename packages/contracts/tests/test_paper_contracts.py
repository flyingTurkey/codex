from datetime import UTC, datetime
from uuid import UUID

import srbg_contracts.models as models


def test_paper_summary_and_detail_keep_access_and_research_maturity_explicit() -> None:
    summary = models.PaperTypeSummary(
        kind="JOURNAL_PAPER",
        doi="10.1000/bridge.2025.1",
        journal="中国公路学报",
        year=2025,
        paper_type="ARTICLE",
        access_level="METADATA_ONLY",
        open_status="CLOSED",
        maturity_level="LAB_PROTOTYPE",
        engineering_domains=["BRIDGE"],
        technology_tags=["DIGITAL_TWIN"],
        relation_status="CURRENT",
        ai_short_comment=None,
    )
    item = models.ItemSummary(
        id=UUID("019b0000-0000-7000-8000-000000006100"),
        publication_revision_id=UUID("019b0000-0000-7000-8000-000000006101"),
        domain="DIGITAL",
        content_type="JOURNAL_PAPER",
        title="桥梁数字孪生研究",
        source_name="OpenAlex",
        source_published_at=datetime(2025, 7, 1, tzinfo=UTC),
        first_discovered_at=datetime(2026, 7, 15, tzinfo=UTC),
        activity_at=datetime(2026, 7, 15, tzinfo=UTC),
        original_url="https://doi.org/10.1000/bridge.2025.1",
        review_status="APPROVED",
        type_summary=summary,
    )
    detail = models.ItemDetail(
        item=item,
        paper=models.PaperDetail(
            doi=summary.doi,
            journal=summary.journal,
            issns=["1001-7372"],
            authors=[models.PaperAuthor(name="张三", orcid=None, institutions=["西南交通大学"])],
            volume="38",
            issue="7",
            pages="1-12",
            year=2025,
            abstract=None,
            abstract_availability="LICENCE_UNCLEAR",
            keywords=["桥梁", "数字孪生"],
            access_level="METADATA_ONLY",
            open_status="CLOSED",
            open_fulltext_url=None,
            maturity_level="LAB_PROTOTYPE",
            engineering_domains=["BRIDGE"],
            technology_tags=["DIGITAL_TWIN"],
            research_interpretation=models.ResearchInterpretation(
                research_object="桥梁监测",
                method="实验室数据验证",
                conditions=["实验室数据集"],
                conclusions=["方法在样本内有效"],
                limitations=["未提供工程生产部署证据"],
                claim_ids=[UUID("019b0000-0000-7000-8000-000000006102")],
                evidence_ids=[UUID("019b0000-0000-7000-8000-000000006103")],
            ),
            similar_papers=[],
            relation_status="CURRENT",
        ),
    )
    assert detail.paper is not None
    assert detail.paper.abstract is None
    assert detail.paper.abstract_availability is models.AbstractAvailability.LICENCE_UNCLEAR
    assert detail.item.type_summary.kind == "JOURNAL_PAPER"
