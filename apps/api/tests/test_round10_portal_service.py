from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from srbg_api.auth import Principal
from srbg_api.discovery.repository import SearchHit
from srbg_api.discovery.service import PortalApplicationService
from srbg_contracts import (
    Channel,
    DailyReport,
    DailyReportItem,
    DailyReportSection,
    EventSummary,
    ItemType,
    ReviewStatus,
)

ITEM_ID = UUID("019b0000-0000-7000-8000-000000001001")
REVISION_ID = UUID("019b0000-0000-7000-8000-000000001002")
REPORT_ID = UUID("019b0000-0000-7000-8000-000000001003")
NOW = datetime(2026, 7, 15, tzinfo=UTC)
PRINCIPAL = Principal(
    user_id=UUID("019b0000-0000-7000-8000-000000009001"),
    display_name="viewer",
    roles=frozenset(),
    local_identity=True,
)
DOCUMENT_NUMBER = "川交规\u30142026\u301510号"


def _summary() -> EventSummary:
    return EventSummary(
        id=ITEM_ID,
        publication_revision_id=REVISION_ID,
        domain=Channel.SAFETY,
        content_type=ItemType.SAFETY_REGULATION,
        title=f"{DOCUMENT_NUMBER}隧道监测预警规定",
        source_name="四川省交通运输厅",
        source_published_at=NOW,
        first_discovered_at=NOW,
        activity_at=NOW,
        original_url="https://example.com/item",
        review_status=ReviewStatus.APPROVED,
        event_type="REGULATION_CHANGE",
        event_status="ACTIVE",
        canonical_event_id=ITEM_ID,
        event_version=1,
    )


class FakeIntelligence:
    async def get_item(self, item_id: UUID) -> SimpleNamespace:
        assert item_id == ITEM_ID
        return SimpleNamespace(item=_summary())

    async def get_event_summary_for_item(self, item_id: UUID) -> EventSummary:
        assert item_id == ITEM_ID
        return _summary()


class FakeRepository:
    async def close(self) -> None:
        pass

    async def search(self, **_: object):
        return (
            [
                SearchHit(
                    item_id=ITEM_ID,
                    match_kind="EXACT_IDENTIFIER",
                    score_bps=10000,
                    activity_at=NOW,
                    matched_fields=("DOCUMENT_NUMBER",),
                    matched_identifiers=(DOCUMENT_NUMBER,),
                )
            ],
            None,
            7,
        )

    async def get_report(self, **_: object) -> DailyReport:
        return DailyReport(
            id=REPORT_ID,
            report_date=date(2026, 7, 15),
            status="PUBLISHED",
            snapshot_at=NOW,
            published_at=NOW,
            requires_regeneration=False,
            sections=[
                DailyReportSection(
                    kind="TODAY_HIGHLIGHTS",
                    title="今日|重点",
                    items=[
                        DailyReportItem(
                            item_id=ITEM_ID,
                            publication_revision_id=REVISION_ID,
                            position=1,
                            title="=2+2 | 隧道",
                            summary="已接受\n事实",
                            current_state="PUBLISHED",
                            original_url="https://example.com/item",
                        )
                    ],
                )
            ],
        )


@pytest.mark.asyncio
async def test_search_reuses_item_summary_and_exposes_bounded_match_context() -> None:
    service = PortalApplicationService(
        repository=FakeRepository(),
        intelligence=FakeIntelligence(),
        cursor_signing_key=b"round10-test-key-with-at-least-32-bytes",
    )

    page = await service.search(
        query=DOCUMENT_NUMBER,
        tokens=(DOCUMENT_NUMBER,),
        domain=None,
        content_type=None,
        region=None,
        source_id=None,
        evidence_status=None,
        sort="relevance",
        cursor=None,
        limit=20,
        principal=PRINCIPAL,
    )

    assert page.items[0].id == ITEM_ID
    assert page.items[0].search_context is not None
    assert page.items[0].search_context.match_kind == "EXACT_IDENTIFIER"
    assert page.items[0].search_context.matched_identifiers == [DOCUMENT_NUMBER]
    assert page.fingerprint == "search:7"


@pytest.mark.asyncio
async def test_markdown_export_uses_snapshot_and_escapes_formula_and_markdown() -> None:
    service = PortalApplicationService(
        repository=FakeRepository(),
        intelligence=FakeIntelligence(),
        cursor_signing_key=b"round10-test-key-with-at-least-32-bytes",
    )

    markdown = await service.export_markdown(report_id=REPORT_ID, principal=PRINCIPAL)

    assert "## 今日\\|重点" in markdown
    assert "'=2+2 \\| 隧道" in markdown
    assert "已接受 事实" in markdown
    assert "https://example.com/item" in markdown
