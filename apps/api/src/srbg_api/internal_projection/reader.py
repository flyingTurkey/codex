"""Low-privilege shadow reader; it intentionally knows no business-schema objects."""

from __future__ import annotations

from datetime import date
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import (
    DailyReport,
    DailyReportItem,
    DailyReportSection,
    PublishedEventDetailV1,
    PublishedEventSummaryV1,
)


class PublishedEventNotFound(LookupError):
    pass


class PublishedProjectionReader:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def list_events(self, *, limit: int = 50) -> list[PublishedEventSummaryV1]:
        bounded_limit = max(1, min(limit, 100))
        async with self._engine.connect() as connection:
            payloads = list(
                await connection.scalars(
                    text(
                        "SELECT summary_payload FROM published_v1.current_event_summary "
                        "ORDER BY generated_at DESC, event_id DESC LIMIT :limit"
                    ),
                    {"limit": bounded_limit},
                )
            )
        return [PublishedEventSummaryV1.model_validate(payload) for payload in payloads]

    async def resolve_event_redirect(self, event_id: UUID) -> UUID | None:
        async with self._engine.connect() as connection:
            resolved = await connection.scalar(
                text(
                    "SELECT canonical_event_id FROM published_v1.event_redirect "
                    "WHERE event_id=:event_id"
                ),
                {"event_id": event_id},
            )
        return cast(UUID | None, resolved)

    async def get_event(self, event_id: UUID) -> PublishedEventDetailV1:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT summary.summary_payload, detail.detail_payload "
                            "FROM published_v1.current_event_summary summary "
                            "LEFT JOIN published_v1.current_event_detail detail "
                            "USING (event_id, generation) WHERE summary.event_id = :event_id"
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise PublishedEventNotFound(str(event_id))
        payload = row["detail_payload"] or {
            "summary": row["summary_payload"],
            "claims": [],
            "evidence": [],
        }
        return PublishedEventDetailV1.model_validate(payload)

    async def title_search(self, query: str, *, limit: int = 20) -> list[PublishedEventSummaryV1]:
        normalized = query.strip()
        if not normalized or len(normalized) > 200:
            return []
        bounded_limit = max(1, min(limit, 100))
        async with self._engine.connect() as connection:
            payloads = list(
                await connection.scalars(
                    text(
                        """
                        SELECT summary.summary_payload
                          FROM published_v1.title_search search
                          JOIN published_v1.current_event_summary summary
                            USING (event_id, generation)
                         WHERE search.title ILIKE :query
                         ORDER BY search.event_id DESC LIMIT :limit
                        """
                    ),
                    {"query": f"%{normalized}%", "limit": bounded_limit},
                )
            )
        return [PublishedEventSummaryV1.model_validate(payload) for payload in payloads]

    async def get_daily_report(
        self, *, report_id: UUID | None = None, report_date: date | None = None
    ) -> DailyReport:
        async with self._engine.connect() as connection:
            report = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM published_v1.daily_report "
                            "WHERE (:report_id IS NULL OR id=:report_id) "
                            "AND (:report_date IS NULL OR report_date=:report_date) "
                            "ORDER BY report_date DESC, published_at DESC LIMIT 1"
                        ),
                        {"report_id": report_id, "report_date": report_date},
                    )
                )
                .mappings()
                .first()
            )
            if report is None:
                raise PublishedEventNotFound("daily report")
            rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM published_v1.daily_report_event "
                            "WHERE report_id=:report_id ORDER BY section, position"
                        ),
                        {"report_id": report["id"]},
                    )
                )
                .mappings()
                .all()
            )
        titles: dict[
            Literal[
                "TODAY_HIGHLIGHTS",
                "DIGITAL_SELECTED",
                "SAFETY_HIGHLIGHTS",
                "WATCHLIST",
                "SOURCE_ANOMALIES",
            ],
            str,
        ] = {
            "TODAY_HIGHLIGHTS": "今日重点",
            "DIGITAL_SELECTED": "数字化精选",
            "SAFETY_HIGHLIGHTS": "安全重点",
            "WATCHLIST": "持续关注",
            "SOURCE_ANOMALIES": "来源异常",
        }
        return DailyReport(
            id=report["id"],
            report_date=report["report_date"],
            status="PUBLISHED",
            snapshot_at=report["snapshot_at"],
            published_at=report["published_at"],
            requires_regeneration=False,
            sections=[
                DailyReportSection(
                    kind=kind,
                    title=title,
                    items=[
                        DailyReportItem.model_validate(row)
                        for row in rows
                        if row["section"] == kind
                    ],
                )
                for kind, title in titles.items()
            ],
        )
