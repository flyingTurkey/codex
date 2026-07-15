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
    AbstractAvailability,
    AiEquipmentTypeSummary,
    Channel,
    ClaimView,
    ConfirmedFact,
    CriticalFieldDiff,
    CriticalSafetyField,
    DiffHunk,
    DigitalCaseDetail,
    DigitalCaseEntity,
    DigitalCaseOutcome,
    DigitalCaseSourceNature,
    DigitalCaseTypeSummary,
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
    IotProductTypeSummary,
    ItemDetail,
    ItemSummary,
    ItemType,
    LowAltitudeEquipmentTypeSummary,
    MaturityLevel,
    OutcomeVerification,
    PageBoundingBox,
    PageDiff,
    PaperAccessLevel,
    PaperAuthor,
    PaperDetail,
    PaperOpenStatus,
    PaperRelationStatus,
    PaperType,
    PaperTypeSummary,
    PdfOcrLocator,
    PdfTableCellLocator,
    PdfTextLocator,
    ProductCapability,
    ProductCapabilityKind,
    ProductEngineeringCase,
    ProductEntity,
    ProductEvidenceLevel,
    ProductNormalizationCandidateView,
    ProductPermitStatus,
    PublicationStatus,
    RecommendedAction,
    RelevanceFactor,
    RelevanceSummary,
    ResearchInterpretation,
    ReviewStatus,
    ReviewTaskDetail,
    ReviewTaskSummary,
    SafetyCaseFactField,
    SafetyCaseTypeSummary,
    SafetyRegulationTypeSummary,
    SimilarPaper,
    SoftwareProductTypeSummary,
    TechnologyProductDetail,
    UnverifiedFact,
    VersionDiffResponse,
    VersionTimelineEntry,
    VersionTimelineResponse,
)

