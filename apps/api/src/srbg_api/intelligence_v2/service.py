"""Application boundary and PostgreSQL implementation for v2 projections."""

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import (
    EventAppendixV2,
    EventProjectionV2,
    FeedPageV2,
    ReviewCaseV2,
    ReviewDecisionCommandV2,
    ReviewDecisionReceiptV2,
)

from srbg_api.config import get_settings
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.cursor import InvalidV2Cursor, V2CursorCodec


class ProjectionNotFound(LookupError):
    """The Event has no projection visible at the requested boundary."""


class ReviewConflict(RuntimeError):
    """The review case changed since the Owner read it."""


_PROJECTION_ADAPTER: TypeAdapter[EventProjectionV2] = TypeAdapter(EventProjectionV2)
_APPENDIX_ADAPTER: TypeAdapter[EventAppendixV2] = TypeAdapter(EventAppendixV2)

_REVIEW_COLUMNS = (
    "SELECT review.id AS case_id,review.event_id,review.document_version_id,review.reason,"
    "review.risk_tier,review.safe_metadata,review.state,review.version,review.created_at,"
    "review.updated_at,CASE "
    "WHEN EXISTS(SELECT 1 FROM owner_review_reprocessing_outbox_v2 outbox "
    "WHERE outbox.case_id=review.id AND outbox.status='PROCESSING') THEN 'PROCESSING' "
    "WHEN EXISTS(SELECT 1 FROM owner_review_reprocessing_outbox_v2 outbox "
    "WHERE outbox.case_id=review.id AND outbox.status='PENDING') THEN 'QUEUED' "
    "WHEN EXISTS(SELECT 1 FROM owner_review_reprocessing_outbox_v2 outbox "
    "WHERE outbox.case_id=review.id AND outbox.status IN ('FAILED','DEAD_LETTER')) THEN 'FAILED' "
    "ELSE 'IDLE' END AS processing_state FROM owner_review_case_v2 review"
)


def _limit(filters: dict[str, object]) -> int:
    value = filters.get("limit", 20)
    return max(1, min(value if isinstance(value, int) else 20, 100))


class V2ObjectStore(Protocol):
    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes: ...
    async def presigned_get(self, key: str, *, max_age_seconds: int) -> str: ...


