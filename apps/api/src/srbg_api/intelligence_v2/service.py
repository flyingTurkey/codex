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
    QuarantineProjectionV2,
    ReviewCaseV2,
    ReviewDecisionCommandV2,
    ReviewDecisionReceiptV2,
)

from srbg_api.config import get_settings
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.cursor import InvalidV2Cursor, V2CursorCodec
from srbg_api.intelligence_v2.media import (
    bounded_signed_url_ttl,
    projectable_download,
    projectable_preview,
)
from srbg_api.observability import INTELLIGENCE_V2_APPENDIX_READS


class ProjectionNotFound(LookupError):
    """The Event has no projection visible at the requested boundary."""


class MediaDeliveryUnavailable(RuntimeError):
    """Private object storage could not complete an otherwise authorized request."""


class ReviewConflict(RuntimeError):
    """The review case changed since the Owner read it."""


_PROJECTION_ADAPTER: TypeAdapter[EventProjectionV2] = TypeAdapter(EventProjectionV2)
_APPENDIX_ADAPTER: TypeAdapter[EventAppendixV2] = TypeAdapter(EventAppendixV2)

_REVIEW_COLUMNS = """
SELECT review.id AS case_id,review.event_id,review.document_version_id,review.reason,
  review.risk_tier,review.safe_metadata,review.state,review.version,review.created_at,
  review.updated_at,CASE
    WHEN EXISTS(SELECT 1 FROM owner_review_reprocessing_outbox_v2 outbox
      WHERE outbox.case_id=review.id AND outbox.status='PROCESSING') THEN 'PROCESSING'
    WHEN EXISTS(SELECT 1 FROM owner_review_reprocessing_outbox_v2 outbox
      WHERE outbox.case_id=review.id AND outbox.status='PENDING') THEN 'QUEUED'
    WHEN EXISTS(SELECT 1 FROM owner_review_reprocessing_outbox_v2 outbox
      WHERE outbox.case_id=review.id AND outbox.status IN ('FAILED','DEAD_LETTER')) THEN 'FAILED'
    ELSE 'IDLE' END AS processing_state,
  preparation.content_preparation
FROM owner_review_case_v2 review
LEFT JOIN LATERAL(
  SELECT jsonb_build_object(
    'status',CASE
      WHEN invalidation.id IS NULL
       AND item.current_document_version_id=candidate.document_version_id THEN 'CURRENT'
      ELSE 'STALE' END,
    'source_excerpt',jsonb_build_object(
      'text',candidate.source_excerpt,
      'claim_ids',to_jsonb(candidate.source_excerpt_claim_ids),
      'evidence_locators',to_jsonb(candidate.evidence_locators)
    ),
    'summary',candidate.summary_payload,
    'claims',candidate.claims_payload,
    'fact_decisions',COALESCE((
      SELECT jsonb_agg(jsonb_build_object(
        'decision_id',decision.id,'command',decision.command,'created_at',decision.created_at
      ) ORDER BY decision.created_at,decision.id)
      FROM owner_review_decision_v2 decision
      WHERE decision.case_id=review.id
        AND decision.command IN ('ACCEPT_CLAIM','REJECT_CLAIM','REPLACE_CLAIM')
    ),'[]'::jsonb),
    'ai_summary_decisions',COALESCE((
      SELECT jsonb_agg(jsonb_build_object(
        'decision_id',decision.id,'command',decision.command,'created_at',decision.created_at
      ) ORDER BY decision.created_at,decision.id)
      FROM owner_review_decision_v2 decision
      WHERE decision.case_id=review.id
        AND decision.command IN (
          'APPROVE_AI_SUMMARY','REJECT_AI_SUMMARY','REGENERATE_AI_SUMMARY'
        )
    ),'[]'::jsonb),
    'invalidation_reason',CASE
      WHEN invalidation.reason IS NOT NULL THEN invalidation.reason
      WHEN item.current_document_version_id<>candidate.document_version_id
        THEN 'DOCUMENT_VERSION_CHANGED'
      ELSE NULL END
  ) AS content_preparation
  FROM content_preparation_candidate_v2 candidate
  JOIN event_identity_binding binding ON binding.event_id=candidate.event_id
  JOIN intelligence_item item ON item.id=binding.item_id
  LEFT JOIN content_preparation_invalidation_v2 invalidation
    ON invalidation.candidate_id=candidate.id
  WHERE candidate.document_version_id=review.document_version_id
  ORDER BY candidate.created_at DESC,candidate.id DESC LIMIT 1
) preparation ON true
"""