from srbg_api.papers.domain import format_bibtex, format_gbt7714, format_ris


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
            digital_profiles = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT source_nature, maturity_level, count(*) AS count
                            FROM digital_case_profile
                            GROUP BY source_nature, maturity_level
                            ORDER BY source_nature, maturity_level
                            """
                        )
                    )
                ).mappings()
            )
            digital_outcomes = dict(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT outcome_kind, count(*) AS count
                            FROM digital_case_outcome
                            GROUP BY outcome_kind
                            """
                        )
                    )
                ).tuples()
            )
            pending_enterprise_review = int(
                await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM digital_case_profile profile
                        JOIN intelligence_item item ON item.id = profile.item_id
                        WHERE profile.source_nature = 'ENTERPRISE_SELF_REPORT'
                          AND item.review_status = 'PENDING'
                        """
                    )
                )
                or 0
            )
            paper_profiles = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT access_level, relation_status, count(*) AS count
                            FROM paper_profile
                            GROUP BY access_level, relation_status
                            ORDER BY access_level, relation_status
                            """
                        )
                    )
                ).mappings()
            )
            paper_queues = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              count(*) FILTER (WHERE status = 'PENDING_REVIEW')
                                AS pending_duplicates,
                              (SELECT count(*) FROM item_relation_candidate
                               WHERE status = 'PENDING_REVIEW'
                                 AND relation_type IN ('CORRECTS','SUPERSEDES','RETRACTS'))
                                AS pending_updates
                            FROM paper_duplicate_candidate
                            """
                        )
                    )
                ).mappings().one()
            )
            product_profiles = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT item_type, evidence_level, permit_status, count(*) AS count
                            FROM technology_product_profile
                            GROUP BY item_type, evidence_level, permit_status
                            ORDER BY item_type, evidence_level, permit_status
                            """
                        )
                    )
                ).mappings()
            )
            product_capabilities = dict(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT kind, count(*) AS count
                            FROM technology_product_capability
                            GROUP BY kind
                            """
                        )
                    )
                ).tuples()
            )
            pending_product_normalization = int(
                await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM product_normalization_candidate
                        WHERE status = 'PENDING_REVIEW'
                        """
                    )
                )
                or 0
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
        rendered += _render_digital_case_metrics(
            profiles=[dict(profile) for profile in digital_profiles],
            outcomes={str(key): int(value) for key, value in digital_outcomes.items()},
            pending_enterprise_review=pending_enterprise_review,
        )
        rendered += _render_paper_metrics(
            profiles=[dict(profile) for profile in paper_profiles],
            pending_duplicates=int(paper_queues["pending_duplicates"]),
            pending_updates=int(paper_queues["pending_updates"]),
        )
        rendered += _render_technology_product_metrics(
            profiles=[dict(profile) for profile in product_profiles],
            capabilities={str(key): int(value) for key, value in product_capabilities.items()},
            pending_normalization=pending_product_normalization,
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
        engineering_domain: str | None = None,
        scenario: str | None = None,
        maturity: str | None = None,
        source_nature: str | None = None,
        paper_type: str | None = None,
        technology_tag: str | None = None,
        access_level: str | None = None,
        year: int | None = None,
        product_kind: str | None = None,
        evidence_level: str | None = None,
        deployment_mode: str | None = None,
    ) -> FeedPage:
        now = datetime.now(UTC)
        if content_type in {
            "SOFTWARE_PRODUCT",
            "IOT_PRODUCT",
            "LOW_ALTITUDE_EQUIPMENT",
            "AI_EQUIPMENT",
        }:
            return await self._get_product_feed(
                mode=mode,
                content_type=content_type,
                cursor=cursor,
                limit=limit,
                product_kind=product_kind,
                evidence_level=evidence_level,
                deployment_mode=deployment_mode,
                scenario=scenario,
                maturity=maturity,
            )
        if content_type == "JOURNAL_PAPER":
            return await self._get_paper_feed(
                mode=mode,
                cursor=cursor,
                limit=limit,
                engineering_domain=engineering_domain,
                technology_tag=technology_tag,
                maturity=maturity,
                paper_type=paper_type,
                access_level=access_level,
                year=year,
            )
        if domain == "digital" or content_type == "DIGITAL_CASE":
            return await self._get_digital_feed(
                mode=mode,
                sort=sort,
                cursor=cursor,
                limit=limit,
                engineering_domain=engineering_domain,
                scenario=scenario,
                maturity=maturity,
                source_nature=source_nature,
            )
        if mode == "selected" or (
            content_type is not None and content_type not in {"SAFETY_REGULATION", "SAFETY_CASE"}
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

    async def _get_digital_feed(
        self,
        *,
        mode: str,
        sort: str,
        cursor: str | None,
        limit: int,
        engineering_domain: str | None,
        scenario: str | None,
        maturity: str | None,
        source_nature: str | None,
    ) -> FeedPage:
        cursor_time, cursor_id = _decode_cursor(cursor)
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT i.id, i.item_type, i.title, i.original_url,
                                   i.source_published_at, i.first_discovered_at,
                                   i.activity_at, i.updated_at, i.review_status,
                                   source.name AS source_name,
                                   publication.status AS publication_status,
                                   publication.current_revision_id AS publication_revision_id,
                                   profile.source_nature, profile.maturity_level,
                                   profile.deployment_scale, profile.srbg_relationship,
                                   relevance.score AS relevance_score,
                                   relevance.rule_version AS relevance_rule_version,
                                   relevance.engineering_points,
                                   relevance.sichuan_points,
                                   relevance.srbg_direct_points,
                                   taxonomy.engineering_domains,
                                   taxonomy.lifecycle_stages,
                                   taxonomy.technology_tags,
                                   taxonomy.application_scenarios,
                                   (SELECT count(*) FROM document_version version
                                    WHERE version.document_id = i.primary_document_id)
                                     AS version_count,
                                   NULL::text AS latest_change_type,
                                   NULL::text AS latest_change_review_state,
                                   false AS source_unavailable,
                                   (SELECT count(*) FROM claim_evidence evidence
                                    JOIN claim ON claim.id = evidence.claim_id
                                    WHERE claim.item_id = i.id
                                      AND claim.verification_status = 'ACCEPTED')
                                     AS evidence_count
                            FROM intelligence_item i
                            JOIN source ON source.id = i.source_id
                            JOIN digital_case_profile profile ON profile.item_id = i.id
                            JOIN digital_case_relevance relevance ON relevance.item_id = i.id
                            LEFT JOIN publication ON publication.item_id = i.id
                            JOIN LATERAL (
                              SELECT
                                COALESCE(array_agg(code ORDER BY code)
                                  FILTER (WHERE facet = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])
                                  AS engineering_domains,
                                COALESCE(array_agg(code ORDER BY code)
                                  FILTER (WHERE facet = 'LIFECYCLE_STAGE'), ARRAY[]::text[])
                                  AS lifecycle_stages,
                                COALESCE(array_agg(code ORDER BY code)
                                  FILTER (WHERE facet = 'TECHNOLOGY_TAG'), ARRAY[]::text[])
                                  AS technology_tags,
                                COALESCE(array_agg(code ORDER BY code)
                                  FILTER (WHERE facet = 'APPLICATION_SCENARIO'), ARRAY[]::text[])
                                  AS application_scenarios
                              FROM digital_case_taxonomy
                              WHERE item_id = i.id
                            ) taxonomy ON true
                            WHERE i.item_type = 'DIGITAL_CASE'
                              AND i.channel = 'DIGITAL'
                              AND i.risk_level <> 'R4'
                              AND i.review_status <> 'REJECTED'
                              AND (
                                :mode <> 'selected'
                                OR (
                                  i.review_status = 'APPROVED'
                                  AND publication.status = 'PUBLISHED'
                                )
                              )
                              AND (
                                CAST(:engineering_domain AS text) IS NULL
                                OR :engineering_domain = ANY(taxonomy.engineering_domains)
                              )
                              AND (
                                CAST(:scenario AS text) IS NULL
                                OR :scenario = ANY(taxonomy.application_scenarios)
                              )
                              AND (
                                CAST(:maturity AS text) IS NULL
                                OR profile.maturity_level = CAST(:maturity AS text)
                              )
                              AND (
                                CAST(:source_nature AS text) IS NULL
                                OR profile.source_nature = CAST(:source_nature AS text)
                              )
                              AND (
                                CAST(:cursor_time AS timestamptz) IS NULL
                                OR (i.activity_at, i.id) <
                                   (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid))
                              )
                            ORDER BY
                              CASE WHEN :sort = 'relevance' THEN relevance.score END DESC,
                              i.activity_at DESC, i.id DESC
                            LIMIT :row_limit
                            """
                        ),
                        {
                            "mode": mode,
                            "sort": sort,
                            "engineering_domain": _none_for_all(engineering_domain),
                            "scenario": _none_for_all(scenario),
                            "maturity": _none_for_all(maturity),
                            "source_nature": _none_for_all(source_nature),
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
        if has_more and visible and sort == "latest":
            next_cursor = _encode_cursor(visible[-1]["activity_at"], visible[-1]["id"])
        return _feed_page(
            items,
            now=datetime.now(UTC),
            mode=mode,
            domain="digital",
            next_cursor=next_cursor,
        )

    async def _get_paper_feed(
        self,
        *,
        mode: str,
        cursor: str | None,
        limit: int,
        engineering_domain: str | None,
        technology_tag: str | None,
        maturity: str | None,
        paper_type: str | None,
        access_level: str | None,
        year: int | None,
    ) -> FeedPage:
        cursor_time, cursor_id = _decode_cursor(cursor)
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT i.id, i.item_type, i.title, i.original_url,
                                   i.source_published_at, i.first_discovered_at,
                                   i.activity_at, i.updated_at, i.review_status,
                                   source.name AS source_name,
                                   publication.status AS publication_status,
                                   publication.current_revision_id AS publication_revision_id,
                                   profile.normalized_doi, profile.journal,
                                   profile.publication_year, profile.paper_type,
                                   profile.access_level, profile.open_status,
                                   profile.maturity_level, profile.relation_status,
                                   taxonomy.engineering_domains, taxonomy.technology_tags,
                                   (SELECT count(*) FROM document_version version
                                    WHERE version.document_id = i.primary_document_id)
                                      AS version_count,
                                   NULL::text AS latest_change_type,
                                   NULL::text AS latest_change_review_state,
                                   false AS source_unavailable,
                                   (SELECT count(*) FROM claim_evidence evidence
                                    JOIN claim ON claim.id = evidence.claim_id
                                    WHERE claim.item_id = i.id
                                      AND claim.verification_status = 'ACCEPTED')
                                      AS evidence_count
                            FROM intelligence_item i
                            JOIN source ON source.id = i.source_id
                            JOIN paper_profile profile ON profile.item_id = i.id
                            LEFT JOIN publication ON publication.item_id = i.id
                            JOIN LATERAL (
                              SELECT
                                COALESCE(array_agg(code ORDER BY code)
                                  FILTER (WHERE dimension = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])
                                  AS engineering_domains,
                                COALESCE(array_agg(code ORDER BY code)
                                  FILTER (WHERE dimension = 'TECHNOLOGY_TAG'), ARRAY[]::text[])
                                  AS technology_tags
                              FROM paper_taxonomy WHERE item_id = i.id
                            ) taxonomy ON true
                            WHERE i.item_type = 'JOURNAL_PAPER'
                              AND i.channel = 'DIGITAL'
                              AND i.risk_level <> 'R4'
                              AND i.review_status <> 'REJECTED'
                              AND (:mode <> 'selected' OR (
                                i.review_status = 'APPROVED'
                                AND publication.status = 'PUBLISHED'
                              ))
                              AND (CAST(:engineering_domain AS text) IS NULL
                                OR :engineering_domain = ANY(taxonomy.engineering_domains))
                              AND (CAST(:technology_tag AS text) IS NULL
                                OR :technology_tag = ANY(taxonomy.technology_tags))
                              AND (CAST(:maturity AS text) IS NULL
                                OR profile.maturity_level = CAST(:maturity AS text))
                              AND (CAST(:paper_type AS text) IS NULL
                                OR profile.paper_type = CAST(:paper_type AS text))
                              AND (CAST(:access_level AS text) IS NULL
                                OR profile.access_level = CAST(:access_level AS text))
                              AND (CAST(:year AS smallint) IS NULL
                                OR profile.publication_year = CAST(:year AS smallint))
                              AND (CAST(:cursor_time AS timestamptz) IS NULL
                                OR (i.activity_at, i.id) <
                                  (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid)))
                            ORDER BY i.activity_at DESC, i.id DESC
                            LIMIT :row_limit
                            """
                        ),
                        {
                            "mode": mode,
                            "engineering_domain": _none_for_all(engineering_domain),
                            "technology_tag": _none_for_all(technology_tag),
                            "maturity": _none_for_all(maturity),
                            "paper_type": _none_for_all(paper_type),
                            "access_level": _none_for_all(access_level),
                            "year": year,
                            "cursor_time": cursor_time,
                            "cursor_id": cursor_id,
                            "row_limit": limit + 1,
                        },
                    )
                ).mappings()
            )
        visible = rows[:limit]
        next_cursor = (
            _encode_cursor(visible[-1]["activity_at"], visible[-1]["id"])
            if len(rows) > limit and visible
            else None
        )
        return _feed_page(
            [_item_summary(row) for row in visible],
            now=datetime.now(UTC),
            mode=mode,
            domain="digital",
            next_cursor=next_cursor,
        )

    async def _get_product_feed(
        self,
        *,
        mode: str,
        content_type: str,
        cursor: str | None,
        limit: int,
        product_kind: str | None,
        evidence_level: str | None,
        deployment_mode: str | None,
        scenario: str | None,
        maturity: str | None,
    ) -> FeedPage:
        cursor_time, cursor_id = _decode_cursor(cursor)
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT item.id, item.item_type, item.title, item.original_url,
                                   item.source_published_at, item.first_discovered_at,
                                   item.activity_at, item.updated_at, item.review_status,
                                   source.name AS source_name,
                                   publication.status AS publication_status,
                                   publication.current_revision_id AS publication_revision_id,
                                   vendor.id AS vendor_id, vendor.name AS vendor_name,
                                   product.id AS product_id, product.name AS product_name,
                                   product.product_kind,
                                   model.id AS model_id, model.model_no,
                                   version.version, profile.evidence_level,
                                   profile.permit_status, profile.maturity_level,
                                   profile.platform_type, profile.equipment_form,
                                   profile.interfaces, profile.deployment_modes,
                                   profile.connectivity, profile.payload_types,
                                   profile.ai_tasks, profile.limitations,
                                   profile.production_validation,
                                   taxonomy.application_scenarios,
                                   capabilities.promotional_claim_count,
                                   capabilities.verified_capability_count,
                                   (SELECT count(*) FROM document_version document_version
                                    WHERE document_version.document_id = item.primary_document_id)
                                      AS version_count,
                                   NULL::text AS latest_change_type,
                                   NULL::text AS latest_change_review_state,
                                   false AS source_unavailable,
                                   (SELECT count(*) FROM claim_evidence evidence
                                    JOIN claim ON claim.id = evidence.claim_id
                                    WHERE claim.item_id = item.id
                                      AND claim.verification_status = 'ACCEPTED') AS evidence_count
                            FROM intelligence_item item
                            JOIN source ON source.id = item.source_id
                            JOIN technology_product_profile profile ON profile.item_id = item.id
                            JOIN technology_product_version version
                              ON version.id = profile.version_id
                            JOIN technology_product_model model ON model.id = version.model_id
                            JOIN technology_product product ON product.id = model.product_id
                            JOIN technology_vendor vendor ON vendor.id = product.vendor_id
                            LEFT JOIN publication ON publication.item_id = item.id
                            LEFT JOIN LATERAL (
                              SELECT
                                count(*) FILTER (WHERE kind = 'PROMOTIONAL_CLAIM')
                                  AS promotional_claim_count,
                                count(*) FILTER (WHERE kind = 'VERIFIED_CAPABILITY')
                                  AS verified_capability_count
                              FROM technology_product_capability
                              WHERE item_id = item.id
                            ) capabilities ON true
                            LEFT JOIN LATERAL (
                              SELECT COALESCE(array_agg(code ORDER BY code)
                                FILTER (WHERE dimension = 'APPLICATION_SCENARIO'), ARRAY[]::text[])
                                  AS application_scenarios
                              FROM technology_product_taxonomy WHERE item_id = item.id
                            ) taxonomy ON true
                            WHERE item.item_type = :content_type
                              AND item.channel = 'DIGITAL'
                              AND item.risk_level = 'R2'
                              AND item.review_status <> 'REJECTED'
                              AND (:mode <> 'selected' OR (
                                item.review_status = 'APPROVED'
                                AND publication.status = 'PUBLISHED'
                              ))
                              AND (CAST(:product_kind AS text) IS NULL
                                OR product.product_kind = CAST(:product_kind AS text))
                              AND (CAST(:evidence_level AS text) IS NULL
                                OR profile.evidence_level = CAST(:evidence_level AS text))
                              AND (CAST(:deployment_mode AS text) IS NULL
                                OR :deployment_mode = ANY(profile.deployment_modes))
                              AND (CAST(:scenario AS text) IS NULL
                                OR :scenario = ANY(taxonomy.application_scenarios))
                              AND (CAST(:maturity AS text) IS NULL
                                OR profile.maturity_level = CAST(:maturity AS text))
                              AND (CAST(:cursor_time AS timestamptz) IS NULL
                                OR (item.activity_at, item.id) <
                                   (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid)))
                            ORDER BY item.activity_at DESC, item.id DESC
                            LIMIT :row_limit
                            """
                        ),
                        {
                            "content_type": content_type,
                            "mode": mode,
                            "product_kind": _none_for_all(product_kind),
                            "evidence_level": _none_for_all(evidence_level),
                            "deployment_mode": _none_for_all(deployment_mode),
                            "scenario": _none_for_all(scenario),
                            "maturity": _none_for_all(maturity),
                            "cursor_time": cursor_time,
                            "cursor_id": cursor_id,
                            "row_limit": limit + 1,
                        },
                    )
                ).mappings()
            )
        visible = rows[:limit]
        next_cursor = (
            _encode_cursor(visible[-1]["activity_at"], visible[-1]["id"])
            if len(rows) > limit and visible
            else None
        )
        return _feed_page(
            [_item_summary(row) for row in visible],
            now=datetime.now(UTC),
            mode=mode,
            domain="digital",
            next_cursor=next_cursor,
        )

    async def get_item(self, item_id: UUID) -> ItemDetail:
        async with self._engine.connect() as connection:
            row = await _item_row(connection, item_id, include_unpublished=False)
            if row is None:
                raise IntelligenceNotFound("intelligence item does not exist")
            item = _item_summary(row)
            product_types = {
                "SOFTWARE_PRODUCT",
                "IOT_PRODUCT",
                "LOW_ALTITUDE_EQUIPMENT",
                "AI_EQUIPMENT",
            }
            if (
                row["item_type"] not in product_types
                and (row["publication_status"] != "PUBLISHED" or row["review_status"] != "APPROVED")
            ):
                return ItemDetail(item=item, notice=_restricted_notice())
            claims, evidence = await _claims_and_evidence(connection, item_id)
            if row["item_type"] == "DIGITAL_CASE":
                digital_case = await _digital_case_detail(connection, row)
                return ItemDetail(
                    item=item,
                    claims=claims,
                    evidence=evidence,
                    digital_case=digital_case,
                )
            if row["item_type"] == "JOURNAL_PAPER":
                return ItemDetail(
                    item=item,
                    claims=claims,
                    evidence=evidence,
                    paper=await _paper_detail(connection, row),
                )
            if row["item_type"] in product_types:
                return ItemDetail(
                    item=item,
                    claims=claims,
                    evidence=evidence,
                    technology_product=await _technology_product_detail(connection, row),
                )
            return ItemDetail(item=item, claims=claims, evidence=evidence)

    async def list_product_normalization_candidates(
        self, *, status: str
    ) -> list[ProductNormalizationCandidateView]:
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT candidate.id, candidate.incoming_version_id,
                                   candidate.candidate_version_id,
                                   candidate.candidate_type, candidate.status,
                                   candidate.created_at,
                                   concat(incoming_vendor.name, ' / ', incoming_product.name,
                                          ' / ', COALESCE(incoming_model.model_no, '型号未知'),
                                          ' / ', COALESCE(incoming_version.version, '版本未知'))
                                     AS incoming_label,
                                   concat(existing_vendor.name, ' / ', existing_product.name,
                                          ' / ', COALESCE(existing_model.model_no, '型号未知'),
                                          ' / ', COALESCE(existing_version.version, '版本未知'))
                                     AS candidate_label
                            FROM product_normalization_candidate candidate
                            JOIN technology_product_version incoming_version
                              ON incoming_version.id = candidate.incoming_version_id
                            JOIN technology_product_model incoming_model
                              ON incoming_model.id = incoming_version.model_id
                            JOIN technology_product incoming_product
                              ON incoming_product.id = incoming_model.product_id
                            JOIN technology_vendor incoming_vendor
                              ON incoming_vendor.id = incoming_product.vendor_id
                            JOIN technology_product_version existing_version
                              ON existing_version.id = candidate.candidate_version_id
                            JOIN technology_product_model existing_model
                              ON existing_model.id = existing_version.model_id
                            JOIN technology_product existing_product
                              ON existing_product.id = existing_model.product_id
                            JOIN technology_vendor existing_vendor
                              ON existing_vendor.id = existing_product.vendor_id
                            WHERE candidate.status = :status
                            ORDER BY candidate.created_at, candidate.id
                            """
                        ),
                        {"status": status},
                    )
                ).mappings()
            )
        return [ProductNormalizationCandidateView.model_validate(row) for row in rows]

    async def get_citation(self, item_id: UUID, citation_format: str) -> tuple[str, str]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT item.title, profile.normalized_doi AS doi,
                                   profile.journal, profile.publication_year AS year,
                                   profile.volume, profile.issue, profile.pages,
                                   COALESCE(
                                     array_agg(author.name ORDER BY authorship.author_order)
                                       FILTER (WHERE author.id IS NOT NULL),
                                     ARRAY[]::text[]
                                   ) AS authors
                            FROM intelligence_item item
                            JOIN paper_profile profile ON profile.item_id = item.id
                            JOIN publication ON publication.item_id = item.id
                              AND publication.status = 'PUBLISHED'
                            LEFT JOIN paper_authorship authorship ON authorship.item_id = item.id
                            LEFT JOIN paper_author author ON author.id = authorship.author_id
                            WHERE item.id = :item_id
                              AND item.item_type = 'JOURNAL_PAPER'
                              AND item.review_status = 'APPROVED'
                            GROUP BY item.id, item.title, profile.normalized_doi,
                                     profile.journal, profile.publication_year,
                                     profile.volume, profile.issue, profile.pages
                            """
                        ),
                        {"item_id": item_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise IntelligenceNotFound("published journal paper does not exist")
        metadata = dict(row)
        formatter = {
            "ris": format_ris,
            "bibtex": format_bibtex,
            "gb-t-7714": format_gbt7714,
        }.get(citation_format)
        if formatter is None:
            raise ValueError("unsupported citation format")
        media_type = {
            "ris": "application/x-research-info-systems; charset=utf-8",
            "bibtex": "application/x-bibtex; charset=utf-8",
            "gb-t-7714": "text/plain; charset=utf-8",
        }[citation_format]
        return formatter(metadata), media_type

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
                digital_case=(
                    await _digital_case_detail(connection, item_row)
                    if item_row["item_type"] == "DIGITAL_CASE"
                    else None
                ),
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
                   digital_profile.source_nature,
                   digital_profile.maturity_level,
                   digital_profile.deployment_scale,
                   digital_profile.applicability,
                   digital_profile.replication_conditions,
                   digital_profile.limitations,
                   digital_profile.risks,
                   digital_profile.srbg_relationship,
                   digital_relevance.score AS relevance_score,
                   digital_relevance.rule_version AS relevance_rule_version,
                   digital_relevance.engineering_points,
                   digital_relevance.sichuan_points,
                   digital_relevance.srbg_direct_points,
                   digital_taxonomy.engineering_domains,
                   digital_taxonomy.lifecycle_stages,
                   digital_taxonomy.technology_tags,
                   digital_taxonomy.application_scenarios,
                   paper_profile.normalized_doi,
                   paper_profile.journal,
                   paper_profile.issns,
                   paper_profile.volume,
                   paper_profile.issue,
                   paper_profile.pages,
                   paper_profile.publication_year,
                   paper_profile.paper_type,
                   paper_profile.access_level,
                   paper_profile.open_status,
                   paper_profile.open_fulltext_url,
                   paper_profile.abstract,
                   paper_profile.abstract_availability,
                   paper_profile.keywords,
                   paper_profile.maturity_level AS paper_maturity_level,
                   paper_profile.research_interpretation,
                   paper_profile.relation_status,
                   paper_taxonomy.engineering_domains AS paper_engineering_domains,
                   paper_taxonomy.technology_tags AS paper_technology_tags,
                   product_profile.item_type AS product_item_type,
                   product_profile.evidence_level,
                   product_profile.permit_status,
                   product_profile.maturity_level AS product_maturity_level,
                   product_profile.platform_type,
                   product_profile.equipment_form,
                   product_profile.interfaces,
                   product_profile.deployment_modes,
                   product_profile.connectivity,
                   product_profile.payload_types,
                   product_profile.ai_tasks,
                   product_profile.limitations AS product_limitations,
                   product_profile.production_validation,
                   product_vendor.id AS vendor_id,
                   product_vendor.name AS vendor_name,
                   product.id AS product_id,
                   product.name AS product_name,
                   product.product_kind,
                   product_model.id AS model_id,
                   product_model.model_no,
                   product_version.version,
                   product_taxonomy.application_scenarios AS product_application_scenarios,
                   product_capabilities.promotional_claim_count,
                   product_capabilities.verified_capability_count,
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
            LEFT JOIN digital_case_profile digital_profile ON digital_profile.item_id = i.id
            LEFT JOIN digital_case_relevance digital_relevance
              ON digital_relevance.item_id = i.id
            LEFT JOIN paper_profile ON paper_profile.item_id = i.id
            LEFT JOIN technology_product_profile product_profile ON product_profile.item_id = i.id
            LEFT JOIN technology_product_version product_version
              ON product_version.id = product_profile.version_id
            LEFT JOIN technology_product_model product_model
              ON product_model.id = product_version.model_id
            LEFT JOIN technology_product product ON product.id = product_model.product_id
            LEFT JOIN technology_vendor product_vendor ON product_vendor.id = product.vendor_id
            LEFT JOIN LATERAL (
              SELECT
                COALESCE(array_agg(code ORDER BY code)
                  FILTER (WHERE facet = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])
                  AS engineering_domains,
                COALESCE(array_agg(code ORDER BY code)
                  FILTER (WHERE facet = 'LIFECYCLE_STAGE'), ARRAY[]::text[])
                  AS lifecycle_stages,
                COALESCE(array_agg(code ORDER BY code)
                  FILTER (WHERE facet = 'TECHNOLOGY_TAG'), ARRAY[]::text[])
                  AS technology_tags,
                COALESCE(array_agg(code ORDER BY code)
                  FILTER (WHERE facet = 'APPLICATION_SCENARIO'), ARRAY[]::text[])
                  AS application_scenarios
              FROM digital_case_taxonomy
              WHERE item_id = i.id
            ) digital_taxonomy ON true
            LEFT JOIN LATERAL (
              SELECT
                COALESCE(array_agg(code ORDER BY code)
                  FILTER (WHERE dimension = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])
                  AS engineering_domains,
                COALESCE(array_agg(code ORDER BY code)
                  FILTER (WHERE dimension = 'TECHNOLOGY_TAG'), ARRAY[]::text[])
                  AS technology_tags
              FROM paper_taxonomy WHERE item_id = i.id
            ) paper_taxonomy ON true
            LEFT JOIN LATERAL (
              SELECT COALESCE(array_agg(code ORDER BY code)
                FILTER (WHERE dimension = 'APPLICATION_SCENARIO'), ARRAY[]::text[])
                  AS application_scenarios
              FROM technology_product_taxonomy WHERE item_id = i.id
            ) product_taxonomy ON true
            LEFT JOIN LATERAL (
              SELECT count(*) FILTER (WHERE kind = 'PROMOTIONAL_CLAIM')
                       AS promotional_claim_count,
                     count(*) FILTER (WHERE kind = 'VERIFIED_CAPABILITY')
                       AS verified_capability_count
              FROM technology_product_capability WHERE item_id = i.id
            ) product_capabilities ON true
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
                OR
                (i.item_type = 'DIGITAL_CASE' AND digital_profile.item_id IS NOT NULL
                  AND digital_relevance.item_id IS NOT NULL)
                OR
                (i.item_type = 'JOURNAL_PAPER' AND paper_profile.item_id IS NOT NULL)
                OR
                (i.item_type IN ('SOFTWARE_PRODUCT','IOT_PRODUCT',
                                 'LOW_ALTITUDE_EQUIPMENT','AI_EQUIPMENT')
                 AND product_profile.item_id IS NOT NULL)
              )
              AND (:include_unpublished OR i.review_status = 'PENDING'
                   OR p.status IN ('PUBLISHED', 'WITHDRAWN'))
            """
        ),
        {"item_id": item_id, "include_unpublished": include_unpublished},
    )
    return result.mappings().first()