class PostgresV2IntelligenceService:
    """Reads only v2 projection rows and appends Owner decisions transactionally."""

    def __init__(
        self,
        reader_engine: AsyncEngine,
        writer_engine: AsyncEngine,
        object_store: V2ObjectStore | None = None,
    ) -> None:
        self._reader = reader_engine
        self._writer = writer_engine
        self._objects = object_store
        self._cursors = V2CursorCodec(
            get_settings().cursor_signing_key.get_secret_value().encode()
        )

    async def close(self) -> None:
        await self._reader.dispose()
        await self._writer.dispose()

    async def _page(
        self,
        sql: str,
        parameters: dict[str, object],
        *,
        surface: str,
        filters: dict[str, object],
        cursor_columns: tuple[str, ...],
    ) -> FeedPageV2:
        raw_limit = parameters["limit"]
        limit = raw_limit if isinstance(raw_limit, int) else 20
        query_parameters = parameters | {"row_limit": limit + 1}
        async with self._reader.connect() as connection:
            rows = list((await connection.execute(text(sql), query_parameters)).mappings())
        visible = rows[:limit]
        next_cursor = None
        if len(rows) > limit and visible:
            last = visible[-1]
            next_cursor = self._cursors.encode(
                surface=surface,
                sort_values=tuple(str(last[column]) for column in cursor_columns),
                filters=filters,
            )
        return FeedPageV2(
            items=[_PROJECTION_ADAPTER.validate_python(row["payload"]) for row in visible],
            next_cursor=next_cursor,
            generated_at=datetime.now(UTC),
        )

    async def feed(self, **filters: object) -> FeedPageV2:
        limit = _limit(filters)
        primary_type = filters.get("primary_type")
        binding: dict[str, object] = {
            "primary_type": str(primary_type) if primary_type else None
        }
        cursor_time: datetime | None = None
        cursor_id: UUID | None = None
        cursor = filters.get("cursor")
        if isinstance(cursor, str):
            try:
                values = self._cursors.decode(
                    cursor, surface="feed", filters=binding, expected_values=2
                )
                cursor_time, cursor_id = datetime.fromisoformat(values[0]), UUID(values[1])
            except (ValueError, TypeError) as exc:
                raise InvalidV2Cursor("invalid feed cursor") from exc
        sql = (
            "SELECT payload,projected_at,event_id FROM intelligence_projection_v2 "
            "WHERE (:primary_type IS NULL OR primary_type=:primary_type) "
            "AND (:cursor_time IS NULL OR (projected_at,event_id)<"
            "(CAST(:cursor_time AS timestamptz),CAST(:cursor_id AS uuid))) "
            "ORDER BY projected_at DESC,event_id DESC LIMIT :row_limit"
        )
        return await self._page(
            sql,
            {
                "limit": limit,
                "primary_type": primary_type,
                "cursor_time": cursor_time,
                "cursor_id": cursor_id,
            },
            surface="feed",
            filters=binding,
            cursor_columns=("projected_at", "event_id"),
        )

    async def search(self, **filters: object) -> FeedPageV2:
        limit = _limit(filters)
        query = str(filters.get("query", ""))
        binding: dict[str, object] = {"q": query}
        cursor_rank: int | None = None
        cursor_time: datetime | None = None
        cursor_id: UUID | None = None
        cursor = filters.get("cursor")
        if isinstance(cursor, str):
            try:
                values = self._cursors.decode(
                    cursor, surface="search", filters=binding, expected_values=3
                )
                cursor_rank = int(values[0])
                cursor_time, cursor_id = datetime.fromisoformat(values[1]), UUID(values[2])
            except (ValueError, TypeError) as exc:
                raise InvalidV2Cursor("invalid search cursor") from exc
        return await self._page(
            "WITH ranked AS (SELECT projection.payload,projection.projected_at,"
            "projection.event_id,floor(ts_rank(search.search_vector,"
            "plainto_tsquery('simple',:query))*1000000)::bigint AS rank_q "
            "FROM search_projection_v2 search JOIN intelligence_projection_v2 projection "
            "ON projection.event_id=search.event_id WHERE search.search_vector @@ "
            "plainto_tsquery('simple',:query)) SELECT payload,projected_at,event_id,rank_q "
            "FROM ranked WHERE :cursor_rank IS NULL OR rank_q<:cursor_rank OR "
            "(rank_q=:cursor_rank AND (projected_at,event_id)<"
            "(CAST(:cursor_time AS timestamptz),CAST(:cursor_id AS uuid))) "
            "ORDER BY rank_q DESC,projected_at DESC,event_id DESC LIMIT :row_limit",
            {
                "query": query,
                "limit": limit,
                "cursor_rank": cursor_rank,
                "cursor_time": cursor_time,
                "cursor_id": cursor_id,
            },
            surface="search",
            filters=binding,
            cursor_columns=("rank_q", "projected_at", "event_id"),
        )

    async def hotspots(self, **filters: object) -> FeedPageV2:
        limit = _limit(filters)
        cursor_time: datetime | None = None
        cursor_id: UUID | None = None
        cursor = filters.get("cursor")
        if isinstance(cursor, str):
            try:
                values = self._cursors.decode(
                    cursor, surface="hotspots", filters={}, expected_values=2
                )
                cursor_time, cursor_id = datetime.fromisoformat(values[0]), UUID(values[1])
            except (ValueError, TypeError) as exc:
                raise InvalidV2Cursor("invalid hotspot cursor") from exc
        return await self._page(
            "SELECT projection.payload,award.awarded_at,projection.event_id "
            "FROM hotspot_award_v2 award "
            "JOIN intelligence_projection_v2 projection ON projection.event_id=award.event_id "
            "WHERE award.revoked_at IS NULL AND (:cursor_time IS NULL OR "
            "(award.awarded_at,projection.event_id)<"
            "(CAST(:cursor_time AS timestamptz),CAST(:cursor_id AS uuid))) "
            "ORDER BY award.awarded_at DESC,projection.event_id DESC LIMIT :row_limit",
            {"limit": limit, "cursor_time": cursor_time, "cursor_id": cursor_id},
            surface="hotspots",
            filters={},
            cursor_columns=("awarded_at", "event_id"),
        )

    async def event(self, event_id: UUID) -> EventProjectionV2:
        async with self._reader.connect() as connection:
            payload = await connection.scalar(
                text("SELECT payload FROM intelligence_projection_v2 WHERE event_id=:event_id"),
                {"event_id": event_id},
            )
        if payload is None:
            raise ProjectionNotFound(str(event_id))
        return _PROJECTION_ADAPTER.validate_python(payload)

    async def appendix(self, event_id: UUID) -> EventAppendixV2:
        async with self._reader.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT projection_kind,appendix_payload "
                            "FROM intelligence_projection_v2 WHERE event_id=:event_id"
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["projection_kind"] != "FULL":
            raise ProjectionNotFound(str(event_id))
        return _APPENDIX_ADAPTER.validate_python(row["appendix_payload"])

    async def _media(self, media_id: UUID) -> dict[str, Any]:
        async with self._reader.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT object_key,mime_type,redistribution_allowed,scan_status "
                            "FROM media_rights_v2 WHERE id=:media_id"
                        ),
                        {"media_id": media_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if (
            row is None
            or not row["redistribution_allowed"]
            or row["scan_status"] != "CLEAN"
            or row["object_key"] is None
            or self._objects is None
        ):
            raise ProjectionNotFound(str(media_id))
        return dict(row)

    async def media_preview(self, media_id: UUID) -> tuple[bytes, str]:
        row = await self._media(media_id)
        if not str(row["mime_type"]).startswith("image/"):
            raise ProjectionNotFound(str(media_id))
        store = self._objects
        if store is None:
            raise ProjectionNotFound(str(media_id))
        content = await store.get_bytes(str(row["object_key"]), max_bytes=10_000_000)
        return content, str(row["mime_type"])

    async def media_download(self, media_id: UUID, *, max_age_seconds: int) -> str:
        row = await self._media(media_id)
        store = self._objects
        if store is None:
            raise ProjectionNotFound(str(media_id))
        return await store.presigned_get(
            str(row["object_key"]), max_age_seconds=min(max_age_seconds, 300)
        )

    async def review_cases(self, **filters: object) -> list[ReviewCaseV2]:
        state = filters.get("state")
        params: dict[str, object] = {}
        if state:
            sql = (
                _REVIEW_COLUMNS
                + " WHERE review.state=:state ORDER BY review.updated_at DESC LIMIT 100"
            )
            params["state"] = state
        else:
            sql = _REVIEW_COLUMNS + " ORDER BY review.updated_at DESC LIMIT 100"
        async with self._reader.connect() as connection:
            rows = (await connection.execute(text(sql), params)).mappings()
            return [ReviewCaseV2.model_validate(dict(row)) for row in rows]

    async def review_case(self, case_id: UUID) -> ReviewCaseV2:
        async with self._reader.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            _REVIEW_COLUMNS + " WHERE review.id=:case_id"
                        ),
                        {"case_id": case_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ProjectionNotFound(str(case_id))
        return ReviewCaseV2.model_validate(dict(row))

    async def decide(
        self,
        *,
        case_id: UUID,
        command: ReviewDecisionCommandV2,
        owner_id: UUID,
        idempotency_key: UUID,
    ) -> ReviewDecisionReceiptV2:
        now = datetime.now(UTC)
        decision_id = uuid7()
        outbox_id = uuid7()
        async with self._writer.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT decision.id,decision.case_id,decision.case_version,"
                            "decision.created_at,outbox.id AS outbox_id "
                            "FROM owner_review_decision_v2 decision "
                            "JOIN owner_review_reprocessing_outbox_v2 outbox "
                            "ON outbox.decision_id=decision.id "
                            "WHERE decision.idempotency_key=:key"
                        ),
                        {"key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return ReviewDecisionReceiptV2(
                    decision_id=existing["id"],
                    case_id=existing["case_id"],
                    version=existing["case_version"],
                    recorded_at=existing["created_at"],
                    reprocessing_outbox_id=existing["outbox_id"],
                    reprocessing_state="QUEUED",
                )
            updated = (
                (
                    await connection.execute(
                        text(
                            "UPDATE owner_review_case_v2 SET version=version+1,updated_at=:now "
                            "WHERE id=:case_id AND version=:version "
                            "RETURNING version,document_version_id"
                        ),
                        {"case_id": case_id, "version": command.expected_version, "now": now},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if updated is None:
                raise ReviewConflict(str(case_id))
            await connection.execute(
                text(
                    "INSERT INTO owner_review_decision_v2("
                    "id,case_id,owner_id,command,reason,payload,case_version,"
                    "idempotency_key,created_at) VALUES("
                    ":id,:case_id,:owner_id,:command,:reason,CAST(:payload AS jsonb),"
                    ":version,:key,:now)"
                ),
                {
                    "id": decision_id,
                    "case_id": case_id,
                    "owner_id": owner_id,
                    "command": command.command,
                    "reason": command.reason,
                    "payload": command.model_dump_json(),
                    "version": updated["version"],
                    "key": idempotency_key,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO owner_review_reprocessing_outbox_v2("
                    "id,case_id,decision_id,document_version_id,status,attempt_count,"
                    "available_at,created_at,updated_at) VALUES("
                    ":id,:case_id,:decision_id,:document_version_id,'PENDING',0,:now,:now,:now)"
                ),
                {
                    "id": outbox_id,
                    "case_id": case_id,
                    "decision_id": decision_id,
                    "document_version_id": updated["document_version_id"],
                    "now": now,
                },
            )
        return ReviewDecisionReceiptV2(
            decision_id=decision_id,
            case_id=case_id,
            version=updated["version"],
            recorded_at=now,
            reprocessing_outbox_id=outbox_id,
            reprocessing_state="QUEUED",
        )