def _limit(filters: dict[str, object]) -> int:
    value = filters.get("limit", 20)
    return max(1, min(value if isinstance(value, int) else 20, 100))


def _escaped_like_contains(value: str) -> str:
    escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


class V2ObjectStore(Protocol):
    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes: ...
    async def object_exists(self, key: str) -> bool: ...
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
        explain_search: bool = False,
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
        items: list[EventProjectionV2] = []
        for row in visible:
            payload = row["payload"]
            if explain_search and payload.get("projection_kind") == "FULL":
                matched_fields = [
                    field
                    for field, column in (
                        ("TITLE", "title_match"),
                        ("SOURCE", "source_match"),
                        ("ACCEPTED_CLAIMS", "claims_match"),
                        ("SOURCE_EXCERPT", "excerpt_match"),
                    )
                    if row[column]
                ]
                payload = dict(payload) | {
                    "search_explanation": {
                        "matched_evidence_fields": matched_fields,
                        "ai_summary_assisted": bool(row["ai_match"]),
                    }
                }
            items.append(_PROJECTION_ADAPTER.validate_python(payload))
        return FeedPageV2(
            items=items,
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
            "WHERE (CAST(:primary_type AS varchar) IS NULL "
            "OR primary_type=CAST(:primary_type AS varchar)) "
            "AND (CAST(:cursor_time AS timestamptz) IS NULL OR (projected_at,event_id)<"
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
        sql = """
        WITH searchable AS (
          SELECT projection.payload,projection.projected_at,projection.event_id,
            search.search_vector,
            search.title_source_claims_excerpt AS evidence_text,
            COALESCE(search.ai_summary_low_weight,'') AS ai_text,
            COALESCE(projection.payload->>'title','') AS title_text,
            COALESCE(projection.payload#>>'{source,name}',
              projection.payload->>'source_name','') AS source_text,
            COALESCE((SELECT string_agg(claim->>'value',' ')
              FROM jsonb_array_elements(COALESCE(
                projection.appendix_payload->'claims','[]'::jsonb)) claim
              WHERE claim->>'decision_status'='ACCEPTED'),'') AS claims_text,
            COALESCE(projection.payload#>>'{source_excerpt,text}','') AS excerpt_text
          FROM search_projection_v2 search
          JOIN intelligence_projection_v2 projection ON projection.event_id=search.event_id
        ), ranked AS (
          SELECT payload,projected_at,event_id,
            floor(ts_rank(search_vector,plainto_tsquery('simple',:query))*1000000)::bigint
              + CASE WHEN evidence_text ILIKE :like_query ESCAPE '!' THEN 1000000 ELSE 0 END
              + CASE WHEN ai_text ILIKE :like_query ESCAPE '!' THEN 1000 ELSE 0 END AS rank_q,
            (to_tsvector('simple',title_text) @@ plainto_tsquery('simple',:query)
              OR title_text ILIKE :like_query ESCAPE '!') AS title_match,
            (to_tsvector('simple',source_text) @@ plainto_tsquery('simple',:query)
              OR source_text ILIKE :like_query ESCAPE '!') AS source_match,
            (to_tsvector('simple',claims_text) @@ plainto_tsquery('simple',:query)
              OR claims_text ILIKE :like_query ESCAPE '!') AS claims_match,
            (to_tsvector('simple',excerpt_text) @@ plainto_tsquery('simple',:query)
              OR excerpt_text ILIKE :like_query ESCAPE '!') AS excerpt_match,
            (to_tsvector('simple',ai_text) @@ plainto_tsquery('simple',:query)
              OR ai_text ILIKE :like_query ESCAPE '!') AS ai_match
          FROM searchable
          WHERE search_vector @@ plainto_tsquery('simple',:query)
            OR evidence_text ILIKE :like_query ESCAPE '!'
            OR ai_text ILIKE :like_query ESCAPE '!'
        )
        SELECT payload,projected_at,event_id,rank_q,title_match,source_match,claims_match,
          excerpt_match,ai_match FROM ranked
        WHERE CAST(:cursor_rank AS bigint) IS NULL OR rank_q<CAST(:cursor_rank AS bigint)
          OR (rank_q=CAST(:cursor_rank AS bigint) AND (projected_at,event_id)<
            (CAST(:cursor_time AS timestamptz),CAST(:cursor_id AS uuid)))
        ORDER BY rank_q DESC,projected_at DESC,event_id DESC LIMIT :row_limit
        """
        return await self._page(
            sql,
            {
                "query": query,
                "like_query": _escaped_like_contains(query),
                "limit": limit,
                "cursor_rank": cursor_rank,
                "cursor_time": cursor_time,
                "cursor_id": cursor_id,
            },
            surface="search",
            filters=binding,
            cursor_columns=("rank_q", "projected_at", "event_id"),
            explain_search=True,
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
            "WITH current_awards AS (SELECT DISTINCT ON (event_id) event_id,awarded_at "
            "FROM hotspot_award_v2 WHERE evaluation_id IS NOT NULL "
            "ORDER BY event_id,awarded_at DESC,id DESC) "
            "SELECT projection.payload,award.awarded_at,projection.event_id "
            "FROM current_awards award "
            "JOIN intelligence_projection_v2 projection ON projection.event_id=award.event_id "
            "WHERE (CAST(:cursor_time AS timestamptz) IS NULL OR "
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
                            "SELECT event_id,appendix_payload,evidence,evidence_total,"
                            "automatic_results,automatic_results_total,relationships,"
                            "relationships_total,automatic_relationships,"
                            "automatic_relationships_total,corrections,corrections_total,"
                            "review_case_id FROM reader_appendix_governance_v2 "
                            "WHERE event_id=:event_id"
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            INTELLIGENCE_V2_APPENDIX_READS.labels(outcome="FAIL_CLOSED").inc()
            raise ProjectionNotFound(str(event_id))
        payload = dict(row["appendix_payload"] or {})
        payload.update(
            {
                "event_id": row["event_id"],
                "evidence": list(row["evidence"] or ()),
                "automatic_results": list(row["automatic_results"] or ()),
                "relationships": list(row["relationships"] or ()),
                "automatic_relationships": list(row["automatic_relationships"] or ()),
                "corrections": list(row["corrections"] or ()),
            }
        )
        case_id = row["review_case_id"]
        if case_id is not None:
            payload["review_context"] = {
                "case_id": case_id,
                "href": f"/review?case_id={case_id}",
            }
        sections = (
            ("EVIDENCE", int(row["evidence_total"]), 500),
            ("AUTOMATIC_RESULTS", int(row["automatic_results_total"]), 100),
            ("REVIEWED_RELATIONSHIPS", int(row["relationships_total"]), 500),
            (
                "AUTOMATIC_RELATIONSHIPS",
                int(row["automatic_relationships_total"]),
                500,
            ),
            ("CORRECTIONS", int(row["corrections_total"]), 100),
        )
        claim_total = len(payload.get("claims") or ())
        total_items = claim_total + sum(total for _, total, _ in sections)
        truncated_sections = [name for name, total, limit in sections if total > limit]
        payload["content_summary"] = {
            "total_items": total_items,
            "heavy_content": total_items >= 100 or bool(truncated_sections),
            "truncated_sections": truncated_sections,
        }
        appendix = _APPENDIX_ADAPTER.validate_python(payload)
        outcome = (
            "HEAVY"
            if appendix.content_summary.heavy_content
            else "EMPTY"
            if appendix.content_summary.total_items == 0
            else "AVAILABLE"
        )
        INTELLIGENCE_V2_APPENDIX_READS.labels(outcome=outcome).inc()
        return appendix

    async def _media(self, media_id: UUID) -> dict[str, Any]:
        async with self._reader.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT media.object_key,media.mime_type,media.rights_basis,"
                            "media.redistribution_allowed,media.scan_status,"
                            "media.attachment_scan_status,media.raw_scan_status,"
                            "media.preview_object_key,"
                            "media.preview_mime_type FROM media_delivery_reader_v2 media "
                            "WHERE media.id=:media_id"
                        ),
                        {"media_id": media_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None or self._objects is None:
            raise ProjectionNotFound(str(media_id))
        return dict(row)

    async def media_preview(self, media_id: UUID) -> tuple[bytes, str]:
        row = await self._media(media_id)
        if (
            not projectable_preview(
                rights_basis=row["rights_basis"],
                scan_status=str(row["scan_status"]),
                attachment_scan_status=str(row["attachment_scan_status"]),
                raw_scan_status=str(row["raw_scan_status"]),
                preview_object_key=row["preview_object_key"],
                preview_mime_type=row["preview_mime_type"],
            )
        ):
            raise ProjectionNotFound(str(media_id))
        store = self._objects
        if store is None:
            raise ProjectionNotFound(str(media_id))
        try:
            content = await store.get_bytes(
                str(row["preview_object_key"]), max_bytes=10_000_000
            )
        except FileNotFoundError as exc:
            raise ProjectionNotFound(str(media_id)) from exc
        except OSError as exc:
            raise MediaDeliveryUnavailable("media preview storage unavailable") from exc
        return content, str(row["preview_mime_type"])

    async def media_download(self, media_id: UUID, *, max_age_seconds: int) -> str:
        row = await self._media(media_id)
        if (
            not projectable_download(
                rights_basis=row["rights_basis"],
                scan_status=str(row["scan_status"]),
                attachment_scan_status=str(row["attachment_scan_status"]),
                raw_scan_status=str(row["raw_scan_status"]),
                redistribution_allowed=bool(row["redistribution_allowed"]),
                object_key=row["object_key"],
            )
        ):
            raise ProjectionNotFound(str(media_id))
        store = self._objects
        if store is None:
            raise ProjectionNotFound(str(media_id))
        object_key = str(row["object_key"])
        try:
            if not await store.object_exists(object_key):
                raise ProjectionNotFound(str(media_id))
            return await store.presigned_get(
                object_key,
                max_age_seconds=bounded_signed_url_ttl(max_age_seconds),
            )
        except ProjectionNotFound:
            raise
        except FileNotFoundError as exc:
            raise ProjectionNotFound(str(media_id)) from exc
        except OSError as exc:
            raise MediaDeliveryUnavailable("media download storage unavailable") from exc

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

    async def quarantine(self, case_id: UUID) -> QuarantineProjectionV2:
        async with self._reader.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,event_id,reason,safe_metadata "
                            "FROM owner_review_case_v2 "
                            "WHERE id=:case_id AND risk_tier='R4' AND state='QUARANTINED'"
                        ),
                        {"case_id": case_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ProjectionNotFound(str(case_id))
        metadata = dict(row["safe_metadata"] or {})
        try:
            return QuarantineProjectionV2(
                case_id=row["id"],
                event_id=row["event_id"],
                title=str(metadata["title"]),
                primary_type=metadata.get("primary_type"),
                official_source=bool(metadata.get("official_source", False)),
                source_published_at=metadata.get("source_published_at"),
                first_discovered_at=metadata.get("first_discovered_at"),
                original_url=str(metadata["original_url"]),
                isolation_reason=str(row["reason"]),
            )
        except (KeyError, ValueError) as exc:
            raise ProjectionNotFound(str(case_id)) from exc

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
        invalidation_id = uuid7()
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
            if command.command in {"ACCEPT_CLAIM", "REJECT_CLAIM", "REPLACE_CLAIM"}:
                # content-preparation-claim-review: a fact decision never approves a
                # summary, and any prior summary candidate becomes stale atomically.
                await connection.execute(
                    text(
                        """
                        INSERT INTO content_preparation_invalidation_v2(
                          id,candidate_id,reason,created_at
                        )
                        SELECT :id,candidate.id,'ACCEPTED_CLAIMS_CHANGED',:now
                        FROM content_preparation_candidate_v2 candidate
                        JOIN owner_review_case_v2 review
                          ON review.document_version_id=candidate.document_version_id
                        WHERE review.id=:case_id
                        ORDER BY candidate.created_at DESC,candidate.id DESC LIMIT 1
                        ON CONFLICT(candidate_id) DO NOTHING
                        """
                    ),
                    {
                        "id": invalidation_id,
                        "case_id": case_id,
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
