# ruff: noqa: E501, RUF001
"""Server-side personal projections for feeds, details, and evidence."""

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    AbstractAvailability,
    AiAssistance,
    AiEquipmentTypeSummary,
    AiJudgmentEvidencePreview,
    AiJudgmentPreview,
    AutomaticRelationshipView,
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
    EventStatus,
    EventSummary,
    EventTimeline,
    EventType,
    EvidenceStatus,
    EvidenceView,
    FeedNotice,
    FeedPage,
    HotTopicPage,
    HotTopicSummary,
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
    ProductPermitStatus,
    PublicationRevisionState,
    PublicationStatus,
    PublishedClaimV1,
    PublishedEvidenceReferenceV1,
    RecommendedAction,
    RelevanceFactor,
    RelevanceSummary,
    ResearchInterpretation,
    ReviewStatus,
    SafetyCaseFactField,
    SafetyCaseTypeSummary,
    SafetyRegulationTypeSummary,
    ScoreDimension,
    ScoreDimensionSummary,
    ScoreFeature,
    ScoreSummary,
    SimilarPaper,
    SoftwareProductTypeSummary,
    SourceComparison,
    SourceComparisonEntry,
    TechnologyProductDetail,
    UnverifiedFact,
    VersionDiffResponse,
    VersionTimelineEntry,
    VersionTimelineResponse,
)

from srbg_api.config import get_settings
from srbg_api.discovery.domain import CursorBindingError, CursorCodec
from srbg_api.papers.domain import format_bibtex, format_gbt7714, format_ris


class IntelligenceNotFound(LookupError):
    pass


class InvalidFeedCursor(ValueError):
    pass


def _feature_explanations(value: object) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}：{item}" for key, item in sorted(value.items())][:30]
    if isinstance(value, list):
        return [str(item) for item in value[:30]]
    return []


class PreviewObjectReader(Protocol):
    async def get_bytes(self, key: str) -> bytes: ...


_SCORE_QUERY_SUFFIX = "\nJOIN score_dimension dimension ON dimension.score_set_id = score_set.id\nLEFT JOIN LATERAL (\n  SELECT candidate.score, candidate.reason\n  FROM score_override candidate\n  WHERE candidate.score_dimension_id = dimension.id\n  ORDER BY candidate.reviewed_at DESC, candidate.id DESC\n  LIMIT 1\n) override ON true\nWHERE {identity_expression} = ANY(CAST(:item_ids AS uuid[]))\n  AND score_set.is_current\nORDER BY score_set.calculated_at DESC, score_set.id DESC\n"
_SCORE_SELECT = "\nSELECT {identity_expression} AS identity_id,\n       score_set.rule_version, score_set.calculated_at, dimension.dimension,\n       dimension.raw_score, dimension.features,\n       override.score AS override_score, override.reason AS override_reason\nFROM score_set\n{alias_join}\n"
_EVENT_SCORE_QUERY = (_SCORE_SELECT + _SCORE_QUERY_SUFFIX).format(
    identity_expression="COALESCE(binding.event_id, score_set.item_id)",
    alias_join="LEFT JOIN event_identity_binding binding ON binding.item_id = score_set.item_id",
)
_LEGACY_SCORE_QUERY = (_SCORE_SELECT + _SCORE_QUERY_SUFFIX).format(
    identity_expression="score_set.item_id", alias_join=""
)


