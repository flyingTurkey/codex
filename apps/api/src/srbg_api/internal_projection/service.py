"""Ordinary content service backed only by the low-privilege published_v1 reader."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from srbg_contracts import (
    DailyReport,
    EventAutomaticResultView,
    EventDetail,
    EventStatus,
    EventSummary,
    EventTimeline,
    EventType,
    FeedPage,
    ItemDetail,
    PublishedClaimV1,
    PublishedEventSummaryV1,
    PublishedEvidenceReferenceV1,
)

from srbg_api.internal_projection.reader import PublishedEventNotFound, PublishedProjectionReader

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
        summaries = self._collapse_event_summaries(
            [self._summary(value) for value in values]
            + [self._personal_summary(value) for value in personal]
        )
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

    @staticmethod
    def _collapse_event_summaries(summaries: list[EventSummary]) -> list[EventSummary]:
        """Keep the strongest projection when old metadata and personal evidence overlap."""

        def rank(value: EventSummary) -> tuple[int, datetime]:
            if value.publication_revision_id is not None:
                projection_rank = 2
            elif value.automatic_result_type == "EVIDENCE_FACT":
                projection_rank = 1
            else:
                projection_rank = 0
            return projection_rank, value.activity_at

        selected: dict[UUID, EventSummary] = {}
        for summary in summaries:
            current = selected.get(summary.id)
            if current is None or rank(summary) > rank(current):
                selected[summary.id] = summary
        return list(selected.values())

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
        personal_signals = await self._reader.list_personal_signals_for_event(event_id)
        try:
            value = await self._reader.get_event(event_id)
        except PublishedEventNotFound:
            if not personal_signals:
                raise
            return self._personal_event_detail(event_id, personal_signals)
        personal_claims, personal_evidence = self._personal_claims_and_evidence(personal_signals)
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
            claims=value.claims or personal_claims,
            evidence=value.evidence or personal_evidence,
            documents=value.documents,
            source_comparison=value.source_comparison,
            type_detail=value.type_detail,
            automatic_results=self._automatic_results(personal_signals),
        )

    @staticmethod
    def _automatic_results(signals: list[dict[str, Any]]) -> list[EventAutomaticResultView]:
        return [
            EventAutomaticResultView(
                signal_id=signal["signal_id"],
                result_type=signal["result_type"],
                title=signal["payload"]["title"],
                original_url=signal["payload"]["original_url"],
                judgment=(
                    signal["payload"].get("judgment")
                    if signal["result_type"] in {"AI_JUDGMENT", "UNVERIFIED_AI"}
                    else None
                ),
                failure_reason_codes=signal["payload"].get("failure_reason_codes", []),
            )
            for signal in signals
        ]

    def _personal_event_detail(
        self, event_id: UUID, personal_signals: list[dict[str, Any]]
    ) -> EventDetail:
        primary = personal_signals[0]
        payload = primary["payload"]
        claims, evidence = self._personal_claims_and_evidence(personal_signals)
        return EventDetail(
            id=event_id,
            title=payload["title"],
            event_type=EventType(payload["event_type"]),
            event_status=EventStatus.ACTIVE,
            canonical_event_id=event_id,
            event_version=max(int(signal.get("generation", 1)) for signal in personal_signals),
            confirmed_facts=[],
            unverified_facts=[],
            timeline=EventTimeline(event_id=event_id, items=[]),
            relations=[],
            similar_scenario_tags=[],
            prevention_measure_tags=[],
            claims=claims,
            evidence=evidence,
            automatic_results=self._automatic_results(personal_signals),
        )

    @staticmethod
    def _personal_claims_and_evidence(
        personal_signals: list[dict[str, Any]],
    ) -> tuple[list[PublishedClaimV1], list[PublishedEvidenceReferenceV1]]:
        evidence_by_id: dict[UUID, PublishedEvidenceReferenceV1] = {}
        claims: list[PublishedClaimV1] = []
        for signal in personal_signals:
            if signal["result_type"] != "EVIDENCE_FACT":
                continue
            for fact in signal["payload"].get("evidence_facts", []):
                evidence_ids: list[UUID] = []
                for evidence in fact.get("evidence", []):
                    evidence_id = UUID(str(evidence["evidence_id"]))
                    evidence_ids.append(evidence_id)
                    evidence_by_id[evidence_id] = PublishedEvidenceReferenceV1(
                        evidence_id=evidence_id,
                        locator=str(evidence["locator"]),
                        content_sha256=str(evidence["excerpt_sha256"]),
                    )
                if evidence_ids:
                    claims.append(
                        PublishedClaimV1(
                            claim_id=UUID(str(fact["claim_id"])),
                            field_name=str(fact["field_name"]),
                            value=str(fact["value"]),
                            evidence_ids=evidence_ids,
                        )
                    )
        return claims, list(evidence_by_id.values())

    async def resolve_event_redirect(self, event_id: UUID) -> UUID | None:
        return await self._reader.resolve_event_redirect(event_id)
