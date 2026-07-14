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
    ConfirmedFact,
    CriticalFieldDiff,
    CriticalSafetyField,
    DiffHunk,
    DocumentPageView,
    DocumentState,
    EventDetail,
    EventItem,
    EventRelationView,
    EventTimeline,
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
    SafetyCaseFactField,
    SafetyCaseTypeSummary,
    SafetyRegulationTypeSummary,
    UnverifiedFact,
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
            safety_profiles = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT report_stage, incident_status, count(*) AS count
                            FROM safety_case_profile
                            GROUP BY report_stage, incident_status
                            ORDER BY report_stage, incident_status
                            """
                        )
                    )
                ).mappings()
            )
            safety_conflicts = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT field_name, count(*) AS count
                            FROM claim_conflict
                            WHERE status = 'PENDING_REVIEW'
                            GROUP BY field_name
                            ORDER BY field_name
                            """
                        )
                    )
                ).mappings()
            )
            safety_queues = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              (SELECT count(*)
                               FROM event_item_candidate candidate
                               WHERE NOT EXISTS (
                                 SELECT 1 FROM event_item_decision decision
                                 WHERE decision.candidate_id = candidate.id
                               )) AS pending_event_candidates,
                              (SELECT count(*)
                               FROM claim protected_claim
                               JOIN intelligence_item item
                                 ON item.id = protected_claim.item_id
                               LEFT JOIN LATERAL (
                                 SELECT decision.action
                                 FROM claim_field_decision decision
                                 WHERE decision.claim_id = protected_claim.id
                                 ORDER BY decision.created_at DESC, decision.id DESC
                                 LIMIT 1
                               ) latest_decision ON true
                               WHERE item.item_type = 'SAFETY_CASE'
                                 AND protected_claim.critical = true
                                 AND protected_claim.claim_type IN (
                                   'deaths','injuries','loss_amount_minor',
                                   'official_direct_causes','responsibility_findings'
                                 )
                                 AND (
                                   latest_decision.action IS NULL
                                   OR latest_decision.action = 'REVOKE'
                                 )) AS pending_critical_claims
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
        rendered += _render_safety_case_metrics(
            profiles=[dict(profile) for profile in safety_profiles],
            conflicts=[dict(conflict) for conflict in safety_conflicts],
            pending_event_candidates=int(safety_queues["pending_event_candidates"]),
            pending_critical_claims=int(safety_queues["pending_critical_claims"]),
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
            or (
                content_type is not None
                and content_type not in {"SAFETY_REGULATION", "SAFETY_CASE"}
            )
        ):
            return _feed_page([], now=now, mode=mode, domain=domain, next_cursor=None)

        cursor_time, cursor_id = _decode_cursor(cursor)
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT i.id, i.item_type, i.title, i.original_url,
                                   i.source_published_at,
                                   i.first_discovered_at, i.activity_at, i.updated_at,
                                   i.review_status, s.name AS source_name,
                                   p.status AS publication_status,
                                   p.current_revision_id AS publication_revision_id,
                                   r.classification, r.document_number,
                                   r.issuing_authority, r.regulation_status,
                                   case_profile.report_stage,
                                   case_profile.accident_type,
                                   case_profile.engineering_type,
                                   case_profile.occurred_at,
                                   case_profile.region_name,
                                   case_profile.deaths,
                                   case_profile.injuries,
                                   case_profile.loss_amount_minor,
                                   case_profile.loss_currency,
                                   case_profile.incident_status,
                                   case_profile.official_direct_causes,
                                   case_profile.responsibility_findings,
                                   case_profile.rectification_has_open_issues,
                                   case_profile.similar_scenario_tags,
                                   case_profile.prevention_measure_tags,
                                   event_link.event_id,
                                   COALESCE(conflicts.fields, ARRAY[]::text[])
                                       AS conflicted_fields,
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
                                      AND (
                                        c.verification_status = 'ACCEPTED'
                                        OR 'ACCEPT' = (
                                          SELECT decision.action
                                          FROM claim_field_decision decision
                                          WHERE decision.claim_id = c.id
                                          ORDER BY decision.created_at DESC, decision.id DESC
                                          LIMIT 1
                                        )
                                      )
                                      AND (
                                        i.item_type <> 'SAFETY_CASE'
                                        OR (
                                          c.verification_status = 'ACCEPTED'
                                          AND c.critical = false
                                        )
                                        OR e.id = (
                                          SELECT decision.evidence_id
                                          FROM claim_field_decision decision
                                          WHERE decision.claim_id = c.id
                                          ORDER BY decision.created_at DESC, decision.id DESC
                                          LIMIT 1
                                        )
                                      )) AS evidence_count
                            FROM intelligence_item i
                            JOIN source s ON s.id = i.source_id
                            LEFT JOIN safety_regulation_profile r ON r.item_id = i.id
                            LEFT JOIN safety_case_profile case_profile
                              ON case_profile.item_id = i.id
                            LEFT JOIN event_item event_link ON event_link.item_id = i.id
                            LEFT JOIN publication p ON p.item_id = i.id
                            LEFT JOIN LATERAL (
                                SELECT array_agg(DISTINCT conflict.field_name)
                                    AS fields
                                FROM public_safety_case_conflict conflict
                                WHERE conflict.source_item_id = i.id
                            ) conflicts ON true
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
                              AND i.risk_level = 'R3'
                              AND (
                                CAST(:content_type AS text) IS NULL
                                OR i.item_type = CAST(:content_type AS text)
                              )
                              AND (
                                (i.item_type = 'SAFETY_REGULATION' AND r.item_id IS NOT NULL)
                                OR
                                (i.item_type = 'SAFETY_CASE'
                                  AND case_profile.item_id IS NOT NULL)
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
                            "content_type": content_type,
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

    async def get_event(self, event_id: UUID) -> EventDetail:
        async with self._engine.connect() as connection:
            event = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH safe_members AS (
                              SELECT membership.event_id AS id,
                                     header_item.id AS item_id,
                                     header_item.title,
                                     header_item.source_published_at,
                                     membership.confirmed_at,
                                     header_profile.occurred_at,
                                     header_profile.region_name,
                                     header_profile.project_name,
                                     header_profile.accident_type,
                                     header_profile.engineering_type,
                                     header_profile.incident_status,
                                     header_profile.rectification_has_open_issues,
                                     header_profile.similar_scenario_tags,
                                     header_profile.prevention_measure_tags
                              FROM event_item membership
                              JOIN event confirmed_event
                                ON confirmed_event.id = membership.event_id
                               AND confirmed_event.confirmation_status = 'CONFIRMED'
                              JOIN intelligence_item header_item
                                ON header_item.id = membership.item_id
                              JOIN publication header_publication
                                ON header_publication.item_id = header_item.id
                               AND header_publication.status = 'PUBLISHED'
                              JOIN safety_case_profile header_profile
                                ON header_profile.item_id = header_item.id
                              WHERE membership.event_id = :event_id
                                AND header_item.risk_level = 'R3'
                                AND header_item.review_status = 'APPROVED'
                            ),
                            latest_member AS (
                              SELECT *
                              FROM safe_members latest
                              ORDER BY latest.source_published_at DESC NULLS LAST,
                                       latest.confirmed_at DESC, latest.item_id DESC
                              LIMIT 1
                            )
                            SELECT latest.id,
                                   (SELECT earliest.title
                                    FROM safe_members earliest
                                    ORDER BY earliest.source_published_at ASC NULLS LAST,
                                             earliest.confirmed_at, earliest.item_id
                                    LIMIT 1) AS title,
                                   (SELECT identity.occurred_at
                                    FROM safe_members identity
                                    WHERE identity.occurred_at IS NOT NULL
                                    ORDER BY identity.source_published_at DESC NULLS LAST,
                                             identity.confirmed_at DESC, identity.item_id DESC
                                    LIMIT 1) AS occurred_at,
                                   (SELECT identity.region_name
                                    FROM safe_members identity
                                    WHERE identity.region_name IS NOT NULL
                                    ORDER BY identity.source_published_at DESC NULLS LAST,
                                             identity.confirmed_at DESC, identity.item_id DESC
                                    LIMIT 1) AS region_name,
                                   (SELECT identity.project_name
                                    FROM safe_members identity
                                    WHERE identity.project_name IS NOT NULL
                                    ORDER BY identity.source_published_at DESC NULLS LAST,
                                             identity.confirmed_at DESC, identity.item_id DESC
                                    LIMIT 1) AS project_name,
                                   (SELECT identity.accident_type
                                    FROM safe_members identity
                                    WHERE identity.accident_type IS NOT NULL
                                    ORDER BY identity.source_published_at DESC NULLS LAST,
                                             identity.confirmed_at DESC, identity.item_id DESC
                                    LIMIT 1) AS accident_type,
                                   (SELECT identity.engineering_type
                                    FROM safe_members identity
                                    WHERE identity.engineering_type IS NOT NULL
                                    ORDER BY identity.source_published_at DESC NULLS LAST,
                                             identity.confirmed_at DESC, identity.item_id DESC
                                    LIMIT 1) AS engineering_type,
                                   latest.incident_status,
                                   latest.rectification_has_open_issues,
                                   latest.similar_scenario_tags,
                                   latest.prevention_measure_tags
                            FROM latest_member latest
                            """
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .first()
            )
            if event is None:
                raise IntelligenceNotFound("safety event does not exist")

            timeline_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT i.id AS item_id, i.title, profile.report_stage,
                                   profile.incident_status, source.name AS source_name,
                                   i.source_published_at, i.original_url, i.review_status,
                                   publication.current_revision_id AS publication_revision_id,
                                   publication.status AS publication_status,
                                   relation.relation_type,
                                   (SELECT count(*) FROM claim_evidence evidence
                                    JOIN claim ON claim.id = evidence.claim_id
                                    WHERE claim.item_id = i.id
                                       AND (
                                         (claim.verification_status = 'ACCEPTED'
                                          AND claim.critical = false)
                                         OR (
                                           'ACCEPT' = (
                                             SELECT decision.action
                                             FROM claim_field_decision decision
                                             WHERE decision.claim_id = claim.id
                                             ORDER BY decision.created_at DESC, decision.id DESC
                                             LIMIT 1
                                           )
                                           AND evidence.id = (
                                             SELECT decision.evidence_id
                                             FROM claim_field_decision decision
                                             WHERE decision.claim_id = claim.id
                                             ORDER BY decision.created_at DESC, decision.id DESC
                                             LIMIT 1
                                           )
                                         )
                                       )
                                       AND NOT EXISTS (
                                        SELECT 1 FROM public_safety_case_conflict conflict
                                        WHERE conflict.event_id = membership.event_id
                                          AND conflict.field_name = claim.claim_type
                                      )) AS evidence_count
                            FROM event_item membership
                            JOIN intelligence_item i ON i.id = membership.item_id
                            JOIN safety_case_profile profile ON profile.item_id = i.id
                            JOIN source ON source.id = i.source_id
                            JOIN publication ON publication.item_id = i.id
                              AND publication.status IN ('PUBLISHED','WITHDRAWN')
                            LEFT JOIN LATERAL (
                                SELECT confirmed.relation_type
                                FROM event_relation confirmed
                                WHERE confirmed.event_id = membership.event_id
                                  AND confirmed.source_item_id = i.id
                                ORDER BY
                                  (confirmed.relation_type = 'CORRECTS') ASC,
                                  confirmed.confirmed_at DESC, confirmed.id DESC
                                LIMIT 1
                            ) relation ON true
                            WHERE membership.event_id = :event_id
                              AND i.risk_level = 'R3'
                              AND i.review_status = 'APPROVED'
                            ORDER BY i.source_published_at NULLS LAST,
                                     membership.confirmed_at, i.id
                            """
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            confirmed_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT source_item_id, claim_id, field_name,
                                   literal_value, evidence_id, reviewed_at,
                                   loss_currency
                            FROM public_safety_case_accepted_claim
                            WHERE event_id = :event_id
                            ORDER BY reviewed_at, claim_id
                            """
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            conflict_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT conflict.source_item_id,
                                   NULL::uuid AS claim_id,
                                   conflict.conflict_id,
                                   conflict.field_name,
                                   ARRAY[]::uuid[] AS evidence_ids
                            FROM public_safety_case_conflict conflict
                            WHERE conflict.event_id = :event_id
                              AND conflict.field_name IN (
                                'deaths','injuries','loss_amount_minor',
                                'official_direct_causes','responsibility_findings'
                              )
                            ORDER BY conflict.detected_at, conflict.conflict_id
                            """
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            pending_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT claim.item_id AS source_item_id, claim.id AS claim_id,
                                   claim.claim_type AS field_name,
                                   array_remove(array_agg(evidence.id), NULL) AS evidence_ids
                            FROM claim
                            JOIN event_item membership ON membership.item_id = claim.item_id
                            JOIN intelligence_item item ON item.id = claim.item_id
                            JOIN publication ON publication.item_id = item.id
                              AND publication.status = 'PUBLISHED'
                            LEFT JOIN LATERAL (
                              SELECT decision.action
                              FROM claim_field_decision decision
                              WHERE decision.claim_id = claim.id
                              ORDER BY decision.created_at DESC, decision.id DESC
                              LIMIT 1
                            ) latest_decision ON true
                            LEFT JOIN claim_evidence evidence ON evidence.claim_id = claim.id
                            WHERE membership.event_id = :event_id
                              AND item.risk_level = 'R3'
                              AND item.review_status = 'APPROVED'
                              AND claim.critical = true
                              AND claim.claim_type IN (
                                'deaths','injuries','loss_amount_minor',
                                'official_direct_causes','responsibility_findings'
                              )
                              AND (
                                latest_decision.action IS NULL
                                OR latest_decision.action = 'REVOKE'
                              )
                            GROUP BY claim.item_id, claim.id, claim.claim_type, claim.created_at
                            ORDER BY claim.created_at, claim.id
                            """
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            relation_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT relation.id, relation.event_id,
                                   relation.source_item_id, relation.target_item_id,
                                   relation.relation_type, relation.confirmed_by,
                                   relation.confirmed_at
                            FROM event_relation relation
                            JOIN intelligence_item source_item
                              ON source_item.id = relation.source_item_id
                            JOIN publication source_publication
                              ON source_publication.item_id = source_item.id
                             AND source_publication.status IN ('PUBLISHED','WITHDRAWN')
                            JOIN intelligence_item target_item
                              ON target_item.id = relation.target_item_id
                            JOIN publication target_publication
                              ON target_publication.item_id = target_item.id
                             AND target_publication.status IN ('PUBLISHED','WITHDRAWN')
                            WHERE relation.event_id = :event_id
                              AND source_item.risk_level = 'R3'
                              AND source_item.review_status = 'APPROVED'
                              AND target_item.risk_level = 'R3'
                              AND target_item.review_status = 'APPROVED'
                            ORDER BY relation.confirmed_at, relation.id
                            """
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )

        confirmed_facts = [_confirmed_fact(row) for row in confirmed_rows]
        unverified_facts = [_conflicting_fact(row) for row in conflict_rows]
        unverified_facts.extend(_pending_fact(row) for row in pending_rows)
        timeline = [
            EventItem(
                item_id=row["item_id"],
                title=row["title"],
                report_stage=row["report_stage"],
                incident_status=row["incident_status"],
                source_name=row["source_name"],
                source_published_at=row["source_published_at"],
                original_url=row["original_url"],
                review_status=row["review_status"],
                publication_revision_id=row["publication_revision_id"],
                relation_type=row["relation_type"],
                evidence_count=row["evidence_count"],
                document_states=(
                    [DocumentState.WITHDRAWN] if row["publication_status"] == "WITHDRAWN" else None
                ),
            )
            for row in timeline_rows
        ]
        relations = [
            EventRelationView(
                id=row["id"],
                event_id=row["event_id"],
                from_item_id=row["source_item_id"],
                to_item_id=row["target_item_id"],
                relation_type=row["relation_type"],
                reviewed_by=row["confirmed_by"],
                reviewed_at=row["confirmed_at"],
            )
            for row in relation_rows
        ]
        return EventDetail(
            id=event["id"],
            title=event["title"],
            project_name=event["project_name"],
            occurred_at=event["occurred_at"],
            region=event["region_name"],
            hazard_type=event["accident_type"],
            engineering_type=event["engineering_type"],
            incident_status=event["incident_status"],
            rectification_has_open_issues=event["rectification_has_open_issues"],
            confirmed_facts=confirmed_facts,
            unverified_facts=unverified_facts,
            timeline=EventTimeline(event_id=event_id, items=timeline),
            relations=relations,
            similar_scenario_tags=list(event["similar_scenario_tags"] or []),
            prevention_measure_tags=list(event["prevention_measure_tags"] or []),
        )

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
            claims, evidence = await _claims_and_evidence(
                connection,
                task_row["item_id"],
                include_candidates=True,
            )
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
            SELECT i.id, i.item_type, i.title, i.original_url, i.source_published_at,
                   i.first_discovered_at, i.activity_at, i.updated_at,
                   i.review_status, s.name AS source_name,
                   p.status AS publication_status,
                   p.current_revision_id AS publication_revision_id,
                   r.classification, r.document_number, r.issuing_authority,
                   r.regulation_status,
                   case_profile.report_stage,
                   case_profile.accident_type,
                   case_profile.engineering_type,
                   case_profile.occurred_at,
                   case_profile.region_name,
                   case_profile.deaths,
                   case_profile.injuries,
                   case_profile.loss_amount_minor,
                   case_profile.loss_currency,
                   case_profile.incident_status,
                   case_profile.official_direct_causes,
                   case_profile.responsibility_findings,
                   case_profile.rectification_has_open_issues,
                   case_profile.similar_scenario_tags,
                   case_profile.prevention_measure_tags,
                   event_link.event_id,
                   COALESCE(conflicts.fields, ARRAY[]::text[]) AS conflicted_fields,
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
                      AND (
                        c.verification_status = 'ACCEPTED'
                        OR 'ACCEPT' = (
                          SELECT decision.action
                          FROM claim_field_decision decision
                          WHERE decision.claim_id = c.id
                          ORDER BY decision.created_at DESC, decision.id DESC
                          LIMIT 1
                        )
                      )
                       AND (
                         i.item_type <> 'SAFETY_CASE'
                         OR (
                           c.verification_status = 'ACCEPTED'
                           AND c.critical = false
                         )
                         OR e.id = (
                          SELECT decision.evidence_id
                          FROM claim_field_decision decision
                          WHERE decision.claim_id = c.id
                          ORDER BY decision.created_at DESC, decision.id DESC
                          LIMIT 1
                        )
                      )) AS evidence_count
            FROM intelligence_item i
            JOIN source s ON s.id = i.source_id
            LEFT JOIN safety_regulation_profile r ON r.item_id = i.id
            LEFT JOIN safety_case_profile case_profile ON case_profile.item_id = i.id
            LEFT JOIN event_item event_link ON event_link.item_id = i.id
            LEFT JOIN publication p ON p.item_id = i.id
            LEFT JOIN LATERAL (
                SELECT array_agg(DISTINCT conflict.field_name) AS fields
                FROM public_safety_case_conflict conflict
                WHERE conflict.source_item_id = i.id
            ) conflicts ON true
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
              AND (:include_unpublished OR i.risk_level <> 'R4')
              AND (
                (i.item_type = 'SAFETY_REGULATION' AND r.item_id IS NOT NULL)
                OR
                (i.item_type = 'SAFETY_CASE' AND case_profile.item_id IS NOT NULL)
              )
              AND (:include_unpublished OR i.review_status = 'PENDING'
                   OR p.status IN ('PUBLISHED', 'WITHDRAWN'))
            """
        ),
        {"item_id": item_id, "include_unpublished": include_unpublished},
    )
    return result.mappings().first()


def _item_summary(row: RowMapping, *, reviewer_projection: bool = False) -> ItemSummary:
    states = _document_states(row)
    item_type = ItemType(str(row.get("item_type", ItemType.SAFETY_REGULATION.value)))
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
            content_type=item_type,
            title=row["title"],
            source_name=row["source_name"],
            source_published_at=row["source_published_at"],
            first_discovered_at=row["first_discovered_at"],
            activity_at=row["activity_at"],
            original_url=row["original_url"],
            review_status=ReviewStatus(row["review_status"]),
            **hints,
        )
    if item_type is ItemType.SAFETY_CASE:
        hidden_fields = {str(field) for field in row.get("conflicted_fields", []) or []}
        conflicted_fields = [
            _critical_safety_field(str(field)) for field in row.get("conflicted_fields", []) or []
        ]
        type_summary: SafetyCaseTypeSummary | SafetyRegulationTypeSummary = SafetyCaseTypeSummary(
            kind="SAFETY_CASE",
            event_id=row.get("event_id"),
            report_stage=row.get("report_stage"),
            incident_status=row.get("incident_status"),
            hazard_type=row.get("accident_type"),
            engineering_type=row.get("engineering_type"),
            occurred_at=row.get("occurred_at"),
            region=row.get("region_name"),
            deaths=None if "deaths" in hidden_fields else row.get("deaths"),
            injuries=None if "injuries" in hidden_fields else row.get("injuries"),
            loss_amount_minor=(
                None if "loss_amount_minor" in hidden_fields else row.get("loss_amount_minor")
            ),
            loss_currency=(
                None if "loss_amount_minor" in hidden_fields else row.get("loss_currency")
            ),
            conflicted_fields=conflicted_fields or None,
            official_direct_causes=(
                None
                if "official_direct_causes" in hidden_fields
                else row.get("official_direct_causes")
            ),
            responsibility_findings=(
                None
                if "responsibility_findings" in hidden_fields
                else row.get("responsibility_findings")
            ),
            rectification_has_open_issues=row.get("rectification_has_open_issues"),
            similar_scenario_tags=row.get("similar_scenario_tags") or None,
            prevention_measure_tags=row.get("prevention_measure_tags") or None,
        )
        tags = ["安全案例", str(row.get("report_stage") or "待核实")]
    else:
        type_summary = SafetyRegulationTypeSummary(
            kind="SAFETY_REGULATION",
            document_number=row["document_number"],
            issuing_authority=row["issuing_authority"],
            regulation_status=row["regulation_status"],
            classification=row["classification"],
        )
        tags = ["安全规定", "部门规章"]

    return ItemSummary(
        id=row["id"],
        publication_revision_id=row["publication_revision_id"] if published else None,
        domain=Channel.SAFETY,
        content_type=item_type,
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
        tags=tags,
        type_summary=type_summary,
        detail_available=True,
        document_states=states or None,
        has_version_history=(row["version_count"] > 1) or None,
    )


def _critical_safety_field(field_name: str) -> CriticalSafetyField:
    mapping = {
        "deaths": CriticalSafetyField.DEATH_COUNT,
        "injuries": CriticalSafetyField.INJURY_COUNT,
        "loss_amount_minor": CriticalSafetyField.LOSS_AMOUNT_MINOR,
        "official_direct_causes": CriticalSafetyField.OFFICIAL_DIRECT_CAUSES,
        "responsibility_findings": CriticalSafetyField.RESPONSIBILITY_FINDINGS,
    }
    return mapping[field_name]


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
    *,
    include_candidates: bool = False,
) -> tuple[list[ClaimView], list[EvidenceView]]:
    rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT c.id AS claim_id, c.claim_type, c.literal_value,
                           c.document_version_id, c.verification_status, c.critical,
                           e.id AS evidence_id, e.paragraph_id, e.char_start,
                           e.char_end, e.excerpt, e.excerpt_sha256, e.original_url,
                           e.locator_type, e.page_number, e.document_text_block_id,
                           e.document_table_cell_id, e.x0_mpt, e.y0_mpt,
                           e.x1_mpt, e.y1_mpt, e.confidence_bps,
                           cell.row_index, cell.column_index,
                           latest_decision.action AS field_decision_action,
                           latest_decision.evidence_id AS field_decision_evidence_id
                    FROM claim c
                    JOIN claim_evidence e ON e.claim_id = c.id
                    JOIN intelligence_item i ON i.id = c.item_id
                    LEFT JOIN document_table_cell cell
                      ON cell.id = e.document_table_cell_id
                    LEFT JOIN LATERAL (
                        SELECT decision.action, decision.evidence_id
                        FROM claim_field_decision decision
                        WHERE decision.claim_id = c.id
                        ORDER BY decision.created_at DESC, decision.id DESC
                        LIMIT 1
                    ) latest_decision ON true
                    WHERE c.item_id = :item_id
                      AND c.document_version_id = i.current_document_version_id
                      AND (
                        (
                          :include_candidates
                          AND i.item_type = 'SAFETY_CASE'
                          AND c.claim_type IN (
                            'deaths','injuries','loss_amount_minor',
                            'official_direct_causes','responsibility_findings'
                          )
                        )
                        OR c.verification_status = 'ACCEPTED'
                        OR latest_decision.action = 'ACCEPT'
                      )
                      AND (
                        i.item_type <> 'SAFETY_CASE'
                        OR :include_candidates
                        OR (
                          c.verification_status = 'ACCEPTED'
                          AND c.critical = false
                        )
                        OR e.id = latest_decision.evidence_id
                      )
                      AND (
                        i.item_type <> 'SAFETY_CASE'
                        OR :include_candidates
                        OR (
                          c.verification_status = 'ACCEPTED'
                          AND c.critical = false
                        )
                        OR EXISTS (
                          SELECT 1
                          FROM public_safety_case_accepted_claim effective
                          WHERE effective.claim_id = c.id
                            AND effective.evidence_id = e.id
                        )
                      )
                    ORDER BY c.created_at, c.id, e.created_at, e.id
                    """
                ),
                {"item_id": item_id, "include_candidates": include_candidates},
            )
        ).mappings()
    )
    labels = {
        "title": "标题",
        "issuing_authority": "发布机关",
        "document_number": "文号",
        "published_at": "发布日期",
        "deaths": "死亡人数",
        "injuries": "受伤人数",
        "loss_amount_minor": "直接经济损失",
        "official_direct_causes": "正式认定原因",
        "responsibility_findings": "责任认定",
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
                decision_status=(
                    _claim_decision_status(
                        row["field_decision_action"],
                        verification_status=row["verification_status"],
                        critical=row["critical"],
                    )
                    if include_candidates
                    else None
                ),
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


def _claim_decision_status(
    action: object,
    *,
    verification_status: object,
    critical: object,
) -> Literal["PENDING", "ACCEPTED", "REJECTED"]:
    if action == "ACCEPT":
        return "ACCEPTED"
    if action == "REJECT":
        return "REJECTED"
    if verification_status == "ACCEPTED" and critical is False:
        return "ACCEPTED"
    return "PENDING"


_SAFETY_FACT_FIELDS = {
    "deaths": SafetyCaseFactField.DEATH_COUNT,
    "injuries": SafetyCaseFactField.INJURY_COUNT,
    "loss_amount_minor": SafetyCaseFactField.LOSS_AMOUNT_MINOR,
    "official_direct_causes": SafetyCaseFactField.OFFICIAL_DIRECT_CAUSES,
    "responsibility_findings": SafetyCaseFactField.RESPONSIBILITY_FINDINGS,
}

_SAFETY_FACT_LABELS = {
    "deaths": "死亡人数",
    "injuries": "受伤人数",
    "loss_amount_minor": "直接经济损失",
    "official_direct_causes": "正式认定原因",
    "responsibility_findings": "责任认定",
}


def _confirmed_fact(row: RowMapping) -> ConfirmedFact:
    field_name = str(row["field_name"])
    return ConfirmedFact(
        source_item_id=row["source_item_id"],
        claim_id=row["claim_id"],
        field=_SAFETY_FACT_FIELDS[field_name],
        label=_SAFETY_FACT_LABELS[field_name],
        value=_safety_fact_value(
            field_name,
            row["literal_value"],
            loss_currency=row["loss_currency"],
        ),
        unit="人" if field_name in {"deaths", "injuries"} else None,
        evidence_ids=[row["evidence_id"]],
        reviewed_at=row["reviewed_at"],
    )


def _conflicting_fact(row: RowMapping) -> UnverifiedFact:
    field_name = str(row["field_name"])
    return UnverifiedFact(
        source_item_id=row["source_item_id"],
        claim_id=row["claim_id"],
        conflict_id=row["conflict_id"],
        field=_SAFETY_FACT_FIELDS[field_name],
        label=_SAFETY_FACT_LABELS[field_name],
        status="CONFLICTING",
        reason="正式来源的关键事实存在冲突。候选值已隐藏，须由其他审核人决定。",
        evidence_ids=list(row["evidence_ids"] or []),
    )


def _pending_fact(row: RowMapping) -> UnverifiedFact:
    field_name = str(row["field_name"])
    return UnverifiedFact(
        source_item_id=row["source_item_id"],
        claim_id=row["claim_id"],
        field=_SAFETY_FACT_FIELDS[field_name],
        label=_SAFETY_FACT_LABELS[field_name],
        status="PENDING_REVIEW",
        reason="关键事实尚未完成人工逐字段审核。",
        evidence_ids=list(row["evidence_ids"] or []),
    )


def _safety_fact_value(
    field_name: str,
    value: object,
    *,
    loss_currency: object = None,
) -> str | int | list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raw = str(value)
    if field_name in {"deaths", "injuries"}:
        return int(raw)
    if field_name == "loss_amount_minor":
        return _format_minor_currency(int(raw), str(loss_currency or "UNKNOWN"))
    if isinstance(value, str) and raw.startswith("["):
        decoded = json.loads(raw)
        if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
            return decoded
    return raw


def _format_minor_currency(amount_minor: int, currency: str) -> str:
    major, minor = divmod(amount_minor, 100)
    currency_label = "人民币元" if currency == "CNY" else currency
    return f"{major:,}.{minor:02d} {currency_label}"


def _render_safety_case_metrics(
    *,
    profiles: list[Mapping[str, Any]],
    conflicts: list[Mapping[str, Any]],
    pending_event_candidates: int,
    pending_critical_claims: int,
) -> str:
    rendered = (
        "# TYPE srbg_safety_event_candidates_pending gauge\n"
        f"srbg_safety_event_candidates_pending {pending_event_candidates}\n"
        "# TYPE srbg_safety_critical_claims_pending gauge\n"
        f"srbg_safety_critical_claims_pending {pending_critical_claims}\n"
        "# TYPE srbg_safety_case_items gauge\n"
    )
    for profile in profiles:
        rendered += (
            "srbg_safety_case_items{"
            f'report_stage="{profile["report_stage"]}",'
            f'incident_status="{profile["incident_status"]}"'
            f"}} {profile['count']}\n"
        )
    rendered += "# TYPE srbg_safety_claim_conflicts_pending gauge\n"
    for conflict in conflicts:
        rendered += (
            "srbg_safety_claim_conflicts_pending{"
            f'field_name="{conflict["field_name"]}"'
            f"}} {conflict['count']}\n"
        )
    return rendered


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
