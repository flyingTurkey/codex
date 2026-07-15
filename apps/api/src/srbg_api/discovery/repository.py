"""PostgreSQL adapter for search, daily reports, saved items, and private collections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    CollectionSummary,
    DailyReport,
    DailyReportItem,
    DailyReportSection,
    FingerprintResponse,
)

from srbg_api.discovery.domain import SearchMatchKind, normalize_identifier


class PortalRepositoryConflict(RuntimeError):
    pass


class PortalRepositoryNotFound(LookupError):
    pass


DailySectionKind = Literal[
    "TODAY_HIGHLIGHTS",
    "DIGITAL_SELECTED",
    "SAFETY_HIGHLIGHTS",
    "WATCHLIST",
    "SOURCE_ANOMALIES",
]


@dataclass(frozen=True, slots=True)
class SearchHit:
    item_id: UUID
    match_kind: SearchMatchKind
    score_bps: int
    activity_at: datetime
    matched_fields: tuple[str, ...]
    matched_identifiers: tuple[str, ...]


class PostgresPortalRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def search(
        self,
        *,
        query: str,
        tokens: tuple[str, ...],
        domain: str | None,
        content_type: str | None,
        region: str | None,
        source_id: UUID | None,
        evidence_status: str | None,
        sort: str,
        cursor_values: tuple[str, ...] | None,
        limit: int,
        embedding: Sequence[float] | None,
    ) -> tuple[list[SearchHit], tuple[str, ...] | None, int]:
        cursor_tier: int | None = None
        cursor_score: int | None = None
        cursor_time: datetime | None = None
        cursor_id: UUID | None = None
        if cursor_values is not None:
            try:
                cursor_tier = int(cursor_values[0])
                cursor_score = int(cursor_values[1])
                cursor_time = datetime.fromisoformat(cursor_values[2])
                cursor_id = UUID(cursor_values[3])
            except (IndexError, TypeError, ValueError) as exc:
                raise PortalRepositoryConflict("search cursor values are invalid") from exc
        normalized_identifier = normalize_identifier(query)
        query_text = " ".join(tokens)
        vector_value = None if embedding is None else "[" + ",".join(map(str, embedding)) + "]"
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            WITH scored AS (
                                SELECT sp.item_id, sp.activity_at,
                                    CASE
                                      WHEN EXISTS (
                                        SELECT 1 FROM search_identifier si
                                        WHERE si.item_id = sp.item_id
                                          AND si.normalized_value = :normalized_identifier
                                      ) THEN 0
                                      WHEN sp.title % :query_text
                                        OR sp.entity_text % :query_text
                                        OR sp.tag_text % :query_text THEN 1
                                      WHEN sp.search_vector @@
                                        plainto_tsquery('simple', :query_text)
                                        THEN 2
                                      ELSE 3
                                    END AS tier,
                                    CASE
                                      WHEN EXISTS (
                                        SELECT 1 FROM search_identifier si
                                        WHERE si.item_id = sp.item_id
                                          AND si.normalized_value = :normalized_identifier
                                      ) THEN 10000
                                      WHEN sp.title % :query_text
                                        OR sp.entity_text % :query_text
                                        OR sp.tag_text % :query_text
                                      THEN CAST(10000 * greatest(
                                        similarity(sp.title, :query_text),
                                        similarity(sp.entity_text, :query_text),
                                        similarity(sp.tag_text, :query_text)
                                      ) AS integer)
                                      WHEN sp.search_vector @@
                                        plainto_tsquery('simple', :query_text)
                                      THEN CAST(10000 * ts_rank_cd(
                                        sp.search_vector, plainto_tsquery('simple', :query_text)
                                      ) AS integer)
                                      ELSE CAST(10000 * (1 - (sp.embedding <=>
                                        CAST(:embedding AS vector))) AS integer)
                                    END AS score_bps
                                FROM search_projection sp
                                WHERE sp.visible AND sp.risk_level <> 'R4'
                                  AND (CAST(:domain AS text) IS NULL OR
                                    sp.domain = CAST(:domain AS text))
                                  AND (CAST(:content_type AS text) IS NULL OR
                                    sp.content_type = CAST(:content_type AS text))
                                  AND (CAST(:region AS text) IS NULL OR
                                    sp.region = CAST(:region AS text))
                                  AND (CAST(:source_id AS uuid) IS NULL OR
                                    sp.source_id = CAST(:source_id AS uuid))
                                  AND (CAST(:evidence_status AS text) IS NULL OR
                                    sp.evidence_status = CAST(:evidence_status AS text))
                                  AND (
                                    EXISTS (
                                      SELECT 1 FROM search_identifier si
                                      WHERE si.item_id = sp.item_id
                                        AND si.normalized_value = :normalized_identifier
                                    )
                                    OR sp.title % :query_text
                                    OR sp.entity_text % :query_text
                                    OR sp.tag_text % :query_text
                                    OR sp.search_vector @@ plainto_tsquery('simple', :query_text)
                                    OR (:embedding IS NOT NULL AND sp.embedding IS NOT NULL
                                      AND sp.embedding <=> CAST(:embedding AS vector) < 0.35)
                                  )
                            ), ranked AS (
                                SELECT *, CASE
                                  WHEN CAST(:sort AS text) = 'latest' AND tier > 0
                                  THEN 1 ELSE tier END
                                    AS sort_tier
                                FROM scored
                            )
                            SELECT r.item_id, r.tier, r.score_bps, r.activity_at,
                              COALESCE((
                                SELECT array_agg(si.kind ORDER BY si.kind)
                                FROM search_identifier si
                                WHERE si.item_id = r.item_id
                                  AND si.normalized_value = :normalized_identifier
                              ), ARRAY[]::text[]) AS matched_fields,
                              COALESCE((
                                SELECT array_agg(si.display_value ORDER BY si.kind)
                                FROM search_identifier si
                                WHERE si.item_id = r.item_id
                                  AND si.normalized_value = :normalized_identifier
                              ), ARRAY[]::text[]) AS matched_identifiers
                            FROM ranked r
                            WHERE CAST(:cursor_tier AS integer) IS NULL
                               OR r.sort_tier > CAST(:cursor_tier AS integer)
                               OR (r.sort_tier = CAST(:cursor_tier AS integer)
                                   AND r.score_bps < CAST(:cursor_score AS integer))
                               OR (r.sort_tier = CAST(:cursor_tier AS integer)
                                   AND r.score_bps = CAST(:cursor_score AS integer)
                                   AND (r.activity_at, r.item_id) <
                                     (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid)))
                            ORDER BY r.sort_tier, r.score_bps DESC,
                              r.activity_at DESC, r.item_id DESC
                            LIMIT :fetch_limit
                            """
                        ),
                        {
                            "normalized_identifier": normalized_identifier,
                            "query_text": query_text,
                            "embedding": vector_value,
                            "domain": domain,
                            "content_type": content_type,
                            "region": region,
                            "source_id": source_id,
                            "evidence_status": evidence_status,
                            "sort": sort,
                            "cursor_tier": cursor_tier,
                            "cursor_score": cursor_score,
                            "cursor_time": cursor_time,
                            "cursor_id": cursor_id,
                            "fetch_limit": limit + 1,
                        },
                    )
                )
                .mappings()
                .all()
            )
            generation = int(
                await connection.scalar(
                    text("SELECT COALESCE(max(generation), 0) FROM search_projection")
                )
                or 0
            )
        visible = rows[:limit]
        hits = [self._search_hit(row) for row in visible]
        next_values = None
        if len(rows) > limit and visible:
            last = visible[-1]
            sort_tier = 1 if sort == "latest" and int(last["tier"]) > 0 else int(last["tier"])
            next_values = (
                str(sort_tier),
                str(int(last["score_bps"])),
                cast(datetime, last["activity_at"]).isoformat(),
                str(last["item_id"]),
            )
        return hits, next_values, generation

    @staticmethod
    def _search_hit(row: RowMapping) -> SearchHit:
        tier = int(row["tier"])
        kind: SearchMatchKind = (
            "EXACT_IDENTIFIER"
            if tier == 0
            else "TITLE_ENTITY_TAG"
            if tier == 1
            else "BODY"
            if tier == 2
            else "SEMANTIC"
        )
        fields = tuple(row["matched_fields"])
        if not fields:
            fields = (
                ("TITLE_ENTITY_TAG",) if tier == 1 else ("BODY",) if tier == 2 else ("SEMANTIC",)
            )
        return SearchHit(
            item_id=cast(UUID, row["item_id"]),
            match_kind=kind,
            score_bps=max(0, int(row["score_bps"])),
            activity_at=cast(datetime, row["activity_at"]),
            matched_fields=fields,
            matched_identifiers=tuple(row["matched_identifiers"]),
        )

    async def list_saved_ids(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID | None,
        cursor_values: tuple[str, ...] | None,
        limit: int,
    ) -> tuple[list[UUID], tuple[str, ...] | None, int]:
        cursor_time: datetime | None = None
        cursor_id: UUID | None = None
        if cursor_values is not None:
            try:
                cursor_time = datetime.fromisoformat(cursor_values[0])
                cursor_id = UUID(cursor_values[1])
            except (IndexError, ValueError) as exc:
                raise PortalRepositoryConflict("saved-items cursor values are invalid") from exc
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT si.item_id, si.saved_at
                            FROM saved_item si
                            JOIN intelligence_item ii ON ii.id = si.item_id
                            LEFT JOIN publication p ON p.item_id = si.item_id
                            LEFT JOIN search_projection sp ON sp.item_id = si.item_id
                            WHERE si.owner_id = :owner_id
                              AND (
                                (sp.visible AND sp.risk_level <> 'R4')
                                OR p.status = 'WITHDRAWN'
                              )
                              AND (
                                CAST(:collection_id AS uuid) IS NULL OR EXISTS (
                                  SELECT 1 FROM collection_item ci
                                  WHERE ci.collection_id = CAST(:collection_id AS uuid)
                                    AND ci.owner_id = :owner_id AND ci.item_id = si.item_id
                                )
                              )
                              AND (CAST(:cursor_time AS timestamptz) IS NULL OR
                                (si.saved_at, si.item_id) <
                                (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid)))
                            ORDER BY si.saved_at DESC, si.item_id DESC
                            LIMIT :fetch_limit
                            """
                        ),
                        {
                            "owner_id": owner_id,
                            "collection_id": collection_id,
                            "cursor_time": cursor_time,
                            "cursor_id": cursor_id,
                            "fetch_limit": limit + 1,
                        },
                    )
                )
                .mappings()
                .all()
            )
            generation = int(
                await connection.scalar(
                    text("SELECT count(*) FROM saved_item WHERE owner_id = :owner_id"),
                    {"owner_id": owner_id},
                )
                or 0
            )
        visible = rows[:limit]
        next_values = None
        if len(rows) > limit and visible:
            next_values = (
                cast(datetime, visible[-1]["saved_at"]).isoformat(),
                str(visible[-1]["item_id"]),
            )
        return [cast(UUID, row["item_id"]) for row in visible], next_values, generation

    async def save_item(
        self,
        *,
        owner_id: UUID,
        item_id: UUID,
        collection_id: UUID | None,
        idempotency_key: str,
        saved_at: datetime,
    ) -> None:
        request_hash = _hash_request({"item_id": str(item_id), "collection_id": str(collection_id)})
        async with self._engine.begin() as connection:
            replay = await self._claim_idempotency(
                connection,
                owner_id=owner_id,
                scope="SAVE_ITEM",
                key=idempotency_key,
                request_hash=request_hash,
                response_id=item_id,
                created_at=saved_at,
            )
            if replay:
                return
            visible = await connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM search_projection WHERE item_id = :item_id "
                    "AND visible AND risk_level <> 'R4')"
                ),
                {"item_id": item_id},
            )
            if not visible:
                raise PortalRepositoryNotFound("item is not available to save")
            if collection_id is not None:
                owns_collection = await connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM user_collection WHERE id = :collection_id "
                        "AND owner_id = :owner_id AND NOT archived)"
                    ),
                    {"collection_id": collection_id, "owner_id": owner_id},
                )
                if not owns_collection:
                    raise PortalRepositoryNotFound("collection was not found")
            await connection.execute(
                text(
                    "INSERT INTO saved_item (owner_id, item_id, saved_at) "
                    "VALUES (:owner_id, :item_id, :saved_at) ON CONFLICT DO NOTHING"
                ),
                {"owner_id": owner_id, "item_id": item_id, "saved_at": saved_at},
            )
            if collection_id is not None:
                await connection.execute(
                    text(
                        "INSERT INTO collection_item (collection_id, owner_id, item_id, added_at) "
                        "VALUES (:collection_id, :owner_id, :item_id, :saved_at) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "collection_id": collection_id,
                        "owner_id": owner_id,
                        "item_id": item_id,
                        "saved_at": saved_at,
                    },
                )

    async def remove_saved_item(
        self, *, owner_id: UUID, item_id: UUID, collection_id: UUID | None
    ) -> None:
        async with self._engine.begin() as connection:
            if collection_id is None:
                await connection.execute(
                    text(
                        "DELETE FROM saved_item WHERE owner_id = :owner_id AND item_id = :item_id"
                    ),
                    {"owner_id": owner_id, "item_id": item_id},
                )
            else:
                await connection.execute(
                    text(
                        "DELETE FROM collection_item WHERE collection_id = :collection_id "
                        "AND owner_id = :owner_id AND item_id = :item_id"
                    ),
                    {"collection_id": collection_id, "owner_id": owner_id, "item_id": item_id},
                )

    async def list_collections(
        self, *, owner_id: UUID, include_archived: bool
    ) -> list[CollectionSummary]:
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT c.*, count(ci.item_id) AS item_count
                            FROM user_collection c
                            LEFT JOIN collection_item ci ON ci.collection_id = c.id
                              AND ci.owner_id = c.owner_id
                            WHERE c.owner_id = :owner_id
                              AND (:include_archived OR NOT c.archived)
                            GROUP BY c.id ORDER BY c.updated_at DESC, c.id DESC
                            """
                        ),
                        {"owner_id": owner_id, "include_archived": include_archived},
                    )
                )
                .mappings()
                .all()
            )
        return [_collection(row) for row in rows]

    async def create_collection(
        self,
        *,
        collection_id: UUID,
        owner_id: UUID,
        name: str,
        idempotency_key: str,
        created_at: datetime,
    ) -> CollectionSummary:
        request_hash = _hash_request({"name": name})
        async with self._engine.begin() as connection:
            replay = await self._claim_idempotency(
                connection,
                owner_id=owner_id,
                scope="CREATE_COLLECTION",
                key=idempotency_key,
                request_hash=request_hash,
                response_id=collection_id,
                created_at=created_at,
            )
            if isinstance(replay, UUID):
                existing_id = replay
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT c.*, 0 AS item_count FROM user_collection c "
                                "WHERE c.id = :id AND c.owner_id = :owner_id"
                            ),
                            {"id": existing_id, "owner_id": owner_id},
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is not None:
                    return _collection(row)
            try:
                row = (
                    (
                        await connection.execute(
                            text(
                                """
                            INSERT INTO user_collection (
                              id, owner_id, name, archived, version, created_at, updated_at
                            ) VALUES (:id, :owner_id, :name, false, 1, :now, :now)
                            RETURNING *, 0 AS item_count
                            """
                            ),
                            {
                                "id": collection_id,
                                "owner_id": owner_id,
                                "name": name,
                                "now": created_at,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
            except Exception as exc:
                raise PortalRepositoryConflict(
                    "an active collection already has this name"
                ) from exc
        return _collection(row)

    async def patch_collection(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID,
        name: str | None,
        archived: bool | None,
        expected_version: int,
        updated_at: datetime,
    ) -> CollectionSummary:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        UPDATE user_collection
                        SET name = COALESCE(:name, name),
                            archived = COALESCE(:archived, archived),
                            version = version + 1, updated_at = :updated_at
                        WHERE id = :id AND owner_id = :owner_id AND version = :expected_version
                        RETURNING *, (
                          SELECT count(*) FROM collection_item ci
                          WHERE ci.collection_id = user_collection.id
                        ) AS item_count
                        """
                        ),
                        {
                            "name": name,
                            "archived": archived,
                            "updated_at": updated_at,
                            "id": collection_id,
                            "owner_id": owner_id,
                            "expected_version": expected_version,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                exists = await connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM user_collection "
                        "WHERE id = :id AND owner_id = :owner_id)"
                    ),
                    {"id": collection_id, "owner_id": owner_id},
                )
                if not exists:
                    raise PortalRepositoryNotFound("collection was not found")
                raise PortalRepositoryConflict("collection version does not match If-Match")
        return _collection(row)

    async def get_daily(self, *, report_date: date | None, include_draft: bool) -> DailyReport:
        target_date = report_date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
        async with self._engine.connect() as connection:
            report_id = await connection.scalar(
                text(
                    "SELECT id FROM daily_report WHERE report_date = :report_date "
                    "AND (status = 'PUBLISHED' OR :include_draft) "
                    "ORDER BY CASE status WHEN 'PUBLISHED' THEN 0 ELSE 1 END, "
                    "snapshot_at DESC LIMIT 1"
                ),
                {"report_date": target_date, "include_draft": include_draft},
            )
        if report_id is None:
            raise PortalRepositoryNotFound("daily report was not found")
        return await self.get_report(report_id=cast(UUID, report_id), include_draft=include_draft)

    async def get_report(self, *, report_id: UUID, include_draft: bool) -> DailyReport:
        async with self._engine.connect() as connection:
            report = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM daily_report WHERE id = :report_id "
                            "AND (status = 'PUBLISHED' OR :include_draft)"
                        ),
                        {"report_id": report_id, "include_draft": include_draft},
                    )
                )
                .mappings()
                .first()
            )
            if report is None:
                raise PortalRepositoryNotFound("daily report was not found")
            items = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT dri.*, CASE
                              WHEN p.status = 'WITHDRAWN' THEN 'WITHDRAWN'
                              ELSE 'PUBLISHED' END AS current_state
                            FROM daily_report_item dri
                            JOIN publication p ON p.item_id = dri.item_id
                            WHERE dri.report_id = :report_id
                            ORDER BY dri.section, dri.position
                            """
                        ),
                        {"report_id": report_id},
                    )
                )
                .mappings()
                .all()
            )
        return daily_report_from_rows(report, items)

    async def fingerprint(self) -> FingerprintResponse:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT
                          COALESCE((SELECT max(generation) FROM publication_projection_state
                            WHERE projection = 'CACHE'), 0) AS feed_generation,
                          COALESCE((SELECT max(generation) FROM search_projection), 0)
                            AS search_generation,
                          COALESCE((SELECT count(*) FROM topic_cluster
                            WHERE status = 'CONFIRMED'), 0) AS hot_topics_generation,
                          (SELECT id FROM daily_report WHERE status = 'PUBLISHED'
                            ORDER BY report_date DESC, published_at DESC LIMIT 1)
                            AS latest_daily_report_id
                        """
                        )
                    )
                )
                .mappings()
                .one()
            )
        generated_at = datetime.now(UTC)
        canonical = json.dumps({key: str(value) for key, value in row.items()}, sort_keys=True)
        return FingerprintResponse(
            generated_at=generated_at,
            feed_generation=int(row["feed_generation"]),
            search_generation=int(row["search_generation"]),
            hot_topics_generation=int(row["hot_topics_generation"]),
            latest_daily_report_id=cast(UUID | None, row["latest_daily_report_id"]),
            fingerprint="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        )

    async def _claim_idempotency(
        self,
        connection: AsyncConnection,
        *,
        owner_id: UUID,
        scope: str,
        key: str,
        request_hash: str,
        response_id: UUID,
        created_at: datetime,
    ) -> bool | UUID:
        existing = (
            (
                await connection.execute(
                    text(
                        "SELECT request_sha256, response_id FROM idempotency_record "
                        "WHERE owner_id = :owner_id AND scope = :scope "
                        "AND idempotency_key = :key FOR UPDATE"
                    ),
                    {"owner_id": owner_id, "scope": scope, "key": key},
                )
            )
            .mappings()
            .first()
        )
        if existing is not None:
            if existing["request_sha256"] != request_hash:
                raise PortalRepositoryConflict("idempotency key was reused with another request")
            return cast(UUID, existing["response_id"])
        await connection.execute(
            text(
                "INSERT INTO idempotency_record (owner_id, scope, idempotency_key, "
                "request_sha256, response_id, created_at) VALUES "
                "(:owner_id, :scope, :key, :request_hash, :response_id, :created_at)"
            ),
            {
                "owner_id": owner_id,
                "scope": scope,
                "key": key,
                "request_hash": request_hash,
                "response_id": response_id,
                "created_at": created_at,
            },
        )
        return False


def _hash_request(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _collection(row: RowMapping) -> CollectionSummary:
    return CollectionSummary(
        id=cast(UUID, row["id"]),
        name=str(row["name"]),
        item_count=int(row["item_count"]),
        archived=bool(row["archived"]),
        version=int(row["version"]),
        created_at=cast(datetime, row["created_at"]),
        updated_at=cast(datetime, row["updated_at"]),
    )


def daily_report_from_rows(report: RowMapping, item_rows: list[RowMapping]) -> DailyReport:
    section_titles: tuple[tuple[DailySectionKind, str], ...] = (
        ("TODAY_HIGHLIGHTS", "今日重点"),
        ("DIGITAL_SELECTED", "数字化精选"),
        ("SAFETY_HIGHLIGHTS", "安全重点"),
        ("WATCHLIST", "持续关注"),
        ("SOURCE_ANOMALIES", "来源异常"),
    )
    grouped: dict[DailySectionKind, list[DailyReportItem]] = {key: [] for key, _ in section_titles}
    for row in item_rows:
        state = cast(Literal["PUBLISHED", "WITHDRAWN", "SOURCE_UNAVAILABLE"], row["current_state"])
        section = cast(DailySectionKind, row["section"])
        grouped[section].append(
            DailyReportItem(
                item_id=cast(UUID, row["item_id"]),
                publication_revision_id=cast(UUID, row["publication_revision_id"]),
                position=int(row["position"]),
                title=str(row["title"]),
                summary=None if state == "WITHDRAWN" else cast(str | None, row["summary"]),
                current_state=state,
                original_url=str(row["original_url"]),
            )
        )
    return DailyReport(
        id=cast(UUID, report["id"]),
        report_date=cast(date, report["report_date"]),
        status=cast(Literal["DRAFT", "PUBLISHED"], report["status"]),
        snapshot_at=cast(datetime, report["snapshot_at"]),
        published_at=cast(datetime | None, report["published_at"]),
        requires_regeneration=bool(report["requires_regeneration"]),
        sections=[
            DailyReportSection(kind=key, title=title, items=grouped[key])
            for key, title in section_titles
        ],
    )
