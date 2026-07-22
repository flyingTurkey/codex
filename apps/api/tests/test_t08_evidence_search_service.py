from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.intelligence_v2.service import PostgresV2IntelligenceService

pytestmark = pytest.mark.asyncio

EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000811")
CLAIM_ID = UUID("019f7c00-0000-7000-8000-000000000812")
NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


class _Rows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self._rows


class _Connection:
    def __init__(self, rows: list[dict[str, object]], statements: list[str]) -> None:
        self._rows = rows
        self._statements = statements

    async def execute(self, _statement: object, _parameters: object) -> _Rows:
        self._statements.append(str(_statement))
        return _Rows(self._rows)


class _Engine:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.statements: list[str] = []

    @asynccontextmanager
    async def connect(self):
        yield _Connection(self._rows, self.statements)

    async def dispose(self) -> None:
        pass


def _full_payload() -> dict[str, object]:
    return {
        "projection_kind": "FULL",
        "event_id": str(EVENT_ID),
        "title": "铁路隧道安全监测更新",
        "primary_type": "SAFETY_INTELLIGENCE",
        "facets": {"engineering_objects": ["RAILWAY", "TUNNEL"]},
        "source": {"name": "国家铁路局", "official": True},
        "human_reviewed": True,
        "source_published_at": None,
        "first_discovered_at": None,
        "source_excerpt": {
            "text": "原文说明铁路隧道安全监测系统完成更新。",
            "claim_ids": [str(CLAIM_ID)],
            "evidence_locators": ["html:p:8"],
        },
        "ai_summary": {"status": "NOT_GENERATED"},
        "original_url": "https://example.gov.cn/tunnel/1",
        "claim_basis": ["AUTHORITY_FINDING"],
    }


async def test_search_explains_evidence_fields_and_low_weight_ai_assistance() -> None:
    rows = [
        {
            "payload": _full_payload(),
            "projected_at": NOW,
            "event_id": EVENT_ID,
            "rank_q": 100,
            "title_match": True,
            "source_match": False,
            "claims_match": True,
            "excerpt_match": True,
            "ai_match": True,
        }
    ]
    engine = _Engine(rows)
    service = PostgresV2IntelligenceService(engine, engine)  # type: ignore[arg-type]

    page = await service.search(query="铁路隧道", limit=20)

    item = page.items[0]
    assert item.projection_kind == "FULL"
    assert item.search_explanation is not None
    assert item.search_explanation.matched_evidence_fields == [
        "TITLE",
        "ACCEPTED_CLAIMS",
        "SOURCE_EXCERPT",
    ]
    assert item.search_explanation.ai_summary_assisted is True


async def test_feed_types_nullable_filters_for_asyncpg() -> None:
    engine = _Engine([])
    service = PostgresV2IntelligenceService(engine, engine)  # type: ignore[arg-type]

    page = await service.feed(limit=1, primary_type=None)

    assert page.items == []
    assert "CAST(:primary_type AS varchar) IS NULL" in engine.statements[0]
    assert "CAST(:cursor_time AS timestamptz) IS NULL" in engine.statements[0]
