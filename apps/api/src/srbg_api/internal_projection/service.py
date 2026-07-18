"""Ordinary content service backed only by the low-privilege published_v1 reader."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from srbg_contracts import (
    DailyReport,
    EventDetail,
    EventStatus,
    EventSummary,
    EventTimeline,
    EventType,
    FeedPage,
    ItemDetail,
    PublishedEventDetailV1,
    PublishedEventSummaryV1,
)

from srbg_api.internal_projection.reader import PublishedProjectionReader

_EVENT_TYPE_BY_CONTENT_TYPE = {
    "DIGITAL_CASE": EventType.DIGITAL_PROJECT,
    "JOURNAL_PAPER": EventType.RESEARCH_RESULT,
    "SOFTWARE_PRODUCT": EventType.PRODUCT_RELEASE,
    "IOT_PRODUCT": EventType.PRODUCT_RELEASE,
    "LOW_ALTITUDE_EQUIPMENT": EventType.PRODUCT_RELEASE,
    "AI_EQUIPMENT": EventType.PRODUCT_RELEASE,
    "SAFETY_REGULATION": EventType.REGULATION_CHANGE,
    "SAFETY_CASE": EventType.SAFETY_INCIDENT,
}


class PublishedIntelligenceQueryService:
    """Adapts versioned projection payloads to the stable public Event contracts."""

    def __init__(self, reader: PublishedProjectionReader) -> None:
        self._reader = reader

    async def close(self) -> None:
        await self._reader.close()

    @staticmethod
    def _summary(value: PublishedEventSummaryV1) -> EventSummary:
        event_type = value.event_type or _EVENT_TYPE_BY_CONTENT_TYPE[value.content_type.value]
        return EventSummary(
            id=value.id,
            publication_revision_id=value.publication_revision_id,
            domain=value.domain,
            content_type=value.content_type,
            title=value.title,
            source_name=value.source_name,
            source_published_at=value.source_published_at,
            first_discovered_at=value.first_discovered_at,
            activity_at=value.source_published_at or value.first_discovered_at,
            original_url=value.original_url,
            review_status=value.review_status,
            one_sentence_fact=value.one_sentence_fact,
            type_summary=value.type_summary,
            event_type=event_type,
            event_status=value.event_status,
            canonical_event_id=value.canonical_event_id or value.id,
            event_version=value.event_version,
        )

    @staticmethod
    def _personal_summary(value: dict[str, Any]) -> EventSummary:
        payload = value["payload"]
        result_type = value["result_type"]
        return EventSummary(
            id=value["event_id"],
            signal_id=value["signal_id"],
            automatic_result_type=result_type,
            publication_revision_id=None,
            domain=payload["domain"],
            content_type=payload["content_type"],
            title=payload["title"],
            source_name=payload["source_name"],
            source_published_at=payload.get("source_published_at"),
            first_discovered_at=payload["first_discovered_at"],
            activity_at=payload["activity_at"],
            original_url=payload["original_url"],
            review_status=payload["review_status"],
            event_type=payload["event_type"],
            event_status=EventStatus.ACTIVE,
            canonical_event_id=value["event_id"],
            event_version=max(1, int(value.get("generation", 1))),
            ai_judgment=(
                payload.get("judgment") if result_type in {"AI_JUDGMENT", "UNVERIFIED_AI"} else None
            ),
            processing_failure_reasons=payload.get("failure_reason_codes", []),
        )

    async def get_feed(self, **filters: Any) -> FeedPage:
        limit = int(filters.get("limit", 20))
        values, personal = await asyncio.gather(
            self._reader.list_events(limit=limit),
            self._reader.list_personal_signals(limit=limit),
        )
        domain = filters.get("domain")
        content_type = filters.get("content_type")
        summaries = [self._summary(value) for value in values] + [
            self._personal_summary(value) for value in personal
        ]
        if domain:
            summaries = [value for value in summaries if value.domain.value == domain.upper()]
        if content_type:
            summaries = [value for value in summaries if value.content_type.value == content_type]
        return FeedPage(
            items=sorted(summaries, key=lambda value: value.activity_at, reverse=True)[:limit],
            next_cursor=None,
            fingerprint="published-v1:event",
            generated_at=datetime.now(UTC),
            freshness="fresh",
            notices=[],
        )

    async def get_event_summary(self, event_id: UUID) -> EventSummary:
        return self._summary((await self._reader.get_event(event_id)).summary)

    async def get_item(self, item_id: UUID) -> ItemDetail:
        raise RuntimeError("legacy Item reads must use the compatibility projection")

    async def get_event_summary_for_item(self, item_id: UUID) -> EventSummary:
        raise RuntimeError("legacy Item reads must resolve through the immutable alias")

    async def search_events(self, query: str, *, limit: int) -> list[EventSummary]:
        published, primary, unverified = await asyncio.gather(
            self._reader.title_search(query, limit=limit),
            self._reader.search_personal_primary(query, limit=limit),
            self._reader.search_personal_unverified(query, limit=limit),
        )
        values = [self._summary(value) for value in published] + [
            self._personal_summary(value) for value in [*primary, *unverified]
        ]
        return sorted(values, key=lambda value: value.activity_at, reverse=True)[:limit]

    async def get_daily_report(
        self, *, report_id: UUID | None = None, report_date: Any = None
    ) -> DailyReport:
        if report_id is None:
            personal = await self._reader.get_personal_daily_report(report_date=report_date)
            if personal is not None:
                return personal
        return await self._reader.get_daily_report(report_id=report_id, report_date=report_date)

    async def get_event(self, event_id: UUID) -> EventDetail:
        value: PublishedEventDetailV1 = await self._reader.get_event(event_id)
        summary = value.summary
        event_type = summary.event_type or _EVENT_TYPE_BY_CONTENT_TYPE[summary.content_type.value]
        return EventDetail(
            id=summary.id,
            title=summary.title,
            event_type=event_type,
            event_status=summary.event_status,
            canonical_event_id=summary.canonical_event_id or summary.id,
            event_version=summary.event_version,
            confirmed_facts=[],
            unverified_facts=[],
            timeline=EventTimeline(event_id=summary.id, items=[]),
            relations=[],
            similar_scenario_tags=[],
            prevention_measure_tags=[],
            summary=summary,
            claims=value.claims,
            evidence=value.evidence,
            documents=value.documents,
            source_comparison=value.source_comparison,
            type_detail=value.type_detail,
        )

    async def resolve_event_redirect(self, event_id: UUID) -> UUID | None:
        return await self._reader.resolve_event_redirect(event_id)
