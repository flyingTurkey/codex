"""Low-privilege shadow reader; it intentionally knows no business-schema objects."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import PublishedEventDetailV1, PublishedEventSummaryV1


class PublishedEventNotFound(LookupError):
    pass


class PublishedProjectionReader:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

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
