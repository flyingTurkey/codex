"""Low-privilege shadow reader; it intentionally knows no business-schema objects."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, cast
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

    async def list_personal_signals(self, *, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 100))
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT id AS signal_id,event_id,result_type,payload,generation "
                            "FROM personal_signal_projection WHERE visible "
                            "ORDER BY updated_at DESC,id DESC LIMIT :limit"
                        ),
                        {"limit": bounded_limit},
                    )
                ).mappings()
            )
        return [dict(row) for row in rows]

    async def search_personal_primary(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        return await self._search_personal_table(
            "personal_primary_search_projection", query, limit=limit
        )

    async def search_personal_unverified(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        return await self._search_personal_table(
            "unverified_ai_search_projection", query, limit=limit
        )

    async def _search_personal_table(
        self, table: str, query: str, *, limit: int
    ) -> list[dict[str, Any]]:
        normalized = query.strip()
        if not normalized or len(normalized) > 200:
            return []
        if table not in {
            "personal_primary_search_projection",
            "unverified_ai_search_projection",
        }:
            raise ValueError("personal search table is not allowed")
        bounded_limit = max(1, min(limit, 100))
        search_sql = (
            """
            SELECT signal.id AS signal_id,signal.event_id,signal.result_type,
              signal.payload,signal.generation,search.activity_at
            FROM personal_primary_search_projection search
            JOIN personal_signal_projection signal ON signal.id=search.signal_id
            WHERE search.visible AND signal.visible
              AND (search.search_vector @@ plainto_tsquery('simple',:query)
                OR search.title ILIKE :like_query)
            ORDER BY search.activity_at DESC,search.signal_id DESC LIMIT :limit
            """
            if table == "personal_primary_search_projection"
            else """
            SELECT signal.id AS signal_id,signal.event_id,signal.result_type,
              signal.payload,signal.generation,search.activity_at
            FROM unverified_ai_search_projection search
            JOIN personal_signal_projection signal ON signal.id=search.signal_id
            WHERE search.visible AND signal.visible
              AND (search.search_vector @@ plainto_tsquery('simple',:query)
                OR search.title ILIKE :like_query)
            ORDER BY search.activity_at DESC,search.signal_id DESC LIMIT :limit
            """
        )
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(search_sql),
                        {
                            "query": normalized,
                            "like_query": f"%{normalized}%",
                            "limit": bounded_limit,
                        },
                    )
                ).mappings()
            )
        return [dict(row) for row in rows]

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
                    kind=cast(Any, kind),
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

    async def get_personal_daily_report(
        self, *, report_date: date | None = None
    ) -> DailyReport | None:
        async with self._engine.connect() as connection:
            report = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM personal_daily_report_projection "
                            "WHERE visible AND (:report_date IS NULL OR report_date=:report_date) "
                            "ORDER BY report_date DESC,generation DESC LIMIT 1"
                        ),
                        {"report_date": report_date},
                    )
                )
                .mappings()
                .first()
            )
            if report is None:
                return None
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT daily.section,daily.position,signal.id AS signal_id,
                              signal.event_id,signal.result_type,signal.payload
                            FROM personal_daily_signal_projection daily
                            JOIN personal_signal_projection signal ON signal.id=daily.signal_id
                            WHERE daily.report_id=:report_id AND signal.visible
                            ORDER BY daily.section,daily.position
                            """
                        ),
                        {"report_id": report["id"]},
                    )
                ).mappings()
            )
        titles = (("EVIDENCE_FACTS", "证据事实"), ("UNVERIFIED_AI", "未验证 AI"))
        return DailyReport(
            id=report["id"],
            report_date=report["report_date"],
            status="PUBLISHED",
            snapshot_at=report["snapshot_at"],
            published_at=report["snapshot_at"],
            requires_regeneration=False,
            sections=[
                DailyReportSection(
                    kind=cast(Any, kind),
                    title=title,
                    items=[
                        DailyReportItem(
                            signal_id=row["signal_id"],
                            event_id=row["event_id"],
                            automatic_result_type=row["result_type"],
                            position=row["position"],
                            title=row["payload"]["title"],
                            summary=(
                                row["payload"].get("judgment", {}).get("why_worth_attention")
                                if row["result_type"] == "UNVERIFIED_AI"
                                else None
                            ),
                            current_state="PUBLISHED",
                            original_url=row["payload"]["original_url"],
                        )
                        for row in rows
                        if row["section"] == kind
                    ],
                )
                for kind, title in titles
            ],
        )