async def _technology_product_detail(
    connection: AsyncConnection, row: RowMapping
) -> TechnologyProductDetail:
    capabilities = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT capability.kind, capability.statement, capability.attribution,
                           capability.claim_id, capability.evidence_ids,
                           capability.independent_evidence_ids
                    FROM technology_product_capability capability
                    JOIN claim ON claim.id = capability.claim_id
                    WHERE capability.item_id = :item_id
                      AND claim.verification_status = 'ACCEPTED'
                    ORDER BY capability.kind, capability.created_at, capability.id
                    """
                ),
                {"item_id": row["id"]},
            )
        ).mappings()
    )
    version_history = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT version.version
                    FROM technology_product_version version
                    WHERE version.model_id = :model_id
                    ORDER BY version.released_at DESC NULLS LAST,
                             version.created_at DESC, version.id DESC
                    """
                ),
                {"model_id": row["model_id"]},
            )
        ).scalars()
    )
    engineering_cases = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT target.id AS item_id, target.title,
                           candidate.evidence_ids
                    FROM item_relation relation
                    JOIN item_relation_candidate candidate ON candidate.id = relation.candidate_id
                    JOIN intelligence_item target ON target.id = relation.target_item_id
                    JOIN publication ON publication.item_id = target.id
                      AND publication.status = 'PUBLISHED'
                    WHERE relation.source_item_id = :item_id
                      AND relation.relation_type = 'APPLIED_IN'
                      AND target.item_type = 'DIGITAL_CASE'
                      AND target.review_status = 'APPROVED'
                    ORDER BY target.activity_at DESC, target.id DESC
                    """
                ),
                {"item_id": row["id"]},
            )
        ).mappings()
    )

    def capability_view(value: RowMapping) -> ProductCapability:
        return ProductCapability(
            claim_id=value["claim_id"],
            statement=value["statement"],
            attribution=value["attribution"],
            kind=ProductCapabilityKind(str(value["kind"])),
            evidence_ids=list(value["evidence_ids"]),
            independent_evidence_ids=list(value["independent_evidence_ids"]),
        )

    promotional = [
        capability_view(value) for value in capabilities if value["kind"] == "PROMOTIONAL_CLAIM"
    ]
    verified = [
        capability_view(value) for value in capabilities if value["kind"] == "VERIFIED_CAPABILITY"
    ]
    item_type = ItemType(str(row["item_type"]))
    is_low_altitude = item_type is ItemType.LOW_ALTITUDE_EQUIPMENT
    return TechnologyProductDetail(
        vendor=ProductEntity(id=row["vendor_id"], name=row["vendor_name"]),
        product=ProductEntity(id=row["product_id"], name=row["product_name"]),
        model=(
            ProductEntity(id=row["model_id"], name=row["model_no"] or "型号未知")
            if row.get("model_id")
            else None
        ),
        current_version=row.get("version"),
        version_history=[str(version) for version in version_history if version],
        product_kind=str(row["product_kind"]),
        promotional_claims=promotional,
        verified_capabilities=verified,
        interfaces=list(row.get("interfaces") or []),
        deployment_modes=list(row.get("deployment_modes") or []),
        application_scenarios=list(row.get("product_application_scenarios") or []),
        engineering_cases=[
            ProductEngineeringCase(
                item_id=value["item_id"],
                title=value["title"],
                evidence_ids=list(value["evidence_ids"]),
            )
            for value in engineering_cases
        ],
        evidence_level=ProductEvidenceLevel(str(row.get("evidence_level", "UNKNOWN"))),
        permit_status=ProductPermitStatus(str(row.get("permit_status", "UNKNOWN"))),
        limitations=list(row.get("product_limitations") or []),
        procurement_notice="仅供技术调研，不构成采购建议",
        low_altitude_notice=(
            "产品发布不代表空域、适航、飞手和项目许可。" if is_low_altitude else None
        ),
    )


def _item_summary(row: RowMapping, *, reviewer_projection: bool = False) -> ItemSummary:
    states = _document_states(row)
    item_type = ItemType(str(row.get("item_type", ItemType.SAFETY_REGULATION.value)))
    published = row["publication_status"] == "PUBLISHED" and row["review_status"] == "APPROVED"
    withdrawn = row["publication_status"] == "WITHDRAWN"
    product_types = {
        ItemType.SOFTWARE_PRODUCT,
        ItemType.IOT_PRODUCT,
        ItemType.LOW_ALTITUDE_EQUIPMENT,
        ItemType.AI_EQUIPMENT,
    }
    if (
        (not published or withdrawn)
        and item_type not in {ItemType.DIGITAL_CASE, ItemType.JOURNAL_PAPER, *product_types}
        and not reviewer_projection
    ):
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
    if item_type is ItemType.DIGITAL_CASE:
        type_summary: (
            DigitalCaseTypeSummary
            | PaperTypeSummary
            | SafetyCaseTypeSummary
            | SafetyRegulationTypeSummary
            | SoftwareProductTypeSummary
            | IotProductTypeSummary
            | LowAltitudeEquipmentTypeSummary
            | AiEquipmentTypeSummary
        )
        type_summary = DigitalCaseTypeSummary(
            kind="DIGITAL_CASE",
            maturity_level=MaturityLevel(str(row["maturity_level"])),
            application_scenarios=list(row.get("application_scenarios") or []),
            source_nature=DigitalCaseSourceNature(str(row["source_nature"])),
            deployment_scale=row.get("deployment_scale"),
            publisher_claim_label=(
                "厂商声明，未经独立验证"
                if row["source_nature"] == "ENTERPRISE_SELF_REPORT"
                else "政府/行业案例汇编"
            ),
            srbg_relationship=str(row["srbg_relationship"]),
            relevance=RelevanceSummary(
                score=int(row["relevance_score"]),
                rule_version="relevance-v1.0.0",
                factors=[
                    RelevanceFactor(
                        code="ENGINEERING_DOMAIN",
                        label="工程专业匹配",
                        points=int(row["engineering_points"]),
                    ),
                    RelevanceFactor(
                        code="SICHUAN",
                        label="四川实施",
                        points=int(row["sichuan_points"]),
                    ),
                    RelevanceFactor(
                        code="SRBG_DIRECT",
                        label="四川路桥直接关系",
                        points=int(row["srbg_direct_points"]),
                    ),
                ],
            ),
        )
        tags = [
            "数字化案例",
            *list(row.get("engineering_domains") or [])[:2],
            *list(row.get("technology_tags") or [])[:2],
        ]
    elif item_type is ItemType.JOURNAL_PAPER:
        maturity_value = row.get("paper_maturity_level", row.get("maturity_level", "UNKNOWN"))
        type_summary = PaperTypeSummary(
            kind="JOURNAL_PAPER",
            doi=row.get("normalized_doi"),
            journal=row.get("journal"),
            year=row.get("publication_year"),
            paper_type=PaperType(str(row.get("paper_type", "UNKNOWN"))),
            access_level=PaperAccessLevel(str(row.get("access_level", "METADATA_ONLY"))),
            open_status=PaperOpenStatus(str(row.get("open_status", "UNKNOWN"))),
            maturity_level=MaturityLevel(str(maturity_value)),
            engineering_domains=list(
                row.get("paper_engineering_domains", row.get("engineering_domains", [])) or []
            ),
            technology_tags=list(
                row.get("paper_technology_tags", row.get("technology_tags", [])) or []
            ),
            relation_status=PaperRelationStatus(str(row.get("relation_status", "CURRENT"))),
        )
        tags = [
            "期刊论文",
            *type_summary.engineering_domains[:2],
            *type_summary.technology_tags[:2],
        ]
    elif item_type in product_types:
        common: dict[str, Any] = {
            "vendor_name": str(row["vendor_name"]),
            "product_name": str(row["product_name"]),
            "product_kind": str(row["product_kind"]),
            "model_no": row.get("model_no"),
            "version": row.get("version"),
            "evidence_level": ProductEvidenceLevel(str(row.get("evidence_level", "UNKNOWN"))),
            "promotional_claim_count": int(row.get("promotional_claim_count") or 0),
            "verified_capability_count": int(row.get("verified_capability_count") or 0),
        }
        if item_type is ItemType.SOFTWARE_PRODUCT:
            type_summary = SoftwareProductTypeSummary(
                kind="SOFTWARE_PRODUCT",
                interfaces=list(row.get("interfaces") or []),
                deployment_modes=list(row.get("deployment_modes") or []),
                **common,
            )
        elif item_type is ItemType.IOT_PRODUCT:
            type_summary = IotProductTypeSummary(
                kind="IOT_PRODUCT",
                connectivity=list(row.get("connectivity") or []),
                maturity_level=MaturityLevel(
                    str(row.get("product_maturity_level", row.get("maturity_level", "UNKNOWN")))
                ),
                **common,
            )
        elif item_type is ItemType.LOW_ALTITUDE_EQUIPMENT:
            type_summary = LowAltitudeEquipmentTypeSummary(
                kind="LOW_ALTITUDE_EQUIPMENT",
                platform_type=row.get("platform_type"),
                payload_types=list(row.get("payload_types") or []),
                permit_status=ProductPermitStatus(str(row.get("permit_status", "UNKNOWN"))),
                **common,
            )
        else:
            type_summary = AiEquipmentTypeSummary(
                kind="AI_EQUIPMENT",
                equipment_form=row.get("equipment_form"),
                ai_tasks=list(row.get("ai_tasks") or []),
                maturity_level=MaturityLevel(
                    str(row.get("product_maturity_level", row.get("maturity_level", "UNKNOWN")))
                ),
                production_validation=bool(row.get("production_validation")),
                **common,
            )
        tags = [
            {
                ItemType.SOFTWARE_PRODUCT: "软件与平台",
                ItemType.IOT_PRODUCT: "物联网产品",
                ItemType.LOW_ALTITUDE_EQUIPMENT: "低空装备",
                ItemType.AI_EQUIPMENT: "AI设备与机器人",
            }[item_type],
            *list(
                row.get("product_application_scenarios", row.get("application_scenarios", []))
                or []
            )[:2],
        ]
    elif item_type is ItemType.SAFETY_CASE:
        hidden_fields = {str(field) for field in row.get("conflicted_fields", []) or []}
        conflicted_fields = [
            _critical_safety_field(str(field)) for field in row.get("conflicted_fields", []) or []
        ]
        type_summary = SafetyCaseTypeSummary(
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
        domain=(
            Channel.DIGITAL
            if item_type in {ItemType.DIGITAL_CASE, ItemType.JOURNAL_PAPER, *product_types}
            else Channel.SAFETY
        ),
        content_type=item_type,
        title=row["title"],
        source_name=row["source_name"],
        source_published_at=row["source_published_at"],
        first_discovered_at=row["first_discovered_at"],
        activity_at=row["activity_at"],
        original_url=row["original_url"],
        review_status=ReviewStatus(row["review_status"]),
        source_role=(
            "企业自述"
            if item_type is ItemType.DIGITAL_CASE
            and row.get("source_nature") == "ENTERPRISE_SELF_REPORT"
            else "政府/行业案例源"
            if item_type is ItemType.DIGITAL_CASE
            else "开放学术元数据"
            if item_type is ItemType.JOURNAL_PAPER
            else "厂商一手来源"
            if item_type in product_types
            else "官方一手来源"
        ),
        last_updated_at=row["updated_at"],
        publication_status=(
            PublicationStatus.WITHDRAWN
            if withdrawn
            else PublicationStatus.PUBLISHED
            if published
            else PublicationStatus.PENDING_REVIEW
        ),
        evidence_status=(EvidenceStatus.VERIFIED if published else EvidenceStatus.WITHHELD),
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


async def _digital_case_detail(
    connection: AsyncConnection,
    row: RowMapping,
) -> DigitalCaseDetail:
    entity_rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT entity.id, entity.entity_type, entity.name,
                           relation.relation_type, relation.claim_id
                    FROM digital_case_entity_relation relation
                    JOIN digital_case_entity entity ON entity.id = relation.entity_id
                    WHERE relation.item_id = :item_id
                    ORDER BY entity.entity_type, entity.name, entity.id
                    """
                ),
                {"item_id": row["id"]},
            )
        ).mappings()
    )
    outcome_rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT outcome.id, outcome.statement, outcome.metric_name,
                           outcome.numeric_value, outcome.unit, outcome.outcome_kind,
                           outcome.evidence_ids, outcome.independent_evidence_ids,
                           entity.name AS attribution
                    FROM digital_case_outcome outcome
                    JOIN digital_case_entity entity
                      ON entity.id = outcome.attribution_entity_id
                    WHERE outcome.item_id = :item_id
                    ORDER BY outcome.created_at, outcome.id
                    """
                ),
                {"item_id": row["id"]},
            )
        ).mappings()
    )
    outcomes = [
        DigitalCaseOutcome(
            id=outcome["id"],
            statement=outcome["statement"],
            attribution=outcome["attribution"],
            verification=OutcomeVerification(str(outcome["outcome_kind"])),
            evidence_ids=list(outcome["evidence_ids"]),
            independent_evidence_ids=list(outcome["independent_evidence_ids"]),
            metric_name=outcome["metric_name"],
            numeric_value=(
                format(outcome["numeric_value"], "f")
                if outcome["numeric_value"] is not None
                else None
            ),
            unit=outcome["unit"],
        )
        for outcome in outcome_rows
    ]
    return DigitalCaseDetail(
        engineering_domains=list(row.get("engineering_domains") or []),
        lifecycle_stages=list(row.get("lifecycle_stages") or []),
        technology_tags=list(row.get("technology_tags") or []),
        application_scenarios=list(row.get("application_scenarios") or []),
        maturity_level=MaturityLevel(str(row["maturity_level"])),
        deployment_scale=row.get("deployment_scale"),
        entities=[
            DigitalCaseEntity(
                id=entity["id"],
                entity_type=entity["entity_type"],
                name=entity["name"],
                relation_type=entity["relation_type"],
                claim_id=entity["claim_id"],
            )
            for entity in entity_rows
        ],
        claimed_outcomes=[
            outcome for outcome in outcomes if outcome.verification is OutcomeVerification.CLAIMED
        ],
        verified_outcomes=[
            outcome for outcome in outcomes if outcome.verification is OutcomeVerification.VERIFIED
        ],
        applicability=list(row.get("applicability") or []),
        replication_conditions=list(row.get("replication_conditions") or []),
        limitations=list(row.get("limitations") or []),
        risks=list(row.get("risks") or []),
        recommended_actions=[
            RecommendedAction.READ_ORIGINAL,
            RecommendedAction.SAVE,
            RecommendedAction.FOLLOW,
            RecommendedAction.TECHNICAL_RESEARCH,
        ],
    )


async def _paper_detail(connection: AsyncConnection, row: RowMapping) -> PaperDetail:
    author_rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT author.name, author.orcid,
                           COALESCE(array_agg(DISTINCT institution.name ORDER BY institution.name)
                             FILTER (WHERE institution.id IS NOT NULL), ARRAY[]::text[])
                             AS institutions
                    FROM paper_authorship authorship
                    JOIN paper_author author ON author.id = authorship.author_id
                    LEFT JOIN paper_author_affiliation affiliation
                      ON affiliation.item_id = authorship.item_id
                     AND affiliation.author_id = authorship.author_id
                    LEFT JOIN paper_institution institution
                      ON institution.id = affiliation.institution_id
                    WHERE authorship.item_id = :item_id
                    GROUP BY author.id, author.name, author.orcid, authorship.author_order
                    ORDER BY authorship.author_order
                    """
                ),
                {"item_id": row["id"]},
            )
        ).mappings()
    )
    similar_rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT item.id, item.title, profile.journal, profile.publication_year,
                           taxonomy.engineering_domains, taxonomy.technology_tags
                    FROM intelligence_item item
                    JOIN paper_profile profile ON profile.item_id = item.id
                    JOIN publication ON publication.item_id = item.id
                      AND publication.status = 'PUBLISHED'
                    JOIN LATERAL (
                      SELECT
                        COALESCE(array_agg(code ORDER BY code)
                          FILTER (WHERE dimension = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])
                          AS engineering_domains,
                        COALESCE(array_agg(code ORDER BY code)
                          FILTER (WHERE dimension = 'TECHNOLOGY_TAG'), ARRAY[]::text[])
                          AS technology_tags
                      FROM paper_taxonomy WHERE item_id = item.id
                    ) taxonomy ON true
                    WHERE item.id <> :item_id
                      AND item.item_type = 'JOURNAL_PAPER'
                      AND item.risk_level <> 'R4'
                      AND item.review_status = 'APPROVED'
                      AND (
                        taxonomy.engineering_domains && CAST(:engineering_domains AS text[])
                        OR taxonomy.technology_tags && CAST(:technology_tags AS text[])
                      )
                    ORDER BY
                      cardinality(ARRAY(
                        SELECT unnest(taxonomy.engineering_domains)
                        INTERSECT SELECT unnest(CAST(:engineering_domains AS text[]))
                      )) DESC,
                      cardinality(ARRAY(
                        SELECT unnest(taxonomy.technology_tags)
                        INTERSECT SELECT unnest(CAST(:technology_tags AS text[]))
                      )) DESC,
                      item.activity_at DESC, item.id
                    LIMIT 5
                    """
                ),
                {
                    "item_id": row["id"],
                    "engineering_domains": list(row.get("paper_engineering_domains") or []),
                    "technology_tags": list(row.get("paper_technology_tags") or []),
                },
            )
        ).mappings()
    )
    current_domains = set(row.get("paper_engineering_domains") or [])
    current_tags = set(row.get("paper_technology_tags") or [])
    similar = []
    for candidate in similar_rows:
        shared_domains = sorted(
            current_domains.intersection(candidate["engineering_domains"] or [])
        )
        shared_tags = sorted(current_tags.intersection(candidate["technology_tags"] or []))
        similar.append(
            SimilarPaper(
                item_id=candidate["id"],
                title=candidate["title"],
                journal=candidate["journal"],
                year=candidate["publication_year"],
                match_reasons=[f"工程专业：{code}" for code in shared_domains]
                + [f"技术标签：{code}" for code in shared_tags],
            )
        )
    interpretation = row.get("research_interpretation")
    return PaperDetail(
        doi=row.get("normalized_doi"),
        journal=row.get("journal"),
        issns=list(row.get("issns") or []),
        authors=[
            PaperAuthor(
                name=author["name"],
                orcid=author["orcid"],
                institutions=list(author["institutions"] or []),
            )
            for author in author_rows
        ],
        volume=row.get("volume"),
        issue=row.get("issue"),
        pages=row.get("pages"),
        year=row.get("publication_year"),
        abstract=row.get("abstract"),
        abstract_availability=AbstractAvailability(str(row["abstract_availability"])),
        keywords=list(row.get("keywords") or []),
        access_level=PaperAccessLevel(str(row["access_level"])),
        open_status=PaperOpenStatus(str(row["open_status"])),
        open_fulltext_url=row.get("open_fulltext_url"),
        maturity_level=MaturityLevel(str(row["paper_maturity_level"])),
        engineering_domains=list(row.get("paper_engineering_domains") or []),
        technology_tags=list(row.get("paper_technology_tags") or []),
        research_interpretation=(
            ResearchInterpretation.model_validate(interpretation) if interpretation else None
        ),
        similar_papers=similar,
        relation_status=PaperRelationStatus(str(row["relation_status"])),
    )


def _none_for_all(value: str | None) -> str | None:
    return None if value in {None, "", "all"} else value


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


def _render_digital_case_metrics(
    *,
    profiles: list[Mapping[str, Any]],
    outcomes: Mapping[str, int],
    pending_enterprise_review: int,
) -> str:
    rendered = "# TYPE srbg_digital_case_items gauge\n"
    for profile in profiles:
        rendered += (
            "srbg_digital_case_items{"
            f'source_nature="{profile["source_nature"]}",'
            f'maturity_level="{profile["maturity_level"]}"'
            f"}} {profile['count']}\n"
        )
    rendered += "# TYPE srbg_digital_case_outcomes gauge\n"
    for verification in ("CLAIMED", "VERIFIED"):
        rendered += (
            "srbg_digital_case_outcomes{"
            f'verification="{verification}"'
            f"}} {int(outcomes.get(verification, 0))}\n"
        )
    rendered += (
        "# TYPE srbg_digital_enterprise_review_pending gauge\n"
        f"srbg_digital_enterprise_review_pending {pending_enterprise_review}\n"
    )
    return rendered


def _render_paper_metrics(
    *,
    profiles: list[dict[str, object]],
    pending_duplicates: int,
    pending_updates: int,
) -> str:
    rendered = "# TYPE srbg_papers_total gauge\n"
    for profile in profiles:
        rendered += (
            "srbg_papers_total{"
            f'access_level="{profile["access_level"]}",'
            f'relation_status="{profile["relation_status"]}"'
            f'}} {profile["count"]}\n'
        )
    rendered += (
        "# TYPE srbg_paper_duplicate_candidates gauge\n"
        f"srbg_paper_duplicate_candidates {pending_duplicates}\n"
        "# TYPE srbg_paper_update_candidates gauge\n"
        f"srbg_paper_update_candidates {pending_updates}\n"
    )
    return rendered


def _render_technology_product_metrics(
    *,
    profiles: list[Mapping[str, Any]],
    capabilities: Mapping[str, int],
    pending_normalization: int,
) -> str:
    rendered = "# TYPE srbg_technology_products gauge\n"
    for profile in profiles:
        rendered += (
            "srbg_technology_products{"
            f'item_type="{profile["item_type"]}",'
            f'evidence_level="{profile["evidence_level"]}",'
            f'permit_status="{profile["permit_status"]}"'
            f"}} {profile['count']}\n"
        )
    rendered += "# TYPE srbg_product_capabilities gauge\n"
    for kind in ("PROMOTIONAL_CLAIM", "VERIFIED_CAPABILITY"):
        rendered += (
            "srbg_product_capabilities{"
            f'kind="{kind}"'
            f"}} {int(capabilities.get(kind, 0))}\n"
        )
    rendered += (
        "# TYPE srbg_product_normalization_pending gauge\n"
        f"srbg_product_normalization_pending {pending_normalization}\n"
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
