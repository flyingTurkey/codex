# ruff: noqa: E501, S608
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Never, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    AiSummaryStatusV2,
    AiSummaryV2,
    AttachmentViewV2,
    ClaimView,
    EventAppendixV2,
    EventFullProjectionV2,
    EventMetadataProjectionV2,
    EventProjectionV2,
    HotspotCandidateV2,
    HotspotReasonV2,
    IntelligenceFacetsV2,
    MediaViewV2,
    OwnerRelationshipCorrectionRequest,
    OwnerRelationshipCorrectionResponse,
    PrimaryIntelligenceType,
    SourceAttributionV2,
    SourceExcerptV2,
)

from srbg_api.identifiers import uuid7
from srbg_api.intelligence_resolution.automatic_relationships import (
    AutomaticRelationshipInput,
    RelationshipKind,
    RelationshipSuppression,
    decide_automatic_relationship,
)
from srbg_api.intelligence_v2.content_candidate_repository import (
    PostgresContentCandidateRepository,
)
from srbg_api.intelligence_v2.content_candidates import accepted_claim_set_sha256
from srbg_api.intelligence_v2.domain import (
    EvaluatedHotspotAward,
    HotspotCandidate,
    HotspotCandidateReason,
    HotspotComponentEvidence,
    HotspotSourceEvidence,
    evaluate_hotspot_candidate,
)
from srbg_api.intelligence_v2.gold_calibration import AutoPassCalibrationGrant
from srbg_api.intelligence_v2.media import projectable_download, projectable_preview
from srbg_api.observability import (
    INTELLIGENCE_V2_HOTSPOT_EVALUATIONS,
    INTELLIGENCE_V2_PUBLICATION_DECISIONS,
    PERSONAL_AUTOMATIC_RELATIONSHIPS,
    PERSONAL_RELATIONSHIP_CORRECTIONS,
    T06_AI_PROJECTION_REFRESH,
)
from srbg_api.publication.personal_signals import (
    PersonalSignalInput,
    build_personal_signal_projections,
)
from srbg_api.publication.service import PublicationDenied

logger = logging.getLogger(__name__)
_V2_PROJECTION_ADAPTER: TypeAdapter[EventProjectionV2] = TypeAdapter(EventProjectionV2)
_V2_SAFETY_FAILURE_REASONS = frozenset(
    {
        "V2_RAW_NOT_CLEAN",
        "V2_FULL_ACCEPTED_CLAIMS_MISMATCH",
        "V2_SUMMARY_ACCEPTED_CLAIMS_MISMATCH",
    }
)


def _primary_type(value: str) -> PrimaryIntelligenceType:
    aliases = {
        "DIGITAL": PrimaryIntelligenceType.DIGITAL_TRANSFORMATION,
        "SAFETY": PrimaryIntelligenceType.SAFETY_INTELLIGENCE,
        "BOTH": PrimaryIntelligenceType.INDUSTRY_UPDATE,
    }
    try:
        return PrimaryIntelligenceType(value)
    except ValueError:
        return aliases.get(value, PrimaryIntelligenceType.INDUSTRY_UPDATE)