class PostgresIntelligenceQueryService:
    def __init__(
        self, engine: AsyncEngine, *, preview_object_reader: PreviewObjectReader | None = None
    ) -> None:
        self._engine = engine
        self._preview_object_reader = preview_object_reader

    async def close(self) -> None:
        await self._engine.dispose()

    async def _with_scores(self, items: list[ItemSummary]) -> list[ItemSummary]:
        visible_ids = [
            item.id
            for item in items
            if item.review_status is ReviewStatus.APPROVED and item.publication_revision_id
        ]
        if not visible_ids:
            return items
        async with self._engine.connect() as connection:
            alias_readable = bool(
                await connection.scalar(
                    text(
                        "SELECT has_table_privilege(current_user, 'event_identity_binding', 'SELECT')"
                    )
                )
            )
            score_query = _EVENT_SCORE_QUERY if alias_readable else _LEGACY_SCORE_QUERY
            rows = list(
                (await connection.execute(text(score_query), {"item_ids": visible_ids})).mappings()
            )
        grouped: dict[UUID, dict[str, ScoreDimensionSummary]] = {}
        for row in rows:
            item_scores = grouped.setdefault(row["identity_id"], {})
            name = str(row["dimension"])
            if name.casefold() in item_scores:
                continue
            raw_features = row["features"] if isinstance(row["features"], list) else []
            features = [
                ScoreFeature(
                    code=str(feature.get("code", "UNKNOWN")),
                    label=str(feature.get("label", "评分特征")),
                    points=int(feature.get("points", 0)),
                    explanation=str(feature.get("explanation", "规则未提供附加说明")),
                )
                for feature in raw_features
            ]
            override_score = row["override_score"]
            item_scores[name.casefold()] = ScoreDimensionSummary(
                dimension=ScoreDimension(name),
                raw_score=row["raw_score"],
                score=override_score if override_score is not None else row["raw_score"],
                features=features,
                rule_version=row["rule_version"],
                calculated_at=row["calculated_at"],
                overridden=override_score is not None,
                override_reason=row["override_reason"],
            )
        return [
            item.model_copy(update={"scores": ScoreSummary(**grouped[item.id])})
            if item.id in grouped
            else item
            for item in items
        ]

    async def _with_round09_projection(self, rows: list[RowMapping]) -> list[dict[str, Any]]:
        """Attach governed AI provenance and immutable revision state to feed rows."""
        if not rows:
            return []
        item_ids = [cast(UUID, row["id"]) for row in rows]
        async with self._engine.connect() as connection:
            projection_rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT item.id, binding.event_id, event.event_type,\n                                   COALESCE(to_jsonb(event)->>'status', 'ACTIVE')\n                                     AS event_status,\n                                   COALESCE(\n                                     (to_jsonb(event)->>'canonical_event_id')::uuid,\n                                     event.id\n                                   ) AS canonical_event_id,\n                                   COALESCE(\n                                     (to_jsonb(event)->>'version')::integer, 1\n                                   ) AS event_version,\n                                   current_revision.revision_number,\n                                   current_revision.action AS revision_action,\n                                   current_revision.created_at AS revision_created_at,\n                                   CASE WHEN current_revision.action = 'WITHDRAW'\n                                        THEN current_revision.created_at\n                                        ELSE NULL END AS revision_withdrawn_at,\n                                   ai.run_id AS ai_pipeline_run_id,\n                                   ai.prompt_version AS ai_prompt_version,\n                                   ai.schema_version AS ai_schema_version,\n                                   ai.model_profile AS ai_model_profile,\n                                   ai.generated_at AS ai_generated_at,\n                                   ai.one_sentence_fact,\n                                   COALESCE(ai.accepted_claims_only, false)\n                                     AS ai_accepted_claims_only\n                            FROM intelligence_item item\n                            LEFT JOIN event_identity_binding binding\n                              ON binding.item_id = item.id\n                            LEFT JOIN event ON event.id = binding.event_id\n                            LEFT JOIN publication\n                              ON publication.item_id = item.id\n                            LEFT JOIN publication_revision current_revision\n                              ON current_revision.id = publication.current_revision_id\n                            LEFT JOIN LATERAL (\n                                SELECT run.id AS run_id,\n                                       prompt.version AS prompt_version,\n                                       schema.version AS schema_version,\n                                       model.version AS model_profile,\n                                       run.completed_at AS generated_at,\n                                       summary.validated_output ->> 'one_sentence'\n                                         AS one_sentence_fact,\n                                       NOT EXISTS (\n                                         SELECT 1\n                                         FROM jsonb_array_elements_text(\n                                           summary.validated_output -> 'used_claim_ids'\n                                         ) used(claim_id)\n                                         WHERE NOT EXISTS (\n                                           SELECT 1 FROM claim accepted\n                                           WHERE accepted.id::text = used.claim_id\n                                             AND accepted.item_id = item.id\n                                             AND accepted.verification_status = 'ACCEPTED'\n                                         )\n                                       ) AS accepted_claims_only\n                                FROM ai_pipeline_run run\n                                JOIN LATERAL (\n                                  SELECT step.* FROM ai_step_run step\n                                  WHERE step.pipeline_run_id = run.id\n                                    AND step.step = 'SUMMARIZE'\n                                    AND step.status = 'SUCCEEDED'\n                                  ORDER BY step.attempt DESC LIMIT 1\n                                ) summary ON true\n                                JOIN ai_prompt_version prompt\n                                  ON prompt.id = summary.prompt_version_id\n                                JOIN ai_schema_version schema\n                                  ON schema.id = summary.schema_version_id\n                                JOIN ai_model_profile model\n                                  ON model.id = summary.model_profile_id\n                                WHERE run.document_version_id = item.current_document_version_id\n                                  AND run.mode = 'LIVE' AND run.status = 'SUCCEEDED'\n                                  AND (\n                                    SELECT count(DISTINCT step.step)\n                                    FROM ai_step_run step\n                                    WHERE step.pipeline_run_id = run.id\n                                      AND step.status = 'SUCCEEDED'\n                                  ) = 4\n                                ORDER BY run.completed_at DESC NULLS LAST,\n                                         run.id DESC LIMIT 1\n                            ) ai ON true\n                            WHERE item.id = ANY(CAST(:item_ids AS uuid[]))\n                            "
                        ),
                        {"item_ids": item_ids},
                    )
                ).mappings()
            )
        projections = {row["id"]: row for row in projection_rows}
        return [
            {**dict(row), **dict(projections[row["id"]])} if row["id"] in projections else dict(row)
            for row in rows
        ]

    async def render_processing_metrics(self) -> str:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT\n                              count(*) FILTER (WHERE parser_name = 'safety_regulation_pdf')\n                                AS pdf_total,\n                              count(*) FILTER (\n                                WHERE parser_name = 'safety_regulation_pdf'\n                                  AND status = 'SUCCEEDED'\n                              ) AS pdf_success,\n                              COALESCE(sum(ocr_page_count), 0) AS ocr_pages,\n                              COALESCE(sum(ocr_usable_page_count), 0) AS ocr_usable_pages,\n                              COALESCE(sum(low_confidence_critical_count), 0)\n                                AS low_confidence_critical\n                            FROM processing_run\n                            "
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
                            "\n                            SELECT change_type, material, count(*) AS count\n                            FROM version_change\n                            GROUP BY change_type, material\n                            ORDER BY change_type, material\n                            "
                        )
                    )
                ).mappings()
            )
            outbox = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT count(*) FILTER (\n                                     WHERE status IN ('PENDING','FAILED')\n                                   ) AS depth,\n                                   COALESCE(extract(epoch FROM (\n                                     now() - min(created_at) FILTER (\n                                       WHERE status IN ('PENDING','FAILED')\n                                     )\n                                   )), 0) AS oldest_seconds,\n                                   COALESCE(sum(attempt_count), 0) AS retries\n                            FROM outbox_event\n                            "
                        )
                    )
                )
                .mappings()
                .one()
            )
            # Enterprise queue and reviewer metrics were retired by PERS-10. Keep
            # only processing, immutable-version, and personal projection health.
            personal_projection_count = int(
                await connection.scalar(
                    text("SELECT count(*) FROM personal_content_projection WHERE visible")
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
                ("srbg_ocr_low_confidence_critical_fields", int(row["low_confidence_critical"])),
                ("srbg_publisher_outbox_depth", int(outbox["depth"])),
                ("srbg_publisher_outbox_oldest_seconds", float(outbox["oldest_seconds"])),
                ("srbg_publisher_outbox_retries_total", int(outbox["retries"])),
                ("srbg_personal_content_projection_visible", personal_projection_count),
            ]
            rendered = "".join(
                f"# TYPE {name} gauge\n{name} {value}\n" for name, value in values
            )
            for change in changes:
                rendered += (
                    "# TYPE srbg_version_changes_total counter\n"
                    f'srbg_version_changes_total{{change_type="{change["change_type"]}",'
                    f'material="{str(change["material"]).lower()}"}} {change["count"]}\n'
                )
            return rendered
            safety_profiles = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT report_stage, incident_status, count(*) AS count\n                            FROM safety_case_profile\n                            GROUP BY report_stage, incident_status\n                            ORDER BY report_stage, incident_status\n                            "
                        )
                    )
                ).mappings()
            )
            safety_conflicts = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT field_name, count(*) AS count\n                            FROM claim_conflict\n                            WHERE status = 'PENDING_REVIEW'\n                            GROUP BY field_name\n                            ORDER BY field_name\n                            "
                        )
                    )
                ).mappings()
            )
            safety_queues = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT 0::bigint AS pending_event_candidates,\n                                   0::bigint AS pending_critical_claims\n                            "
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
                            "\n                            SELECT source_nature, maturity_level, count(*) AS count\n                            FROM digital_case_profile\n                            GROUP BY source_nature, maturity_level\n                            ORDER BY source_nature, maturity_level\n                            "
                        )
                    )
                ).mappings()
            )
            digital_outcome_rows = (
                await connection.execute(
                    text(
                        "\n                        SELECT outcome_kind, count(*) AS count\n                        FROM digital_case_outcome\n                        GROUP BY outcome_kind\n                        "
                    )
                )
            ).mappings()
            digital_outcomes = {
                str(outcome["outcome_kind"]): int(outcome["count"])
                for outcome in digital_outcome_rows
            }
            pending_enterprise_review = int(
                await connection.scalar(
                    text(
                        "\n                        SELECT count(*)\n                        FROM digital_case_profile profile\n                        JOIN intelligence_item item ON item.id = profile.item_id\n                        WHERE profile.source_nature = 'ENTERPRISE_SELF_REPORT'\n                          AND item.review_status = 'PENDING'\n                        "
                    )
                )
                or 0
            )
            paper_profiles = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT access_level, relation_status, count(*) AS count\n                            FROM paper_profile\n                            GROUP BY access_level, relation_status\n                            ORDER BY access_level, relation_status\n                            "
                        )
                    )
                ).mappings()
            )
            paper_queues = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT\n                              count(*) FILTER (WHERE status = 'PENDING_REVIEW')\n                                AS pending_duplicates,\n                              (SELECT count(*) FROM item_relation_candidate\n                               WHERE status = 'PENDING_REVIEW'\n                                 AND relation_type IN ('CORRECTS','SUPERSEDES','RETRACTS'))\n                                AS pending_updates\n                            FROM paper_duplicate_candidate\n                            "
                        )
                    )
                )
                .mappings()
                .one()
            )
            product_profiles = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT item_type, evidence_level, permit_status, count(*) AS count\n                            FROM technology_product_profile\n                            GROUP BY item_type, evidence_level, permit_status\n                            ORDER BY item_type, evidence_level, permit_status\n                            "
                        )
                    )
                ).mappings()
            )
            product_capability_rows = (
                await connection.execute(
                    text(
                        "\n                        SELECT kind, count(*) AS count\n                        FROM technology_product_capability\n                        GROUP BY kind\n                        "
                    )
                )
            ).mappings()
            product_capabilities = {
                str(capability["kind"]): int(capability["count"])
                for capability in product_capability_rows
            }
            pending_product_normalization = int(
                await connection.scalar(
                    text(
                        "\n                        SELECT count(*) FROM product_normalization_candidate\n                        WHERE status = 'PENDING_REVIEW'\n                        "
                    )
                )
                or 0
            )
            resolution_metrics = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT\n                              (SELECT count(*) FROM duplicate_candidate\n                               WHERE status = 'PENDING_REVIEW') AS duplicate_pending,\n                              (SELECT count(*) FROM duplicate_candidate\n                               WHERE cardinality(hard_conflicts) > 0) AS hard_constraint_blocks,\n                              (SELECT count(*) FROM duplicate_candidate\n                               WHERE 'PGVECTOR' = ANY(recall_methods)) AS vector_recall_candidates,\n                              (SELECT count(*) FROM topic_cluster\n                               WHERE status = 'PENDING_REVIEW') AS topic_pending,\n                              (SELECT count(*) FROM score_set\n                               WHERE is_current) AS scored_items,\n                              (SELECT count(*) FROM score_override) AS score_overrides,\n                              (SELECT count(*) FROM cluster_decision\n                               WHERE action = 'SPLIT') AS cluster_splits,\n                              (SELECT count(*) FROM cluster_decision\n                               WHERE action = 'MERGE') AS cluster_merges\n                            "
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
            ("srbg_ocr_usable_ratio", int(row["ocr_usable_pages"]) / ocr_pages if ocr_pages else 0),
            ("srbg_ocr_low_confidence_critical_fields", int(row["low_confidence_critical"])),
            ("srbg_publisher_outbox_depth", int(outbox["depth"])),
            ("srbg_publisher_outbox_oldest_seconds", float(outbox["oldest_seconds"])),
            ("srbg_publisher_outbox_retries_total", int(outbox["retries"])),
        ]
        rendered = "".join((f"# TYPE {name} gauge\n{name} {value}\n" for name, value in values))
        for change in changes:
            rendered += f'''# TYPE srbg_version_changes_total counter\nsrbg_version_changes_total{{change_type="{change["change_type"]}",material="{str(change["material"]).lower()}"}} {change["count"]}\n'''
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
        rendered += _render_resolution_metrics(dict(resolution_metrics))
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
        region: str | None = None,
        source_id: UUID | None = None,
        source_authority: str | None = None,
        published_from: date | None = None,
        published_to: date | None = None,
        review_status: str | None = None,
        evidence_status: str | None = None,
    ) -> FeedPage:
        now = datetime.now(UTC)

        async def finish(page: FeedPage) -> FeedPage:
            filtered = await self._apply_common_feed_filters(
                page,
                region=region,
                source_id=source_id,
                source_authority=source_authority,
                published_from=published_from,
                published_to=published_to,
                review_status=review_status,
                evidence_status=evidence_status,
            )
            return await self._with_feed_freshness(filtered, now=now)

        if content_type in {
            "SOFTWARE_PRODUCT",
            "IOT_PRODUCT",
            "LOW_ALTITUDE_EQUIPMENT",
            "AI_EQUIPMENT",
        }:
            page = await self._get_product_feed(
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
            return await finish(page)
        if content_type == "JOURNAL_PAPER":
            page = await self._get_paper_feed(
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
            return await finish(page)
        if domain == "digital" or content_type == "DIGITAL_CASE":
            page = await self._get_digital_feed(
                mode=mode,
                sort=sort,
                cursor=cursor,
                limit=limit,
                engineering_domain=engineering_domain,
                scenario=scenario,
                maturity=maturity,
                source_nature=source_nature,
            )
            return await finish(page)
        if content_type is not None and content_type not in {"SAFETY_REGULATION", "SAFETY_CASE"}:
            return await finish(_feed_page([], now=now, mode=mode, domain=domain, next_cursor=None))
        cursor_time, cursor_id = _decode_cursor(cursor)
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT i.id, i.item_type, i.title, i.original_url,\n                                   i.source_published_at,\n                                   i.first_discovered_at, i.activity_at, i.updated_at,\n                                   i.review_status, s.name AS source_name,\n                                   p.status AS publication_status,\n                                   p.current_revision_id AS publication_revision_id,\n                                   r.classification, r.document_number,\n                                   r.issuing_authority, r.regulation_status,\n                                   case_profile.report_stage,\n                                   case_profile.accident_type,\n                                   case_profile.engineering_type,\n                                   case_profile.occurred_at,\n                                   case_profile.region_name,\n                                   case_profile.deaths,\n                                   case_profile.injuries,\n                                   case_profile.loss_amount_minor,\n                                   case_profile.loss_currency,\n                                   case_profile.incident_status,\n                                   case_profile.official_direct_causes,\n                                   case_profile.responsibility_findings,\n                                   case_profile.rectification_has_open_issues,\n                                   case_profile.similar_scenario_tags,\n                                   case_profile.prevention_measure_tags,\n                                   event_link.event_id,\n                                   COALESCE(conflicts.fields, ARRAY[]::text[])\n                                       AS conflicted_fields,\n                                   (SELECT count(*) FROM document_version version\n                                    WHERE version.document_id = i.primary_document_id)\n                                       AS version_count,\n                                   latest_change.change_type AS latest_change_type,\n                                   latest_change.review_state AS latest_change_review_state,\n                                   (\n                                     (SELECT url_check.outcome FROM source_url_check url_check\n                                      WHERE url_check.document_id = i.primary_document_id\n                                      ORDER BY url_check.checked_at DESC, url_check.id DESC LIMIT 1)\n                                       IN ('NOT_FOUND','GONE')\n                                     AND\n                                     (SELECT url_check.outcome FROM source_url_check url_check\n                                      WHERE url_check.document_id = i.primary_document_id\n                                      ORDER BY url_check.checked_at DESC, url_check.id DESC\n                                      LIMIT 1 OFFSET 1)\n                                       IN ('NOT_FOUND','GONE')\n                                   ) OR (\n                                     (SELECT count(*) FROM (\n                                        SELECT url_check.outcome FROM source_url_check url_check\n                                        WHERE url_check.document_id = i.primary_document_id\n                                        ORDER BY url_check.checked_at DESC, url_check.id DESC\n                                        LIMIT 3\n                                     ) recent\n                                     WHERE recent.outcome IN ('TIMEOUT','SERVER_ERROR')) = 3\n                                   ) AS source_unavailable,\n                                   (SELECT count(*) FROM claim_evidence e\n                                    JOIN claim c ON c.id = e.claim_id\n                                    WHERE c.item_id = i.id\n                                      AND (\n                                        c.verification_status = 'ACCEPTED'\n                                        OR 'ACCEPT' = (\n                                          SELECT decision.action\n                                          FROM claim_field_decision decision\n                                          WHERE decision.claim_id = c.id\n                                          ORDER BY decision.created_at DESC, decision.id DESC\n                                          LIMIT 1\n                                        )\n                                      )\n                                      AND (\n                                        i.item_type <> 'SAFETY_CASE'\n                                        OR (\n                                          c.verification_status = 'ACCEPTED'\n                                          AND c.critical = false\n                                        )\n                                        OR e.id = (\n                                          SELECT decision.evidence_id\n                                          FROM claim_field_decision decision\n                                          WHERE decision.claim_id = c.id\n                                          ORDER BY decision.created_at DESC, decision.id DESC\n                                          LIMIT 1\n                                        )\n                                      )) AS evidence_count\n                            FROM intelligence_item i\n                            JOIN source s ON s.id = i.source_id\n                            LEFT JOIN safety_regulation_profile r ON r.item_id = i.id\n                            LEFT JOIN safety_case_profile case_profile\n                              ON case_profile.item_id = i.id\n                            LEFT JOIN event_item event_link ON event_link.item_id = i.id\n                            LEFT JOIN publication p ON p.item_id = i.id\n                            LEFT JOIN LATERAL (\n                                SELECT array_agg(DISTINCT conflict.field_name)\n                                    AS fields\n                                FROM public_safety_case_conflict conflict\n                                WHERE conflict.source_item_id = i.id\n                            ) conflicts ON true\n                            LEFT JOIN LATERAL (\n                                SELECT change.change_type, change.review_state\n                                FROM version_change change\n                                WHERE change.document_id = i.primary_document_id\n                                ORDER BY change.created_at DESC, change.id DESC LIMIT 1\n                            ) latest_change ON true\n                            WHERE (\n                                i.review_status = 'PENDING'\n                                OR p.status IN ('PUBLISHED', 'WITHDRAWN')\n                            )\n                              AND i.risk_level = 'R3'\n                              AND (:mode <> 'selected' OR (\n                                p.status = 'PUBLISHED'\n                                AND EXISTS (\n                                  SELECT 1 FROM score_set selected_score\n                                  WHERE selected_score.item_id = i.id\n                                    AND selected_score.is_current\n                                )\n                              ))\n                              AND (\n                                CAST(:content_type AS text) IS NULL\n                                OR i.item_type = CAST(:content_type AS text)\n                              )\n                              AND (\n                                (i.item_type = 'SAFETY_REGULATION' AND r.item_id IS NOT NULL)\n                                OR\n                                (i.item_type = 'SAFETY_CASE'\n                                  AND case_profile.item_id IS NOT NULL)\n                              )\n                              AND (\n                                CAST(:cursor_time AS timestamptz) IS NULL\n                                OR (i.activity_at, i.id) <\n                                   (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid))\n                              )\n                            ORDER BY i.activity_at DESC, i.id DESC\n                            LIMIT :row_limit\n                            "
                        ),
                        {
                            "cursor_time": cursor_time,
                            "cursor_id": cursor_id,
                            "content_type": content_type,
                            "mode": mode,
                            "row_limit": limit + 1,
                        },
                    )
                ).mappings()
            )
        has_more = len(rows) > limit
        visible = rows[:limit]
        projected = await self._with_round09_projection(visible)
        items = await self._with_scores([_item_summary(row) for row in projected])
        next_cursor = None
        if has_more and visible:
            next_cursor = _encode_cursor(visible[-1]["activity_at"], visible[-1]["id"])
        return await finish(
            _feed_page(items, now=now, mode=mode, domain=domain, next_cursor=next_cursor)
        )

    async def _apply_common_feed_filters(
        self,
        page: FeedPage,
        *,
        region: str | None,
        source_id: UUID | None,
        source_authority: str | None,
        published_from: date | None,
        published_to: date | None,
        review_status: str | None,
        evidence_status: str | None,
    ) -> FeedPage:
        items = [
            item
            for item in page.items
            if (review_status is None or item.review_status.value == review_status)
            and (
                evidence_status is None
                or (
                    item.evidence_status is not None
                    and item.evidence_status.value == evidence_status
                )
            )
        ]
        database_filter = any(
            value is not None
            for value in (region, source_id, source_authority, published_from, published_to)
        )
        if database_filter and items:
            async with self._engine.connect() as connection:
                allowed = set(
                    (
                        await connection.execute(
                            text(
                                "\n                                SELECT i.id FROM intelligence_item i\n                                JOIN source s ON s.id = i.source_id\n                                LEFT JOIN safety_case_profile scp ON scp.item_id = i.id\n                                LEFT JOIN publication p ON p.item_id = i.id\n                                LEFT JOIN publication_revision pr ON pr.id = p.current_revision_id\n                                WHERE i.id = ANY(CAST(:item_ids AS uuid[]))\n                                  AND (CAST(:source_id AS uuid) IS NULL OR\n                                    i.source_id = CAST(:source_id AS uuid))\n                                  AND (CAST(:source_authority AS text) IS NULL OR\n                                    s.authority_level = CAST(:source_authority AS text))\n                                  AND (CAST(:published_from AS date) IS NULL\n                                    OR i.source_published_at::date >= CAST(:published_from AS date))\n                                  AND (CAST(:published_to AS date) IS NULL\n                                    OR i.source_published_at::date <= CAST(:published_to AS date))\n                                  AND (CAST(:region AS text) IS NULL OR COALESCE(\n                                    scp.region_name,\n                                    pr.snapshot->>'region_name',\n                                    pr.snapshot->>'region'\n                                  ) = CAST(:region AS text))\n                                "
                            ),
                            {
                                "item_ids": [item.id for item in items],
                                "source_id": source_id,
                                "source_authority": source_authority,
                                "published_from": published_from,
                                "published_to": published_to,
                                "region": region,
                            },
                        )
                    ).scalars()
                )
            items = [item for item in items if item.id in allowed]
        if items == page.items:
            return page
        fingerprint = sha256(
            (page.fingerprint + "|" + "|".join((str(item.id) for item in items))).encode()
        ).hexdigest()
        return page.model_copy(update={"items": items, "fingerprint": f"sha256:{fingerprint}"})

    async def _with_feed_freshness(self, page: FeedPage, *, now: datetime) -> FeedPage:
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT source.name, source.channel, source.priority,\n                              checkpoint.last_success_at, checkpoint.consecutive_failures\n                            FROM source\n                            JOIN source_connector connector ON connector.source_id = source.id\n                              AND connector.enabled\n                            LEFT JOIN source_checkpoint checkpoint\n                              ON checkpoint.source_connector_id = connector.id\n                            WHERE source.state = 'ACTIVE' AND source.enabled\n                            "
                        )
                    )
                )
                .mappings()
                .all()
            )
        if not rows:
            return page
        delayed: list[str] = []
        for row in rows:
            threshold_seconds = (
                30 * 60
                if row["channel"] in {"SAFETY", "BOTH"} and row["priority"] == "P0"
                else 4 * 60 * 60
            )
            last_success = cast(datetime | None, row["last_success_at"])
            if (
                last_success is None
                or (now - last_success).total_seconds() > threshold_seconds
                or int(row["consecutive_failures"] or 0) > 0
            ):
                delayed.append(str(row["name"]))
        if not delayed:
            return page
        freshness = "delayed" if len(delayed) == len(rows) else "partial"
        suffix = "、".join(delayed[:5])
        if len(delayed) > 5:
            suffix += f"等{len(delayed)}个来源"
        notice = FeedNotice(
            code="SOURCE_DELAYED",
            level="warning",
            message=f"以下活动来源采集延迟或失败：{suffix}。内容时间可能不完整。",
        )
        return page.model_copy(update={"freshness": freshness, "notices": [*page.notices, notice]})

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
                            "\n                            SELECT i.id, i.item_type, i.title, i.original_url,\n                                   i.source_published_at, i.first_discovered_at,\n                                   i.activity_at, i.updated_at, i.review_status,\n                                   source.name AS source_name,\n                                   publication.status AS publication_status,\n                                   publication.current_revision_id AS publication_revision_id,\n                                   profile.source_nature, profile.maturity_level,\n                                   profile.deployment_scale, profile.srbg_relationship,\n                                   relevance.score AS relevance_score,\n                                   relevance.rule_version AS relevance_rule_version,\n                                   relevance.engineering_points,\n                                   relevance.sichuan_points,\n                                   relevance.srbg_direct_points,\n                                   taxonomy.engineering_domains,\n                                   taxonomy.lifecycle_stages,\n                                   taxonomy.technology_tags,\n                                   taxonomy.application_scenarios,\n                                   (SELECT count(*) FROM document_version version\n                                    WHERE version.document_id = i.primary_document_id)\n                                     AS version_count,\n                                   NULL::text AS latest_change_type,\n                                   NULL::text AS latest_change_review_state,\n                                   false AS source_unavailable,\n                                   (SELECT count(*) FROM claim_evidence evidence\n                                    JOIN claim ON claim.id = evidence.claim_id\n                                    WHERE claim.item_id = i.id\n                                      AND claim.verification_status = 'ACCEPTED')\n                                     AS evidence_count\n                            FROM intelligence_item i\n                            JOIN source ON source.id = i.source_id\n                            JOIN digital_case_profile profile ON profile.item_id = i.id\n                            JOIN digital_case_relevance relevance ON relevance.item_id = i.id\n                            LEFT JOIN publication ON publication.item_id = i.id\n                            JOIN LATERAL (\n                              SELECT\n                                COALESCE(array_agg(code ORDER BY code)\n                                  FILTER (WHERE facet = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])\n                                  AS engineering_domains,\n                                COALESCE(array_agg(code ORDER BY code)\n                                  FILTER (WHERE facet = 'LIFECYCLE_STAGE'), ARRAY[]::text[])\n                                  AS lifecycle_stages,\n                                COALESCE(array_agg(code ORDER BY code)\n                                  FILTER (WHERE facet = 'TECHNOLOGY_TAG'), ARRAY[]::text[])\n                                  AS technology_tags,\n                                COALESCE(array_agg(code ORDER BY code)\n                                  FILTER (WHERE facet = 'APPLICATION_SCENARIO'), ARRAY[]::text[])\n                                  AS application_scenarios\n                              FROM digital_case_taxonomy\n                              WHERE item_id = i.id\n                            ) taxonomy ON true\n                            WHERE i.item_type = 'DIGITAL_CASE'\n                              AND i.channel = 'DIGITAL'\n                              AND i.risk_level <> 'R4'\n                              AND i.review_status <> 'REJECTED'\n                              AND (\n                                :mode <> 'selected'\n                                OR (\n                                  i.review_status = 'APPROVED'\n                                  AND publication.status = 'PUBLISHED'\n                                  AND EXISTS (\n                                    SELECT 1 FROM score_set selected_score\n                                    WHERE selected_score.item_id = i.id\n                                      AND selected_score.is_current\n                                  )\n                                )\n                              )\n                              AND (\n                                CAST(:engineering_domain AS text) IS NULL\n                                OR :engineering_domain = ANY(taxonomy.engineering_domains)\n                              )\n                              AND (\n                                CAST(:scenario AS text) IS NULL\n                                OR :scenario = ANY(taxonomy.application_scenarios)\n                              )\n                              AND (\n                                CAST(:maturity AS text) IS NULL\n                                OR profile.maturity_level = CAST(:maturity AS text)\n                              )\n                              AND (\n                                CAST(:source_nature AS text) IS NULL\n                                OR profile.source_nature = CAST(:source_nature AS text)\n                              )\n                              AND (\n                                CAST(:cursor_time AS timestamptz) IS NULL\n                                OR (i.activity_at, i.id) <\n                                   (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid))\n                              )\n                            ORDER BY\n                              CASE WHEN :sort = 'relevance' THEN relevance.score END DESC,\n                              i.activity_at DESC, i.id DESC\n                            LIMIT :row_limit\n                            "
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
        projected = await self._with_round09_projection(visible)
        items = await self._with_scores([_item_summary(row) for row in projected])
        next_cursor = None
        if has_more and visible and (sort == "latest"):
            next_cursor = _encode_cursor(visible[-1]["activity_at"], visible[-1]["id"])
        return _feed_page(
            items, now=datetime.now(UTC), mode=mode, domain="digital", next_cursor=next_cursor
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
                            "\n                            SELECT i.id, i.item_type, i.title, i.original_url,\n                                   i.source_published_at, i.first_discovered_at,\n                                   i.activity_at, i.updated_at, i.review_status,\n                                   source.name AS source_name,\n                                   publication.status AS publication_status,\n                                   publication.current_revision_id AS publication_revision_id,\n                                   profile.normalized_doi, profile.journal,\n                                   profile.publication_year, profile.paper_type,\n                                   profile.access_level, profile.open_status,\n                                   profile.maturity_level, profile.relation_status,\n                                   taxonomy.engineering_domains, taxonomy.technology_tags,\n                                   (SELECT count(*) FROM document_version version\n                                    WHERE version.document_id = i.primary_document_id)\n                                      AS version_count,\n                                   NULL::text AS latest_change_type,\n                                   NULL::text AS latest_change_review_state,\n                                   false AS source_unavailable,\n                                   (SELECT count(*) FROM claim_evidence evidence\n                                    JOIN claim ON claim.id = evidence.claim_id\n                                    WHERE claim.item_id = i.id\n                                      AND claim.verification_status = 'ACCEPTED')\n                                      AS evidence_count\n                            FROM intelligence_item i\n                            JOIN source ON source.id = i.source_id\n                            JOIN paper_profile profile ON profile.item_id = i.id\n                            LEFT JOIN publication ON publication.item_id = i.id\n                            JOIN LATERAL (\n                              SELECT\n                                COALESCE(array_agg(code ORDER BY code)\n                                  FILTER (WHERE dimension = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])\n                                  AS engineering_domains,\n                                COALESCE(array_agg(code ORDER BY code)\n                                  FILTER (WHERE dimension = 'TECHNOLOGY_TAG'), ARRAY[]::text[])\n                                  AS technology_tags\n                              FROM paper_taxonomy WHERE item_id = i.id\n                            ) taxonomy ON true\n                            WHERE i.item_type = 'JOURNAL_PAPER'\n                              AND i.channel = 'DIGITAL'\n                              AND i.risk_level <> 'R4'\n                              AND i.review_status <> 'REJECTED'\n                              AND (:mode <> 'selected' OR (\n                                i.review_status = 'APPROVED'\n                                AND publication.status = 'PUBLISHED'\n                                AND EXISTS (\n                                  SELECT 1 FROM score_set selected_score\n                                  WHERE selected_score.item_id = i.id\n                                    AND selected_score.is_current\n                                )\n                              ))\n                              AND (CAST(:engineering_domain AS text) IS NULL\n                                OR :engineering_domain = ANY(taxonomy.engineering_domains))\n                              AND (CAST(:technology_tag AS text) IS NULL\n                                OR :technology_tag = ANY(taxonomy.technology_tags))\n                              AND (CAST(:maturity AS text) IS NULL\n                                OR profile.maturity_level = CAST(:maturity AS text))\n                              AND (CAST(:paper_type AS text) IS NULL\n                                OR profile.paper_type = CAST(:paper_type AS text))\n                              AND (CAST(:access_level AS text) IS NULL\n                                OR profile.access_level = CAST(:access_level AS text))\n                              AND (CAST(:year AS smallint) IS NULL\n                                OR profile.publication_year = CAST(:year AS smallint))\n                              AND (CAST(:cursor_time AS timestamptz) IS NULL\n                                OR (i.activity_at, i.id) <\n                                  (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid)))\n                            ORDER BY i.activity_at DESC, i.id DESC\n                            LIMIT :row_limit\n                            "
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
        projected = await self._with_round09_projection(visible)
        next_cursor = (
            _encode_cursor(visible[-1]["activity_at"], visible[-1]["id"])
            if len(rows) > limit and visible
            else None
        )
        items = await self._with_scores([_item_summary(row) for row in projected])
        return _feed_page(
            items, now=datetime.now(UTC), mode=mode, domain="digital", next_cursor=next_cursor
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
                            "\n                            SELECT item.id, item.item_type, item.title, item.original_url,\n                                   item.source_published_at, item.first_discovered_at,\n                                   item.activity_at, item.updated_at, item.review_status,\n                                   source.name AS source_name,\n                                   publication.status AS publication_status,\n                                   publication.current_revision_id AS publication_revision_id,\n                                   vendor.id AS vendor_id, vendor.name AS vendor_name,\n                                   product.id AS product_id, product.name AS product_name,\n                                   product.product_kind,\n                                   model.id AS model_id, model.model_no,\n                                   version.version, profile.evidence_level,\n                                   profile.permit_status, profile.maturity_level,\n                                   profile.platform_type, profile.equipment_form,\n                                   profile.interfaces, profile.deployment_modes,\n                                   profile.connectivity, profile.payload_types,\n                                   profile.ai_tasks, profile.limitations,\n                                   profile.production_validation,\n                                   taxonomy.application_scenarios,\n                                   capabilities.promotional_claim_count,\n                                   capabilities.verified_capability_count,\n                                   (SELECT count(*) FROM document_version document_version\n                                    WHERE document_version.document_id = item.primary_document_id)\n                                      AS version_count,\n                                   NULL::text AS latest_change_type,\n                                   NULL::text AS latest_change_review_state,\n                                   false AS source_unavailable,\n                                   (SELECT count(*) FROM claim_evidence evidence\n                                    JOIN claim ON claim.id = evidence.claim_id\n                                    WHERE claim.item_id = item.id\n                                      AND claim.verification_status = 'ACCEPTED') AS evidence_count\n                            FROM intelligence_item item\n                            JOIN source ON source.id = item.source_id\n                            JOIN technology_product_profile profile ON profile.item_id = item.id\n                            JOIN technology_product_version version\n                              ON version.id = profile.version_id\n                            JOIN technology_product_model model ON model.id = version.model_id\n                            JOIN technology_product product ON product.id = model.product_id\n                            JOIN technology_vendor vendor ON vendor.id = product.vendor_id\n                            LEFT JOIN publication ON publication.item_id = item.id\n                            LEFT JOIN LATERAL (\n                              SELECT\n                                count(*) FILTER (WHERE kind = 'PROMOTIONAL_CLAIM')\n                                  AS promotional_claim_count,\n                                count(*) FILTER (WHERE kind = 'VERIFIED_CAPABILITY')\n                                  AS verified_capability_count\n                              FROM technology_product_capability\n                              WHERE item_id = item.id\n                            ) capabilities ON true\n                            LEFT JOIN LATERAL (\n                              SELECT COALESCE(array_agg(code ORDER BY code)\n                                FILTER (WHERE dimension = 'APPLICATION_SCENARIO'), ARRAY[]::text[])\n                                  AS application_scenarios\n                              FROM technology_product_taxonomy WHERE item_id = item.id\n                            ) taxonomy ON true\n                            WHERE item.item_type = :content_type\n                              AND item.channel = 'DIGITAL'\n                              AND item.risk_level = 'R2'\n                              AND item.review_status <> 'REJECTED'\n                              AND (:mode <> 'selected' OR (\n                                item.review_status = 'APPROVED'\n                                AND publication.status = 'PUBLISHED'\n                                AND EXISTS (\n                                  SELECT 1 FROM score_set selected_score\n                                  WHERE selected_score.item_id = item.id\n                                    AND selected_score.is_current\n                                )\n                              ))\n                              AND (CAST(:product_kind AS text) IS NULL\n                                OR product.product_kind = CAST(:product_kind AS text))\n                              AND (CAST(:evidence_level AS text) IS NULL\n                                OR profile.evidence_level = CAST(:evidence_level AS text))\n                              AND (CAST(:deployment_mode AS text) IS NULL\n                                OR :deployment_mode = ANY(profile.deployment_modes))\n                              AND (CAST(:scenario AS text) IS NULL\n                                OR :scenario = ANY(taxonomy.application_scenarios))\n                              AND (CAST(:maturity AS text) IS NULL\n                                OR profile.maturity_level = CAST(:maturity AS text))\n                              AND (CAST(:cursor_time AS timestamptz) IS NULL\n                                OR (item.activity_at, item.id) <\n                                   (CAST(:cursor_time AS timestamptz), CAST(:cursor_id AS uuid)))\n                            ORDER BY item.activity_at DESC, item.id DESC\n                            LIMIT :row_limit\n                            "
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
        projected = await self._with_round09_projection(visible)
        next_cursor = (
            _encode_cursor(visible[-1]["activity_at"], visible[-1]["id"])
            if len(rows) > limit and visible
            else None
        )
        items = await self._with_scores([_item_summary(row) for row in projected])
        return _feed_page(
            items, now=datetime.now(UTC), mode=mode, domain="digital", next_cursor=next_cursor
        )

    async def get_item(self, item_id: UUID) -> ItemDetail:
        async with self._engine.connect() as connection:
            row = await _item_row(connection, item_id, include_unpublished=False)
            if row is None:
                raise IntelligenceNotFound("intelligence item does not exist")
            item = (await self._with_scores([_item_summary(row)]))[0]
            product_types = {
                "SOFTWARE_PRODUCT",
                "IOT_PRODUCT",
                "LOW_ALTITUDE_EQUIPMENT",
                "AI_EQUIPMENT",
            }
            if row["item_type"] not in product_types and (
                row["publication_status"] != "PUBLISHED" or row["review_status"] != "APPROVED"
            ):
                return ItemDetail(item=item, notice=_restricted_notice())
            claims, evidence = await _claims_and_evidence(connection, item_id)
            if row["item_type"] == "DIGITAL_CASE":
                digital_case = await _digital_case_detail(connection, row)
                return ItemDetail(
                    item=item, claims=claims, evidence=evidence, digital_case=digital_case
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

    async def resolve_item_event(self, item_id: UUID) -> UUID:
        """Resolve the immutable Item alias, with reviewed split allocation overlay."""
        async with self._engine.connect() as connection:
            event_id = await connection.scalar(
                text(
                    "\n                    SELECT COALESCE(split.child_event_id, binding.event_id)\n                      FROM event_identity_binding binding\n                      LEFT JOIN LATERAL (\n                        SELECT allocation.child_event_id\n                          FROM event_split_allocation allocation\n                          JOIN event_identity_change_request request\n                            ON request.id=allocation.request_id AND request.status='APPLIED'\n                         WHERE allocation.item_id=binding.item_id\n                         ORDER BY request.created_at DESC, request.id DESC LIMIT 1\n                      ) split ON true\n                     WHERE binding.item_id=:item_id\n                    "
                ),
                {"item_id": item_id},
            )
        if event_id is None:
            raise IntelligenceNotFound("item has no canonical event identity")
        return UUID(str(event_id))

    async def resolve_event_redirect(self, event_id: UUID) -> UUID | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT COALESCE(to_jsonb(event)->>'status','ACTIVE') AS status, COALESCE((to_jsonb(event)->>'canonical_event_id')::uuid,id) AS canonical_event_id FROM event WHERE id=:event_id"
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        if row["status"] == "MERGED":
            return UUID(str(row["canonical_event_id"]))
        return event_id

    async def get_event_item_projection(self, event_id: UUID) -> ItemDetail:
        """Return type-specific content inside the Event detail, never as a second identity."""
        async with self._engine.connect() as connection:
            item_id = await connection.scalar(
                text(
                    "\n                    SELECT binding.item_id\n                      FROM event_identity_binding binding\n                      JOIN publication ON publication.item_id=binding.item_id\n                     WHERE binding.event_id=:event_id\n                       AND publication.status='PUBLISHED'\n                     ORDER BY publication.updated_at DESC, binding.item_id DESC\n                     LIMIT 1\n                    "
                ),
                {"event_id": event_id},
            )
        if item_id is None:
            raise IntelligenceNotFound("event has no published content projection")
        return await self.get_item(UUID(str(item_id)))

    async def get_event_summary_for_item(self, item_id: UUID) -> EventSummary:
        detail = await self.get_item(item_id)
        async with self._engine.connect() as connection:
            identity = (
                (
                    await connection.execute(
                        text(
                            "\n                        SELECT event.id,event.event_type,\n                               COALESCE(to_jsonb(event)->>'status','ACTIVE') AS status,\n                               COALESCE(\n                                 (to_jsonb(event)->>'canonical_event_id')::uuid,\n                                 event.id\n                               ) AS canonical_event_id,\n                               COALESCE(\n                                 (to_jsonb(event)->>'version')::integer, 1\n                               ) AS version\n                          FROM event_identity_binding binding\n                          JOIN event ON event.id=binding.event_id\n                         WHERE binding.item_id=:item_id\n                        "
                        ),
                        {"item_id": item_id},
                    )
                )
                .mappings()
                .first()
            )
        if identity is None:
            raise IntelligenceNotFound("item has no canonical event identity")
        return EventSummary.model_validate(
            detail.item.model_dump()
            | {
                "id": identity["id"],
                "event_type": identity["event_type"],
                "event_status": identity["status"],
                "canonical_event_id": identity["canonical_event_id"],
                "event_version": identity["version"],
            }
        )

    async def get_citation(self, item_id: UUID, citation_format: str) -> tuple[str, str]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT item.title, profile.normalized_doi AS doi,\n                                   profile.journal, profile.publication_year AS year,\n                                   profile.volume, profile.issue, profile.pages,\n                                   COALESCE(\n                                     array_agg(author.name ORDER BY authorship.author_order)\n                                       FILTER (WHERE author.id IS NOT NULL),\n                                     ARRAY[]::text[]\n                                   ) AS authors\n                            FROM intelligence_item item\n                            JOIN paper_profile profile ON profile.item_id = item.id\n                            JOIN publication ON publication.item_id = item.id\n                              AND publication.status = 'PUBLISHED'\n                            LEFT JOIN paper_authorship authorship ON authorship.item_id = item.id\n                            LEFT JOIN paper_author author ON author.id = authorship.author_id\n                            WHERE item.id = :item_id\n                              AND item.item_type = 'JOURNAL_PAPER'\n                              AND item.review_status = 'APPROVED'\n                            GROUP BY item.id, item.title, profile.normalized_doi,\n                                     profile.journal, profile.publication_year,\n                                     profile.volume, profile.issue, profile.pages\n                            "
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
        formatter = {"ris": format_ris, "bibtex": format_bibtex, "gb-t-7714": format_gbt7714}.get(
            citation_format
        )
        if formatter is None:
            raise ValueError("unsupported citation format")
        media_type = {
            "ris": "application/x-research-info-systems; charset=utf-8",
            "bibtex": "application/x-bibtex; charset=utf-8",
            "gb-t-7714": "text/plain; charset=utf-8",
        }[citation_format]
        return (formatter(metadata), media_type)

    async def list_automatic_relationships(self, event_id: UUID) -> list[AutomaticRelationshipView]:
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            WITH members AS (\n                              SELECT item_id FROM event_identity_binding WHERE event_id=:event_id\n                              UNION SELECT item_id FROM event_item WHERE event_id=:event_id\n                            )\n                            SELECT decision.id,decision.relationship_key,\n                              decision.relationship_kind,decision.source_item_id,\n                              decision.target_item_id,decision.status,decision.score_bps,\n                              decision.reason_codes,decision.algorithm_version,\n                              decision.model_version,decision.input_fingerprint_sha256,\n                              decision.created_at\n                            FROM automatic_relationship_decision_version decision\n                            WHERE decision.source_item_id IN (SELECT item_id FROM members)\n                               OR decision.target_item_id IN (SELECT item_id FROM members)\n                            ORDER BY (decision.status='ACTIVE') DESC,\n                              decision.created_at DESC,decision.id DESC\n                            "
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
        return [
            AutomaticRelationshipView(
                id=row["id"],
                relationship_key=row["relationship_key"],
                kind=row["relationship_kind"],
                source_item_id=row["source_item_id"],
                target_item_id=row["target_item_id"],
                status=row["status"],
                score_bps=row["score_bps"],
                reason_codes=list(row["reason_codes"]),
                algorithm_version=row["algorithm_version"],
                model_version=row["model_version"],
                input_fingerprint_sha256=row["input_fingerprint_sha256"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def get_event(self, event_id: UUID) -> EventDetail:
        async with self._engine.connect() as connection:
            identity = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,event_type,title, COALESCE(to_jsonb(event)->>'status','ACTIVE') AS status, COALESCE((to_jsonb(event)->>'canonical_event_id')::uuid,id) AS canonical_event_id, COALESCE((to_jsonb(event)->>'version')::integer,1) AS version FROM event WHERE id = :event_id"
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .first()
            )
            if identity is not None and identity["status"] == EventStatus.SPLIT:
                child_ids = list(
                    await connection.scalars(
                        text(
                            "\n                            SELECT DISTINCT child.event_id\n                              FROM event_identity_change_target source\n                              JOIN event_identity_change_request request\n                                ON request.id=source.request_id\n                               AND request.operation='SPLIT'\n                               AND request.status='APPLIED'\n                              JOIN event_identity_change_target child\n                                ON child.request_id=source.request_id\n                               AND child.target_role='CHILD'\n                             WHERE source.event_id=:event_id\n                               AND source.target_role='SOURCE'\n                            UNION\n                            SELECT DISTINCT (allocation->>'child_event_id')::uuid\n                              FROM owner_relationship_correction correction\n                              CROSS JOIN LATERAL jsonb_array_elements(\n                                correction.payload->'allocations'\n                              ) allocation\n                             WHERE correction.event_id=:event_id\n                               AND correction.action='SPLIT_EVENT'\n                             ORDER BY 1\n                            "
                        ),
                        {"event_id": event_id},
                    )
                )
                return EventDetail(
                    id=identity["id"],
                    title=identity["title"],
                    event_type=identity["event_type"],
                    event_status=EventStatus.SPLIT,
                    canonical_event_id=identity["canonical_event_id"],
                    event_version=identity["version"],
                    split_child_event_ids=child_ids,
                    confirmed_facts=[],
                    unverified_facts=[],
                    timeline=EventTimeline(event_id=event_id, items=[]),
                    relations=[],
                    similar_scenario_tags=[],
                    prevention_measure_tags=[],
                )
            event_type = None if identity is None else identity["event_type"]
        if event_type is not None and event_type != "SAFETY_INCIDENT":
            return await self._get_generic_event(event_id)
        async with self._engine.connect() as connection:
            event = (
                (
                    await connection.execute(
                        text(
                            "\n                            WITH safe_members AS (\n                              SELECT membership.event_id AS id,\n                                     header_item.id AS item_id,\n                                     header_item.title,\n                                     header_item.source_published_at,\n                                     membership.confirmed_at,\n                                     header_profile.occurred_at,\n                                     header_profile.region_name,\n                                     header_profile.project_name,\n                                     header_profile.accident_type,\n                                     header_profile.engineering_type,\n                                     header_profile.incident_status,\n                                     header_profile.rectification_has_open_issues,\n                                     header_profile.similar_scenario_tags,\n                                     header_profile.prevention_measure_tags\n                              FROM event_item membership\n                              JOIN event confirmed_event\n                                ON confirmed_event.id = membership.event_id\n                               AND confirmed_event.confirmation_status = 'CONFIRMED'\n                              JOIN intelligence_item header_item\n                                ON header_item.id = membership.item_id\n                              JOIN publication header_publication\n                                ON header_publication.item_id = header_item.id\n                               AND header_publication.status = 'PUBLISHED'\n                              JOIN safety_case_profile header_profile\n                                ON header_profile.item_id = header_item.id\n                              WHERE membership.event_id = :event_id\n                                AND header_item.risk_level = 'R3'\n                                AND header_item.review_status = 'APPROVED'\n                            ),\n                            latest_member AS (\n                              SELECT *\n                              FROM safe_members latest\n                              ORDER BY latest.source_published_at DESC NULLS LAST,\n                                       latest.confirmed_at DESC, latest.item_id DESC\n                              LIMIT 1\n                            )\n                            SELECT latest.id,\n                                   (SELECT earliest.title\n                                    FROM safe_members earliest\n                                    ORDER BY earliest.source_published_at ASC NULLS LAST,\n                                             earliest.confirmed_at, earliest.item_id\n                                    LIMIT 1) AS title,\n                                   (SELECT identity.occurred_at\n                                    FROM safe_members identity\n                                    WHERE identity.occurred_at IS NOT NULL\n                                    ORDER BY identity.source_published_at DESC NULLS LAST,\n                                             identity.confirmed_at DESC, identity.item_id DESC\n                                    LIMIT 1) AS occurred_at,\n                                   (SELECT identity.region_name\n                                    FROM safe_members identity\n                                    WHERE identity.region_name IS NOT NULL\n                                    ORDER BY identity.source_published_at DESC NULLS LAST,\n                                             identity.confirmed_at DESC, identity.item_id DESC\n                                    LIMIT 1) AS region_name,\n                                   (SELECT identity.project_name\n                                    FROM safe_members identity\n                                    WHERE identity.project_name IS NOT NULL\n                                    ORDER BY identity.source_published_at DESC NULLS LAST,\n                                             identity.confirmed_at DESC, identity.item_id DESC\n                                    LIMIT 1) AS project_name,\n                                   (SELECT identity.accident_type\n                                    FROM safe_members identity\n                                    WHERE identity.accident_type IS NOT NULL\n                                    ORDER BY identity.source_published_at DESC NULLS LAST,\n                                             identity.confirmed_at DESC, identity.item_id DESC\n                                    LIMIT 1) AS accident_type,\n                                   (SELECT identity.engineering_type\n                                    FROM safe_members identity\n                                    WHERE identity.engineering_type IS NOT NULL\n                                    ORDER BY identity.source_published_at DESC NULLS LAST,\n                                             identity.confirmed_at DESC, identity.item_id DESC\n                                    LIMIT 1) AS engineering_type,\n                                   latest.incident_status,\n                                   latest.rectification_has_open_issues,\n                                   latest.similar_scenario_tags,\n                                   latest.prevention_measure_tags\n                            FROM latest_member latest\n                            "
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
                            "\n                            SELECT i.id AS item_id, i.title, profile.report_stage,\n                                   profile.incident_status, source.name AS source_name,\n                                   i.source_published_at, i.original_url, i.review_status,\n                                   publication.current_revision_id AS publication_revision_id,\n                                   publication.status AS publication_status,\n                                   relation.relation_type,\n                                   (SELECT count(*) FROM claim_evidence evidence\n                                    JOIN claim ON claim.id = evidence.claim_id\n                                    WHERE claim.item_id = i.id\n                                       AND (\n                                         (claim.verification_status = 'ACCEPTED'\n                                          AND claim.critical = false)\n                                         OR (\n                                           'ACCEPT' = (\n                                             SELECT decision.action\n                                             FROM claim_field_decision decision\n                                             WHERE decision.claim_id = claim.id\n                                             ORDER BY decision.created_at DESC, decision.id DESC\n                                             LIMIT 1\n                                           )\n                                           AND evidence.id = (\n                                             SELECT decision.evidence_id\n                                             FROM claim_field_decision decision\n                                             WHERE decision.claim_id = claim.id\n                                             ORDER BY decision.created_at DESC, decision.id DESC\n                                             LIMIT 1\n                                           )\n                                         )\n                                       )\n                                       AND NOT EXISTS (\n                                        SELECT 1 FROM public_safety_case_conflict conflict\n                                        WHERE conflict.event_id = membership.event_id\n                                          AND conflict.field_name = claim.claim_type\n                                      )) AS evidence_count\n                            FROM event_item membership\n                            JOIN intelligence_item i ON i.id = membership.item_id\n                            JOIN safety_case_profile profile ON profile.item_id = i.id\n                            JOIN source ON source.id = i.source_id\n                            JOIN publication ON publication.item_id = i.id\n                              AND publication.status IN ('PUBLISHED','WITHDRAWN')\n                            LEFT JOIN LATERAL (\n                                SELECT confirmed.relation_type\n                                FROM event_relation confirmed\n                                WHERE confirmed.event_id = membership.event_id\n                                  AND confirmed.source_item_id = i.id\n                                ORDER BY\n                                  (confirmed.relation_type = 'CORRECTS') ASC,\n                                  confirmed.confirmed_at DESC, confirmed.id DESC\n                                LIMIT 1\n                            ) relation ON true\n                            WHERE membership.event_id = :event_id\n                              AND i.risk_level = 'R3'\n                              AND i.review_status = 'APPROVED'\n                            ORDER BY i.source_published_at NULLS LAST,\n                                     membership.confirmed_at, i.id\n                            "
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            confirmed_rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT source_item_id, claim_id, field_name,\n                                   literal_value, evidence_id, reviewed_at,\n                                   loss_currency\n                            FROM public_safety_case_accepted_claim\n                            WHERE event_id = :event_id\n                            ORDER BY reviewed_at, claim_id\n                            "
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            conflict_rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT conflict.source_item_id,\n                                   NULL::uuid AS claim_id,\n                                   conflict.conflict_id,\n                                   conflict.field_name,\n                                   ARRAY[]::uuid[] AS evidence_ids\n                            FROM public_safety_case_conflict conflict\n                            WHERE conflict.event_id = :event_id\n                              AND conflict.field_name IN (\n                                'deaths','injuries','loss_amount_minor',\n                                'official_direct_causes','responsibility_findings'\n                              )\n                            ORDER BY conflict.detected_at, conflict.conflict_id\n                            "
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            pending_rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT claim.item_id AS source_item_id, claim.id AS claim_id,\n                                   claim.claim_type AS field_name,\n                                   array_remove(array_agg(evidence.id), NULL) AS evidence_ids\n                            FROM claim\n                            JOIN event_item membership ON membership.item_id = claim.item_id\n                            JOIN intelligence_item item ON item.id = claim.item_id\n                            JOIN publication ON publication.item_id = item.id\n                              AND publication.status = 'PUBLISHED'\n                            LEFT JOIN LATERAL (\n                              SELECT decision.action\n                              FROM claim_field_decision decision\n                              WHERE decision.claim_id = claim.id\n                              ORDER BY decision.created_at DESC, decision.id DESC\n                              LIMIT 1\n                            ) latest_decision ON true\n                            LEFT JOIN claim_evidence evidence ON evidence.claim_id = claim.id\n                            WHERE membership.event_id = :event_id\n                              AND item.risk_level = 'R3'\n                              AND item.review_status = 'APPROVED'\n                              AND claim.critical = true\n                              AND claim.claim_type IN (\n                                'deaths','injuries','loss_amount_minor',\n                                'official_direct_causes','responsibility_findings'\n                              )\n                              AND (\n                                latest_decision.action IS NULL\n                                OR latest_decision.action = 'REVOKE'\n                              )\n                            GROUP BY claim.item_id, claim.id, claim.claim_type, claim.created_at\n                            ORDER BY claim.created_at, claim.id\n                            "
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            relation_rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT relation.id, relation.event_id,\n                                   relation.source_item_id, relation.target_item_id,\n                                   relation.relation_type, relation.confirmed_by,\n                                   relation.confirmed_at\n                            FROM event_relation relation\n                            JOIN intelligence_item source_item\n                              ON source_item.id = relation.source_item_id\n                            JOIN publication source_publication\n                              ON source_publication.item_id = source_item.id\n                             AND source_publication.status IN ('PUBLISHED','WITHDRAWN')\n                            JOIN intelligence_item target_item\n                              ON target_item.id = relation.target_item_id\n                            JOIN publication target_publication\n                              ON target_publication.item_id = target_item.id\n                             AND target_publication.status IN ('PUBLISHED','WITHDRAWN')\n                            WHERE relation.event_id = :event_id\n                              AND source_item.risk_level = 'R3'\n                              AND source_item.review_status = 'APPROVED'\n                              AND target_item.risk_level = 'R3'\n                              AND target_item.review_status = 'APPROVED'\n                            ORDER BY relation.confirmed_at, relation.id\n                            "
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
                document_states=[DocumentState.WITHDRAWN]
                if row["publication_status"] == "WITHDRAWN"
                else None,
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
            event_type=EventType.SAFETY_INCIDENT,
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

    async def _get_generic_event(self, event_id: UUID) -> EventDetail:
        async with self._engine.connect() as connection:
            personal = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT event.id,event.event_type,event.title,event.occurred_at,\n                              event.region_name,event.project_name,projection.item_id,\n                              projection.evidence_facts,item.original_url,item.review_status,\n                              item.source_published_at,source.name AS source_name\n                            FROM event\n                            JOIN event_identity_binding binding ON binding.event_id=event.id\n                            JOIN personal_content_projection projection\n                              ON projection.item_id=binding.item_id AND projection.visible\n                            JOIN intelligence_item item ON item.id=projection.item_id\n                            JOIN source ON source.id=item.source_id\n                            WHERE event.id=:event_id AND event.confirmation_status='CONFIRMED'\n                            "
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .first()
            )
            if personal is not None:
                judgment_rows = list(
                    (
                        await connection.execute(
                            text(
                                "\n                                SELECT judgment.id,judgment.document_version_id,\n                                  judgment.field_name,judgment.candidate_value,\n                                  judgment.confidence_bps,judgment.attribution,\n                                  judgment.reason_codes,judgment.rule_version,\n                                  evidence.id AS evidence_id,evidence.excerpt,\n                                  evidence.excerpt_sha256,evidence.locator\n                                FROM ai_judgment judgment\n                                LEFT JOIN ai_judgment_evidence evidence\n                                  ON evidence.judgment_id=judgment.id\n                                WHERE judgment.item_id=:item_id AND judgment.status='CURRENT'\n                                ORDER BY judgment.created_at,judgment.id,evidence.id\n                                "
                            ),
                            {"item_id": personal["item_id"]},
                        )
                    ).mappings()
                )
                return _personal_event_projection(personal, judgment_rows)
            event = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT id, event_type, title, occurred_at, region_name, project_name\n                            FROM event\n                            WHERE id = :event_id AND confirmation_status = 'CONFIRMED'\n                            "
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .first()
            )
            if event is None:
                raise IntelligenceNotFound("confirmed event does not exist")
            rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT item.id AS item_id, item.title,\n                                   source.name AS source_name, item.source_published_at,\n                                   item.original_url, item.review_status,\n                                   publication.current_revision_id AS publication_revision_id,\n                                   (SELECT count(*) FROM claim_evidence evidence\n                                    JOIN claim ON claim.id = evidence.claim_id\n                                    WHERE claim.item_id = item.id\n                                      AND claim.verification_status = 'ACCEPTED') AS evidence_count\n                            FROM event_item membership\n                            JOIN intelligence_item item ON item.id = membership.item_id\n                            JOIN source ON source.id = item.source_id\n                            JOIN publication ON publication.item_id = item.id\n                              AND publication.status = 'PUBLISHED'\n                            WHERE membership.event_id = :event_id\n                              AND item.review_status = 'APPROVED'\n                            ORDER BY item.source_published_at, item.id\n                            "
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
            topic_ids = list(
                (
                    await connection.scalars(
                        text("SELECT topic_id FROM topic_cluster_event WHERE event_id = :event_id"),
                        {"event_id": event_id},
                    )
                ).all()
            )
        comparison = await self.get_source_comparison(event_id)
        return EventDetail(
            id=event["id"],
            title=event["title"],
            event_type=event["event_type"],
            project_name=event["project_name"],
            occurred_at=event["occurred_at"],
            region=event["region_name"],
            incident_status=None,
            confirmed_facts=[],
            unverified_facts=[],
            timeline=EventTimeline(
                event_id=event_id,
                items=[
                    EventItem(
                        item_id=row["item_id"],
                        title=row["title"],
                        report_stage=None,
                        incident_status=None,
                        source_name=row["source_name"],
                        source_published_at=row["source_published_at"],
                        original_url=row["original_url"],
                        review_status=row["review_status"],
                        publication_revision_id=row["publication_revision_id"],
                        evidence_count=row["evidence_count"],
                    )
                    for row in rows
                ],
            ),
            relations=[],
            similar_scenario_tags=[],
            prevention_measure_tags=[],
            topic_ids=topic_ids,
            independent_source_count=comparison.independent_source_count,
        )

    async def list_hot_topics(
        self, *, domain: str | None, window_days: int, cursor: str | None, limit: int
    ) -> HotTopicPage:
        cursor_heat, cursor_time, cursor_id = _decode_hot_cursor(
            cursor, domain=domain, window_days=window_days
        )
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            WITH topics AS (\n                            SELECT topic.id, topic.title, topic.domain,\n                                   count(DISTINCT membership.event_id) AS event_count,\n                                   count(DISTINCT (\n                                     COALESCE(lineage.lineage_root, item.source_id::text),\n                                     COALESCE(affiliation.organization_key, item.source_id::text)\n                                   )) FILTER (\n                                     WHERE lineage.role IS NULL\n                                        OR lineage.role IN (\n                                          'ORIGINAL','INDEPENDENT_REPORT','INDEPENDENT_VERIFICATION'\n                                        )\n                                   ) AS independent_source_count,\n                                   max(item.activity_at) AS latest_activity_at,\n                                   COALESCE(max(CASE WHEN dimension.dimension = 'HEAT'\n                                     THEN COALESCE(override.score, dimension.raw_score) END), 0)\n                                     AS heat_score\n                            FROM topic_cluster topic\n                            JOIN topic_cluster_event membership ON membership.topic_id = topic.id\n                            JOIN event_item event_member\n                              ON event_member.event_id = membership.event_id\n                            JOIN intelligence_item item ON item.id = event_member.item_id\n                            JOIN publication ON publication.item_id = item.id\n                              AND publication.status = 'PUBLISHED'\n                            LEFT JOIN source_lineage lineage ON lineage.item_id = item.id\n                            LEFT JOIN source_affiliation affiliation\n                              ON affiliation.source_id = item.source_id\n                            LEFT JOIN score_set score_set\n                              ON score_set.item_id = item.id AND score_set.is_current\n                            LEFT JOIN score_dimension dimension\n                              ON dimension.score_set_id = score_set.id\n                            LEFT JOIN LATERAL (\n                              SELECT candidate.score FROM score_override candidate\n                              WHERE candidate.score_dimension_id = dimension.id\n                              ORDER BY candidate.reviewed_at DESC, candidate.id DESC LIMIT 1\n                            ) override ON true\n                            WHERE topic.status = 'CONFIRMED'\n                              AND (\n                                CAST(:domain AS text) IS NULL\n                                OR topic.domain = CAST(:domain AS text)\n                              )\n                              AND item.activity_at >= now() - make_interval(days => :window_days)\n                            GROUP BY topic.id, topic.title, topic.domain\n                            )\n                            SELECT * FROM topics\n                            WHERE CAST(:cursor_heat AS integer) IS NULL\n                               OR heat_score < CAST(:cursor_heat AS integer)\n                               OR (heat_score = CAST(:cursor_heat AS integer)\n                                   AND latest_activity_at < CAST(:cursor_time AS timestamptz))\n                               OR (heat_score = CAST(:cursor_heat AS integer)\n                                   AND latest_activity_at = CAST(:cursor_time AS timestamptz)\n                                   AND id > CAST(:cursor_id AS uuid))\n                            ORDER BY heat_score DESC, latest_activity_at DESC, id\n                            LIMIT :limit\n                            "
                        ),
                        {
                            "domain": domain,
                            "window_days": window_days,
                            "cursor_heat": cursor_heat,
                            "cursor_time": cursor_time,
                            "cursor_id": cursor_id,
                            "limit": limit + 1,
                        },
                    )
                ).mappings()
            )
        visible = rows[:limit]
        next_cursor = None
        if len(rows) > limit and visible:
            last = visible[-1]
            next_cursor = _encode_hot_cursor(
                int(last["heat_score"]),
                cast(datetime, last["latest_activity_at"]),
                cast(UUID, last["id"]),
                domain=domain,
                window_days=window_days,
            )
        return HotTopicPage(
            items=[
                HotTopicSummary(
                    id=row["id"],
                    title=row["title"],
                    domain=row["domain"],
                    heat_score=row["heat_score"],
                    event_count=row["event_count"],
                    independent_source_count=row["independent_source_count"],
                    latest_activity_at=row["latest_activity_at"],
                    rule_version="scoring-v1.0.0",
                )
                for row in visible
            ],
            next_cursor=next_cursor,
            generated_at=datetime.now(UTC),
            evaluation_tier="INTERNAL_TEST_FIXTURE",
            auto_merge_enabled=False,
        )

    async def get_source_comparison(self, event_id: UUID) -> SourceComparison:
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT item.id AS item_id, source.name AS source_name,\n                                   COALESCE(affiliation.organization_key, source.id::text)\n                                     AS organization_key,\n                                   COALESCE(lineage.lineage_root, source.id::text)\n                                     AS lineage_root,\n                                   COALESCE(lineage.role, 'INDEPENDENT_REPORT') AS role,\n                                   item.source_published_at, item.original_url,\n                                   (SELECT count(*) FROM claim\n                                    WHERE claim.item_id = item.id\n                                      AND claim.verification_status = 'ACCEPTED')\n                                     AS accepted_claim_count,\n                                   (SELECT count(*) FROM claim_evidence evidence\n                                    JOIN claim ON claim.id = evidence.claim_id\n                                    WHERE claim.item_id = item.id\n                                      AND claim.verification_status = 'ACCEPTED')\n                                     AS evidence_count\n                            FROM event_item membership\n                            JOIN intelligence_item item ON item.id = membership.item_id\n                            JOIN source ON source.id = item.source_id\n                            JOIN publication ON publication.item_id = item.id\n                              AND publication.status = 'PUBLISHED'\n                            LEFT JOIN source_affiliation affiliation\n                              ON affiliation.source_id = source.id\n                            LEFT JOIN source_lineage lineage ON lineage.item_id = item.id\n                            WHERE membership.event_id = :event_id\n                              AND item.review_status = 'APPROVED'\n                            ORDER BY lineage_root, item.source_published_at, item.id\n                            "
                        ),
                        {"event_id": event_id},
                    )
                ).mappings()
            )
        sources = [SourceComparisonEntry(**dict(row)) for row in rows]
        independent = {
            (entry.lineage_root, entry.organization_key)
            for entry in sources
            if entry.role.value in {"ORIGINAL", "INDEPENDENT_REPORT"}
        }
        return SourceComparison(
            event_id=event_id, independent_source_count=len(independent), sources=sources
        )

    async def get_versions(
        self, item_id: UUID, *, include_restricted: bool
    ) -> VersionTimelineResponse:
        async with self._engine.connect() as connection:
            await _assert_item_projection_allowed(
                connection, item_id=item_id, include_restricted=include_restricted
            )
            rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT v.id, v.version_number, v.acquired_at,\n                                   i.current_document_version_id = v.id AS is_current,\n                                   COALESCE(state.state, 'READY') AS processing_state,\n                                   COALESCE(change_state.change_type, change.change_type, 'INITIAL')\n                                       AS change_type,\n                                   COALESCE(change_state.material, change.material, true)\n                                       AS material,\n                                   COALESCE(\n                                       change_state.state,\n                                       change.review_state,\n                                       'RE_REVIEW_PENDING'\n                                   )\n                                       AS review_state\n                            FROM intelligence_item i\n                            JOIN document_version v ON v.document_id = i.primary_document_id\n                            LEFT JOIN LATERAL (\n                                SELECT event.state\n                                FROM document_version_state_event event\n                                WHERE event.document_version_id = v.id\n                                ORDER BY event.created_at DESC, event.id DESC LIMIT 1\n                            ) state ON true\n                            LEFT JOIN version_change change\n                              ON change.to_document_version_id = v.id\n                            LEFT JOIN LATERAL (\n                                SELECT event.state, event.change_type, event.material\n                                FROM version_change_state_event event\n                                WHERE event.version_change_id = change.id\n                                ORDER BY event.created_at DESC, event.id DESC LIMIT 1\n                            ) change_state ON true\n                            WHERE i.id = :item_id\n                            ORDER BY v.version_number, v.id\n                            "
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
        self, item_id: UUID, *, from_version_id: UUID, to_version_id: UUID, include_restricted: bool
    ) -> VersionDiffResponse:
        async with self._engine.connect() as connection:
            await _assert_item_projection_allowed(
                connection, item_id=item_id, include_restricted=include_restricted
            )
            change = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT COALESCE(state.change_type, change.change_type) AS change_type,\n                                   COALESCE(state.material, change.material) AS material,\n                                   changed_token_count,\n                                   changed_token_ratio_bps, critical_field_diffs\n                            FROM version_change change\n                            JOIN intelligence_item item\n                              ON item.primary_document_id = change.document_id\n                            LEFT JOIN LATERAL (\n                                SELECT event.change_type, event.material\n                                FROM version_change_state_event event\n                                WHERE event.version_change_id = change.id\n                                ORDER BY event.created_at DESC, event.id DESC LIMIT 1\n                            ) state ON true\n                            WHERE item.id = :item_id\n                              AND change.from_document_version_id = :from_version_id\n                              AND change.to_document_version_id = :to_version_id\n                            "
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
                    field=value["field"], before=value.get("before"), after=value.get("after")
                )
                for value in critical
                if isinstance(value, Mapping) and "field" in value
            ],
        )

    async def get_document_page(
        self, document_version_id: UUID, page_number: int, *, include_restricted: bool
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
            preview_url=f"/api/v1/document-versions/{document_version_id}/pages/{page_number}/preview",
        )

    async def get_page_preview(
        self, document_version_id: UUID, page_number: int, *, include_restricted: bool
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
        return (content, row["preview_sha256"])


async def _assert_item_projection_allowed(
    connection: AsyncConnection, *, item_id: UUID, include_restricted: bool
) -> None:
    row = (
        (
            await connection.execute(
                text(
                    "\n                    SELECT i.review_status, p.status AS publication_status\n                    FROM intelligence_item i\n                    LEFT JOIN publication p ON p.item_id = i.id\n                    WHERE i.id = :item_id\n                    "
                ),
                {"item_id": item_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise IntelligenceNotFound("intelligence item does not exist")
    if not include_restricted and (
        not (
            row["review_status"] == "APPROVED"
            and row["publication_status"] in {"PUBLISHED", "WITHDRAWN"}
        )
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
                    "\n                    SELECT page.page_number, page.width_mpt, page.height_mpt,\n                           page.rotation, page.text_source, page.preview_object_key,\n                           page.preview_sha256,\n                           (\n                               SELECT count(*)\n                               FROM document_page all_pages\n                               WHERE all_pages.document_version_id = page.document_version_id\n                           ) AS page_count,\n                           item.review_status, publication.status AS publication_status\n                    FROM document_page page\n                    JOIN intelligence_item item\n                      ON item.primary_document_id = (\n                          SELECT version.document_id FROM document_version version\n                          WHERE version.id = page.document_version_id\n                      )\n                    LEFT JOIN publication ON publication.item_id = item.id\n                    WHERE page.document_version_id = :version_id\n                      AND page.page_number = :page_number\n                    "
                ),
                {"version_id": document_version_id, "page_number": page_number},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise IntelligenceNotFound("document page does not exist")
    if not include_restricted and (
        not (
            row["review_status"] == "APPROVED"
            and row["publication_status"] in {"PUBLISHED", "WITHDRAWN"}
        )
    ):
        raise IntelligenceNotFound("document page is not available in this projection")
    return row


async def _version_page_text(
    connection: AsyncConnection, document_version_id: UUID
) -> dict[int, dict[str, str]]:
    rows = list(
        (
            await connection.execute(
                text(
                    "\n                    SELECT page.page_number, block.block_kind, block.normalized_text\n                    FROM document_page page\n                    JOIN document_text_block block ON block.document_page_id = page.id\n                    WHERE page.document_version_id = :version_id\n                    ORDER BY page.page_number, block.block_index\n                    "
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
        page_number: {"margin": "\n".join(value["margin"]), "body": "\n".join(value["body"])}
        for page_number, value in pages.items()
    }


def _page_diffs(
    before: dict[int, dict[str, str]], after: dict[int, dict[str, str]]
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
                before=" ".join(before_words[old_start:old_end]) or None,
                after=" ".join(after_words[new_start:new_end]) or None,
            )
        )
    return result


async def _item_row(
    connection: AsyncConnection, item_id: UUID, *, include_unpublished: bool
) -> RowMapping | None:
    result = await connection.execute(
        text(
            "\n            SELECT i.id, i.item_type, i.title, i.original_url, i.source_published_at,\n                   i.first_discovered_at, i.activity_at, i.updated_at,\n                   i.review_status, s.name AS source_name,\n                   p.status AS publication_status,\n                   p.current_revision_id AS publication_revision_id,\n                   current_revision.revision_number,\n                   current_revision.action AS revision_action,\n                   current_revision.created_at AS revision_created_at,\n                   CASE WHEN current_revision.action = 'WITHDRAW'\n                        THEN current_revision.created_at ELSE NULL END AS revision_withdrawn_at,\n                   ai.run_id AS ai_pipeline_run_id,\n                   ai.prompt_version AS ai_prompt_version,\n                   ai.schema_version AS ai_schema_version,\n                   ai.model_profile AS ai_model_profile,\n                   ai.generated_at AS ai_generated_at,\n                   ai.one_sentence_fact,\n                   COALESCE(ai.accepted_claims_only, false) AS ai_accepted_claims_only,\n                   r.classification, r.document_number, r.issuing_authority,\n                   r.regulation_status,\n                   case_profile.report_stage,\n                   case_profile.accident_type,\n                   case_profile.engineering_type,\n                   case_profile.occurred_at,\n                   case_profile.region_name,\n                   case_profile.deaths,\n                   case_profile.injuries,\n                   case_profile.loss_amount_minor,\n                   case_profile.loss_currency,\n                   case_profile.incident_status,\n                   case_profile.official_direct_causes,\n                   case_profile.responsibility_findings,\n                   case_profile.rectification_has_open_issues,\n                   case_profile.similar_scenario_tags,\n                   case_profile.prevention_measure_tags,\n                   digital_profile.source_nature,\n                   digital_profile.maturity_level,\n                   digital_profile.deployment_scale,\n                   digital_profile.applicability,\n                   digital_profile.replication_conditions,\n                   digital_profile.limitations,\n                   digital_profile.risks,\n                   digital_profile.srbg_relationship,\n                   digital_relevance.score AS relevance_score,\n                   digital_relevance.rule_version AS relevance_rule_version,\n                   digital_relevance.engineering_points,\n                   digital_relevance.sichuan_points,\n                   digital_relevance.srbg_direct_points,\n                   digital_taxonomy.engineering_domains,\n                   digital_taxonomy.lifecycle_stages,\n                   digital_taxonomy.technology_tags,\n                   digital_taxonomy.application_scenarios,\n                   paper_profile.normalized_doi,\n                   paper_profile.journal,\n                   paper_profile.issns,\n                   paper_profile.volume,\n                   paper_profile.issue,\n                   paper_profile.pages,\n                   paper_profile.publication_year,\n                   paper_profile.paper_type,\n                   paper_profile.access_level,\n                   paper_profile.open_status,\n                   paper_profile.open_fulltext_url,\n                   paper_profile.abstract,\n                   paper_profile.abstract_availability,\n                   paper_profile.keywords,\n                   paper_profile.maturity_level AS paper_maturity_level,\n                   paper_profile.research_interpretation,\n                   paper_profile.relation_status,\n                   paper_taxonomy.engineering_domains AS paper_engineering_domains,\n                   paper_taxonomy.technology_tags AS paper_technology_tags,\n                   product_profile.item_type AS product_item_type,\n                   product_profile.evidence_level,\n                   product_profile.permit_status,\n                   product_profile.maturity_level AS product_maturity_level,\n                   product_profile.platform_type,\n                   product_profile.equipment_form,\n                   product_profile.interfaces,\n                   product_profile.deployment_modes,\n                   product_profile.connectivity,\n                   product_profile.payload_types,\n                   product_profile.ai_tasks,\n                   product_profile.limitations AS product_limitations,\n                   product_profile.production_validation,\n                   product_vendor.id AS vendor_id,\n                   product_vendor.name AS vendor_name,\n                   product.id AS product_id,\n                   product.name AS product_name,\n                   product.product_kind,\n                   product_model.id AS model_id,\n                   product_model.model_no,\n                   product_version.version,\n                   product_taxonomy.application_scenarios AS product_application_scenarios,\n                   product_capabilities.promotional_claim_count,\n                   product_capabilities.verified_capability_count,\n                   event_link.event_id,\n                   COALESCE(conflicts.fields, ARRAY[]::text[]) AS conflicted_fields,\n                   (SELECT count(*) FROM document_version version\n                    WHERE version.document_id = i.primary_document_id) AS version_count,\n                   latest_change.change_type AS latest_change_type,\n                   latest_change.review_state AS latest_change_review_state,\n                   (\n                     (SELECT url_check.outcome FROM source_url_check url_check\n                      WHERE url_check.document_id = i.primary_document_id\n                      ORDER BY url_check.checked_at DESC, url_check.id DESC LIMIT 1)\n                       IN ('NOT_FOUND','GONE')\n                     AND\n                     (SELECT url_check.outcome FROM source_url_check url_check\n                      WHERE url_check.document_id = i.primary_document_id\n                      ORDER BY url_check.checked_at DESC, url_check.id DESC LIMIT 1 OFFSET 1)\n                       IN ('NOT_FOUND','GONE')\n                   ) OR (\n                     (SELECT count(*) FROM (\n                        SELECT url_check.outcome FROM source_url_check url_check\n                        WHERE url_check.document_id = i.primary_document_id\n                        ORDER BY url_check.checked_at DESC, url_check.id DESC LIMIT 3\n                     ) recent WHERE recent.outcome IN ('TIMEOUT','SERVER_ERROR')) = 3\n                   ) AS source_unavailable,\n                   (SELECT count(*) FROM claim_evidence e\n                    JOIN claim c ON c.id = e.claim_id\n                    WHERE c.item_id = i.id\n                      AND (\n                        c.verification_status = 'ACCEPTED'\n                        OR 'ACCEPT' = (\n                          SELECT decision.action\n                          FROM claim_field_decision decision\n                          WHERE decision.claim_id = c.id\n                          ORDER BY decision.created_at DESC, decision.id DESC\n                          LIMIT 1\n                        )\n                      )\n                       AND (\n                         i.item_type <> 'SAFETY_CASE'\n                         OR (\n                           c.verification_status = 'ACCEPTED'\n                           AND c.critical = false\n                         )\n                         OR e.id = (\n                          SELECT decision.evidence_id\n                          FROM claim_field_decision decision\n                          WHERE decision.claim_id = c.id\n                          ORDER BY decision.created_at DESC, decision.id DESC\n                          LIMIT 1\n                        )\n                      )) AS evidence_count\n            FROM intelligence_item i\n            JOIN source s ON s.id = i.source_id\n            LEFT JOIN safety_regulation_profile r ON r.item_id = i.id\n            LEFT JOIN safety_case_profile case_profile ON case_profile.item_id = i.id\n            LEFT JOIN digital_case_profile digital_profile ON digital_profile.item_id = i.id\n            LEFT JOIN digital_case_relevance digital_relevance\n              ON digital_relevance.item_id = i.id\n            LEFT JOIN paper_profile ON paper_profile.item_id = i.id\n            LEFT JOIN technology_product_profile product_profile ON product_profile.item_id = i.id\n            LEFT JOIN technology_product_version product_version\n              ON product_version.id = product_profile.version_id\n            LEFT JOIN technology_product_model product_model\n              ON product_model.id = product_version.model_id\n            LEFT JOIN technology_product product ON product.id = product_model.product_id\n            LEFT JOIN technology_vendor product_vendor ON product_vendor.id = product.vendor_id\n            LEFT JOIN LATERAL (\n              SELECT\n                COALESCE(array_agg(code ORDER BY code)\n                  FILTER (WHERE facet = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])\n                  AS engineering_domains,\n                COALESCE(array_agg(code ORDER BY code)\n                  FILTER (WHERE facet = 'LIFECYCLE_STAGE'), ARRAY[]::text[])\n                  AS lifecycle_stages,\n                COALESCE(array_agg(code ORDER BY code)\n                  FILTER (WHERE facet = 'TECHNOLOGY_TAG'), ARRAY[]::text[])\n                  AS technology_tags,\n                COALESCE(array_agg(code ORDER BY code)\n                  FILTER (WHERE facet = 'APPLICATION_SCENARIO'), ARRAY[]::text[])\n                  AS application_scenarios\n              FROM digital_case_taxonomy\n              WHERE item_id = i.id\n            ) digital_taxonomy ON true\n            LEFT JOIN LATERAL (\n              SELECT\n                COALESCE(array_agg(code ORDER BY code)\n                  FILTER (WHERE dimension = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])\n                  AS engineering_domains,\n                COALESCE(array_agg(code ORDER BY code)\n                  FILTER (WHERE dimension = 'TECHNOLOGY_TAG'), ARRAY[]::text[])\n                  AS technology_tags\n              FROM paper_taxonomy WHERE item_id = i.id\n            ) paper_taxonomy ON true\n            LEFT JOIN LATERAL (\n              SELECT COALESCE(array_agg(code ORDER BY code)\n                FILTER (WHERE dimension = 'APPLICATION_SCENARIO'), ARRAY[]::text[])\n                  AS application_scenarios\n              FROM technology_product_taxonomy WHERE item_id = i.id\n            ) product_taxonomy ON true\n            LEFT JOIN LATERAL (\n              SELECT count(*) FILTER (WHERE kind = 'PROMOTIONAL_CLAIM')\n                       AS promotional_claim_count,\n                     count(*) FILTER (WHERE kind = 'VERIFIED_CAPABILITY')\n                       AS verified_capability_count\n              FROM technology_product_capability WHERE item_id = i.id\n            ) product_capabilities ON true\n            LEFT JOIN event_item event_link ON event_link.item_id = i.id\n            LEFT JOIN publication p ON p.item_id = i.id\n            LEFT JOIN publication_revision current_revision\n              ON current_revision.id = p.current_revision_id\n            LEFT JOIN LATERAL (\n                SELECT run.id AS run_id,\n                       prompt.version AS prompt_version,\n                       schema.version AS schema_version,\n                       model.version AS model_profile,\n                       run.completed_at AS generated_at,\n                       summary.validated_output ->> 'one_sentence' AS one_sentence_fact,\n                       NOT EXISTS (\n                         SELECT 1\n                         FROM jsonb_array_elements_text(\n                           summary.validated_output -> 'used_claim_ids'\n                         ) used(claim_id)\n                         WHERE NOT EXISTS (\n                           SELECT 1 FROM claim accepted\n                           WHERE accepted.id::text = used.claim_id\n                             AND accepted.item_id = i.id\n                             AND accepted.verification_status = 'ACCEPTED'\n                         )\n                       ) AS accepted_claims_only\n                FROM ai_pipeline_run run\n                JOIN LATERAL (\n                  SELECT step.* FROM ai_step_run step\n                  WHERE step.pipeline_run_id = run.id AND step.step = 'SUMMARIZE'\n                    AND step.status = 'SUCCEEDED'\n                  ORDER BY step.attempt DESC LIMIT 1\n                ) summary ON true\n                JOIN ai_prompt_version prompt ON prompt.id = summary.prompt_version_id\n                JOIN ai_schema_version schema ON schema.id = summary.schema_version_id\n                JOIN ai_model_profile model ON model.id = summary.model_profile_id\n                WHERE run.document_version_id = i.current_document_version_id\n                  AND run.mode = 'LIVE' AND run.status = 'SUCCEEDED'\n                  AND (SELECT count(DISTINCT step.step) FROM ai_step_run step\n                       WHERE step.pipeline_run_id = run.id\n                         AND step.status = 'SUCCEEDED') = 4\n                ORDER BY run.completed_at DESC NULLS LAST, run.id DESC LIMIT 1\n            ) ai ON true\n            LEFT JOIN LATERAL (\n                SELECT array_agg(DISTINCT conflict.field_name) AS fields\n                FROM public_safety_case_conflict conflict\n                WHERE conflict.source_item_id = i.id\n            ) conflicts ON true\n            LEFT JOIN LATERAL (\n                SELECT COALESCE(state.change_type, change.change_type) AS change_type,\n                       COALESCE(state.state, change.review_state) AS review_state\n                FROM version_change change\n                LEFT JOIN LATERAL (\n                    SELECT event.change_type, event.state\n                    FROM version_change_state_event event\n                    WHERE event.version_change_id = change.id\n                    ORDER BY event.created_at DESC, event.id DESC LIMIT 1\n                ) state ON true\n                WHERE change.document_id = i.primary_document_id\n                ORDER BY change.created_at DESC, change.id DESC LIMIT 1\n            ) latest_change ON true\n            WHERE i.id = :item_id\n              AND (:include_unpublished OR i.risk_level <> 'R4')\n              AND (\n                (i.item_type = 'SAFETY_REGULATION' AND r.item_id IS NOT NULL)\n                OR\n                (i.item_type = 'SAFETY_CASE' AND case_profile.item_id IS NOT NULL)\n                OR\n                (i.item_type = 'DIGITAL_CASE' AND digital_profile.item_id IS NOT NULL\n                  AND digital_relevance.item_id IS NOT NULL)\n                OR\n                (i.item_type = 'JOURNAL_PAPER' AND paper_profile.item_id IS NOT NULL)\n                OR\n                (i.item_type IN ('SOFTWARE_PRODUCT','IOT_PRODUCT',\n                                 'LOW_ALTITUDE_EQUIPMENT','AI_EQUIPMENT')\n                 AND product_profile.item_id IS NOT NULL)\n              )\n              AND (:include_unpublished OR i.review_status = 'PENDING'\n                   OR p.status IN ('PUBLISHED', 'WITHDRAWN'))\n            "
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
                    "\n                    SELECT capability.kind, capability.statement, capability.attribution,\n                           capability.claim_id, capability.evidence_ids,\n                           capability.independent_evidence_ids\n                    FROM technology_product_capability capability\n                    JOIN claim ON claim.id = capability.claim_id\n                    WHERE capability.item_id = :item_id\n                      AND claim.verification_status = 'ACCEPTED'\n                    ORDER BY capability.kind, capability.created_at, capability.id\n                    "
                ),
                {"item_id": row["id"]},
            )
        ).mappings()
    )
    version_history = list(
        (
            await connection.execute(
                text(
                    "\n                    SELECT version.version\n                    FROM technology_product_version version\n                    WHERE version.model_id = :model_id\n                    ORDER BY version.released_at DESC NULLS LAST,\n                             version.created_at DESC, version.id DESC\n                    "
                ),
                {"model_id": row["model_id"]},
            )
        ).scalars()
    )
    engineering_cases = list(
        (
            await connection.execute(
                text(
                    "\n                    SELECT target.id AS item_id, target.title,\n                           candidate.evidence_ids\n                    FROM item_relation relation\n                    JOIN item_relation_candidate candidate ON candidate.id = relation.candidate_id\n                    JOIN intelligence_item target ON target.id = relation.target_item_id\n                    JOIN publication ON publication.item_id = target.id\n                      AND publication.status = 'PUBLISHED'\n                    WHERE relation.source_item_id = :item_id\n                      AND relation.relation_type = 'APPLIED_IN'\n                      AND target.item_type = 'DIGITAL_CASE'\n                      AND target.review_status = 'APPROVED'\n                    ORDER BY target.activity_at DESC, target.id DESC\n                    "
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
        model=ProductEntity(id=row["model_id"], name=row["model_no"] or "型号未知")
        if row.get("model_id")
        else None,
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
        low_altitude_notice="产品发布不代表空域、适航、飞手和项目许可。"
        if is_low_altitude
        else None,
    )


def _item_summary(
    row: RowMapping | Mapping[str, Any], *, reviewer_projection: bool = False
) -> ItemSummary:
    states = _document_states(row)
    item_type = ItemType(str(row.get("item_type", ItemType.SAFETY_REGULATION.value)))
    event_id = row.get("event_id") if row.get("event_type") is not None else None
    summary_model = EventSummary if event_id is not None else ItemSummary
    identity: dict[str, Any] = {}
    if event_id is not None:
        identity = {
            "event_type": EventType(str(row["event_type"])),
            "event_status": EventStatus(str(row["event_status"])),
            "canonical_event_id": row["canonical_event_id"],
            "event_version": int(row["event_version"]),
        }
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
        and (not reviewer_projection)
    ):
        hints: dict[str, Any] = {}
        if states:
            hints["document_states"] = states
        if row["version_count"] > 1:
            hints["has_version_history"] = True
        return summary_model(
            id=event_id or row["id"],
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
            **identity,
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
            publisher_claim_label="厂商声明，未经独立验证"
            if row["source_nature"] == "ENTERPRISE_SELF_REPORT"
            else "政府/行业案例汇编",
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
                        code="SICHUAN", label="四川实施", points=int(row["sichuan_points"])
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
                row.get("product_application_scenarios", row.get("application_scenarios", [])) or []
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
            loss_amount_minor=None
            if "loss_amount_minor" in hidden_fields
            else row.get("loss_amount_minor"),
            loss_currency=None
            if "loss_amount_minor" in hidden_fields
            else row.get("loss_currency"),
            conflicted_fields=conflicted_fields or None,
            official_direct_causes=None
            if "official_direct_causes" in hidden_fields
            else row.get("official_direct_causes"),
            responsibility_findings=None
            if "responsibility_findings" in hidden_fields
            else row.get("responsibility_findings"),
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
    return summary_model(
        id=event_id or row["id"],
        publication_revision_id=row["publication_revision_id"] if published else None,
        domain=Channel.DIGITAL
        if item_type in {ItemType.DIGITAL_CASE, ItemType.JOURNAL_PAPER, *product_types}
        else Channel.SAFETY,
        content_type=item_type,
        title=row["title"],
        source_name=row["source_name"],
        source_published_at=row["source_published_at"],
        first_discovered_at=row["first_discovered_at"],
        activity_at=row["activity_at"],
        original_url=row["original_url"],
        review_status=ReviewStatus(row["review_status"]),
        one_sentence_fact=str(row["one_sentence_fact"])
        if row.get("one_sentence_fact") and row.get("ai_accepted_claims_only") is True
        else None,
        source_role="企业自述"
        if item_type is ItemType.DIGITAL_CASE
        and row.get("source_nature") == "ENTERPRISE_SELF_REPORT"
        else "政府/行业案例源"
        if item_type is ItemType.DIGITAL_CASE
        else "开放学术元数据"
        if item_type is ItemType.JOURNAL_PAPER
        else "厂商一手来源"
        if item_type in product_types
        else "官方一手来源",
        last_updated_at=row["updated_at"],
        publication_status=PublicationStatus.WITHDRAWN
        if withdrawn
        else PublicationStatus.PUBLISHED
        if published
        else PublicationStatus.PENDING_REVIEW,
        evidence_status=EvidenceStatus.VERIFIED if published else EvidenceStatus.WITHHELD,
        evidence_count=row["evidence_count"],
        tags=tags,
        type_summary=type_summary,
        detail_available=True,
        document_states=states or None,
        has_version_history=row["version_count"] > 1 or None,
        ai_assistance=AiAssistance(
            status="ASSISTED" if row.get("ai_pipeline_run_id") else "DEGRADED",
            pipeline_run_id=row.get("ai_pipeline_run_id"),
            prompt_version=row.get("ai_prompt_version"),
            schema_version=row.get("ai_schema_version"),
            model_profile=row.get("ai_model_profile"),
            generated_at=row.get("ai_generated_at"),
            accepted_claims_only=row.get("ai_accepted_claims_only") is True,
        )
        if "ai_pipeline_run_id" in row
        else None,
        revision_state=PublicationRevisionState(
            revision_number=int(row["revision_number"]),
            action=cast(
                Literal["PUBLISH", "REVISE", "WITHDRAW", "REPUBLISH"], str(row["revision_action"])
            ),
            created_at=row["revision_created_at"],
            withdrawn_at=row.get("revision_withdrawn_at"),
        )
        if row.get("revision_number") is not None
        else None,
        **identity,
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


def _document_states(row: RowMapping | Mapping[str, Any]) -> list[DocumentState]:
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


async def _digital_case_detail(connection: AsyncConnection, row: RowMapping) -> DigitalCaseDetail:
    entity_rows = list(
        (
            await connection.execute(
                text(
                    "\n                    SELECT entity.id, entity.entity_type, entity.name,\n                           relation.relation_type, relation.claim_id\n                    FROM digital_case_entity_relation relation\n                    JOIN digital_case_entity entity ON entity.id = relation.entity_id\n                    WHERE relation.item_id = :item_id\n                    ORDER BY entity.entity_type, entity.name, entity.id\n                    "
                ),
                {"item_id": row["id"]},
            )
        ).mappings()
    )
    outcome_rows = list(
        (
            await connection.execute(
                text(
                    "\n                    SELECT outcome.id, outcome.statement, outcome.metric_name,\n                           outcome.numeric_value, outcome.unit, outcome.outcome_kind,\n                           outcome.evidence_ids, outcome.independent_evidence_ids,\n                           entity.name AS attribution\n                    FROM digital_case_outcome outcome\n                    JOIN digital_case_entity entity\n                      ON entity.id = outcome.attribution_entity_id\n                    WHERE outcome.item_id = :item_id\n                    ORDER BY outcome.created_at, outcome.id\n                    "
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
            numeric_value=format(outcome["numeric_value"], "f")
            if outcome["numeric_value"] is not None
            else None,
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
                    "\n                    SELECT author.name, author.orcid,\n                           COALESCE(array_agg(DISTINCT institution.name ORDER BY institution.name)\n                             FILTER (WHERE institution.id IS NOT NULL), ARRAY[]::text[])\n                             AS institutions\n                    FROM paper_authorship authorship\n                    JOIN paper_author author ON author.id = authorship.author_id\n                    LEFT JOIN paper_author_affiliation affiliation\n                      ON affiliation.item_id = authorship.item_id\n                     AND affiliation.author_id = authorship.author_id\n                    LEFT JOIN paper_institution institution\n                      ON institution.id = affiliation.institution_id\n                    WHERE authorship.item_id = :item_id\n                    GROUP BY author.id, author.name, author.orcid, authorship.author_order\n                    ORDER BY authorship.author_order\n                    "
                ),
                {"item_id": row["id"]},
            )
        ).mappings()
    )
    similar_rows = list(
        (
            await connection.execute(
                text(
                    "\n                    SELECT item.id, item.title, profile.journal, profile.publication_year,\n                           taxonomy.engineering_domains, taxonomy.technology_tags\n                    FROM intelligence_item item\n                    JOIN paper_profile profile ON profile.item_id = item.id\n                    JOIN publication ON publication.item_id = item.id\n                      AND publication.status = 'PUBLISHED'\n                    JOIN LATERAL (\n                      SELECT\n                        COALESCE(array_agg(code ORDER BY code)\n                          FILTER (WHERE dimension = 'ENGINEERING_DOMAIN'), ARRAY[]::text[])\n                          AS engineering_domains,\n                        COALESCE(array_agg(code ORDER BY code)\n                          FILTER (WHERE dimension = 'TECHNOLOGY_TAG'), ARRAY[]::text[])\n                          AS technology_tags\n                      FROM paper_taxonomy WHERE item_id = item.id\n                    ) taxonomy ON true\n                    WHERE item.id <> :item_id\n                      AND item.item_type = 'JOURNAL_PAPER'\n                      AND item.risk_level <> 'R4'\n                      AND item.review_status = 'APPROVED'\n                      AND (\n                        taxonomy.engineering_domains && CAST(:engineering_domains AS text[])\n                        OR taxonomy.technology_tags && CAST(:technology_tags AS text[])\n                      )\n                    ORDER BY\n                      cardinality(ARRAY(\n                        SELECT unnest(taxonomy.engineering_domains)\n                        INTERSECT SELECT unnest(CAST(:engineering_domains AS text[]))\n                      )) DESC,\n                      cardinality(ARRAY(\n                        SELECT unnest(taxonomy.technology_tags)\n                        INTERSECT SELECT unnest(CAST(:technology_tags AS text[]))\n                      )) DESC,\n                      item.activity_at DESC, item.id\n                    LIMIT 5\n                    "
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
        research_interpretation=ResearchInterpretation.model_validate(interpretation)
        if interpretation
        else None,
        similar_papers=similar,
        relation_status=PaperRelationStatus(str(row["relation_status"])),
    )


def _none_for_all(value: str | None) -> str | None:
    return None if value in {None, "", "all"} else value


def _personal_event_projection(row: RowMapping, judgment_rows: list[RowMapping]) -> EventDetail:
    facts = list(row["evidence_facts"] or [])
    claims: list[PublishedClaimV1] = []
    evidence: list[PublishedEvidenceReferenceV1] = []
    seen_evidence: set[UUID] = set()
    for fact in facts:
        refs = list(fact.get("evidence") or [])
        ids = [UUID(str(ref["evidence_id"])) for ref in refs]
        claims.append(
            PublishedClaimV1(
                claim_id=UUID(str(fact["claim_id"])),
                field_name=str(fact["field_name"]),
                value=fact["value"]
                if isinstance(fact["value"], str)
                else json.dumps(fact["value"], ensure_ascii=False),
                evidence_ids=ids,
                fact_kind="EVIDENCE_FACT",
            )
        )
        for ref, evidence_id in zip(refs, ids, strict=True):
            if evidence_id in seen_evidence:
                continue
            seen_evidence.add(evidence_id)
            evidence.append(
                PublishedEvidenceReferenceV1(
                    evidence_id=evidence_id,
                    locator=str(ref["locator"]),
                    content_sha256=str(ref["excerpt_sha256"]),
                )
            )
    grouped: dict[UUID, dict[str, Any]] = {}
    for judgment in judgment_rows:
        judgment_id = cast(UUID, judgment["id"])
        value = grouped.setdefault(judgment_id, {"row": judgment, "evidence": []})
        if judgment["evidence_id"] is not None:
            value["evidence"].append(
                AiJudgmentEvidencePreview(
                    evidence_id=judgment["evidence_id"],
                    excerpt=judgment["excerpt"],
                    excerpt_sha256=judgment["excerpt_sha256"],
                    locator=judgment["locator"],
                )
            )
    judgments = [
        AiJudgmentPreview(
            id=judgment_id,
            document_version_id=value["row"]["document_version_id"],
            field_name=value["row"]["field_name"],
            value=value["row"]["candidate_value"]
            if isinstance(value["row"]["candidate_value"], str)
            else json.dumps(value["row"]["candidate_value"], ensure_ascii=False),
            confidence_bps=value["row"]["confidence_bps"],
            attribution=value["row"]["attribution"],
            reason_codes=list(value["row"]["reason_codes"]),
            rule_version=value["row"]["rule_version"],
            evidence=value["evidence"],
        )
        for judgment_id, value in grouped.items()
    ]
    return EventDetail(
        id=row["id"],
        title=row["title"],
        event_type=row["event_type"],
        project_name=row["project_name"],
        occurred_at=row["occurred_at"],
        region=row["region_name"],
        confirmed_facts=[],
        unverified_facts=[],
        timeline=EventTimeline(
            event_id=row["id"],
            items=[
                EventItem(
                    item_id=row["item_id"],
                    title=row["title"],
                    source_name=row["source_name"],
                    source_published_at=row["source_published_at"],
                    original_url=row["original_url"],
                    review_status=row["review_status"],
                    publication_revision_id=None,
                    evidence_count=len(evidence),
                )
            ],
        ),
        relations=[],
        similar_scenario_tags=[],
        prevention_measure_tags=[],
        claims=claims,
        evidence=evidence,
        ai_judgments=judgments,
    )


async def _claims_and_evidence(
    connection: AsyncConnection, item_id: UUID, *, include_candidates: bool = False
) -> tuple[list[ClaimView], list[EvidenceView]]:
    rows = list(
        (
            await connection.execute(
                text(
                    "\n                    SELECT c.id AS claim_id, c.claim_type, c.literal_value,\n                           c.document_version_id, c.verification_status, c.critical,\n                           e.id AS evidence_id, e.paragraph_id, e.char_start,\n                           e.char_end, e.excerpt, e.excerpt_sha256, e.original_url,\n                           e.locator_type, e.page_number, e.document_text_block_id,\n                           e.document_table_cell_id, e.x0_mpt, e.y0_mpt,\n                           e.x1_mpt, e.y1_mpt, e.confidence_bps,\n                           cell.row_index, cell.column_index,\n                           latest_decision.action AS field_decision_action,\n                           ai_decision.action AS ai_decision_action,\n                           latest_decision.evidence_id AS field_decision_evidence_id\n                    FROM claim c\n                    JOIN claim_evidence e ON e.claim_id = c.id\n                    JOIN intelligence_item i ON i.id = c.item_id\n                    LEFT JOIN document_table_cell cell\n                      ON cell.id = e.document_table_cell_id\n                    LEFT JOIN LATERAL (\n                        SELECT decision.action, decision.evidence_id\n                        FROM claim_field_decision decision\n                        WHERE decision.claim_id = c.id\n                        ORDER BY decision.created_at DESC, decision.id DESC\n                        LIMIT 1\n                    ) latest_decision ON true\n                    LEFT JOIN ai_claim_review_decision ai_decision\n                      ON ai_decision.claim_id = c.id\n                    WHERE c.item_id = :item_id\n                      AND c.document_version_id = i.current_document_version_id\n                      AND (\n                        (\n                          :include_candidates\n                          AND (\n                            (\n                              i.item_type = 'SAFETY_CASE'\n                              AND c.claim_type IN (\n                                'deaths','injuries','loss_amount_minor',\n                                'official_direct_causes','responsibility_findings'\n                              )\n                            )\n                            OR EXISTS(\n                              SELECT 1 FROM ai_candidate_claim_origin origin\n                              WHERE origin.claim_id=c.id\n                            )\n                          )\n                        )\n                        OR c.verification_status = 'ACCEPTED'\n                        OR latest_decision.action = 'ACCEPT'\n                        OR ai_decision.action = 'ACCEPT'\n                      )\n                      AND (\n                        i.item_type <> 'SAFETY_CASE'\n                        OR :include_candidates\n                        OR (\n                          c.verification_status = 'ACCEPTED'\n                          AND c.critical = false\n                        )\n                        OR e.id = latest_decision.evidence_id\n                      )\n                      AND (\n                        i.item_type <> 'SAFETY_CASE'\n                        OR :include_candidates\n                        OR (\n                          c.verification_status = 'ACCEPTED'\n                          AND c.critical = false\n                        )\n                        OR EXISTS (\n                          SELECT 1\n                          FROM public_safety_case_accepted_claim effective\n                          WHERE effective.claim_id = c.id\n                            AND effective.evidence_id = e.id\n                        )\n                      )\n                    ORDER BY c.created_at, c.id, e.created_at, e.id\n                    "
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
                decision_status=_claim_decision_status(
                    row["ai_decision_action"] or row["field_decision_action"],
                    verification_status=row["verification_status"],
                    critical=row["critical"],
                )
                if include_candidates
                else None,
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
    return (claims, evidence)


def _claim_decision_status(
    action: object, *, verification_status: object, critical: object
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
            field_name, row["literal_value"], loss_currency=row["loss_currency"]
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
    field_name: str, value: object, *, loss_currency: object = None
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
    rendered = f"# TYPE srbg_safety_event_candidates_pending gauge\nsrbg_safety_event_candidates_pending {pending_event_candidates}\n# TYPE srbg_safety_critical_claims_pending gauge\nsrbg_safety_critical_claims_pending {pending_critical_claims}\n# TYPE srbg_safety_case_items gauge\n"
    for profile in profiles:
        rendered += f'''srbg_safety_case_items{{report_stage="{profile["report_stage"]}",incident_status="{profile["incident_status"]}"}} {profile["count"]}\n'''
    rendered += "# TYPE srbg_safety_claim_conflicts_pending gauge\n"
    for conflict in conflicts:
        rendered += f'''srbg_safety_claim_conflicts_pending{{field_name="{conflict["field_name"]}"}} {conflict["count"]}\n'''
    return rendered


def _render_digital_case_metrics(
    *,
    profiles: list[Mapping[str, Any]],
    outcomes: Mapping[str, int],
    pending_enterprise_review: int,
) -> str:
    rendered = "# TYPE srbg_digital_case_items gauge\n"
    for profile in profiles:
        rendered += f'''srbg_digital_case_items{{source_nature="{profile["source_nature"]}",maturity_level="{profile["maturity_level"]}"}} {profile["count"]}\n'''
    rendered += "# TYPE srbg_digital_case_outcomes gauge\n"
    for verification in ("CLAIMED", "VERIFIED"):
        rendered += f'srbg_digital_case_outcomes{{verification="{verification}"}} {int(outcomes.get(verification, 0))}\n'
    rendered += f"# TYPE srbg_digital_enterprise_review_pending gauge\nsrbg_digital_enterprise_review_pending {pending_enterprise_review}\n"
    return rendered


def _render_paper_metrics(
    *, profiles: list[dict[str, object]], pending_duplicates: int, pending_updates: int
) -> str:
    rendered = "# TYPE srbg_papers_total gauge\n"
    for profile in profiles:
        rendered += f'''srbg_papers_total{{access_level="{profile["access_level"]}",relation_status="{profile["relation_status"]}"}} {profile["count"]}\n'''
    rendered += f"# TYPE srbg_paper_duplicate_candidates gauge\nsrbg_paper_duplicate_candidates {pending_duplicates}\n# TYPE srbg_paper_update_candidates gauge\nsrbg_paper_update_candidates {pending_updates}\n"
    return rendered


def _render_technology_product_metrics(
    *,
    profiles: list[Mapping[str, Any]],
    capabilities: Mapping[str, int],
    pending_normalization: int,
) -> str:
    rendered = "# TYPE srbg_technology_products gauge\n"
    for profile in profiles:
        rendered += f'''srbg_technology_products{{item_type="{profile["item_type"]}",evidence_level="{profile["evidence_level"]}",permit_status="{profile["permit_status"]}"}} {profile["count"]}\n'''
    rendered += "# TYPE srbg_product_capabilities gauge\n"
    for kind in ("PROMOTIONAL_CLAIM", "VERIFIED_CAPABILITY"):
        rendered += f'srbg_product_capabilities{{kind="{kind}"}} {int(capabilities.get(kind, 0))}\n'
    rendered += f"# TYPE srbg_product_normalization_pending gauge\nsrbg_product_normalization_pending {pending_normalization}\n"
    return rendered


def _render_resolution_metrics(metrics: dict[str, object]) -> str:
    names = {
        "duplicate_pending": "srbg_resolution_duplicate_candidates_pending",
        "hard_constraint_blocks": "srbg_resolution_hard_constraint_blocks_total",
        "vector_recall_candidates": "srbg_resolution_vector_recall_candidates_total",
        "topic_pending": "srbg_resolution_topic_candidates_pending",
        "scored_items": "srbg_resolution_scored_items",
        "score_overrides": "srbg_resolution_score_overrides_total",
        "cluster_splits": "srbg_resolution_cluster_splits_total",
        "cluster_merges": "srbg_resolution_cluster_merges_total",
    }
    return "".join(
        (
            f"# TYPE {metric_name} gauge\n{metric_name} {cast(int, metrics[key])}\n"
            for key, metric_name in names.items()
        )
    )


def _evidence_locator(
    row: RowMapping,
) -> PdfTextLocator | PdfOcrLocator | PdfTableCellLocator | None:
    locator_type = row["locator_type"]
    if locator_type not in {"PDF_TEXT", "PDF_OCR", "PDF_TABLE_CELL"}:
        return None
    bbox = PageBoundingBox(x0=row["x0_mpt"], y0=row["y0_mpt"], x1=row["x1_mpt"], y1=row["y1_mpt"])
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


def _feed_page(
    items: list[ItemSummary],
    *,
    now: datetime,
    mode: str,
    domain: str | None,
    next_cursor: str | None,
) -> FeedPage:
    event_items = [cast(EventSummary, item) for item in items]
    if any(not isinstance(item, EventSummary) for item in items):
        raise RuntimeError("consumer switch requires EventSummary identities")
    fingerprint = sha256(
        "|".join([mode, domain or "all", *(str(item.id) for item in items)]).encode()
    ).hexdigest()
    notices = []
    if any(item.review_status == "PENDING" for item in items):
        notices.append(_restricted_notice())
    return FeedPage(
        items=event_items,
        next_cursor=next_cursor,
        fingerprint=f"sha256:{fingerprint}",
        generated_at=now,
        freshness="fresh",
        notices=notices,
    )


def _restricted_notice() -> FeedNotice:
    return FeedNotice(
        code="R3_RESTRICTED", level="info", message="待人工审核；暂不展示高风险字段。"
    )


def _encode_cursor(activity_at: datetime, item_id: UUID) -> str:
    return _cursor_codec().encode(
        sort_values=(activity_at.isoformat(), str(item_id)), binding={"kind": "feed-v1"}
    )


def _decode_cursor(value: str | None) -> tuple[datetime | None, UUID | None]:
    if value is None:
        return (None, None)
    try:
        decoded = _cursor_codec().decode(value, binding={"kind": "feed-v1"})
        if len(decoded) != 2:
            raise ValueError
        activity_at = datetime.fromisoformat(decoded[0])
        item_id = UUID(decoded[1])
        if activity_at.tzinfo is None or item_id.version != 7:
            raise ValueError
        return (activity_at, item_id)
    except (ValueError, CursorBindingError) as exc:
        raise InvalidFeedCursor("invalid feed cursor") from exc


def _cursor_codec() -> CursorCodec:
    return CursorCodec(get_settings().cursor_signing_key.get_secret_value().encode())


def _encode_hot_cursor(
    heat: int, activity_at: datetime, topic_id: UUID, *, domain: str | None, window_days: int
) -> str:
    return _cursor_codec().encode(
        sort_values=(str(heat), activity_at.isoformat(), str(topic_id)),
        binding={"kind": "hot-v1", "domain": domain, "window_days": window_days},
    )


def _decode_hot_cursor(
    value: str | None, *, domain: str | None, window_days: int
) -> tuple[int | None, datetime | None, UUID | None]:
    if value is None:
        return (None, None, None)
    try:
        decoded = _cursor_codec().decode(
            value, binding={"kind": "hot-v1", "domain": domain, "window_days": window_days}
        )
        if len(decoded) != 3:
            raise ValueError
        activity_at = datetime.fromisoformat(decoded[1])
        topic_id = UUID(decoded[2])
        if activity_at.tzinfo is None or topic_id.version != 7:
            raise ValueError
        return (int(decoded[0]), activity_at, topic_id)
    except (ValueError, CursorBindingError) as exc:
        raise InvalidFeedCursor("invalid hot-topic cursor") from exc
