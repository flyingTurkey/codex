# ruff: noqa: RUF001
"""Server-side R3 projections for feeds, details, evidence, and review work."""

import base64
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    Channel,
    ClaimView,
    CriticalFieldDiff,
    DiffHunk,
    DocumentPageView,
    DocumentState,
    EvidenceStatus,
    EvidenceView,
    FeedNotice,
    FeedPage,
    ItemDetail,
    ItemSummary,
    ItemType,
    PageBoundingBox,
    PageDiff,
    PdfOcrLocator,
    PdfTableCellLocator,
    PdfTextLocator,
    PublicationStatus,
    ReviewStatus,
    ReviewTaskDetail,
    ReviewTaskSummary,
    TypeSummary,
    VersionDiffResponse,
    VersionTimelineEntry,
    VersionTimelineResponse,
)


class IntelligenceNotFound(LookupError):
    pass


class InvalidFeedCursor(ValueError):
    pass


class PreviewObjectReader(Protocol):
    async def get_bytes(self, key: str) -> bytes: ...


class PostgresIntelligenceQueryService:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        preview_object_reader: PreviewObjectReader | None = None,
    ) -> None:
        self._engine = engine
        self._preview_object_reader = preview_object_reader

    async def close(self) -> None:
        await self._engine.dispose()

    async def render_processing_metrics(self) -> str:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              count(*) FILTER (WHERE parser_name = 'safety_regulation_pdf')
                                AS pdf_total,
                              count(*) FILTER (
                                WHERE parser_name = 'safety_regulation_pdf'
                                  AND status = 'SUCCEEDED'
                              ) AS pdf_success,
                              COALESCE(sum(ocr_page_count), 0) AS ocr_pages,
                              COALESCE(sum(ocr_usable_page_count), 0) AS ocr_usable_pages,
                              COALESCE(sum(low_confidence_critical_count), 0)
                                AS low_confidence_critical
                            FROM processing_run
                            """
                        )
                    )
                )
                .mappings()
                .one()
            )
            changes = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT change_type, material, count(*) AS count
                            FROM version_change
                            GROUP BY change_type, material
                            ORDER BY change_type, material
                            """
                        )
                    )
                ).mappings()
            )
            outbox = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT count(*) FILTER (
                                     WHERE status IN ('PENDING','FAILED')
                                   ) AS depth,
                                   COALESCE(extract(epoch FROM (
                                     now() - min(created_at) FILTER (
                                       WHERE status IN ('PENDING','FAILED')
                                     )
                                   )), 0) AS oldest_seconds,
                                   COALESCE(sum(attempt_count), 0) AS retries
                            FROM outbox_event
                            """
                        )
                    )
                )
                .mappings()
                .one()
            )
        pdf_total = int(row["pdf_total"])
        ocr_pages = int(row["ocr_pages"])
        values = [
            ("srbg_pdf_parse_total", pdf_total),
            ("srbg_pdf_parse_success_total", int(row["pdf_success"])),
            (
                "srbg_pdf_parse_success_ratio",
                int(row["pdf_success"]) / pdf_total if pdf_total else 0,
            ),
            ("srbg_ocr_pages_total", ocr_pages),
            ("srbg_ocr_usable_pages_total", int(row["ocr_usable_pages"])),
            (
                "srbg_ocr_usable_ratio",
                int(row["ocr_usable_pages"]) / ocr_pages if ocr_pages else 0,
            ),
            (
                "srbg_ocr_low_confidence_critical_fields",
                int(row["low_confidence_critical"]),
            ),
            ("srbg_publisher_outbox_depth", int(outbox["depth"])),
            ("srbg_publisher_outbox_oldest_seconds", float(outbox["oldest_seconds"])),
            ("srbg_publisher_outbox_retries_total", int(outbox["retries"])),
        ]
        rendered = "".join(f"# TYPE {name} gauge\n{name} {value}\n" for name, value in values)
        for change in changes:
            rendered += (
                "# TYPE srbg_version_changes_total counter\n"
                "srbg_version_changes_total{"
                f'change_type="{change["change_type"]}",'
                f'material="{str(change["material"]).lower()}"'
                f"}} {change['count']}\n"
            )
        return rendered

    async def get_feed(
        self,
        *,
        mode: str,
        domain: str | None,
        content_type: str | None,
        sort: str,
        cursor: str | None,
        limit: int,
    ) -> FeedPage:
        now = datetime.now(UTC)
        if (
            mode == "selected"
            or domain == "digital"
            or (content_type is not None and content_type != "SAFETY_REGULATION")
        ):
            return _feed_page([], now=now, mode=mode, domain=domain, next_cursor=None)

        cursor_time, cursor_id = _decode_cursor(cursor)
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT i.id, i.title, i.original_url, i.source_published_at,
                                   i.first_discovered_at, i.activity_at, i.updated_at,
                                   i.review_status, s.name AS source_name,
                                   p.status AS publication_status,
                                   p.current_revision_id AS publication_revision_id,
                                   r.classification, r.document_number,
                                   r.issuing_authority, r.regulation_status,
                                   (SELECT count(*) FROM document_version version
                                    WHERE version.document_id = i.primary_document_id)
                                       AS version_count,
                                   latest_change.change_type AS latest_change_type,
                                   latest_change.review_state AS latest_change_review_state,
                                   (
                                     (SELECT url_check.outcome FROM source_url_check url_check
                                      WHERE url_check.document_id = i.primary_document_id
                                      ORDER BY url_check.checked_at DESC, url_check.id DESC LIMIT 1)
                                       IN ('NOT_FOUND','GONE')
                                     AND
                                     (SELECT url_check.outcome FROM source_url_check url_check
                                      WHERE url_check.document_id = i.primary_document_id
                                      ORDER BY url_check.checked_at DESC, url_check.id DESC
                                      LIMIT 1 OFFSET 1)
                                       IN ('NOT_FOUND','GONE')
                                   ) OR (
                                     (SELECT count(*) FROM (
                                        SELECT url_check.outcome FROM source_url_check url_check
                                        WHERE url_check.document_id = i.primary_document_id
                                        ORDER BY url_check.checked_at DESC, url_check.id DESC
                                        LIMIT 3
                                     ) recent
                                     WHERE recent.outcome IN ('TIMEOUT','SERVER_ERROR')) = 3
                                   ) AS source_unavailable,
                                   (SELECT count(*) FROM claim_evidence e
                                    JOIN claim c ON c.id = e.claim_id
                                    WHERE c.item_id = i.id
                                      AND c.verification_status = 'ACCEPTED') AS evidence_count
                            FROM intelligence_item i
                            JOIN source s ON s.id = i.source_id
                            JOIN safety_regulation_profile r ON r.item_id = i.id
                            LEFT JOIN publication p ON p.item_id = i.id
                            LEFT JOIN LATERAL (
                                SELECT change.change_type, change.review_state
                                FROM version_change change
                                WHERE change.document_id = i.primary_document_id
                                ORDER BY change.created_at DESC, change.id DESC LIMIT 1
                            ) latest_change ON true
                            WHERE (
                                i.review_status = 'PENDING'
                                OR p.status IN ('PUBLISHED', 'WITHDRAWN')
                            )
                              AND (
                                CAST(:cursor_time AS timestamptz) IS NULL
                                OR (i.activity_at, i.id) <
                                   (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid))
                              )
                            ORDER BY i.activity_at DESC, i.id DESC
                            LIMIT :row_limit
                            """
                        ),
                        {
                            "cursor_time": cursor_time,
                            "cursor_id": cursor_id,
                            "row_limit": limit + 1,
                        },
                    )
                ).mappings()
            )
        has_more = len(rows) > limit
        visible = rows[:limit]
        items = [_item_summary(row) for row in visible]
        next_cursor = None
        if has_more and visible:
            next_cursor = _encode_cursor(visible[-1]["activity_at"], visible[-1]["id"])
        return _feed_page(items, now=now, mode=mode, domain=domain, next_cursor=next_cursor)

    async def get_item(self, item_id: UUID) -> ItemDetail:
        async with self._engine.connect() as connection:
            row = await _item_row(connection, item_id, include_unpublished=False)
            if row is None:
                raise IntelligenceNotFound("intelligence item does not exist")
            item = _item_summary(row)
            if row["publication_status"] != "PUBLISHED" or row["review_status"] != "APPROVED":
                return ItemDetail(item=item, notice=_restricted_notice())
            claims, evidence = await _claims_and_evidence(connection, item_id)
            return ItemDetail(item=item, claims=claims, evidence=evidence)

    async def list_review_tasks(self) -> list[ReviewTaskSummary]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT r.id, r.item_id, r.status, r.risk_level, i.title,
                               s.name AS source_name, r.submitted_by, r.submitted_at,
                               r.assigned_to
                        FROM review_task r
                        JOIN intelligence_item i ON i.id = r.item_id
                        JOIN source s ON s.id = i.source_id
                        ORDER BY (r.status = 'PENDING') DESC, r.submitted_at, r.id
                        """
                    )
                )
            ).mappings()
            return [_review_summary(row) for row in rows]

    async def get_review_task(self, task_id: UUID) -> ReviewTaskDetail:
        async with self._engine.connect() as connection:
            task_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id, r.item_id, r.status, r.risk_level, i.title,
                                   s.name AS source_name, r.submitted_by, r.submitted_at,
                                   r.assigned_to
                            FROM review_task r
                            JOIN intelligence_item i ON i.id = r.item_id
                            JOIN source s ON s.id = i.source_id
                            WHERE r.id = :task_id
                            """
                        ),
                        {"task_id": task_id},
                    )
                )
                .mappings()
                .first()
            )
            if task_row is None:
                raise IntelligenceNotFound("review task does not exist")
            item_row = await _item_row(connection, task_row["item_id"], include_unpublished=True)
            if item_row is None:
                raise IntelligenceNotFound("review item does not exist")
            claims, evidence = await _claims_and_evidence(connection, task_row["item_id"])
            return ReviewTaskDetail(
                task=_review_summary(task_row),
                item=_item_summary(item_row, reviewer_projection=True),
                claims=claims,
                evidence=evidence,
            )

    async def get_versions(
        self,
        item_id: UUID,
        *,
        include_restricted: bool,
    ) -> VersionTimelineResponse:
        async with self._engine.connect() as connection:
            await _assert_item_projection_allowed(
                connection,
                item_id=item_id,
                include_restricted=include_restricted,
            )
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT v.id, v.version_number, v.acquired_at,
                                   i.current_document_version_id = v.id AS is_current,
                                   COALESCE(state.state, 'READY') AS processing_state,
                                   COALESCE(change_state.change_type, change.change_type, 'INITIAL')
                                       AS change_type,
                                   COALESCE(change_state.material, change.material, true)
                                       AS material,
                                   COALESCE(
                                       change_state.state,
                                       change.review_state,
                                       'RE_REVIEW_PENDING'
                                   )
                                       AS review_state
                            FROM intelligence_item i
                            JOIN document_version v ON v.document_id = i.primary_document_id
                            LEFT JOIN LATERAL (
                                SELECT event.state
                                FROM document_version_state_event event
                                WHERE event.document_version_id = v.id
                                ORDER BY event.created_at DESC, event.id DESC LIMIT 1
                            ) state ON true
                            LEFT JOIN version_change change
                              ON change.to_document_version_id = v.id
                            LEFT JOIN LATERAL (
                                SELECT event.state, event.change_type, event.material
                                FROM version_change_state_event event
                                WHERE event.version_change_id = change.id
                                ORDER BY event.created_at DESC, event.id DESC LIMIT 1
                            ) change_state ON true
                            WHERE i.id = :item_id
                            ORDER BY v.version_number, v.id
                            """
                        ),
                        {"item_id": item_id},
                    )
                ).mappings()
            )
        return VersionTimelineResponse(
            item_id=item_id,
            versions=[
                VersionTimelineEntry(
                    version_id=row["id"],
                    version_number=row["version_number"],
                    processing_state=row["processing_state"],
                    change_type=row["change_type"],
                    material=row["material"],
                    review_state=row["review_state"],
                    acquired_at=row["acquired_at"],
                    is_current=row["is_current"],
                )
                for row in rows
            ],
        )

    async def get_diff(
        self,
        item_id: UUID,
        *,
        from_version_id: UUID,
        to_version_id: UUID,
        include_restricted: bool,
    ) -> VersionDiffResponse:
        async with self._engine.connect() as connection:
            await _assert_item_projection_allowed(
                connection,
                item_id=item_id,
                include_restricted=include_restricted,
            )
            change = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COALESCE(state.change_type, change.change_type) AS change_type,
                                   COALESCE(state.material, change.material) AS material,
                                   changed_token_count,
                                   changed_token_ratio_bps, critical_field_diffs
                            FROM version_change change
                            JOIN intelligence_item item
                              ON item.primary_document_id = change.document_id
                            LEFT JOIN LATERAL (
                                SELECT event.change_type, event.material
                                FROM version_change_state_event event
                                WHERE event.version_change_id = change.id
                                ORDER BY event.created_at DESC, event.id DESC LIMIT 1
                            ) state ON true
                            WHERE item.id = :item_id
                              AND change.from_document_version_id = :from_version_id
                              AND change.to_document_version_id = :to_version_id
                            """
                        ),
                        {
                            "item_id": item_id,
                            "from_version_id": from_version_id,
                            "to_version_id": to_version_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if change is None:
                raise IntelligenceNotFound("version change does not exist")
            before = await _version_page_text(connection, from_version_id)
            after = await _version_page_text(connection, to_version_id)
        critical = change["critical_field_diffs"] or []
        return VersionDiffResponse(
            item_id=item_id,
            from_version_id=from_version_id,
            to_version_id=to_version_id,
            change_type=change["change_type"],
            material=change["material"],
            changed_token_count=change["changed_token_count"],
            changed_token_ratio_bps=change["changed_token_ratio_bps"],
            pages=_page_diffs(before, after),
            critical_fields=[
                CriticalFieldDiff(
                    field=value["field"],
                    before=value.get("before"),
                    after=value.get("after"),
                )
                for value in critical
                if isinstance(value, Mapping) and "field" in value
            ],
        )

    async def get_document_page(
        self,
        document_version_id: UUID,
        page_number: int,
        *,
        include_restricted: bool,
    ) -> DocumentPageView:
        async with self._engine.connect() as connection:
            row = await _document_page_row(
                connection,
                document_version_id=document_version_id,
                page_number=page_number,
                include_restricted=include_restricted,
            )
        return DocumentPageView(
            document_version_id=document_version_id,
            page_number=row["page_number"],
            page_count=row["page_count"],
            width_mpt=row["width_mpt"],
            height_mpt=row["height_mpt"],
            rotation=row["rotation"],
            text_source=row["text_source"],
            preview_url=(
                f"/api/v1/document-versions/{document_version_id}/pages/{page_number}/preview"
            ),
        )

    async def get_page_preview(
        self,
        document_version_id: UUID,
        page_number: int,
        *,
        include_restricted: bool,
    ) -> tuple[bytes, str]:
        if self._preview_object_reader is None:
            raise IntelligenceNotFound("page preview is unavailable")
        async with self._engine.connect() as connection:
            row = await _document_page_row(
                connection,
                document_version_id=document_version_id,
                page_number=page_number,
                include_restricted=include_restricted,
            )
        content = await self._preview_object_reader.get_bytes(row["preview_object_key"])
        if sha256(content).hexdigest() != row["preview_sha256"]:
            raise RuntimeError("page preview hash mismatch")
        return content, row["preview_sha256"]


async def _assert_item_projection_allowed(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    include_restricted: bool,
) -> None:
    row = (
        (
            await connection.execute(
                text(
                    """
                    SELECT i.review_status, p.status AS publication_status
                    FROM intelligence_item i
                    LEFT JOIN publication p ON p.item_id = i.id
                    WHERE i.id = :item_id
                    """
                ),
                {"item_id": item_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise IntelligenceNotFound("intelligence item does not exist")
    if not include_restricted and not (
        row["review_status"] == "APPROVED"
        and row["publication_status"] in {"PUBLISHED", "WITHDRAWN"}
    ):
        raise IntelligenceNotFound("version evidence is not available in this projection")


async def _document_page_row(
    connection: AsyncConnection,
    *,
    document_version_id: UUID,
    page_number: int,
    include_restricted: bool,
) -> RowMapping:
    row = (
        (
            await connection.execute(
                text(
                    """
                    SELECT page.page_number, page.width_mpt, page.height_mpt,
                           page.rotation, page.text_source, page.preview_object_key,
                           page.preview_sha256,
                           (
                               SELECT count(*)
                               FROM document_page all_pages
                               WHERE all_pages.document_version_id = page.document_version_id
                           ) AS page_count,
                           item.review_status, publication.status AS publication_status
                    FROM document_page page
                    JOIN intelligence_item item
                      ON item.primary_document_id = (
                          SELECT version.document_id FROM document_version version
                          WHERE version.id = page.document_version_id
                      )
                    LEFT JOIN publication ON publication.item_id = item.id
                    WHERE page.document_version_id = :version_id
                      AND page.page_number = :page_number
                    """
                ),
                {"version_id": document_version_id, "page_number": page_number},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise IntelligenceNotFound("document page does not exist")
    if not include_restricted and not (
        row["review_status"] == "APPROVED"
        and row["publication_status"] in {"PUBLISHED", "WITHDRAWN"}
    ):
        raise IntelligenceNotFound("document page is not available in this projection")
    return row


async def _version_page_text(
    connection: AsyncConnection,
    document_version_id: UUID,
) -> dict[int, dict[str, str]]:
    rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT page.page_number, block.block_kind, block.normalized_text
                    FROM document_page page
                    JOIN document_text_block block ON block.document_page_id = page.id
                    WHERE page.document_version_id = :version_id
                    ORDER BY page.page_number, block.block_index
                    """
                ),
                {"version_id": document_version_id},
            )
        ).mappings()
    )
    pages: dict[int, dict[str, list[str]]] = {}
    for row in rows:
        page = pages.setdefault(row["page_number"], {"margin": [], "body": []})
        bucket = "margin" if row["block_kind"] in {"HEADER", "FOOTER"} else "body"
        page[bucket].append(row["normalized_text"])
    return {
        page_number: {
            "margin": "\n".join(value["margin"]),
            "body": "\n".join(value["body"]),
        }
        for page_number, value in pages.items()
    }


def _page_diffs(
    before: dict[int, dict[str, str]],
    after: dict[int, dict[str, str]],
) -> list[PageDiff]:
    result: list[PageDiff] = []
    for page_number in sorted(set(before) | set(after)):
        old = before.get(page_number, {"margin": "", "body": ""})
        new = after.get(page_number, {"margin": "", "body": ""})
        categories: tuple[tuple[str, Literal["HEADER_FOOTER", "BODY"]], ...] = (
            ("margin", "HEADER_FOOTER"),
            ("body", "BODY"),
        )
        for bucket, category in categories:
            if old[bucket] == new[bucket]:
                continue
            result.append(
                PageDiff(
                    page_number=page_number,
                    category=category,
                    hunks=_diff_hunks(old[bucket], new[bucket]),
                )
            )
    return result


def _diff_hunks(before: str, after: str) -> list[DiffHunk]:
    before_words = before.split()
    after_words = after.split()
    result: list[DiffHunk] = []
    matcher = SequenceMatcher(a=before_words, b=after_words, autojunk=False)
    operations: dict[str, Literal["INSERT", "DELETE", "REPLACE", "EQUAL"]] = {
        "equal": "EQUAL",
        "insert": "INSERT",
        "delete": "DELETE",
        "replace": "REPLACE",
    }
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        result.append(
            DiffHunk(
                operation=operations[operation],
                before=(" ".join(before_words[old_start:old_end]) or None),
                after=(" ".join(after_words[new_start:new_end]) or None),
            )
        )
    return result


async def _item_row(
    connection: AsyncConnection,
    item_id: UUID,
    *,
    include_unpublished: bool,
) -> RowMapping | None:
    result = await connection.execute(
        text(
            """
            SELECT i.id, i.title, i.original_url, i.source_published_at,
                   i.first_discovered_at, i.activity_at, i.updated_at,
                   i.review_status, s.name AS source_name,
                   p.status AS publication_status,
                   p.current_revision_id AS publication_revision_id,
                   r.classification, r.document_number, r.issuing_authority,
                   r.regulation_status,
                   (SELECT count(*) FROM document_version version
                    WHERE version.document_id = i.primary_document_id) AS version_count,
                   latest_change.change_type AS latest_change_type,
                   latest_change.review_state AS latest_change_review_state,
                   (
                     (SELECT url_check.outcome FROM source_url_check url_check
                      WHERE url_check.document_id = i.primary_document_id
                      ORDER BY url_check.checked_at DESC, url_check.id DESC LIMIT 1)
                       IN ('NOT_FOUND','GONE')
                     AND
                     (SELECT url_check.outcome FROM source_url_check url_check
                      WHERE url_check.document_id = i.primary_document_id
                      ORDER BY url_check.checked_at DESC, url_check.id DESC LIMIT 1 OFFSET 1)
                       IN ('NOT_FOUND','GONE')
                   ) OR (
                     (SELECT count(*) FROM (
                        SELECT url_check.outcome FROM source_url_check url_check
                        WHERE url_check.document_id = i.primary_document_id
                        ORDER BY url_check.checked_at DESC, url_check.id DESC LIMIT 3
                     ) recent WHERE recent.outcome IN ('TIMEOUT','SERVER_ERROR')) = 3
                   ) AS source_unavailable,
                   (SELECT count(*) FROM claim_evidence e
                    JOIN claim c ON c.id = e.claim_id
                    WHERE c.item_id = i.id
                      AND c.verification_status = 'ACCEPTED') AS evidence_count
            FROM intelligence_item i
            JOIN source s ON s.id = i.source_id
            JOIN safety_regulation_profile r ON r.item_id = i.id
            LEFT JOIN publication p ON p.item_id = i.id
            LEFT JOIN LATERAL (
                SELECT COALESCE(state.change_type, change.change_type) AS change_type,
                       COALESCE(state.state, change.review_state) AS review_state
                FROM version_change change
                LEFT JOIN LATERAL (
                    SELECT event.change_type, event.state
                    FROM version_change_state_event event
                    WHERE event.version_change_id = change.id
                    ORDER BY event.created_at DESC, event.id DESC LIMIT 1
                ) state ON true
                WHERE change.document_id = i.primary_document_id
                ORDER BY change.created_at DESC, change.id DESC LIMIT 1
            ) latest_change ON true
            WHERE i.id = :item_id
              AND (:include_unpublished OR i.review_status = 'PENDING'
                   OR p.status IN ('PUBLISHED', 'WITHDRAWN'))
            """
        ),
        {"item_id": item_id, "include_unpublished": include_unpublished},
    )
    return result.mappings().first()


def _item_summary(row: RowMapping, *, reviewer_projection: bool = False) -> ItemSummary:
    states = _document_states(row)
    published = row["publication_status"] == "PUBLISHED" and row["review_status"] == "APPROVED"
    withdrawn = row["publication_status"] == "WITHDRAWN"
    if (not published or withdrawn) and not reviewer_projection:
        hints: dict[str, Any] = {}
        if states:
            hints["document_states"] = states
        if row["version_count"] > 1:
            hints["has_version_history"] = True
        return ItemSummary(
            id=row["id"],
            publication_revision_id=None,
            domain=Channel.SAFETY,
            content_type=ItemType.SAFETY_REGULATION,
            title=row["title"],
            source_name=row["source_name"],
            source_published_at=row["source_published_at"],
            first_discovered_at=row["first_discovered_at"],
            activity_at=row["activity_at"],
            original_url=row["original_url"],
            review_status=ReviewStatus(row["review_status"]),
            **hints,
        )
    return ItemSummary(
        id=row["id"],
        publication_revision_id=row["publication_revision_id"] if published else None,
        domain=Channel.SAFETY,
        content_type=ItemType.SAFETY_REGULATION,
        title=row["title"],
        source_name=row["source_name"],
        source_published_at=row["source_published_at"],
        first_discovered_at=row["first_discovered_at"],
        activity_at=row["activity_at"],
        original_url=row["original_url"],
        review_status=ReviewStatus(row["review_status"]),
        source_role="官方一手来源",
        last_updated_at=row["updated_at"],
        publication_status=(
            PublicationStatus.WITHDRAWN
            if withdrawn
            else PublicationStatus.PUBLISHED
            if published
            else PublicationStatus.PENDING_REVIEW
        ),
        evidence_status=EvidenceStatus.VERIFIED,
        evidence_count=row["evidence_count"],
        tags=["安全规定", "部门规章"],
        type_summary=TypeSummary(
            kind="SAFETY_REGULATION",
            document_number=row["document_number"],
            issuing_authority=row["issuing_authority"],
            regulation_status=row["regulation_status"],
            classification=row["classification"],
        ),
        detail_available=True,
        document_states=states or None,
        has_version_history=(row["version_count"] > 1) or None,
    )


def _document_states(row: RowMapping) -> list[DocumentState]:
    states: list[DocumentState] = []
    if row["publication_status"] == "WITHDRAWN":
        states.append(DocumentState.WITHDRAWN)
    latest_change = row["latest_change_type"]
    if latest_change not in {None, "INITIAL"}:
        states.append(DocumentState.UPDATED)
    if row["latest_change_review_state"] == "RE_REVIEW_PENDING" and latest_change != "INITIAL":
        states.append(DocumentState.RE_REVIEW_PENDING)
    if row["source_unavailable"] is True:
        states.append(DocumentState.SOURCE_UNAVAILABLE)
    return states


async def _claims_and_evidence(
    connection: AsyncConnection,
    item_id: UUID,
) -> tuple[list[ClaimView], list[EvidenceView]]:
    rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT c.id AS claim_id, c.claim_type, c.literal_value,
                           c.document_version_id,
                           e.id AS evidence_id, e.paragraph_id, e.char_start,
                           e.char_end, e.excerpt, e.excerpt_sha256, e.original_url,
                           e.locator_type, e.page_number, e.document_text_block_id,
                           e.document_table_cell_id, e.x0_mpt, e.y0_mpt,
                           e.x1_mpt, e.y1_mpt, e.confidence_bps,
                           cell.row_index, cell.column_index
                    FROM claim c
                    JOIN claim_evidence e ON e.claim_id = c.id
                    JOIN intelligence_item i ON i.id = c.item_id
                    LEFT JOIN document_table_cell cell
                      ON cell.id = e.document_table_cell_id
                    WHERE c.item_id = :item_id
                      AND c.document_version_id = i.current_document_version_id
                      AND c.verification_status = 'ACCEPTED'
                    ORDER BY c.created_at, c.id, e.created_at, e.id
                    """
                ),
                {"item_id": item_id},
            )
        ).mappings()
    )
    labels = {
        "title": "标题",
        "issuing_authority": "发布机关",
        "document_number": "文号",
        "published_at": "发布日期",
    }
    evidence_by_claim: dict[UUID, list[UUID]] = {}
    for row in rows:
        evidence_by_claim.setdefault(row["claim_id"], []).append(row["evidence_id"])
    claims: list[ClaimView] = []
    seen_claims: set[UUID] = set()
    for row in rows:
        claim_id = row["claim_id"]
        if claim_id in seen_claims:
            continue
        seen_claims.add(claim_id)
        claims.append(
            ClaimView(
                id=claim_id,
                claim_type=row["claim_type"],
                label=labels.get(row["claim_type"], row["claim_type"]),
                value=str(row["literal_value"]),
                evidence_ids=evidence_by_claim[claim_id],
            )
        )
    evidence = [
        EvidenceView(
            id=row["evidence_id"],
            claim_ids=[row["claim_id"]],
            document_version_id=row["document_version_id"],
            locator=_evidence_locator(row),
            paragraph_id=row["paragraph_id"],
            char_start=row["char_start"],
            char_end=row["char_end"],
            excerpt=row["excerpt"],
            excerpt_sha256=row["excerpt_sha256"],
            original_url=row["original_url"],
        )
        for row in rows
    ]
    return claims, evidence


def _evidence_locator(
    row: RowMapping,
) -> PdfTextLocator | PdfOcrLocator | PdfTableCellLocator | None:
    locator_type = row["locator_type"]
    if locator_type not in {"PDF_TEXT", "PDF_OCR", "PDF_TABLE_CELL"}:
        return None
    bbox = PageBoundingBox(
        x0=row["x0_mpt"],
        y0=row["y0_mpt"],
        x1=row["x1_mpt"],
        y1=row["y1_mpt"],
    )
    if locator_type == "PDF_OCR":
        return PdfOcrLocator(
            type="PDF_OCR",
            page_number=row["page_number"],
            block_id=row["document_text_block_id"],
            bbox=bbox,
            confidence_bps=row["confidence_bps"],
        )
    if locator_type == "PDF_TABLE_CELL":
        return PdfTableCellLocator(
            type="PDF_TABLE_CELL",
            page_number=row["page_number"],
            table_cell_id=row["document_table_cell_id"],
            row_index=row["row_index"],
            column_index=row["column_index"],
            bbox=bbox,
            confidence_bps=row["confidence_bps"],
        )
    return PdfTextLocator(
        type="PDF_TEXT",
        page_number=row["page_number"],
        block_id=row["document_text_block_id"],
        bbox=bbox,
    )


def _review_summary(row: RowMapping) -> ReviewTaskSummary:
    return ReviewTaskSummary(
        id=row["id"],
        item_id=row["item_id"],
        status=row["status"],
        risk_level=row["risk_level"],
        title=row["title"],
        source_name=row["source_name"],
        submitted_by=row["submitted_by"],
        submitted_at=row["submitted_at"],
        assigned_to=row["assigned_to"],
    )


def _feed_page(
    items: list[ItemSummary],
    *,
    now: datetime,
    mode: str,
    domain: str | None,
    next_cursor: str | None,
) -> FeedPage:
    fingerprint = sha256(
        "|".join([mode, domain or "all", *(str(item.id) for item in items)]).encode()
    ).hexdigest()
    notices = []
    if any(item.review_status == "PENDING" for item in items):
        notices.append(_restricted_notice())
    if mode == "selected":
        notices.append(
            FeedNotice(
                code="SELECTED_SCORES_UNAVAILABLE",
                level="info",
                message="暂无真实评分，精选频道不会返回未评分内容。",
            )
        )
    return FeedPage(
        items=items,
        next_cursor=next_cursor,
        fingerprint=f"sha256:{fingerprint}",
        generated_at=now,
        freshness="fresh",
        notices=notices,
    )


def _restricted_notice() -> FeedNotice:
    return FeedNotice(
        code="R3_RESTRICTED",
        level="info",
        message="待人工审核；暂不展示高风险字段。",
    )


def _encode_cursor(activity_at: datetime, item_id: UUID) -> str:
    raw = json.dumps([activity_at.isoformat(), str(item_id)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[datetime | None, UUID | None]:
    if value is None:
        return None, None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(decoded, list) or len(decoded) != 2:
            raise ValueError
        activity_at = datetime.fromisoformat(str(decoded[0]))
        item_id = UUID(str(decoded[1]))
        if activity_at.tzinfo is None or item_id.version != 7:
            raise ValueError
        return activity_at, item_id
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidFeedCursor("invalid feed cursor") from exc