class PostgresPublicationRepository:
    """The only repository configured with the dedicated publication writer role."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def load_auto_pass_calibration(
        self, *, corpus_version: str, rule_version: str, model_id: str, prompt_version: str
    ) -> AutoPassCalibrationGrant | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT auto_pass_threshold_bps,corpus_version,rule_version,"
                            "model_id,prompt_version,prediction_seal_sha256,fact_sha256 "
                            "FROM owner_gold_calibration_v2 calibration "
                            "WHERE EXISTS (SELECT 1 FROM owner_gold_prediction_seal_v2 seal "
                            "WHERE seal.prediction_seal_sha256=calibration.prediction_seal_sha256 "
                            "AND seal.corpus_version=calibration.corpus_version "
                            "AND seal.rule_version=calibration.rule_version "
                            "AND seal.model_id=calibration.model_id "
                            "AND seal.prompt_version=calibration.prompt_version) "
                            "AND fact_version='intelligence-v2-owner-gold-calibration-2.0.0' "
                            "AND decision='GO' AND authorizes_auto_pass=true "
                            "AND corpus_version=:corpus_version "
                            "AND rule_version=:rule_version AND model_id=:model_id "
                            "AND prompt_version=:prompt_version "
                            "ORDER BY calibrated_at DESC LIMIT 1"
                        ),
                        {
                            "corpus_version": corpus_version,
                            "rule_version": rule_version,
                            "model_id": model_id,
                            "prompt_version": prompt_version,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return AutoPassCalibrationGrant(
            threshold_bps=int(row["auto_pass_threshold_bps"]),
            corpus_version=str(row["corpus_version"]),
            rule_version=str(row["rule_version"]),
            model_id=str(row["model_id"]),
            prompt_version=str(row["prompt_version"]),
            prediction_seal_sha256=str(row["prediction_seal_sha256"]),
            fact_sha256=str(row["fact_sha256"]),
        )

    async def append_hotspot_candidate(
        self,
        *,
        event_id: UUID,
        document_version_id: UUID,
        candidate: HotspotCandidateV2,
        model: str,
        prompt_version: str,
        schema_version: str,
        input_sha256: str,
        created_at: datetime,
    ) -> UUID:
        candidate_id = uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO hotspot_candidate_v2("
                    "id,event_id,document_version_id,claim_ids,reasons,model,prompt_version,"
                    "schema_version,input_sha256,created_at) VALUES("
                    ":id,:event_id,:version_id,:claim_ids,CAST(:reasons AS jsonb),:model,"
                    ":prompt_version,:schema_version,:input_sha256,:created_at)"
                ),
                {
                    "id": candidate_id,
                    "event_id": event_id,
                    "version_id": document_version_id,
                    "claim_ids": candidate.claim_ids,
                    "reasons": json.dumps(
                        [reason.model_dump(mode="json") for reason in candidate.reasons],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "model": model,
                    "prompt_version": prompt_version,
                    "schema_version": schema_version,
                    "input_sha256": input_sha256,
                    "created_at": created_at,
                },
            )
        return candidate_id

    async def evaluate_hotspot(
        self,
        *,
        event_id: UUID,
        document_version_id: UUID,
        evaluated_at: datetime,
    ) -> EvaluatedHotspotAward:
        """Append one evaluation and optional award from current PostgreSQL facts."""

        params = {
            "event_id": event_id,
            "version_id": document_version_id,
            "evaluated_at": evaluated_at,
        }
        async with self._engine.connect() as connection:
            candidate_row = (
                (
                    await connection.execute(
                        text(
                            "SELECT candidate.id,candidate.claim_ids,candidate.reasons "
                            "FROM hotspot_candidate_v2 candidate "
                            "JOIN qualification_acceptance_v2 qualification "
                            "ON qualification.event_id=candidate.event_id "
                            "AND qualification.document_version_id=candidate.document_version_id "
                            "JOIN intelligence_item item "
                            "ON item.current_document_version_id=candidate.document_version_id "
                            "JOIN event_identity_binding binding ON binding.item_id=item.id "
                            "AND binding.event_id=candidate.event_id "
                            "WHERE candidate.event_id=:event_id "
                            "AND candidate.document_version_id=:version_id "
                            "ORDER BY candidate.created_at DESC,candidate.id DESC LIMIT 1"
                        ),
                        params,
                    )
                )
                .mappings()
                .one_or_none()
            )
            qualification_row = (
                (
                    await connection.execute(
                        text(
                            "SELECT primary_type FROM qualification_acceptance_v2 "
                            "WHERE event_id=:event_id AND document_version_id=:version_id "
                            "ORDER BY accepted_at DESC,id DESC LIMIT 1"
                        ),
                        params,
                    )
                )
                .mappings()
                .one_or_none()
            )
            score_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT dimension.dimension,COALESCE(override.score,"
                            "dimension.raw_score) AS raw_score,score.rule_version "
                            "FROM event_identity_binding binding "
                            "JOIN intelligence_item item ON item.id=binding.item_id "
                            "JOIN score_set score ON score.item_id=item.id AND score.is_current "
                            "JOIN score_dimension dimension ON dimension.score_set_id=score.id "
                            "LEFT JOIN LATERAL(SELECT value.score FROM score_override value "
                            "WHERE value.score_dimension_id=dimension.id "
                            "ORDER BY value.reviewed_at DESC,value.id DESC LIMIT 1) override ON true "
                            "WHERE binding.event_id=:event_id "
                            "AND item.current_document_version_id=:version_id"
                        ),
                        params,
                    )
                ).mappings()
            )
            source_rows = list(
                (
                    await connection.execute(
                        text(
                            "WITH members AS ("
                            "SELECT item_id FROM event_item WHERE event_id=:event_id UNION "
                            "SELECT item_id FROM event_identity_binding WHERE event_id=:event_id) "
                            "SELECT item.source_id,"
                            "COALESCE(affiliation.organization_key,item.source_id::text) "
                            "AS organization_key,"
                            "COALESCE(lineage.lineage_root,item.source_id::text) AS lineage_root,"
                            "COALESCE(lineage.role,'INDEPENDENT_REPORT') AS role,"
                            "item.source_published_at,source.source_type,"
                            "COALESCE(array_agg(DISTINCT claim.id) FILTER (WHERE claim.id IS NOT NULL),"
                            "ARRAY[]::uuid[]) AS accepted_claim_ids,"
                            "EXISTS(SELECT 1 FROM qualification_acceptance_v2 qualification "
                            "WHERE qualification.event_id=:event_id "
                            "AND qualification.document_version_id=item.current_document_version_id) "
                            "AND COALESCE((SELECT assessment.verdict='ADMIT' "
                            "FROM source_admission_assessment_v2 assessment "
                            "WHERE assessment.source_id=item.source_id "
                            "AND assessment.assessed_at<=:evaluated_at "
                            "ORDER BY assessment.assessed_at DESC,assessment.id DESC LIMIT 1),false) "
                            "AS qualified "
                            "FROM members JOIN intelligence_item item ON item.id=members.item_id "
                            "JOIN source ON source.id=item.source_id "
                            "LEFT JOIN source_affiliation affiliation ON affiliation.source_id=item.source_id "
                            "LEFT JOIN source_lineage lineage ON lineage.item_id=item.id "
                            "LEFT JOIN claim ON claim.item_id=item.id "
                            "AND claim.document_version_id=item.current_document_version_id "
                            "AND claim.verification_status='ACCEPTED' "
                            "AND EXISTS(SELECT 1 FROM claim_evidence evidence "
                            "WHERE evidence.claim_id=claim.id "
                            "AND evidence.document_version_id=item.current_document_version_id) "
                            "GROUP BY item.id,item.source_id,affiliation.organization_key,"
                            "lineage.lineage_root,lineage.role,source.source_type"
                        ),
                        params,
                    )
                ).mappings()
            )

        if candidate_row is None or qualification_row is None:
            raise PublicationDenied(("HOTSPOT_CURRENT_QUALIFIED_CANDIDATE_REQUIRED",))
        scores = {str(row["dimension"]): int(row["raw_score"]) for row in score_rows}
        required_scores = {"IMPACT", "RELEVANCE", "NOVELTY", "TIMELINESS"}
        if not required_scores.issubset(scores) or not {"AUTHORITY", "EVIDENCE"}.intersection(
            scores
        ):
            raise PublicationDenied(("HOTSPOT_CURRENT_SERVER_SCORE_FACTS_REQUIRED",))
        claim_ids = frozenset(candidate_row["claim_ids"])
        candidate = HotspotCandidate(
            claim_ids=claim_ids,
            reasons=tuple(
                HotspotCandidateReason(
                    text=str(reason["text"]),
                    claim_ids=frozenset(UUID(str(value)) for value in reason["claim_ids"]),
                )
                for reason in candidate_row["reasons"]
            ),
        )

        def scaled(dimension: str, cap: int) -> int:
            return (scores[dimension] * cap + 50) // 100

        authority_score = max(scores.get("AUTHORITY", 0), scores.get("EVIDENCE", 0))
        component_evidence = (
            HotspotComponentEvidence("impact_scope", scaled("IMPACT", 25), claim_ids),
            HotspotComponentEvidence("engineering_materiality", scaled("RELEVANCE", 25), claim_ids),
            HotspotComponentEvidence("novelty", scaled("NOVELTY", 20), claim_ids),
            HotspotComponentEvidence("urgency", scaled("TIMELINESS", 15), claim_ids),
            HotspotComponentEvidence(
                "evidence_authority", (authority_score * 15 + 50) // 100, claim_ids
            ),
        )
        sources = tuple(
            HotspotSourceEvidence(
                source_id=row["source_id"],
                organization_key=str(row["organization_key"]),
                lineage_root=str(row["lineage_root"]),
                role=row["role"],
                published_at=row["source_published_at"],
                accepted_claim_ids=frozenset(row["accepted_claim_ids"]),
                qualified=bool(row["qualified"]),
                authoritative_first_party=str(row["source_type"]).lower()
                in {"government", "official", "standards_body"},
            )
            for row in source_rows
            if row["source_published_at"] is not None
        )
        result = evaluate_hotspot_candidate(
            candidate=candidate,
            component_evidence=component_evidence,
            sources=sources,
            primary_type=_primary_type(str(qualification_row["primary_type"])),
            evaluated_at=evaluated_at,
        )
        evidence_payload = {
            "candidate_id": str(candidate_row["id"]),
            "candidate_claim_ids": sorted(str(value) for value in candidate.claim_ids),
            "raw_scores": dict(sorted(scores.items())),
            "score_rule_versions": sorted({str(row["rule_version"]) for row in score_rows}),
            "components": {
                fact.component: {
                    "points": fact.points,
                    "claim_ids": sorted(map(str, fact.claim_ids)),
                }
                for fact in component_evidence
            },
            "sources": [
                {
                    "source_id": str(source.source_id),
                    "organization_key": source.organization_key,
                    "lineage_root": source.lineage_root,
                    "role": source.role,
                    "published_at": source.published_at.isoformat(),
                    "accepted_claim_ids": sorted(map(str, source.accepted_claim_ids)),
                    "qualified": source.qualified,
                    "authoritative_first_party": source.authoritative_first_party,
                }
                for source in sources
            ],
        }
        evidence_sha256 = sha256(
            json.dumps(
                evidence_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
        evaluation_id = uuid7()
        components_payload = {
            "impact_scope": result.components.impact_scope,
            "engineering_materiality": result.components.engineering_materiality,
            "novelty": result.components.novelty,
            "urgency": result.components.urgency,
            "evidence_authority": result.components.evidence_authority,
        }
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO hotspot_evaluation_v2("
                    "id,candidate_id,event_id,document_version_id,primary_type,outcome,"
                    "trigger_path,independent_source_count,components,evaluation_inputs,score,reasons,"
                    "reason_codes,rule_version,evidence_sha256,evaluated_at) VALUES("
                    ":id,:candidate_id,:event_id,:version_id,:primary_type,:outcome,:trigger,"
                    ":source_count,CAST(:components AS jsonb),CAST(:evaluation_inputs AS jsonb),"
                    ":score,:reasons,:reason_codes,"
                    ":rule_version,:evidence_sha256,:evaluated_at)"
                ),
                {
                    "id": evaluation_id,
                    "candidate_id": candidate_row["id"],
                    "event_id": event_id,
                    "version_id": document_version_id,
                    "primary_type": result.primary_type.value,
                    "outcome": "AWARDED" if result.awarded else "REJECTED",
                    "trigger": result.trigger,
                    "source_count": result.independent_source_count,
                    "components": json.dumps(components_payload, sort_keys=True),
                    "evaluation_inputs": json.dumps(
                        evidence_payload, sort_keys=True, separators=(",", ":")
                    ),
                    "score": result.score,
                    "reasons": list(result.reasons),
                    "reason_codes": list(result.reason_codes),
                    "rule_version": result.rule_version,
                    "evidence_sha256": evidence_sha256,
                    "evaluated_at": evaluated_at,
                },
            )
            if result.awarded:
                await connection.execute(
                    text(
                        "INSERT INTO hotspot_award_v2("
                        "id,event_id,trigger_path,independent_source_count,components,score,"
                        "reasons,rule_version,awarded_at,revoked_at,revocation_reason,"
                        "evaluation_id,document_version_id,evidence_sha256) VALUES("
                        ":id,:event_id,:trigger,:source_count,CAST(:components AS jsonb),:score,"
                        ":reasons,:rule_version,:evaluated_at,NULL,NULL,:evaluation_id,"
                        ":version_id,:evidence_sha256)"
                    ),
                    {
                        "id": uuid7(),
                        "event_id": event_id,
                        "trigger": result.trigger,
                        "source_count": result.independent_source_count,
                        "components": json.dumps(components_payload, sort_keys=True),
                        "score": result.score,
                        "reasons": list(result.reasons),
                        "rule_version": result.rule_version,
                        "evaluated_at": evaluated_at,
                        "evaluation_id": evaluation_id,
                        "version_id": document_version_id,
                        "evidence_sha256": evidence_sha256,
                    },
                )
        INTELLIGENCE_V2_HOTSPOT_EVALUATIONS.labels(
            outcome="AWARDED" if result.awarded else "REJECTED"
        ).inc()
        logger.info(
            "hotspot evaluation persisted",
            extra={
                "event_id": str(event_id),
                "evaluation_id": str(evaluation_id),
                "outcome": "AWARDED" if result.awarded else "REJECTED",
                "rule_version": result.rule_version,
            },
        )
        return result

    async def build_internal_projection(self, *, actor_id: UUID, generated_at: datetime) -> Any:
        from srbg_api.internal_projection.backfill import backfill_internal_projection

        return await backfill_internal_projection(self._engine, actor_id=actor_id, now=generated_at)

    async def internal_projection_metrics(self) -> dict[str, float]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT\n                              COALESCE((\n                                SELECT difference_count\n                                  FROM published_v1.projection_build_run\n                                 WHERE status = 'SUCCEEDED'\n                                 ORDER BY generation DESC LIMIT 1\n                              ), 0) AS differences,\n                              COALESCE(EXTRACT(EPOCH FROM (\n                                SELECT completed_at\n                                  FROM published_v1.projection_build_run\n                                 WHERE status = 'SUCCEEDED'\n                                 ORDER BY generation DESC LIMIT 1\n                              )), 0) AS projection_timestamp,\n                              COALESCE(EXTRACT(EPOCH FROM (\n                                SELECT max(anchored_at) FROM audit_chain_anchor\n                              )), 0) AS anchor_timestamp\n                            "
                        )
                    )
                )
                .mappings()
                .one()
            )
        return {
            "reconciliation_differences": float(row["differences"]),
            "last_projection_success_timestamp": float(row["projection_timestamp"]),
            "last_anchor_success_timestamp": float(row["anchor_timestamp"]),
        }

    async def upsert_v2_projection(
        self,
        *,
        document_version_id: UUID,
        projection: EventProjectionV2,
        appendix: EventAppendixV2,
        risk_tier: str,
        projected_at: datetime,
    ) -> None:
        """Write reader and search projections in one publisher transaction."""

        if projection.projection_kind == "FULL":
            source_name = projection.source.name
            excerpt = projection.source_excerpt.text
            ai_text = projection.ai_summary.body
        else:
            source_name = projection.source_name
            excerpt = ""
            ai_text = None
        claim_text = " ".join(
            claim.value for claim in appendix.claims if claim.decision_status == "ACCEPTED"
        )
        searchable = " ".join((projection.title, source_name, claim_text, excerpt)).strip()
        async with self._engine.begin() as connection:
            generation = await connection.scalar(
                text(
                    "SELECT COALESCE(max(generation),0)+1 "
                    "FROM intelligence_projection_v2 WHERE event_id=:event_id"
                ),
                {"event_id": projection.event_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO intelligence_projection_v2("
                    "event_id,document_version_id,projection_kind,primary_type,risk_tier,"
                    "payload,appendix_payload,generation,projected_at) VALUES("
                    ":event_id,:document_version_id,:projection_kind,:primary_type,:risk_tier,"
                    "CAST(:payload AS jsonb),CAST(:appendix AS jsonb),:generation,:projected_at) "
                    "ON CONFLICT(event_id) DO UPDATE SET "
                    "document_version_id=EXCLUDED.document_version_id,"
                    "projection_kind=EXCLUDED.projection_kind,primary_type=EXCLUDED.primary_type,"
                    "risk_tier=EXCLUDED.risk_tier,payload=EXCLUDED.payload,"
                    "appendix_payload=EXCLUDED.appendix_payload,generation=EXCLUDED.generation,"
                    "projected_at=EXCLUDED.projected_at"
                ),
                {
                    "event_id": projection.event_id,
                    "document_version_id": document_version_id,
                    "projection_kind": projection.projection_kind,
                    "primary_type": projection.primary_type.value,
                    "risk_tier": risk_tier,
                    "payload": projection.model_dump_json(),
                    "appendix": appendix.model_dump_json(),
                    "generation": generation,
                    "projected_at": projected_at,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO search_projection_v2("
                    "event_id,title_source_claims_excerpt,ai_summary_low_weight,search_vector,"
                    "generation,updated_at) VALUES("
                    ":event_id,:searchable,:ai_text,"
                    "setweight(to_tsvector('simple',:searchable),'A') || "
                    "setweight(to_tsvector('simple',COALESCE(:ai_text,'')),'D'),"
                    ":generation,:updated_at) ON CONFLICT(event_id) DO UPDATE SET "
                    "title_source_claims_excerpt=EXCLUDED.title_source_claims_excerpt,"
                    "ai_summary_low_weight=EXCLUDED.ai_summary_low_weight,"
                    "search_vector=EXCLUDED.search_vector,generation=EXCLUDED.generation,"
                    "updated_at=EXCLUDED.updated_at"
                ),
                {
                    "event_id": projection.event_id,
                    "searchable": searchable,
                    "ai_text": ai_text,
                    "generation": generation,
                    "updated_at": projected_at,
                },
            )

    async def refresh_v2_projection(
        self,
        *,
        event_id: UUID,
        document_version_id: UUID,
        projected_at: datetime,
    ) -> None:
        """Rebuild a strict projection only from current authoritative database facts."""

        params = {"event_id": event_id, "version_id": document_version_id}
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT item.id AS item_id,item.title,item.original_url,"
                            "item.risk_level,item.source_published_at,item.first_discovered_at,"
                            "item.current_document_version_id,source.name AS source_name,"
                            "source.source_type,review.state AS review_state,"
                            "review.risk_tier AS review_risk,review.safe_metadata,raw.scan_status,"
                            "(EXISTS(SELECT 1 FROM raw_object_security_fact security "
                            "WHERE security.raw_object_id=raw.id AND security.status='CLEAN') "
                            "AND NOT EXISTS(SELECT 1 FROM raw_object_security_fact security "
                            "WHERE security.raw_object_id=raw.id AND security.status IN "
                            "('REJECTED','QUARANTINED'))) AS raw_security_clean,"
                            "qualification.primary_type,qualification.engineering_objects,"
                            "qualification.specialty_facets,qualification.equipment_domains,"
                            "qualification.cross_type_tags,candidate.id AS candidate_id,"
                            "COALESCE(excerpt.accepted_claim_set_sha256,"
                            "candidate.accepted_claim_set_sha256) AS accepted_claim_set_sha256,"
                            "COALESCE(excerpt.source_excerpt,candidate.source_excerpt) AS source_excerpt,"
                            "COALESCE(excerpt.source_excerpt_claim_ids,"
                            "candidate.source_excerpt_claim_ids) AS source_excerpt_claim_ids,"
                            "COALESCE(excerpt.evidence_locators,candidate.evidence_locators) "
                            "AS evidence_locators,COALESCE(excerpt.accepted_claim_ids,"
                            "candidate.claim_ids) AS accepted_claim_ids,candidate.claim_ids "
                            "AS candidate_claim_ids,COALESCE(excerpt.claim_basis,"
                            "candidate.claim_basis) AS claim_basis,candidate.claims_payload,"
                            "candidate.summary_payload,candidate.model,candidate.created_at,"
                            "COALESCE(summary_state.status,CASE WHEN candidate.id IS NOT NULL "
                            "THEN 'SUCCEEDED' ELSE 'NOT_GENERATED' END) AS summary_status,"
                            "summary_state.reason_code AS summary_reason "
                            "FROM event_identity_binding binding "
                            "JOIN intelligence_item item ON item.id=binding.item_id "
                            "JOIN source ON source.id=item.source_id "
                            "JOIN document_version version ON version.id=:version_id "
                            "JOIN raw_object raw ON raw.id=version.raw_object_id "
                            "LEFT JOIN qualification_acceptance_v2 qualification "
                            "ON qualification.event_id=:event_id "
                            "AND qualification.document_version_id=:version_id "
                            "LEFT JOIN owner_review_case_v2 review "
                            "ON review.document_version_id=:version_id "
                            "LEFT JOIN LATERAL(SELECT prepared.* "
                            "FROM content_preparation_candidate_v2 prepared "
                            "LEFT JOIN content_preparation_invalidation_v2 invalidation "
                            "ON invalidation.candidate_id=prepared.id "
                            "WHERE prepared.event_id=:event_id "
                            "AND prepared.document_version_id=:version_id "
                            "AND invalidation.id IS NULL "
                            "ORDER BY prepared.created_at DESC,prepared.id DESC LIMIT 1"
                            ") candidate ON true "
                            "LEFT JOIN LATERAL(SELECT prepared.* "
                            "FROM source_excerpt_version_v2 prepared "
                            "WHERE prepared.event_id=:event_id "
                            "AND prepared.document_version_id=:version_id "
                            "ORDER BY prepared.created_at DESC,prepared.id DESC LIMIT 1"
                            ") excerpt ON true "
                            "LEFT JOIN LATERAL(SELECT state.status,state.reason_code "
                            "FROM ai_summary_state_event_v2 state "
                            "WHERE state.event_id=:event_id "
                            "AND state.document_version_id=:version_id "
                            "ORDER BY state.created_at DESC,state.id DESC LIMIT 1"
                            ") summary_state ON true "
                            "WHERE binding.event_id=:event_id "
                            "AND version.id=item.current_document_version_id "
                            "ORDER BY review.updated_at DESC NULLS LAST LIMIT 1"
                        ),
                        params,
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["current_document_version_id"] != document_version_id:
            await self._deny_v2_projection(
                event_id, document_version_id, "NOT_FOUND", "V2_DOCUMENT_NOT_CURRENT", projected_at
            )
        if row["scan_status"] != "CLEAN" or not row["raw_security_clean"]:
            await self._deny_v2_projection(
                event_id, document_version_id, "NOT_FOUND", "V2_RAW_NOT_CLEAN", projected_at
            )
        if row["primary_type"] is None:
            await self._deny_v2_projection(
                event_id,
                document_version_id,
                "NOT_FOUND",
                "V2_QUALIFICATION_NOT_ACCEPTED",
                projected_at,
            )
        risk_tier = str(row["review_risk"] or row["risk_level"])
        if risk_tier == "R4":
            await self._deny_v2_projection(
                event_id,
                document_version_id,
                "QUARANTINE",
                "R4_CANNOT_ENTER_READER_PROJECTION",
                projected_at,
            )
        official_source = str(row["source_type"]).lower() in {
            "government",
            "official",
            "standards_body",
        }
        if risk_tier == "R3" and row["review_state"] != "RESOLVED":
            metadata = dict(row["safe_metadata"] or {})
            projection = EventMetadataProjectionV2(
                event_id=event_id,
                title=str(metadata.get("title") or row["title"]),
                primary_type=_primary_type(str(row["primary_type"])),
                official_source=official_source,
                source_name=str(row["source_name"]),
                source_published_at=row["source_published_at"],
                first_discovered_at=row["first_discovered_at"],
                original_url=str(row["original_url"]),
                review_state="PENDING_OWNER_REVIEW",
            )
            await self.upsert_v2_projection(
                document_version_id=document_version_id,
                projection=projection,
                appendix=EventAppendixV2(event_id=event_id),
                risk_tier="R3",
                projected_at=projected_at,
            )
            await self._record_v2_publication_decision(
                event_id=event_id,
                document_version_id=document_version_id,
                outcome="R3_METADATA",
                reason_codes=("R3_PENDING_OWNER_REVIEW",),
                projection=projection,
                created_at=projected_at,
            )
            return
        if row["source_excerpt"] is None:
            await self._deny_v2_projection(
                event_id,
                document_version_id,
                "NOT_FOUND",
                "V2_CURRENT_SOURCE_EXCERPT_REQUIRED",
                projected_at,
            )
        async with self._engine.connect() as connection:
            claim_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT claim.id,claim.claim_type,claim.predicate,"
                            "claim.literal_value,array_agg(evidence.id ORDER BY evidence.id) "
                            "AS evidence_ids FROM claim "
                            "JOIN event_identity_binding binding ON binding.item_id=claim.item_id "
                            "JOIN claim_evidence evidence ON evidence.claim_id=claim.id "
                            "WHERE binding.event_id=:event_id "
                            "AND claim.document_version_id=:version_id "
                            "AND claim.verification_status='ACCEPTED' "
                            "AND (COALESCE(claim.acceptance_method,'HUMAN_REVIEW')"
                            "<>'AUTOMATED_EVIDENCE_GATE' OR "
                            "'ACTIVE'=(SELECT state.state "
                            "FROM automatic_evidence_fact_state_event state "
                            "WHERE state.claim_id=claim.id "
                            "ORDER BY state.created_at DESC,state.id DESC LIMIT 1)) "
                            "GROUP BY claim.id,claim.claim_type,claim.predicate,claim.literal_value "
                            "ORDER BY claim.id"
                        ),
                        params,
                    )
                ).mappings()
            )
            human_reviewed = bool(
                await connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM owner_review_decision_v2 decision "
                        "JOIN owner_review_case_v2 review ON review.id=decision.case_id "
                        "WHERE review.document_version_id=:version_id "
                        "AND decision.command IN ('ACCEPT_CLAIM','REPLACE_CLAIM'))"
                    ),
                    params,
                )
            )
            hotspot_row = (
                (
                    await connection.execute(
                        text(
                            "SELECT trigger_path,independent_source_count,reasons "
                            "FROM hotspot_award_v2 WHERE event_id=:event_id "
                            "AND evaluation_id IS NOT NULL "
                            "ORDER BY awarded_at DESC,id DESC LIMIT 1"
                        ),
                        params,
                    )
                )
                .mappings()
                .one_or_none()
            )
            media_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT media.id,media.name,media.source_url,media.mime_type,"
                            "media.rights_basis,media.redistribution_allowed,media.scan_status,"
                            "media.object_key,media.preview_object_key,media.preview_mime_type,"
                            "media.attachment_scan_status,media.raw_scan_status "
                            "FROM media_delivery_reader_v2 media "
                            "WHERE media.document_version_id=:version_id "
                            "ORDER BY media.created_at,media.id"
                        ),
                        params,
                    )
                ).mappings()
            )
        try:
            current_claims = await PostgresContentCandidateRepository(
                self._engine
            ).load_active_claims(document_version_id)
        except (RuntimeError, ValueError):
            await self._deny_v2_projection(
                event_id,
                document_version_id,
                "NOT_FOUND",
                "V2_FULL_ACCEPTED_CLAIMS_MISMATCH",
                projected_at,
            )
        current_claim_hash = accepted_claim_set_sha256(current_claims)
        accepted_claim_ids = {claim["id"] for claim in claim_rows}
        excerpt_accepted_claim_ids = set(row["accepted_claim_ids"] or ())
        excerpt_claim_ids = set(row["source_excerpt_claim_ids"] or ())
        if (
            not accepted_claim_ids
            or row["accepted_claim_set_sha256"] != current_claim_hash
            or excerpt_accepted_claim_ids != accepted_claim_ids
            or not excerpt_claim_ids
            or not excerpt_claim_ids.issubset(accepted_claim_ids)
        ):
            await self._deny_v2_projection(
                event_id,
                document_version_id,
                "NOT_FOUND",
                "V2_FULL_ACCEPTED_CLAIMS_MISMATCH",
                projected_at,
            )
        summary_status = AiSummaryStatusV2(str(row["summary_status"]))
        paragraphs: list[dict[str, Any]] = []
        summary_claim_ids: set[UUID] = set()
        if summary_status is AiSummaryStatusV2.SUCCEEDED:
            candidate_claim_ids = set(row["candidate_claim_ids"] or ())
            if row["candidate_id"] is None:
                summary_status = AiSummaryStatusV2.STALE
            else:
                summary_payload = dict(row["summary_payload"] or {})
                paragraphs = list(summary_payload.get("paragraphs") or ())
                summary_claim_ids = {
                    UUID(str(claim_id))
                    for paragraph in paragraphs
                    if paragraph.get("kind") == "FACT"
                    for claim_id in paragraph.get("claim_ids", ())
                }
                if (
                    candidate_claim_ids != accepted_claim_ids
                    or not summary_claim_ids
                    or not summary_claim_ids.issubset(accepted_claim_ids)
                ):
                    await self._deny_v2_projection(
                        event_id,
                        document_version_id,
                        "NOT_FOUND",
                        "V2_SUMMARY_ACCEPTED_CLAIMS_MISMATCH",
                        projected_at,
                    )
        appendix = EventAppendixV2(
            event_id=event_id,
            claims=[
                ClaimView(
                    id=claim["id"],
                    claim_type=str(claim["claim_type"]),
                    label=str(claim["predicate"]),
                    value=(
                        claim["literal_value"]
                        if isinstance(claim["literal_value"], str)
                        else json.dumps(claim["literal_value"], ensure_ascii=False)
                    ),
                    evidence_ids=list(claim["evidence_ids"]),
                    decision_status="ACCEPTED",
                )
                for claim in claim_rows
            ],
        )
        hotspot = (
            HotspotReasonV2(
                trigger=hotspot_row["trigger_path"],
                independent_source_count=hotspot_row["independent_source_count"],
                reasons=list(hotspot_row["reasons"]),
            )
            if hotspot_row is not None
            else None
        )
        media = [
            MediaViewV2(
                media_id=media_row["id"],
                name=str(media_row["name"]),
                preview_url=f"/api/v2/media/{media_row['id']}/preview",
                rights_basis=media_row["rights_basis"],
            )
            for media_row in media_rows
            if str(media_row["mime_type"]).startswith("image/")
            and projectable_preview(
                rights_basis=media_row["rights_basis"],
                scan_status=str(media_row["scan_status"]),
                attachment_scan_status=str(media_row["attachment_scan_status"]),
                raw_scan_status=str(media_row["raw_scan_status"]),
                preview_object_key=media_row["preview_object_key"],
                preview_mime_type=media_row["preview_mime_type"],
            )
        ]
        attachments = [
            AttachmentViewV2(
                media_id=(
                    media_row["id"]
                    if projectable_download(
                        rights_basis=media_row["rights_basis"],
                        scan_status=str(media_row["scan_status"]),
                        attachment_scan_status=str(media_row["attachment_scan_status"]),
                        raw_scan_status=str(media_row["raw_scan_status"]),
                        redistribution_allowed=bool(media_row["redistribution_allowed"]),
                        object_key=media_row["object_key"],
                    )
                    else None
                ),
                name=str(media_row["name"]),
                download_url=(
                    f"/api/v2/media/{media_row['id']}/download"
                    if projectable_download(
                        rights_basis=media_row["rights_basis"],
                        scan_status=str(media_row["scan_status"]),
                        attachment_scan_status=str(media_row["attachment_scan_status"]),
                        raw_scan_status=str(media_row["raw_scan_status"]),
                        redistribution_allowed=bool(media_row["redistribution_allowed"]),
                        object_key=media_row["object_key"],
                    )
                    else None
                ),
                source_url=str(media_row["source_url"]),
                redistribution_allowed=bool(media_row["redistribution_allowed"]),
            )
            for media_row in media_rows
            if not str(media_row["mime_type"]).startswith("image/")
        ]
        full_projection = EventFullProjectionV2(
            event_id=event_id,
            title=str(row["title"]),
            primary_type=row["primary_type"],
            facets=IntelligenceFacetsV2(
                engineering_objects=list(row["engineering_objects"] or ()),
                specialties=list(row["specialty_facets"] or ()),
                equipment_domains=list(row["equipment_domains"] or ()),
                cross_type_tags=list(row["cross_type_tags"] or ()),
            ),
            source=SourceAttributionV2(name=str(row["source_name"]), official=official_source),
            human_reviewed=human_reviewed,
            source_published_at=row["source_published_at"],
            first_discovered_at=row["first_discovered_at"],
            source_excerpt=SourceExcerptV2(
                text=str(row["source_excerpt"]),
                claim_ids=list(row["source_excerpt_claim_ids"]),
                evidence_locators=list(row["evidence_locators"]),
            ),
            ai_summary=AiSummaryV2.model_validate(
                {
                    "status": summary_status,
                    "body": (
                        "\n".join(str(paragraph["text"]) for paragraph in paragraphs)
                        if summary_status is AiSummaryStatusV2.SUCCEEDED
                        else None
                    ),
                    "paragraphs": paragraphs,
                    "claim_ids": sorted(summary_claim_ids, key=str),
                    "model": (
                        str(row["model"])
                        if summary_status is AiSummaryStatusV2.SUCCEEDED
                        else None
                    ),
                    "generated_at": (
                        row["created_at"]
                        if summary_status is AiSummaryStatusV2.SUCCEEDED
                        else None
                    ),
                }
            ),
            original_url=str(row["original_url"]),
            claim_basis=list(row["claim_basis"]),
            hotspot=hotspot,
            media=media,
            attachments=attachments,
        )
        await self.upsert_v2_projection(
            document_version_id=document_version_id,
            projection=full_projection,
            appendix=appendix,
            risk_tier=risk_tier,
            projected_at=projected_at,
        )
        await self._record_v2_publication_decision(
            event_id=event_id,
            document_version_id=document_version_id,
            outcome="FULL",
            reason_codes=("CURRENT_ACCEPTED_CLAIMS", f"AI_SUMMARY_{summary_status.value}"),
            projection=full_projection,
            created_at=projected_at,
        )

    async def process_ai_projection_refresh_once(self, *, processed_at: datetime) -> bool:
        """Claim one durable AI result and rebuild only at the publisher boundary."""

        async with self._engine.begin() as connection:
            work = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,event_id,document_version_id,attempt_count "
                            "FROM ai_projection_refresh_outbox_v2 WHERE status IN "
                            "('PENDING','FAILED') AND available_at<=:now AND attempt_count<3 "
                            "ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1"
                        ),
                        {"now": processed_at},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if work is None:
                return False
            await connection.execute(
                text(
                    "UPDATE ai_projection_refresh_outbox_v2 SET status='PROCESSING',"
                    "attempt_count=attempt_count+1,updated_at=:now WHERE id=:id"
                ),
                {"id": work["id"], "now": processed_at},
            )
        try:
            await self.refresh_v2_projection(
                event_id=work["event_id"],
                document_version_id=work["document_version_id"],
                projected_at=processed_at,
            )
        except Exception as error:
            code = (
                error.reasons[0]
                if isinstance(error, PublicationDenied) and error.reasons
                else type(error).__name__.upper()
            )[:80]
            next_attempt = int(work["attempt_count"]) + 1
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE ai_projection_refresh_outbox_v2 SET status=:status,"
                        "last_error_code=:code,available_at=:available,updated_at=:now "
                        "WHERE id=:id AND status='PROCESSING'"
                    ),
                    {
                        "id": work["id"],
                        "status": "DEAD_LETTER" if next_attempt >= 3 else "FAILED",
                        "code": code,
                        "available": processed_at
                        + timedelta(seconds=(5, 15, 45)[min(next_attempt - 1, 2)]),
                        "now": processed_at,
                    },
                )
            T06_AI_PROJECTION_REFRESH.labels(
                outcome="dead_letter" if next_attempt >= 3 else "failed"
            ).inc()
            return True
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE ai_projection_refresh_outbox_v2 SET status='COMPLETED',"
                    "last_error_code=NULL,updated_at=:now WHERE id=:id "
                    "AND status='PROCESSING'"
                ),
                {"id": work["id"], "now": processed_at},
            )
        T06_AI_PROJECTION_REFRESH.labels(outcome="completed").inc()
        return True

    async def _record_v2_publication_decision(
        self,
        *,
        event_id: UUID | None,
        document_version_id: UUID,
        outcome: str,
        reason_codes: tuple[str, ...],
        projection: EventProjectionV2 | None,
        created_at: datetime,
    ) -> None:
        projection_hash = (
            sha256(projection.model_dump_json().encode()).hexdigest()
            if projection is not None
            else None
        )
        metric_outcome = (
            "SAFETY_FAILURE" if _V2_SAFETY_FAILURE_REASONS.intersection(reason_codes) else outcome
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtextextended(CAST(:version_id AS text),0))"
                ),
                {"version_id": str(document_version_id)},
            )
            await connection.execute(
                text(
                    "INSERT INTO publication_decision_v2("
                    "id,event_id,document_version_id,outcome,reason_codes,projection_sha256,"
                    "created_at) SELECT :id,:event_id,:version_id,"
                    "CAST(:outcome AS varchar(30)),CAST(:reasons AS varchar(80)[]),"
                    "CAST(:hash AS varchar(64)),:now "
                    "WHERE NOT EXISTS(SELECT 1 FROM publication_decision_v2 "
                    "WHERE document_version_id=:version_id "
                    "AND outcome=CAST(:outcome AS varchar(30)) "
                    "AND reason_codes=CAST(:reasons AS varchar(80)[]) "
                    "AND projection_sha256 IS NOT DISTINCT FROM :hash)"
                ),
                {
                    "id": uuid7(),
                    "event_id": event_id,
                    "version_id": document_version_id,
                    "outcome": outcome,
                    "reasons": list(reason_codes),
                    "hash": projection_hash,
                    "now": created_at,
                },
            )
        INTELLIGENCE_V2_PUBLICATION_DECISIONS.labels(outcome=metric_outcome).inc()

    async def _deny_v2_projection(
        self,
        event_id: UUID,
        document_version_id: UUID,
        outcome: str,
        reason: str,
        created_at: datetime,
    ) -> Never:
        await self._remove_v2_projection(event_id=event_id)
        await self._record_v2_publication_decision(
            event_id=event_id,
            document_version_id=document_version_id,
            outcome=outcome,
            reason_codes=(reason,),
            projection=None,
            created_at=created_at,
        )
        raise PublicationDenied((reason,))

    async def _remove_v2_projection(self, *, event_id: UUID) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM intelligence_projection_v2 WHERE event_id=:event_id"),
                {"event_id": event_id},
            )

    async def process_v2_review_reprocessing(
        self,
        *,
        outbox_id: UUID,
        processed_at: datetime,
    ) -> None:
        """Apply exactly one idempotent review Outbox fact, failing closed."""

        async with self._engine.begin() as connection:
            work = (
                (
                    await connection.execute(
                        text(
                            "SELECT outbox.id,outbox.status,outbox.attempt_count,outbox.updated_at,"
                            "outbox.document_version_id,decision.command,decision.payload,"
                            "review.id AS case_id,review.event_id "
                            "FROM owner_review_reprocessing_outbox_v2 outbox "
                            "JOIN owner_review_decision_v2 decision "
                            "ON decision.id=outbox.decision_id "
                            "JOIN owner_review_case_v2 review ON review.id=outbox.case_id "
                            "WHERE outbox.id=:id FOR UPDATE OF outbox"
                        ),
                        {"id": outbox_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if work is None:
                raise LookupError(f"unknown review reprocessing outbox {outbox_id}")
            if work["status"] == "COMPLETED":
                return
            if work["status"] == "PROCESSING" and processed_at - work["updated_at"] <= timedelta(
                minutes=5
            ):
                return
            if work["attempt_count"] >= 3:
                await connection.execute(
                    text(
                        "UPDATE owner_review_reprocessing_outbox_v2 "
                        "SET status='DEAD_LETTER',updated_at=:now WHERE id=:id"
                    ),
                    {"id": outbox_id, "now": processed_at},
                )
                return
            await connection.execute(
                text(
                    "UPDATE owner_review_reprocessing_outbox_v2 SET status='PROCESSING',"
                    "attempt_count=attempt_count+1,last_error_code=NULL,updated_at=:now "
                    "WHERE id=:id"
                ),
                {"id": outbox_id, "now": processed_at},
            )
        event_id = work["event_id"]
        command = str(work["command"])
        try:
            if command == "EXCLUDE_RELEVANCE":
                if event_id is not None:
                    await self._remove_v2_projection(event_id=event_id)
                state = "RESOLVED"
            elif (
                command == "DECIDE_RISK"
                and dict(work["payload"] or {}).get("payload", {}).get("risk_tier") == "R4"
            ):
                if event_id is not None:
                    await self._remove_v2_projection(event_id=event_id)
                state = "QUARANTINED"
            else:
                if event_id is None:
                    raise PublicationDenied(("V2_REPROCESSING_EVENT_NOT_MATERIALIZED",))
                await self.refresh_v2_projection(
                    event_id=event_id,
                    document_version_id=work["document_version_id"],
                    projected_at=processed_at,
                )
                state = "RESOLVED"
        except Exception as exc:
            error_code = (
                exc.reasons[0]
                if isinstance(exc, PublicationDenied) and exc.reasons
                else "V2_REPROCESSING_FAILED"
            )
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE owner_review_reprocessing_outbox_v2 SET status='FAILED',"
                        "last_error_code=:error,updated_at=:now WHERE id=:id"
                    ),
                    {"id": outbox_id, "error": error_code, "now": processed_at},
                )
            raise
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE owner_review_case_v2 SET state=:state,updated_at=:now WHERE id=:case_id"
                ),
                {
                    "case_id": work["case_id"],
                    "state": state,
                    "now": processed_at,
                },
            )
            await connection.execute(
                text(
                    "UPDATE owner_review_reprocessing_outbox_v2 "
                    "SET status='COMPLETED',updated_at=:now WHERE id=:id"
                ),
                {"id": outbox_id, "now": processed_at},
            )

    async def process_personal_content_once(self, *, processed_at: datetime) -> bool:
        async with self._engine.begin() as connection:
            event = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT id,item_id,document_version_id,action\n                            FROM personal_content_outbox\n                            WHERE status IN ('PENDING','FAILED') AND available_at<=:now\n                              AND attempt_count<5\n                            ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1\n                            "
                        ),
                        {"now": processed_at},
                    )
                )
                .mappings()
                .first()
            )
            if event is None:
                return False
            if event["action"] == "PROJECT":
                facts = list(
                    (
                        await connection.execute(
                            text(
                                "\n                                SELECT claim.id,claim.claim_type,claim.literal_value,\n                                  jsonb_agg(jsonb_build_object(\n                                    'evidence_id',evidence.id,\n                                    'excerpt_sha256',evidence.excerpt_sha256,\n                                    'locator',COALESCE(evidence.locator_type,'HTML_PARAGRAPH')\n                                  ) ORDER BY evidence.id) AS evidence\n                                FROM claim\n                                JOIN automatic_evidence_acceptance acceptance\n                                  ON acceptance.claim_id=claim.id\n                                 AND acceptance.input_document_version_id=:version_id\n                                JOIN claim_evidence evidence ON evidence.claim_id=claim.id\n                                WHERE claim.item_id=:item_id\n                                  AND claim.document_version_id=:version_id\n                                  AND claim.verification_status='ACCEPTED'\n                                  AND claim.acceptance_method='AUTOMATED_EVIDENCE_GATE'\n                                  AND 'ACTIVE'=(SELECT state.state\n                                    FROM automatic_evidence_fact_state_event state\n                                    WHERE state.claim_id=claim.id\n                                    ORDER BY state.created_at DESC,state.id DESC LIMIT 1)\n                                GROUP BY claim.id,claim.claim_type,claim.literal_value\n                                ORDER BY claim.claim_type,claim.id\n                                "
                            ),
                            {
                                "item_id": event["item_id"],
                                "version_id": event["document_version_id"],
                            },
                        )
                    ).mappings()
                )
                item = (
                    (
                        await connection.execute(
                            text(
                                "SELECT item.title,item.original_url,item.current_document_version_id,item.channel,item.item_type,item.source_published_at,item.first_discovered_at,item.review_status,source.name AS source_name,binding.event_id,event.event_type FROM intelligence_item item JOIN source ON source.id=item.source_id JOIN event_identity_binding binding ON binding.item_id=item.id JOIN event ON event.id=binding.event_id WHERE item.id=:item_id FOR SHARE OF item"
                            ),
                            {"item_id": event["item_id"]},
                        )
                    )
                    .mappings()
                    .one()
                )
                if item["current_document_version_id"] != event["document_version_id"]:
                    raise RuntimeError("PERSONAL_PROJECTION_STALE_DOCUMENT")
                relationship_items = await _recalculate_automatic_relationships(
                    connection,
                    item_id=event["item_id"],
                    document_version_id=event["document_version_id"],
                    calculated_at=processed_at,
                )
                if relationship_items:
                    await _refresh_relationship_projections(
                        connection,
                        event_id=item["event_id"],
                        item_ids=relationship_items,
                        changed_at=processed_at,
                    )
                payload = [
                    {
                        "claim_id": str(row["id"]),
                        "fact_kind": "EVIDENCE_FACT",
                        "field_name": row["claim_type"],
                        "value": row["literal_value"],
                        "evidence": row["evidence"],
                    }
                    for row in facts
                ]
                await connection.execute(
                    text(
                        "\n                        INSERT INTO personal_content_projection(\n                          item_id,document_version_id,title,original_url,evidence_facts,\n                          visible,generation,updated_at\n                        ) VALUES(:item_id,:version_id,:title,:url,CAST(:facts AS jsonb),true,1,:now)\n                        ON CONFLICT(item_id) DO UPDATE SET\n                          document_version_id=EXCLUDED.document_version_id,\n                          title=EXCLUDED.title,original_url=EXCLUDED.original_url,\n                          evidence_facts=EXCLUDED.evidence_facts,visible=true,\n                          generation=personal_content_projection.generation+1,updated_at=EXCLUDED.updated_at\n                        "
                    ),
                    {
                        "item_id": event["item_id"],
                        "version_id": event["document_version_id"],
                        "title": item["title"],
                        "url": item["original_url"],
                        "facts": json.dumps(payload, ensure_ascii=False, default=str),
                        "now": processed_at,
                    },
                )
                judgment = (
                    (
                        await connection.execute(
                            text(
                                "\n                                SELECT id,status,judgment_payload,failure_reason_codes\n                                FROM ai_judgment_version\n                                WHERE item_id=:item_id AND document_version_id=:version_id\n                                  AND status<>'INVALIDATED'\n                                ORDER BY created_at DESC,id DESC LIMIT 1\n                                "
                            ),
                            {
                                "item_id": event["item_id"],
                                "version_id": event["document_version_id"],
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                signals = build_personal_signal_projections(
                    PersonalSignalInput(
                        event_id=item["event_id"],
                        item_id=event["item_id"],
                        document_version_id=event["document_version_id"],
                        title=item["title"],
                        original_url=item["original_url"],
                        source_name=item["source_name"],
                        domain=item["channel"],
                        content_type=item["item_type"],
                        source_published_at=item["source_published_at"],
                        first_discovered_at=item["first_discovered_at"],
                        activity_at=item["source_published_at"] or item["first_discovered_at"],
                        review_status=item["review_status"],
                        event_type=item["event_type"],
                        evidence_facts=payload,
                        judgment_version_id=judgment["id"] if judgment else None,
                        judgment_status=judgment["status"] if judgment else None,
                        judgment_payload=judgment["judgment_payload"] if judgment else None,
                        failure_reason_codes=tuple(judgment["failure_reason_codes"] or ())
                        if judgment
                        else (),
                    )
                )
                report_date = processed_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
                report_id = await connection.scalar(
                    text(
                        "\n                        INSERT INTO personal_daily_report_projection(\n                          id,report_date,snapshot_at,visible,generation,created_at,updated_at\n                        ) VALUES(:id,:report_date,:now,true,1,:now,:now)\n                        ON CONFLICT(report_date) DO UPDATE SET snapshot_at=EXCLUDED.snapshot_at,\n                          visible=true,generation=personal_daily_report_projection.generation+1,\n                          updated_at=EXCLUDED.updated_at\n                        RETURNING id\n                        "
                    ),
                    {"id": uuid7(), "report_date": report_date, "now": processed_at},
                )
                await connection.execute(
                    text(
                        "\n                        DELETE FROM personal_daily_signal_projection\n                        WHERE signal_id IN (\n                          SELECT id FROM personal_signal_projection\n                          WHERE document_version_id=:version_id\n                        )\n                        "
                    ),
                    {"version_id": event["document_version_id"]},
                )
                for delete_statement in (
                    "\n                    DELETE FROM personal_primary_search_projection\n                    WHERE signal_id IN (\n                      SELECT id FROM personal_signal_projection\n                      WHERE document_version_id=:version_id\n                    )\n                    ",
                    "\n                    DELETE FROM unverified_ai_search_projection\n                    WHERE signal_id IN (\n                      SELECT id FROM personal_signal_projection\n                      WHERE document_version_id=:version_id\n                    )\n                    ",
                ):
                    await connection.execute(
                        text(delete_statement),
                        {"version_id": event["document_version_id"]},
                    )
                await connection.execute(
                    text(
                        "\n                        UPDATE personal_signal_projection\n                        SET visible=false,generation=generation+1,updated_at=:now\n                        WHERE document_version_id=:version_id\n                        "
                    ),
                    {"version_id": event["document_version_id"], "now": processed_at},
                )
                for signal in signals:
                    await connection.execute(
                        text(
                            "\n                            INSERT INTO personal_signal_projection(\n                              id,event_id,item_id,document_version_id,judgment_version_id,\n                              result_type,payload,visible,generation,created_at,updated_at\n                            ) VALUES(:id,:event_id,:item_id,:version_id,:judgment_id,\n                              :result_type,CAST(:payload AS jsonb),true,1,:now,:now)\n                            ON CONFLICT(document_version_id,result_type) DO UPDATE SET\n                              judgment_version_id=EXCLUDED.judgment_version_id,\n                              payload=EXCLUDED.payload,visible=true,\n                              generation=personal_signal_projection.generation+1,\n                              updated_at=EXCLUDED.updated_at\n                            "
                        ),
                        {
                            "id": signal.signal_id,
                            "event_id": signal.event_id,
                            "item_id": signal.item_id,
                            "version_id": signal.document_version_id,
                            "judgment_id": signal.judgment_version_id,
                            "result_type": signal.result_type,
                            "payload": json.dumps(signal.payload, ensure_ascii=False, default=str),
                            "now": processed_at,
                        },
                    )
                    for delete_statement in (
                        "DELETE FROM personal_primary_search_projection WHERE signal_id=:id",
                        "DELETE FROM unverified_ai_search_projection WHERE signal_id=:id",
                    ):
                        await connection.execute(text(delete_statement), {"id": signal.signal_id})
                    if signal.search_surface is not None:
                        table = (
                            "personal_primary_search_projection"
                            if signal.search_surface == "PRIMARY"
                            else "unverified_ai_search_projection"
                        )
                        await connection.execute(
                            text(
                                f"\n                                INSERT INTO {table}(\n                                  signal_id,event_id,result_type,title,search_text,\n                                  activity_at,visible,generation\n                                ) VALUES(:id,:event_id,:result_type,:title,:search_text,:now,true,1)\n                                ON CONFLICT(signal_id) DO UPDATE SET title=EXCLUDED.title,\n                                  search_text=EXCLUDED.search_text,activity_at=EXCLUDED.activity_at,\n                                  visible=true,generation={table}.generation+1\n                                "
                            ),
                            {
                                "id": signal.signal_id,
                                "event_id": signal.event_id,
                                "result_type": signal.result_type,
                                "title": item["title"],
                                "search_text": " ".join(
                                    (item["title"], json.dumps(signal.payload, ensure_ascii=False))
                                ),
                                "now": processed_at,
                            },
                        )
                    await connection.execute(
                        text(
                            "DELETE FROM personal_daily_signal_projection WHERE report_id=:report_id AND signal_id=:signal_id"
                        ),
                        {"report_id": report_id, "signal_id": signal.signal_id},
                    )
                    if signal.daily_section is not None:
                        position = int(
                            await connection.scalar(
                                text(
                                    "SELECT COALESCE(max(position),0)+1 FROM personal_daily_signal_projection WHERE report_id=:report_id AND section=:section"
                                ),
                                {"report_id": report_id, "section": signal.daily_section},
                            )
                            or 1
                        )
                        await connection.execute(
                            text(
                                "INSERT INTO personal_daily_signal_projection(report_id,signal_id,section,position) VALUES(:report_id,:signal_id,:section,:position)"
                            ),
                            {
                                "report_id": report_id,
                                "signal_id": signal.signal_id,
                                "section": signal.daily_section,
                                "position": position,
                            },
                        )
                    if signal.judgment_version_id is not None:
                        surfaces = ["FEED", "CACHE"]
                        if signal.search_surface is not None:
                            surfaces.append("SEARCH")
                        if signal.daily_section is not None:
                            surfaces.append("DAILY")
                        for surface in surfaces:
                            await connection.execute(
                                text(
                                    "INSERT INTO ai_judgment_projection_reference(judgment_version_id,signal_id,surface,created_at) VALUES(:judgment_id,:signal_id,:surface,:now) ON CONFLICT DO NOTHING"
                                ),
                                {
                                    "judgment_id": signal.judgment_version_id,
                                    "signal_id": signal.signal_id,
                                    "surface": surface,
                                    "now": processed_at,
                                },
                            )
            else:
                await connection.execute(
                    text(
                        """
                        INSERT INTO content_preparation_invalidation_v2(
                          id,candidate_id,reason,created_at
                        )
                        SELECT :id,candidate.id,
                          CASE WHEN :action='INVALIDATE'
                            THEN 'SOURCE_WITHDRAWN' ELSE 'SOURCE_CORRECTED' END,:now
                        FROM content_preparation_candidate_v2 candidate
                        JOIN event_identity_binding binding
                          ON binding.event_id=candidate.event_id
                        WHERE binding.item_id=:item_id
                        ORDER BY candidate.created_at DESC,candidate.id DESC LIMIT 1
                        ON CONFLICT(candidate_id) DO NOTHING
                        """
                    ),
                    {
                        "id": uuid7(),
                        "action": event["action"],
                        "item_id": event["item_id"],
                        "now": processed_at,
                    },
                )
                await connection.execute(
                    text(
                        "UPDATE personal_content_projection SET visible=false,generation=generation+1,updated_at=:now WHERE item_id=:item_id"
                    ),
                    {"item_id": event["item_id"], "now": processed_at},
                )
                invalidation_statements = (
                    "\n                    UPDATE personal_signal_projection SET visible=false,\n                      generation=generation+1,updated_at=:now WHERE item_id=:item_id\n                    ",
                    "\n                    UPDATE personal_primary_search_projection search SET visible=false,\n                      generation=search.generation+1 FROM personal_signal_projection signal\n                    WHERE search.signal_id=signal.id AND signal.item_id=:item_id\n                    ",
                    "\n                    UPDATE unverified_ai_search_projection search SET visible=false,\n                      generation=search.generation+1 FROM personal_signal_projection signal\n                    WHERE search.signal_id=signal.id AND signal.item_id=:item_id\n                    ",
                    "\n                    UPDATE personal_daily_report_projection report SET visible=false,\n                      generation=report.generation+1,updated_at=:now\n                    WHERE EXISTS(SELECT 1 FROM personal_daily_signal_projection daily\n                      JOIN personal_signal_projection signal ON signal.id=daily.signal_id\n                      WHERE daily.report_id=report.id AND signal.item_id=:item_id)\n                    ",
                    "\n                    UPDATE ai_judgment_version SET status='INVALIDATED',\n                      invalidation_reason=:reason,invalidated_at=:now\n                    WHERE item_id=:item_id AND status<>'INVALIDATED'\n                    ",
                )
                for statement in invalidation_statements:
                    await connection.execute(
                        text(statement),
                        {
                            "item_id": event["item_id"],
                            "reason": "CONTENT_INVALIDATED",
                            "now": processed_at,
                        },
                    )
            await connection.execute(
                text(
                    "UPDATE personal_content_outbox SET status='SUCCEEDED',processed_at=:now,attempt_count=attempt_count+1 WHERE id=:id"
                ),
                {"id": event["id"], "now": processed_at},
            )
            return True

    async def correct_automatic_relationship(
        self,
        *,
        event_id: UUID,
        payload: OwnerRelationshipCorrectionRequest,
        owner_id: UUID,
        corrected_at: datetime,
    ) -> OwnerRelationshipCorrectionResponse:
        """Record an Owner correction and invalidate every old projection atomically."""
        async with self._engine.begin() as connection:
            prior = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT id,action FROM owner_relationship_correction\n                            WHERE command_id=:command_id\n                            UNION ALL\n                            SELECT id,'WITHDRAW_RELATION' AS action\n                            FROM owner_relationship_withdrawal\n                            WHERE command_id=:command_id\n                            LIMIT 1\n                            "
                        ),
                        {"command_id": payload.command_id},
                    )
                )
                .mappings()
                .first()
            )
            event = (
                (
                    await connection.execute(
                        text("SELECT id,version,status FROM event WHERE id=:id FOR UPDATE"),
                        {"id": event_id},
                    )
                )
                .mappings()
                .first()
            )
            if event is None:
                raise PublicationDenied(("PERS08_EVENT_NOT_FOUND",))
            if prior is not None:
                generation = await _relationship_projection_generation(connection, event_id)
                return OwnerRelationshipCorrectionResponse(
                    correction_id=cast(UUID, prior["id"]),
                    event_id=event_id,
                    action=str(prior["action"]),
                    event_version=int(event["version"]),
                    projection_generation=generation,
                )
            correction_id = uuid7()
            affected_item_ids = set(
                (
                    await connection.scalars(
                        text(
                            "\n                            SELECT item_id FROM event_identity_binding WHERE event_id=:event_id\n                            UNION SELECT item_id FROM event_item WHERE event_id=:event_id\n                            "
                        ),
                        {"event_id": event_id},
                    )
                ).all()
            )
            affected_item_ids.update(payload.member_item_ids)
            affected_item_ids.update(allocation.item_id for allocation in payload.allocations)
            if payload.action == "WITHDRAW_RELATION":
                decision = (
                    (
                        await connection.execute(
                            text(
                                "\n                                SELECT id,relationship_kind,source_item_id,target_item_id,\n                                  input_fingerprint_sha256,status\n                                FROM automatic_relationship_decision_version\n                                WHERE id=:id FOR UPDATE\n                                "
                            ),
                            {"id": payload.decision_id},
                        )
                    )
                    .mappings()
                    .first()
                )
                if decision is None or decision["status"] != "ACTIVE":
                    raise PublicationDenied(("PERS08_RELATION_NOT_ACTIVE",))
                members = [decision["source_item_id"], decision["target_item_id"]]
                if not set(members).intersection(affected_item_ids):
                    raise PublicationDenied(("PERS08_RELATION_EVENT_MISMATCH",))
                affected_item_ids.update(members)
                await connection.execute(
                    text(
                        "\n                        INSERT INTO owner_relationship_withdrawal(\n                          id,command_id,decision_id,relationship_kind,member_item_ids,\n                          input_fingerprint_sha256,reason,owner_id,created_at\n                        ) VALUES(:id,:command_id,:decision_id,:kind,:members,:fingerprint,\n                          :reason,:owner_id,:now)\n                        "
                    ),
                    {
                        "id": correction_id,
                        "command_id": payload.command_id,
                        "decision_id": payload.decision_id,
                        "kind": decision["relationship_kind"],
                        "members": members,
                        "fingerprint": decision["input_fingerprint_sha256"],
                        "reason": payload.reason.strip(),
                        "owner_id": owner_id,
                        "now": corrected_at,
                    },
                )
                await connection.execute(
                    text(
                        "UPDATE automatic_relationship_decision_version SET status='WITHDRAWN',invalidated_at=:now WHERE id=:id"
                    ),
                    {"id": payload.decision_id, "now": corrected_at},
                )
                await connection.execute(
                    text(
                        "\n                        INSERT INTO automatic_relationship_invalidation(\n                          id,invalidated_decision_id,withdrawal_id,reason,created_at\n                        ) VALUES(:id,:decision_id,:withdrawal_id,:reason,:now)\n                        "
                    ),
                    {
                        "id": uuid7(),
                        "decision_id": payload.decision_id,
                        "withdrawal_id": correction_id,
                        "reason": payload.reason.strip(),
                        "now": corrected_at,
                    },
                )
            else:
                if payload.action == "SPLIT_EVENT":
                    allocated = {allocation.item_id for allocation in payload.allocations}
                    if affected_item_ids != allocated:
                        raise PublicationDenied(("PERS08_SPLIT_ALLOCATION_INCOMPLETE",))
                serialized = payload.model_dump(mode="json", exclude={"reason"})
                await connection.execute(
                    text(
                        "\n                        INSERT INTO owner_relationship_correction(\n                          id,command_id,event_id,decision_id,action,payload,reason,\n                          owner_id,created_at\n                        ) VALUES(:id,:command_id,:event_id,:decision_id,:action,\n                          CAST(:payload AS jsonb),:reason,:owner_id,:now)\n                        "
                    ),
                    {
                        "id": correction_id,
                        "command_id": payload.command_id,
                        "event_id": event_id,
                        "decision_id": payload.decision_id,
                        "action": payload.action,
                        "payload": json.dumps(serialized, ensure_ascii=False),
                        "reason": payload.reason.strip(),
                        "owner_id": owner_id,
                        "now": corrected_at,
                    },
                )
                relationship_filter = ""
                parameters: dict[str, Any] = {"now": corrected_at, "correction_id": correction_id}
                if payload.action == "SPLIT_EVENT":
                    relationship_filter = " AND (source_item_id=ANY(CAST(:member_ids AS uuid[])) OR target_item_id=ANY(CAST(:member_ids AS uuid[])))"
                    parameters["member_ids"] = list(affected_item_ids)
                elif payload.action == "KEEP_INDEPENDENT":
                    relationship_filter = " AND source_item_id=ANY(CAST(:member_ids AS uuid[])) AND target_item_id=ANY(CAST(:member_ids AS uuid[]))"
                    parameters["member_ids"] = list(payload.member_item_ids)
                elif payload.action == "CORRECT_MODEL_RELATION":
                    relationship_filter = " AND relationship_kind IN ('MODEL_ALIAS','VERSION_SUCCESSOR') AND (source_item_id IN (:source_id,:target_id) OR target_item_id IN (:source_id,:target_id))"
                    parameters["source_id"] = payload.corrected_source_item_id
                    parameters["target_id"] = payload.corrected_target_item_id
                invalidated = list(
                    (
                        await connection.scalars(
                            text(
                                "UPDATE automatic_relationship_decision_version SET status='INVALIDATED',invalidated_at=:now WHERE status='ACTIVE'"
                                + relationship_filter
                                + " RETURNING id"
                            ),
                            parameters,
                        )
                    ).all()
                )
                for decision_id in invalidated:
                    await connection.execute(
                        text(
                            "\n                            INSERT INTO automatic_relationship_invalidation(\n                              id,invalidated_decision_id,correction_id,reason,created_at\n                            ) VALUES(:id,:decision_id,:correction_id,:reason,:now)\n                            "
                        ),
                        {
                            "id": uuid7(),
                            "decision_id": decision_id,
                            "correction_id": correction_id,
                            "reason": payload.reason.strip(),
                            "now": corrected_at,
                        },
                    )
                if payload.action == "SPLIT_EVENT":
                    child_event_ids = {
                        allocation.child_event_id for allocation in payload.allocations
                    }
                    if event_id in child_event_ids or len(child_event_ids) < 2:
                        raise PublicationDenied(("PERS08_SPLIT_REQUIRES_DISTINCT_CHILDREN",))
                    for child_event_id in child_event_ids:
                        await connection.execute(
                            text(
                                "\n                                INSERT INTO event(\n                                  id,event_type,title,occurred_at,region_code,region_name,\n                                  project_name,subject_names,accident_type,engineering_type,\n                                  incident_status,confirmation_status,confirmed_by,confirmed_at,\n                                  created_at,updated_at,canonical_event_id,status,version\n                                ) SELECT :child_id,event_type,title,occurred_at,\n                                  region_code,region_name,\n                                  project_name,subject_names,accident_type,engineering_type,\n                                  incident_status,confirmation_status,confirmed_by,confirmed_at,\n                                  :now,:now,:child_id,'ACTIVE',1\n                                FROM event WHERE id=:source_id\n                                ON CONFLICT (id) DO NOTHING\n                                "
                            ),
                            {
                                "child_id": child_event_id,
                                "source_id": event_id,
                                "now": corrected_at,
                            },
                        )
                    for allocation in payload.allocations:
                        await connection.execute(
                            text(
                                "UPDATE event_item SET event_id=:child_event_id WHERE event_id=:source_event_id AND item_id=:item_id"
                            ),
                            {
                                "child_event_id": allocation.child_event_id,
                                "source_event_id": event_id,
                                "item_id": allocation.item_id,
                            },
                        )
                    await connection.execute(
                        text(
                            "UPDATE event SET status='SPLIT',version=version+1,updated_at=:now WHERE id=:id"
                        ),
                        {"id": event_id, "now": corrected_at},
                    )
                elif payload.action == "CORRECT_MODEL_RELATION":
                    corrected_decision_id = uuid7()
                    corrected_members = sorted(
                        (payload.corrected_source_item_id, payload.corrected_target_item_id),
                        key=str,
                    )
                    corrected_key = (
                        f"{payload.corrected_kind}:{corrected_members[0]}:{corrected_members[1]}"
                    )
                    fingerprint = sha256(f"{corrected_key}:{correction_id}".encode()).hexdigest()
                    await connection.execute(
                        text(
                            "\n                            INSERT INTO automatic_relationship_decision_version(\n                              id,relationship_key,relationship_kind,source_item_id,target_item_id,\n                              algorithm_version,model_version,score_bps,reason_codes,reason,\n                              input_fingerprint_sha256,status,created_at\n                            ) VALUES(:id,:key,:kind,:source,:target,'owner-correction-v1',NULL,\n                              10000,ARRAY['OWNER_CORRECTION'],'OWNER_CORRECTION',:fingerprint,\n                              'ACTIVE',:now)\n                            "
                        ),
                        {
                            "id": corrected_decision_id,
                            "key": corrected_key,
                            "kind": payload.corrected_kind,
                            "source": payload.corrected_source_item_id,
                            "target": payload.corrected_target_item_id,
                            "fingerprint": fingerprint,
                            "now": corrected_at,
                        },
                    )
                    await connection.execute(
                        text(
                            "UPDATE owner_relationship_correction SET resulting_decision_id=:decision_id WHERE id=:correction_id"
                        ),
                        {"decision_id": corrected_decision_id, "correction_id": correction_id},
                    )
            generation = await _refresh_relationship_projections(
                connection, event_id=event_id, item_ids=affected_item_ids, changed_at=corrected_at
            )
            await _append_audit(
                connection,
                event_type=f"PERS08_{payload.action}",
                actor_id=owner_id,
                target_type="automatic_relationship",
                target_id=correction_id,
                after_state={"event_id": str(event_id), "action": payload.action},
                reason=payload.reason.strip(),
                request_id=str(payload.command_id),
                now=corrected_at,
            )
            PERSONAL_RELATIONSHIP_CORRECTIONS.labels(action=payload.action, outcome="applied").inc()
            event_version = int(event["version"]) + (1 if payload.action == "SPLIT_EVENT" else 0)
            return OwnerRelationshipCorrectionResponse(
                correction_id=correction_id,
                event_id=event_id,
                action=payload.action,
                event_version=event_version,
                projection_generation=generation,
            )

    async def is_ai_claim_candidate(self, candidate_id: UUID) -> bool:
        async with self._engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ai_candidate_claim_origin WHERE claim_id=:claim_id)"
                    ),
                    {"claim_id": candidate_id},
                )
            )

    async def process_projection_invalidation_once(
        self,
        *,
        processed_at: datetime,
        cache_generation: Callable[[UUID, int, bool], Awaitable[None]],
        search_projection: Callable[[UUID, int, bool], Awaitable[None]] | None,
        daily_digest: Callable[[UUID, int, bool], Awaitable[None]] | None,
    ) -> bool:
        """Consume one projection event; rollback leaves it pending on cache failure."""
        async with self._engine.begin() as connection:
            event = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT id, publication_id, projection, action, generation\n                            FROM publication_projection_invalidation\n                            WHERE status = 'PENDING'\n                            ORDER BY created_at, id\n                            FOR UPDATE SKIP LOCKED LIMIT 1\n                            "
                        )
                    )
                )
                .mappings()
                .first()
            )
            if event is None:
                return False
            if event["projection"] == "CACHE":
                await cache_generation(
                    cast(UUID, event["publication_id"]),
                    int(event["generation"]),
                    event["action"] != "WITHDRAW",
                )
            elif event["projection"] == "SEARCH":
                if search_projection is None:
                    raise RuntimeError("search projection callback is required")
                await search_projection(
                    cast(UUID, event["publication_id"]),
                    int(event["generation"]),
                    event["action"] != "WITHDRAW",
                )
            elif event["projection"] == "DAILY_DIGEST":
                if daily_digest is None:
                    raise RuntimeError("daily digest projection callback is required")
                await daily_digest(
                    cast(UUID, event["publication_id"]),
                    int(event["generation"]),
                    event["action"] != "WITHDRAW",
                )
            await connection.execute(
                text(
                    "\n                    UPDATE publication_projection_invalidation\n                    SET status = 'APPLIED', applied_at = :processed_at\n                    WHERE id = :event_id AND status = 'PENDING'\n                    "
                ),
                {"event_id": event["id"], "processed_at": processed_at},
            )
            return True


async def _recalculate_automatic_relationships(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    document_version_id: UUID,
    calculated_at: datetime,
) -> set[UUID]:
    """Create conservative, versioned decisions from current authoritative inputs."""
    current = (
        (
            await connection.execute(
                text(
                    "\n                    SELECT item.id AS item_id,item.item_type,item.current_document_version_id,\n                      version.document_id,version.content_hash,\n                      fingerprint.model_no_key,fingerprint.accident_stage,\n                      fingerprint.region_key,fingerprint.project_key,\n                      fingerprint.embedding_model,\n                      lineage.role AS source_role,\n                      COALESCE(membership.event_id,binding.event_id) AS event_id\n                    FROM intelligence_item item\n                    JOIN document_version version ON version.id=:version_id\n                    LEFT JOIN document_fingerprint fingerprint ON fingerprint.item_id=item.id\n                    LEFT JOIN source_lineage lineage ON lineage.item_id=item.id\n                    LEFT JOIN event_identity_binding binding ON binding.item_id=item.id\n                    LEFT JOIN LATERAL (\n                      SELECT event_id FROM event_item\n                      WHERE item_id=item.id ORDER BY confirmed_at DESC LIMIT 1\n                    ) membership ON true\n                    WHERE item.id=:item_id AND item.current_document_version_id=:version_id\n                    "
                ),
                {"item_id": item_id, "version_id": document_version_id},
            )
        )
        .mappings()
        .first()
    )
    if current is None:
        return set()
    candidates = list(
        (
            await connection.execute(
                text(
                    "\n                    SELECT DISTINCT other.id AS item_id,other.item_type,\n                      other.current_document_version_id,version.document_id,\n                      version.content_hash,fingerprint.model_no_key,\n                      fingerprint.accident_stage,fingerprint.region_key,\n                      fingerprint.project_key,fingerprint.embedding_model,\n                      lineage.role AS source_role,\n                      COALESCE(membership.event_id,binding.event_id) AS event_id,\n                      EXISTS(\n                        SELECT 1 FROM item_identity_key left_key\n                        JOIN item_identity_key right_key\n                          ON right_key.key_type=left_key.key_type\n                         AND right_key.scope_key=left_key.scope_key\n                         AND right_key.normalized_value=left_key.normalized_value\n                        WHERE left_key.item_id=:item_id AND right_key.item_id=other.id\n                      ) AS exact_identity,\n                      EXISTS(\n                        SELECT 1 FROM topic_cluster_event left_topic\n                        JOIN topic_cluster_event right_topic\n                          ON right_topic.topic_id=left_topic.topic_id\n                        WHERE left_topic.event_id=\n                          COALESCE(current_membership.event_id,current_binding.event_id)\n                          AND right_topic.event_id=COALESCE(membership.event_id,binding.event_id)\n                      ) AS same_topic\n                    FROM intelligence_item other\n                    JOIN document_version version\n                      ON version.id=other.current_document_version_id\n                    LEFT JOIN document_fingerprint fingerprint ON fingerprint.item_id=other.id\n                    LEFT JOIN source_lineage lineage ON lineage.item_id=other.id\n                    LEFT JOIN event_identity_binding binding ON binding.item_id=other.id\n                    LEFT JOIN LATERAL (\n                      SELECT event_id FROM event_item\n                      WHERE item_id=other.id ORDER BY confirmed_at DESC LIMIT 1\n                    ) membership ON true\n                    LEFT JOIN event_identity_binding current_binding\n                      ON current_binding.item_id=:item_id\n                    LEFT JOIN LATERAL (\n                      SELECT event_id FROM event_item\n                      WHERE item_id=:item_id ORDER BY confirmed_at DESC LIMIT 1\n                    ) current_membership ON true\n                    WHERE other.id<>:item_id\n                      AND (\n                        EXISTS(\n                          SELECT 1 FROM item_identity_key left_key\n                          JOIN item_identity_key right_key\n                            ON right_key.key_type=left_key.key_type\n                           AND right_key.scope_key=left_key.scope_key\n                           AND right_key.normalized_value=left_key.normalized_value\n                          WHERE left_key.item_id=:item_id AND right_key.item_id=other.id\n                        )\n                        OR COALESCE(membership.event_id,binding.event_id)=\n                           COALESCE(current_membership.event_id,current_binding.event_id)\n                        OR (\n                          fingerprint.model_no_key IS NOT NULL\n                          AND fingerprint.model_no_key=(\n                            SELECT model_no_key FROM document_fingerprint WHERE item_id=:item_id\n                          )\n                        )\n                        OR EXISTS(\n                          SELECT 1 FROM topic_cluster_event left_topic\n                          JOIN topic_cluster_event right_topic\n                            ON right_topic.topic_id=left_topic.topic_id\n                          WHERE left_topic.event_id=\n                            COALESCE(current_membership.event_id,current_binding.event_id)\n                            AND right_topic.event_id=COALESCE(membership.event_id,binding.event_id)\n                        )\n                      )\n                    ORDER BY other.id LIMIT 100\n                    "
                ),
                {"item_id": item_id},
            )
        ).mappings()
    )
    withdrawal_rows = list(
        (
            await connection.execute(
                text(
                    "SELECT relationship_kind,member_item_ids,input_fingerprint_sha256 FROM owner_relationship_withdrawal WHERE :item_id=ANY(member_item_ids)"
                ),
                {"item_id": item_id},
            )
        ).mappings()
    )
    correction_rows = list(
        (
            await connection.execute(
                text(
                    "SELECT action,payload FROM owner_relationship_correction WHERE action IN ('KEEP_INDEPENDENT','SPLIT_EVENT')"
                )
            )
        ).mappings()
    )
    suppressions: list[RelationshipSuppression] = [
        RelationshipSuppression(
            kind=RelationshipKind(row["relationship_kind"]),
            member_ids=frozenset(row["member_item_ids"]),
            input_fingerprint_sha256=row["input_fingerprint_sha256"],
        )
        for row in withdrawal_rows
    ]
    keep_independent_pairs = {
        frozenset(UUID(value) for value in row["payload"].get("member_item_ids", []))
        for row in correction_rows
        if row["action"] == "KEEP_INDEPENDENT" and isinstance(row["payload"], dict)
    }
    split_allocations = {
        UUID(allocation["item_id"]): UUID(allocation["child_event_id"])
        for row in correction_rows
        if row["action"] == "SPLIT_EVENT" and isinstance(row["payload"], dict)
        for allocation in row["payload"].get("allocations", [])
    }
    changed_items: set[UUID] = set()
    product_types = {"SOFTWARE_PRODUCT", "IOT_PRODUCT", "LOW_ALTITUDE_EQUIPMENT", "AI_EQUIPMENT"}
    for candidate in candidates:
        pair = frozenset((item_id, cast(UUID, candidate["item_id"])))
        if pair in keep_independent_pairs:
            continue
        if (
            item_id in split_allocations
            and candidate["item_id"] in split_allocations
            and (split_allocations[item_id] != split_allocations[candidate["item_id"]])
        ):
            continue
        conflicts: list[str] = []
        for field, code in (("region_key", "REGION"), ("project_key", "PROJECT")):
            if current[field] and candidate[field] and (current[field] != candidate[field]):
                conflicts.append(code)
        same_event = bool(current["event_id"] and current["event_id"] == candidate["event_id"])
        same_model = bool(
            current["model_no_key"]
            and current["model_no_key"] == candidate["model_no_key"]
            and (current["item_type"] in product_types)
            and (candidate["item_type"] in product_types)
        )
        hint = (
            "VERSION_SUCCESSOR"
            if same_model
            else "SAME_EVENT"
            if same_event
            else "TOPIC"
            if candidate["same_topic"]
            else None
        )
        value = AutomaticRelationshipInput(
            left_item_id=item_id,
            right_item_id=candidate["item_id"],
            left_document_version_id=document_version_id,
            right_document_version_id=candidate["current_document_version_id"],
            left_content_sha256=current["content_hash"],
            right_content_sha256=candidate["content_hash"],
            score_bps=10000 if candidate["exact_identity"] or same_event or same_model else 9000,
            hard_conflicts=tuple(conflicts),
            exact_identity=bool(candidate["exact_identity"]),
            relation_hint=hint,
            left_report_stage=current["accident_stage"],
            right_report_stage=candidate["accident_stage"],
            left_source_role=current["source_role"],
            right_source_role=candidate["source_role"],
            model_version=current["embedding_model"] or candidate["embedding_model"],
        )
        decision = decide_automatic_relationship(value, suppressions=tuple(suppressions))
        if decision is None:
            continue
        member_ids = sorted((decision.source_item_id, decision.target_item_id), key=str)
        relationship_key = f"{decision.kind.value}:{member_ids[0]}:{member_ids[1]}"
        previous = (
            (
                await connection.execute(
                    text(
                        "SELECT id,input_fingerprint_sha256,algorithm_version FROM automatic_relationship_decision_version WHERE relationship_key=:key AND status='ACTIVE' FOR UPDATE"
                    ),
                    {"key": relationship_key},
                )
            )
            .mappings()
            .first()
        )
        if (
            previous is not None
            and previous["input_fingerprint_sha256"] == decision.input_fingerprint_sha256
        ):
            continue
        if previous is not None and previous["algorithm_version"].startswith("owner-correction"):
            continue
        decision_id = uuid7()
        if previous is not None:
            await connection.execute(
                text(
                    "UPDATE automatic_relationship_decision_version SET status='SUPERSEDED',invalidated_at=:now WHERE id=:id"
                ),
                {"id": previous["id"], "now": calculated_at},
            )
        await connection.execute(
            text(
                "\n                INSERT INTO automatic_relationship_decision_version(\n                  id,relationship_key,relationship_kind,source_item_id,target_item_id,\n                  algorithm_version,model_version,score_bps,reason_codes,reason,\n                  input_fingerprint_sha256,status,supersedes_decision_id,created_at\n                ) VALUES(:id,:key,:kind,:source,:target,:algorithm,:model,:score,\n                  :reasons,:reason,:fingerprint,'ACTIVE',:supersedes,:now)\n                "
            ),
            {
                "id": decision_id,
                "key": relationship_key,
                "kind": decision.kind.value,
                "source": decision.source_item_id,
                "target": decision.target_item_id,
                "algorithm": value.algorithm_version,
                "model": value.model_version,
                "score": decision.score_bps,
                "reasons": list(decision.reason_codes),
                "reason": ",".join(decision.reason_codes),
                "fingerprint": decision.input_fingerprint_sha256,
                "supersedes": previous["id"] if previous else None,
                "now": calculated_at,
            },
        )
        input_rows = (current, candidate)
        for position, member in enumerate(input_rows, start=1):
            await connection.execute(
                text(
                    "\n                    INSERT INTO automatic_relationship_member(\n                      id,decision_id,intelligence_item_id,document_id,document_version_id,\n                      event_id,content_sha256,source_role,position\n                    ) VALUES(:id,:decision_id,:item_id,:document_id,:version_id,\n                      :event_id,:hash,:role,:position)\n                    "
                ),
                {
                    "id": uuid7(),
                    "decision_id": decision_id,
                    "item_id": member["item_id"],
                    "document_id": member["document_id"],
                    "version_id": member["current_document_version_id"],
                    "event_id": member["event_id"],
                    "hash": member["content_hash"],
                    "role": member["source_role"],
                    "position": position,
                },
            )
        if previous is not None:
            await connection.execute(
                text(
                    "\n                    INSERT INTO automatic_relationship_invalidation(\n                      id,invalidated_decision_id,successor_decision_id,reason,created_at\n                    ) VALUES(:id,:previous,:successor,'INPUT_MATERIAL_CHANGED',:now)\n                    "
                ),
                {
                    "id": uuid7(),
                    "previous": previous["id"],
                    "successor": decision_id,
                    "now": calculated_at,
                },
            )
        changed_items.update(pair)
        logger.info(
            "automatic_relationship_decided",
            extra={"kind": decision.kind.value, "score_bps": decision.score_bps},
        )
        PERSONAL_AUTOMATIC_RELATIONSHIPS.labels(kind=decision.kind.value, outcome="active").inc()
    return changed_items


async def _relationship_projection_generation(connection: AsyncConnection, event_id: UUID) -> int:
    value = await connection.scalar(
        text(
            "\n            SELECT COALESCE(max(projection.generation),1)\n            FROM personal_content_projection projection\n            JOIN event_identity_binding binding ON binding.item_id=projection.item_id\n            WHERE binding.event_id=:event_id\n            "
        ),
        {"event_id": event_id},
    )
    return int(value or 1)


async def _refresh_relationship_projections(
    connection: AsyncConnection, *, event_id: UUID, item_ids: set[UUID], changed_at: datetime
) -> int:
    """Advance all database projections before cache invalidation can be observed."""
    if not item_ids:
        return await _relationship_projection_generation(connection, event_id)
    parameters = {"item_ids": list(item_ids), "now": changed_at}
    await connection.execute(
        text(
            "UPDATE personal_content_projection SET generation=generation+1,updated_at=:now WHERE item_id=ANY(CAST(:item_ids AS uuid[]))"
        ),
        parameters,
    )
    await connection.execute(
        text(
            "UPDATE personal_signal_projection SET generation=generation+1,updated_at=:now WHERE item_id=ANY(CAST(:item_ids AS uuid[]))"
        ),
        parameters,
    )
    for table in ("personal_primary_search_projection", "unverified_ai_search_projection"):
        await connection.execute(
            text(
                f"UPDATE {table} search SET generation=search.generation+1 FROM personal_signal_projection signal WHERE signal.id=search.signal_id AND signal.item_id=ANY(CAST(:item_ids AS uuid[]))"
            ),
            parameters,
        )
    await connection.execute(
        text(
            "\n            UPDATE personal_daily_report_projection report\n            SET generation=report.generation+1,updated_at=:now\n            WHERE EXISTS(\n              SELECT 1 FROM personal_daily_signal_projection daily\n              JOIN personal_signal_projection signal ON signal.id=daily.signal_id\n              WHERE daily.report_id=report.id\n                AND signal.item_id=ANY(CAST(:item_ids AS uuid[]))\n            )\n            "
        ),
        parameters,
    )
    publications = list(
        (
            await connection.scalars(
                text("SELECT id FROM publication WHERE item_id=ANY(CAST(:item_ids AS uuid[]))"),
                parameters,
            )
        ).all()
    )
    for publication_id in publications:
        for projection in ("CACHE", "SEARCH", "DAILY_DIGEST"):
            generation = int(
                await connection.scalar(
                    text(
                        "SELECT COALESCE(max(generation),0)+1 FROM publication_projection_invalidation WHERE publication_id=:publication_id AND projection=:projection"
                    ),
                    {"publication_id": publication_id, "projection": projection},
                )
                or 1
            )
            await connection.execute(
                text(
                    "\n                    INSERT INTO publication_projection_invalidation(\n                      id,publication_id,projection,action,generation,status,created_at,applied_at\n                    ) VALUES(:id,:publication_id,:projection,'UPSERT',:generation,\n                      'PENDING',:now,NULL)\n                    "
                ),
                {
                    "id": uuid7(),
                    "publication_id": publication_id,
                    "projection": projection,
                    "generation": generation,
                    "now": changed_at,
                },
            )
    return await _relationship_projection_generation(connection, event_id)


async def _append_audit(
    connection: AsyncConnection,
    *,
    event_type: str,
    actor_id: UUID,
    target_type: str,
    target_id: UUID,
    after_state: dict[str, Any],
    reason: str,
    request_id: str,
    now: datetime,
) -> UUID:
    audit_id = uuid7()
    await connection.execute(
        text(
            "\n            SELECT append_audit_event(\n                :id, :event_type, :actor_id, :target_type, :target_id, NULL,\n                CAST(:after_state AS jsonb), :reason, :request_id, :created_at\n            )\n            "
        ),
        {
            "id": audit_id,
            "event_type": event_type,
            "actor_id": actor_id,
            "target_type": target_type,
            "target_id": target_id,
            "after_state": _json(after_state),
            "reason": reason,
            "request_id": request_id,
            "created_at": now,
        },
    )
    return audit_id


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
