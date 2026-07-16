"""Publisher-role repository and authoritative publication evaluation transaction."""

import json
import logging
import re
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    ClaimConflict,
    ClaimConflictDecisionAction,
    ClaimConflictDecisionResponse,
    ClaimConflictStatus,
    CriticalSafetyField,
    DailyReport,
    DigitalCaseReviewPatch,
    PreventionMeasureTag,
    ReviewDecisionResponse,
    ReviewStatus,
    SafetyCaseProfileMetadataField,
    SimilarScenarioTag,
)

from srbg_api.digital_cases.domain import (
    MaturityEvidence,
    calculate_relevance,
    validate_maturity,
    validate_taxonomy,
)
from srbg_api.discovery.repository import daily_report_from_rows
from srbg_api.identifiers import uuid7
from srbg_api.publication.service import PublicationDenied, PublicationTransaction
from srbg_api.source_registry.repository import canonical_json_hash
from srbg_api.technology_products.domain import contains_procurement_conclusion

logger = logging.getLogger(__name__)

_SAFETY_PROTECTED_CLAIM_TYPES = frozenset(
    {
        "deaths",
        "injuries",
        "loss_amount_minor",
        "official_direct_causes",
        "responsibility_findings",
    }
)
_SAFETY_METADATA_CLAIM_TYPES = frozenset(
    {
        "title",
        "published_at",
        "source_published_at",
        "report_stage",
        "incident_status",
        "occurred_at",
        "region",
        "region_code",
        "region_name",
        "project_name",
        "accident_type",
        "hazard_type",
        "engineering_type",
        "missing_count",
        "enforcement_actions",
        "rectification_has_open_issues",
        "similar_scenario_tags",
        "prevention_measure_tags",
    }
)
_SAFETY_OPERATIONAL_CLAIM_TYPES = frozenset(
    {
        "corrective_actions",
        "operational_instructions",
        "site_operation_instruction",
    }
)
_SAFETY_PROFILE_METADATA_FACT_KEYS = {
    SafetyCaseProfileMetadataField.REPORT_STAGE.value: "safety_report_stage",
    SafetyCaseProfileMetadataField.INCIDENT_STATUS.value: "safety_incident_status",
    SafetyCaseProfileMetadataField.ACCIDENT_TYPE.value: "safety_accident_type",
    SafetyCaseProfileMetadataField.ENGINEERING_TYPE.value: "safety_engineering_type",
    SafetyCaseProfileMetadataField.OCCURRED_AT.value: "safety_occurred_at",
    SafetyCaseProfileMetadataField.REGION_NAME.value: "safety_region_name",
    SafetyCaseProfileMetadataField.PROJECT_NAME.value: "safety_project_name",
    SafetyCaseProfileMetadataField.RECTIFICATION_HAS_OPEN_ISSUES.value: (
        "safety_rectification_has_open_issues"
    ),
    SafetyCaseProfileMetadataField.SIMILAR_SCENARIO_TAGS.value: ("safety_similar_scenario_tags"),
    SafetyCaseProfileMetadataField.PREVENTION_MEASURE_TAGS.value: (
        "safety_prevention_measure_tags"
    ),
}
_ALWAYS_REQUIRED_SAFETY_PROFILE_METADATA_FIELDS = frozenset(
    {
        SafetyCaseProfileMetadataField.REPORT_STAGE.value,
        SafetyCaseProfileMetadataField.INCIDENT_STATUS.value,
    }
)
_REPORT_STAGE_EVIDENCE_TERMS = {
    "INITIAL_REPORT": ("初报", "首次通报", "初次处置", "处置中"),
    "FOLLOW_UP_REPORT": ("续报", "新闻发布会", "继续救援"),
    "FINAL_INVESTIGATION": ("调查评估", "调查评估组", "调查评估报告", "事故调查报告"),
    "ENFORCEMENT": ("追责问责", "处罚决定"),
    "RECTIFICATION": ("整改措施落实情况", "整改落实评估报告"),
}
_INCIDENT_STATUS_EVIDENCE_TERMS = {
    "UNVERIFIED_LEAD": ("待核实", "事故线索"),
    "INITIAL_OFFICIAL_REPORT": (
        "初次处置",
        "首次通报",
        "官方通报",
        "处置中",
        "处置工作正在进行",
    ),
    "UNDER_INVESTIGATION": ("新闻发布会", "继续救援", "正在调查"),
    "FINAL_INVESTIGATION_REPORT": (
        "调查评估",
        "调查评估组",
        "调查评估报告",
        "事故调查报告",
    ),
    "ENFORCEMENT_DECISION": ("追责问责", "处罚决定"),
    "RECTIFICATION_FOLLOW_UP": ("整改措施落实情况", "整改落实评估报告"),
    "CLOSED": ("结案", "完成闭环"),
    "CORRECTED": ("更正", "订正"),
    "WITHDRAWN": ("撤回", "撤销"),
}
_ACCIDENT_TYPE_EVIDENCE_TERMS = {
    "ROADBED_COLLAPSE": ("塌方", "塌陷", "路基坍塌", "路堤坍塌"),
}
_ENGINEERING_TYPE_EVIDENCE_TERMS = {
    "EXPRESSWAY": ("高速", "高速公路"),
    "HIGHWAY": ("公路",),
}
_SIMILAR_TAG_EVIDENCE_TERM_GROUPS = {
    "HIGHWAY_OPERATION_GEOLOGICAL_RISK": (("高速", "高速公路"), ("地质", "灾害", "塌方")),
    "ROADBED_SLOPE_INSTABILITY": (("路堤", "边坡", "塌方", "塌陷"),),
    "BRIDGE_APPROACH_TRANSITION": (("桥头", "桥台"), ("过渡", "沉降", "跳车")),
    "EXTREME_WEATHER_EXPOSURE": (("极端天气", "强降雨", "暴雨", "洪水"),),
    "TEMPORARY_STRUCTURE_FAILURE": (("临时结构", "支架", "脚手架"), ("失稳", "坍塌")),
    "TUNNEL_GEOLOGICAL_RISK": (("隧道",), ("地质", "突水", "涌泥", "塌方")),
}
_PREVENTION_TAG_EVIDENCE_TERM_GROUPS = {
    "HAZARD_IDENTIFICATION": (("隐患识别", "风险辨识", "危险源辨识", "隐患排查"),),
    "MONITORING_AND_EARLY_WARNING": (("监测", "预警"),),
    "INSPECTION_AND_MAINTENANCE": (("排查", "巡查", "养护", "维护"),),
    "DESIGN_REVIEW": (("设计复核", "设计审查"),),
    "CONSTRUCTION_QUALITY_CONTROL": (("施工质量", "质量控制"),),
    "EMERGENCY_PREPAREDNESS": (("应急预案", "应急准备", "应急演练"),),
    "TRAFFIC_OPERATION_RISK_CONTROL": (("交通管控", "运营安全", "交通安全"),),
    "RESPONSIBILITY_AND_OVERSIGHT": (("责任", "监管", "监督"),),
}
_RECTIFICATION_BOOLEAN_EVIDENCE_TERMS = {
    True: ("仍然存在", "尚未完成", "未完成", "薄弱环节", "仍有问题", "整改中"),
    False: ("已完成", "全部落实", "完成闭环", "无未解决问题"),
}


class PostgresPublicationRepository:
    """The only repository configured with the dedicated publication writer role."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def request_event_identity_change(
        self,
        *,
        operation: str,
        event_ids: list[UUID],
        canonical_event_id: UUID | None,
        allocations: Mapping[UUID, UUID],
        submitted_by: UUID,
        reason: str,
        created_at: datetime,
    ) -> UUID:
        request_id = uuid7()
        async with self._engine.begin() as connection:
            existing = set(
                (
                    await connection.scalars(
                        text("SELECT id FROM event WHERE id=ANY(CAST(:ids AS uuid[])) FOR SHARE"),
                        {"ids": event_ids},
                    )
                ).all()
            )
            if existing != set(event_ids):
                raise PublicationDenied(("EVENT_IDENTITY_TARGET_NOT_FOUND",))
            await connection.execute(
                text(
                    """
                    INSERT INTO event_identity_change_request
                      (id,operation,status,reason,submitted_by,created_at)
                    VALUES (:id,:operation,'PENDING',:reason,:submitted_by,:created_at)
                    """
                ),
                {
                    "id": request_id,
                    "operation": operation,
                    "reason": reason,
                    "submitted_by": submitted_by,
                    "created_at": created_at,
                },
            )
            for event_id in event_ids:
                role = "TARGET"
                if operation == "MERGE":
                    role = "CANONICAL" if event_id == canonical_event_id else "ALIAS"
                elif operation == "SPLIT":
                    role = "SOURCE" if event_id == canonical_event_id else "CHILD"
                await connection.execute(
                    text(
                        "INSERT INTO event_identity_change_target "
                        "(request_id,event_id,target_role) VALUES (:request_id,:event_id,:role)"
                    ),
                    {"request_id": request_id, "event_id": event_id, "role": role},
                )
            for item_id, child_event_id in allocations.items():
                await connection.execute(
                    text(
                        "INSERT INTO event_split_allocation "
                        "(request_id,item_id,child_event_id,created_at) "
                        "VALUES (:request_id,:item_id,:child_event_id,:created_at)"
                    ),
                    {
                        "request_id": request_id,
                        "item_id": item_id,
                        "child_event_id": child_event_id,
                        "created_at": created_at,
                    },
                )
            await _append_audit(
                connection,
                event_type=f"EVENT_IDENTITY_{operation}_REQUESTED",
                actor_id=submitted_by,
                target_type="event_identity_change_request",
                target_id=request_id,
                after_state={"event_ids": [str(value) for value in event_ids]},
                reason=reason,
                request_id=str(request_id),
                now=created_at,
            )
        return request_id

    async def decide_event_identity_change(
        self,
        *,
        request_id: UUID,
        approve: bool,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            request = (
                (
                    await connection.execute(
                        text(
                            "SELECT operation,submitted_by,status "
                            "FROM event_identity_change_request "
                            "WHERE id=:request_id FOR UPDATE"
                        ),
                        {"request_id": request_id},
                    )
                )
                .mappings()
                .first()
            )
            if request is None or request["status"] != "PENDING":
                raise PublicationDenied(("EVENT_IDENTITY_REQUEST_NOT_PENDING",))
            if request["submitted_by"] == reviewer_id:
                raise PublicationDenied(("EVENT_IDENTITY_SEPARATION_OF_DUTIES",))
            decision_label = "APPROVED" if approve else "REJECTED"
            audit_id = await _append_audit(
                connection,
                event_type=f"EVENT_IDENTITY_{request['operation']}_{decision_label}",
                actor_id=reviewer_id,
                target_type="event_identity_change_request",
                target_id=request_id,
                after_state={"approved": approve},
                reason=reason,
                request_id=str(request_id),
                now=decided_at,
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO event_identity_change_decision
                      (id,request_id,decision,reviewer_id,submitted_by,audit_log_id,created_at)
                    VALUES (
                      :id,:request_id,:decision,:reviewer_id,
                      :submitted_by,:audit_id,:created_at
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "request_id": request_id,
                    "decision": "APPROVE" if approve else "REJECT",
                    "reviewer_id": reviewer_id,
                    "submitted_by": request["submitted_by"],
                    "audit_id": audit_id,
                    "created_at": decided_at,
                },
            )
            if approve:
                await _apply_event_identity_change(
                    connection, request_id=request_id, operation=str(request["operation"])
                )
            await connection.execute(
                text(
                    "UPDATE event_identity_change_request SET status=:status WHERE id=:request_id"
                ),
                {"status": "APPLIED" if approve else "REJECTED", "request_id": request_id},
            )

    async def build_internal_projection(self, *, actor_id: UUID, generated_at: datetime) -> Any:
        from srbg_api.internal_projection.backfill import backfill_internal_projection

        return await backfill_internal_projection(
            self._engine,
            actor_id=actor_id,
            now=generated_at,
        )

    async def internal_projection_metrics(self) -> dict[str, float]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              COALESCE((
                                SELECT difference_count
                                  FROM published_v1.projection_build_run
                                 WHERE status = 'SUCCEEDED'
                                 ORDER BY generation DESC LIMIT 1
                              ), 0) AS differences,
                              COALESCE(EXTRACT(EPOCH FROM (
                                SELECT completed_at
                                  FROM published_v1.projection_build_run
                                 WHERE status = 'SUCCEEDED'
                                 ORDER BY generation DESC LIMIT 1
                              )), 0) AS projection_timestamp,
                              COALESCE(EXTRACT(EPOCH FROM (
                                SELECT max(anchored_at) FROM audit_chain_anchor
                              )), 0) AS anchor_timestamp
                            """
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

    async def create_daily_draft(
        self,
        *,
        report_date: date,
        actor_id: UUID,
        idempotency_key: str,
        created_at: datetime,
    ) -> DailyReport:
        request_hash = sha256(report_date.isoformat().encode()).hexdigest()
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT request_sha256, response_id FROM idempotency_record "
                            "WHERE owner_id = :actor_id AND scope = 'DAILY_DRAFT' "
                            "AND idempotency_key = :key FOR UPDATE"
                        ),
                        {"actor_id": actor_id, "key": idempotency_key},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if existing["request_sha256"] != request_hash:
                    raise PublicationDenied(("IDEMPOTENCY_KEY_REUSED",))
                return await self._load_daily_report(
                    connection, cast(UUID, existing["response_id"])
                )

            report_id = uuid7()
            await connection.execute(
                text(
                    """
                    INSERT INTO daily_report (
                      id, report_date, status, snapshot_at, published_at, created_by,
                      reviewer_id, requires_regeneration, version
                    ) VALUES (:id, :report_date, 'DRAFT', :now, NULL, :actor_id, NULL, false, 1)
                    """
                ),
                {
                    "id": report_id,
                    "report_date": report_date,
                    "now": created_at,
                    "actor_id": actor_id,
                },
            )
            candidates = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT projection.event_id, projection.event_revision_id,
                              projection.publication_revision_id,
                              projection.summary_payload->>'domain' AS domain,
                              projection.summary_payload->>'title' AS title,
                              projection.summary_payload->>'original_url' AS original_url,
                              projection.summary_payload->>'one_sentence_fact' AS summary
                            FROM published_v1.event_projection_revision projection
                            WHERE projection.state='ACTIVE'
                              AND projection.projection_level='FULL'
                              AND projection.generation=(
                                SELECT max(current_projection.generation)
                                FROM published_v1.event_projection_revision current_projection
                                WHERE current_projection.event_id=projection.event_id
                                  AND current_projection.state='ACTIVE'
                              )
                            ORDER BY projection.generated_at DESC, projection.event_id DESC
                            LIMIT 30
                            """
                        )
                    )
                )
                .mappings()
                .all()
            )
            used: set[UUID] = set()
            sections: list[tuple[str, RowMapping]] = []

            def add(section: str, rows: list[RowMapping], count: int) -> None:
                for row in rows:
                    event_id = cast(UUID, row["event_id"])
                    if event_id in used:
                        continue
                    used.add(event_id)
                    sections.append((section, row))
                    if sum(1 for name, _ in sections if name == section) >= count:
                        break

            add("TODAY_HIGHLIGHTS", candidates, 5)
            add("DIGITAL_SELECTED", [row for row in candidates if row["domain"] == "DIGITAL"], 5)
            add("SAFETY_HIGHLIGHTS", [row for row in candidates if row["domain"] == "SAFETY"], 5)
            add("WATCHLIST", candidates, 5)
            positions: dict[str, int] = {}
            for section, row in sections:
                positions[section] = positions.get(section, 0) + 1
                await connection.execute(
                    text(
                        """
                        INSERT INTO daily_report_item (
                          report_id, section, position, event_id,
                          publication_revision_id, event_revision_id,
                          title, summary, original_url
                        ) VALUES (
                          :report_id, :section, :position, :event_id,
                          :revision_id, :event_revision_id,
                          :title, :summary, :original_url
                        )
                        """
                    ),
                    {
                        "report_id": report_id,
                        "section": section,
                        "position": positions[section],
                        "event_id": row["event_id"],
                        "revision_id": row["publication_revision_id"],
                        "event_revision_id": row["event_revision_id"],
                        "title": row["title"],
                        "summary": row["summary"],
                        "original_url": row["original_url"],
                    },
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO idempotency_record (
                      owner_id, scope, idempotency_key, request_sha256, response_id, created_at
                    ) VALUES (:actor_id, 'DAILY_DRAFT', :key, :request_hash, :report_id, :now)
                    """
                ),
                {
                    "actor_id": actor_id,
                    "key": idempotency_key,
                    "request_hash": request_hash,
                    "report_id": report_id,
                    "now": created_at,
                },
            )
            return await self._load_daily_report(connection, report_id)

    async def publish_daily_report(
        self,
        *,
        report_id: UUID,
        reviewer_id: UUID,
        idempotency_key: str,
        published_at: datetime,
    ) -> DailyReport:
        request_hash = sha256(str(report_id).encode()).hexdigest()
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT request_sha256, response_id FROM idempotency_record "
                            "WHERE owner_id = :reviewer_id AND scope = 'DAILY_PUBLISH' "
                            "AND idempotency_key = :key FOR UPDATE"
                        ),
                        {"reviewer_id": reviewer_id, "key": idempotency_key},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if existing["request_sha256"] != request_hash:
                    raise PublicationDenied(("IDEMPOTENCY_KEY_REUSED",))
                return await self._load_daily_report(
                    connection, cast(UUID, existing["response_id"])
                )
            report = (
                (
                    await connection.execute(
                        text("SELECT * FROM daily_report WHERE id = :id FOR UPDATE"),
                        {"id": report_id},
                    )
                )
                .mappings()
                .first()
            )
            if report is None or report["status"] != "DRAFT":
                raise PublicationDenied(("DAILY_REPORT_NOT_DRAFT",))
            if report["requires_regeneration"]:
                raise PublicationDenied(("DAILY_REPORT_REGENERATION_REQUIRED",))
            item_count = int(
                await connection.scalar(
                    text("SELECT count(*) FROM daily_report_item WHERE report_id = :id"),
                    {"id": report_id},
                )
                or 0
            )
            if item_count == 0:
                raise PublicationDenied(("DAILY_REPORT_EMPTY",))
            invalid_count = int(
                await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM daily_report_item dri
                        LEFT JOIN publication p ON p.item_id = dri.item_id
                        LEFT JOIN publication_revision pr ON pr.id = dri.publication_revision_id
                        LEFT JOIN search_projection sp ON sp.item_id = dri.item_id
                        WHERE dri.report_id = :id AND (
                          p.status <> 'PUBLISHED'
                          OR p.current_revision_id <> dri.publication_revision_id
                          OR NOT pr.valid OR NOT sp.visible OR sp.risk_level = 'R4'
                          OR EXISTS (
                            SELECT 1 FROM publication_projection_invalidation pi
                            WHERE pi.revision_id = dri.publication_revision_id
                              AND pi.status = 'PENDING'
                          )
                        )
                        """
                    ),
                    {"id": report_id},
                )
                or 0
            )
            if invalid_count:
                raise PublicationDenied(("DAILY_REPORT_ITEM_NOT_CURRENT",))
            await connection.execute(
                text(
                    "UPDATE daily_report SET status = 'PUBLISHED', published_at = :now, "
                    "reviewer_id = :reviewer_id, version = version + 1 WHERE id = :id"
                ),
                {"now": published_at, "reviewer_id": reviewer_id, "id": report_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO idempotency_record (owner_id, scope, idempotency_key, "
                    "request_sha256, response_id, created_at) VALUES "
                    "(:reviewer_id, 'DAILY_PUBLISH', :key, :request_hash, :id, :now)"
                ),
                {
                    "reviewer_id": reviewer_id,
                    "key": idempotency_key,
                    "request_hash": request_hash,
                    "id": report_id,
                    "now": published_at,
                },
            )
            await _append_audit(
                connection,
                event_type="DAILY_REPORT_PUBLISHED",
                actor_id=reviewer_id,
                target_type="daily_report",
                target_id=report_id,
                after_state={"status": "PUBLISHED", "item_count": item_count},
                reason="DAILY_REVIEW_APPROVED",
                request_id=f"daily:{idempotency_key[:80]}",
                now=published_at,
            )
            return await self._load_daily_report(connection, report_id)

    @staticmethod
    async def _load_daily_report(connection: AsyncConnection, report_id: UUID) -> DailyReport:
        report = (
            (
                await connection.execute(
                    text("SELECT * FROM daily_report WHERE id = :id"), {"id": report_id}
                )
            )
            .mappings()
            .one()
        )
        items = list(
            (
                await connection.execute(
                    text(
                        """
                        SELECT dri.*, CASE WHEN p.status = 'WITHDRAWN'
                          THEN 'WITHDRAWN' ELSE 'PUBLISHED' END AS current_state
                        FROM daily_report_item dri
                        JOIN publication p ON p.item_id = dri.item_id
                        WHERE dri.report_id = :id ORDER BY dri.section, dri.position
                        """
                    ),
                    {"id": report_id},
                )
            )
            .mappings()
            .all()
        )
        return daily_report_from_rows(report, items)

    async def list_claim_conflicts(self) -> list[ClaimConflict]:
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT conflict.id, conflict.event_id, conflict.field_name,
                                   conflict.current_claim_id,
                                   conflict.current_value_snapshot,
                                   conflict.candidate_claim_id,
                                   conflict.candidate_value_snapshot,
                                   conflict.status, conflict.detected_at,
                                   decision.chosen_claim_id AS resolved_claim_id,
                                   decision.reviewer_id AS resolved_by,
                                   decision.created_at AS resolved_at,
                                   decision.reason AS resolution_reason
                            FROM claim_conflict conflict
                            LEFT JOIN LATERAL (
                                SELECT candidate.chosen_claim_id, candidate.reviewer_id,
                                       candidate.created_at, candidate.reason
                                FROM claim_conflict_decision candidate
                                WHERE candidate.conflict_id = conflict.id
                                  AND candidate.action IN (
                                    'ACCEPT_CANDIDATE','KEEP_CURRENT'
                                  )
                                ORDER BY candidate.created_at DESC, candidate.id DESC
                                LIMIT 1
                            ) decision ON true
                            ORDER BY (conflict.status = 'PENDING_REVIEW') DESC,
                                     conflict.detected_at, conflict.id
                            """
                        )
                    )
                ).mappings()
            )
        return [
            ClaimConflict(
                id=row["id"],
                event_id=row["event_id"],
                field=_critical_conflict_field(str(row["field_name"])),
                current_claim_id=row["current_claim_id"],
                current_value=row["current_value_snapshot"],
                candidate_claim_id=row["candidate_claim_id"],
                candidate_value=row["candidate_value_snapshot"],
                status=row["status"],
                detected_at=row["detected_at"],
                resolved_claim_id=row["resolved_claim_id"],
                resolved_by=row["resolved_by"],
                resolved_at=row["resolved_at"],
                resolution_reason=row["resolution_reason"],
            )
            for row in rows
        ]

    async def process_outbox_once(self, *, processed_at: datetime) -> bool:
        event_id: UUID | None = None
        try:
            async with self._engine.begin() as connection:
                event = (
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT id, event_type, aggregate_id, payload
                                FROM outbox_event
                                WHERE status IN ('PENDING','FAILED')
                                  AND available_at <= :now
                                  AND attempt_count < 5
                                ORDER BY available_at, id
                                FOR UPDATE SKIP LOCKED LIMIT 1
                                """
                            ),
                            {"now": processed_at},
                        )
                    )
                    .mappings()
                    .first()
                )
                if event is None:
                    return False
                event_id = cast(UUID, event["id"])
                await _process_outbox_event(connection, event=event, now=processed_at)
                await connection.execute(
                    text(
                        """
                        UPDATE outbox_event
                        SET status = 'PROCESSED', processed_at = :now,
                            attempt_count = attempt_count + 1, last_error_code = NULL
                        WHERE id = :id
                        """
                    ),
                    {"id": event_id, "now": processed_at},
                )
                return True
        except Exception as error:
            if event_id is None:
                raise
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        UPDATE outbox_event
                        SET attempt_count = attempt_count + 1,
                            status = CASE WHEN attempt_count + 1 >= 5
                                THEN 'DEAD_LETTER' ELSE 'FAILED' END,
                            available_at = CAST(:now AS timestamptz)
                                + ((attempt_count + 1) * interval '5 seconds'),
                            last_error_code = :error_code
                        WHERE id = :id AND status IN ('PENDING','FAILED')
                        """
                    ),
                    {
                        "id": event_id,
                        "now": processed_at,
                        "error_code": type(error).__name__[:100],
                    },
                )
            return True

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
                            """
                            SELECT id, publication_id, projection, action, generation
                            FROM publication_projection_invalidation
                            WHERE status = 'PENDING'
                            ORDER BY created_at, id
                            FOR UPDATE SKIP LOCKED LIMIT 1
                            """
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
                    """
                    UPDATE publication_projection_invalidation
                    SET status = 'APPLIED', applied_at = :processed_at
                    WHERE id = :event_id AND status = 'PENDING'
                    """
                ),
                {"event_id": event["id"], "processed_at": processed_at},
            )
            return True

    async def decide_cluster(
        self,
        *,
        candidate_id: UUID,
        candidate_kind: str,
        action: str,
        member_ids: list[UUID],
        relation_type: str | None,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None:
        if not reason.strip():
            raise PublicationDenied(("CLUSTER_DECISION_REASON_REQUIRED",))
        if len(set(member_ids)) < 2:
            raise PublicationDenied(("CLUSTER_MEMBERS_INVALID",))
        decision_id = uuid7()
        async with self._engine.begin() as connection:
            if candidate_kind == "DUPLICATE":
                candidate = (
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT id, left_item_id, right_item_id, hard_conflicts, status
                                FROM duplicate_candidate
                                WHERE id = :candidate_id FOR UPDATE
                                """
                            ),
                            {"candidate_id": candidate_id},
                        )
                    )
                    .mappings()
                    .first()
                )
                if candidate is None or candidate["status"] != "PENDING_REVIEW":
                    raise PublicationDenied(("DUPLICATE_CANDIDATE_NOT_PENDING",))
                expected = {candidate["left_item_id"], candidate["right_item_id"]}
                if set(member_ids) != expected:
                    raise PublicationDenied(("DUPLICATE_CANDIDATE_MEMBERS_MISMATCH",))
                if action == "MERGE" and candidate["hard_conflicts"]:
                    raise PublicationDenied(("DUPLICATE_HARD_CONSTRAINT_BLOCKED",))
                await connection.execute(
                    text(
                        """
                        INSERT INTO duplicate_decision (
                            id, candidate_id, action, relation_type, reason,
                            reviewed_by, reviewed_at
                        ) VALUES (
                            :id, :candidate_id, :action, :relation_type, :reason,
                            :reviewer_id, :decided_at
                        )
                        """
                    ),
                    {
                        "id": decision_id,
                        "candidate_id": candidate_id,
                        "action": action,
                        "relation_type": relation_type,
                        "reason": reason.strip(),
                        "reviewer_id": reviewer_id,
                        "decided_at": decided_at,
                    },
                )
                await connection.execute(
                    text(
                        "UPDATE duplicate_candidate SET status = :status WHERE id = :candidate_id"
                    ),
                    {
                        "status": "REJECTED" if action == "KEEP_DISTINCT" else "ACCEPTED",
                        "candidate_id": candidate_id,
                    },
                )
                if action == "MERGE":
                    canonical, duplicate = sorted(member_ids, key=str)
                    await connection.execute(
                        text(
                            """
                            INSERT INTO duplicate_link (
                                id, canonical_item_id, duplicate_item_id, decision_id, linked_at
                            ) VALUES (:id, :canonical, :duplicate, :decision_id, :decided_at)
                            """
                        ),
                        {
                            "id": uuid7(),
                            "canonical": canonical,
                            "duplicate": duplicate,
                            "decision_id": decision_id,
                            "decided_at": decided_at,
                        },
                    )
            elif candidate_kind == "EVENT":
                await _decide_event_item_candidate(
                    connection,
                    candidate_id=candidate_id,
                    action="ACCEPT" if action == "MERGE" else "REJECT",
                    reviewer_id=reviewer_id,
                    reason=reason.strip(),
                    decided_at=decided_at,
                )
            elif candidate_kind == "RELATION":
                await _decide_event_relation_candidate(
                    connection,
                    candidate_id=candidate_id,
                    action="ACCEPT" if action == "LINK_RELATION" else "REJECT",
                    reviewer_id=reviewer_id,
                    reason=reason.strip(),
                    decided_at=decided_at,
                )
            elif candidate_kind == "TOPIC":
                topic_status = "CONFIRMED" if action == "MERGE" else "REJECTED"
                updated = await connection.execute(
                    text(
                        """
                        UPDATE topic_cluster SET status = :status, updated_at = :decided_at
                        WHERE id = :candidate_id AND status = 'PENDING_REVIEW'
                        """
                    ),
                    {
                        "status": topic_status,
                        "decided_at": decided_at,
                        "candidate_id": candidate_id,
                    },
                )
                if updated.rowcount != 1:
                    raise PublicationDenied(("TOPIC_CANDIDATE_NOT_PENDING",))
            await connection.execute(
                text(
                    """
                    INSERT INTO cluster_decision (
                        id, candidate_kind, candidate_id, action, member_ids,
                        relation_type, reason, reviewed_by, reviewed_at
                    ) VALUES (
                        :id, :candidate_kind, :candidate_id, :action, :member_ids,
                        :relation_type, :reason, :reviewer_id, :decided_at
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "candidate_kind": candidate_kind,
                    "candidate_id": candidate_id,
                    "action": action,
                    "member_ids": member_ids,
                    "relation_type": relation_type,
                    "reason": reason.strip(),
                    "reviewer_id": reviewer_id,
                    "decided_at": decided_at,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO resolution_regression_sample (
                        id, sample_kind, decision_id, payload, created_at
                    ) VALUES (
                        :id, :sample_kind, :decision_id, CAST(:payload AS jsonb), :created_at
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "sample_kind": candidate_kind,
                    "decision_id": decision_id,
                    "payload": _json(
                        {
                            "candidate_id": str(candidate_id),
                            "action": action,
                            "member_ids": [str(value) for value in member_ids],
                            "relation_type": relation_type,
                        }
                    ),
                    "created_at": decided_at,
                },
            )
            await _append_audit(
                connection,
                event_type=f"CLUSTER_{candidate_kind}_{action}",
                actor_id=reviewer_id,
                target_type="cluster_candidate",
                target_id=candidate_id,
                after_state={"member_ids": [str(value) for value in member_ids]},
                reason=reason.strip(),
                request_id=str(candidate_id),
                now=decided_at,
            )

    async def override_score(
        self,
        *,
        item_id: UUID,
        dimension: object,
        score: int,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None:
        if not reason.strip():
            raise PublicationDenied(("SCORE_OVERRIDE_REASON_REQUIRED",))
        dimension_value = getattr(dimension, "value", str(dimension))
        async with self._engine.begin() as connection:
            score_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT dimension.id
                            FROM score_set score_set
                            JOIN score_dimension dimension
                              ON dimension.score_set_id = score_set.id
                            WHERE score_set.item_id = :item_id
                              AND score_set.is_current
                              AND dimension.dimension = :dimension
                            ORDER BY score_set.calculated_at DESC, score_set.id DESC
                            LIMIT 1 FOR UPDATE OF dimension
                            """
                        ),
                        {"item_id": item_id, "dimension": dimension_value},
                    )
                )
                .mappings()
                .first()
            )
            if score_row is None:
                raise PublicationDenied(("SCORE_DIMENSION_NOT_AVAILABLE",))
            previous_id = await connection.scalar(
                text(
                    """
                    SELECT id FROM score_override
                    WHERE score_dimension_id = :score_dimension_id
                    ORDER BY reviewed_at DESC, id DESC LIMIT 1
                    """
                ),
                {"score_dimension_id": score_row["id"]},
            )
            override_id = uuid7()
            await connection.execute(
                text(
                    """
                    INSERT INTO score_override (
                        id, score_dimension_id, score, reason, reviewed_by,
                        reviewed_at, supersedes_override_id
                    ) VALUES (
                        :id, :score_dimension_id, :score, :reason, :reviewer_id,
                        :reviewed_at, :previous_id
                    )
                    """
                ),
                {
                    "id": override_id,
                    "score_dimension_id": score_row["id"],
                    "score": score,
                    "reason": reason.strip(),
                    "reviewer_id": reviewer_id,
                    "reviewed_at": decided_at,
                    "previous_id": previous_id,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO resolution_regression_sample (
                        id, sample_kind, decision_id, payload, created_at
                    ) VALUES (:id, 'SCORE', :decision_id, CAST(:payload AS jsonb), :created_at)
                    """
                ),
                {
                    "id": uuid7(),
                    "decision_id": override_id,
                    "payload": _json(
                        {"item_id": str(item_id), "dimension": dimension_value, "score": score}
                    ),
                    "created_at": decided_at,
                },
            )
            await _append_audit(
                connection,
                event_type="SCORE_OVERRIDE_CREATED",
                actor_id=reviewer_id,
                target_type="intelligence_item",
                target_id=item_id,
                after_state={"dimension": dimension_value, "score": score},
                reason=reason.strip(),
                request_id=str(override_id),
                now=decided_at,
            )

    @asynccontextmanager
    async def approval_transaction(
        self,
        *,
        review_task_id: UUID,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> AsyncIterator[PublicationTransaction]:
        async with self._engine.connect() as connection:
            transaction = await connection.begin()
            try:
                task = await _locked_review_task(connection, review_task_id)
                _validate_pending_review(task, reviewer_id, reason)
                await connection.execute(
                    text(
                        """
                        UPDATE review_task
                        SET status = 'APPROVED', decided_by = :reviewer_id,
                            decided_at = :decided_at, decision_reason = :reason
                        WHERE id = :task_id
                        """
                    ),
                    {
                        "task_id": review_task_id,
                        "reviewer_id": reviewer_id,
                        "decided_at": decided_at,
                        "reason": reason,
                    },
                )
                await _append_review_decision(
                    connection,
                    review_task_id=review_task_id,
                    action="APPROVE",
                    submitted_by=task["submitted_by"],
                    decided_by=reviewer_id,
                    reason=reason,
                    decided_at=decided_at,
                )
                yield _PostgresPublicationTransaction(connection, task)
                await transaction.commit()
            except BaseException:
                await transaction.rollback()
                raise

    async def reject(
        self,
        *,
        review_task_id: UUID,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> ReviewDecisionResponse:
        async with self._engine.begin() as connection:
            task = await _locked_review_task(connection, review_task_id)
            _validate_pending_review(task, reviewer_id, reason)
            await connection.execute(
                text(
                    """
                    UPDATE review_task
                    SET status = 'REJECTED', decided_by = :reviewer_id,
                        decided_at = :decided_at, decision_reason = :reason
                    WHERE id = :task_id
                    """
                ),
                {
                    "task_id": review_task_id,
                    "reviewer_id": reviewer_id,
                    "decided_at": decided_at,
                    "reason": reason,
                },
            )
            await _append_review_decision(
                connection,
                review_task_id=review_task_id,
                action="REJECT",
                submitted_by=task["submitted_by"],
                decided_by=reviewer_id,
                reason=reason,
                decided_at=decided_at,
            )
            await connection.execute(
                text(
                    """
                    UPDATE intelligence_item
                    SET review_status = 'REJECTED', updated_at = :decided_at
                    WHERE id = :item_id
                    """
                ),
                {"item_id": task["item_id"], "decided_at": decided_at},
            )
            await _append_reviewed_version_change_state(
                connection,
                document_version_id=task["document_version_id"],
                state="REJECTED",
                reviewer_id=reviewer_id,
                reason=reason,
                now=decided_at,
            )
            await _append_audit(
                connection,
                event_type="R3_REVIEW_REJECTED",
                actor_id=reviewer_id,
                target_type="review_task",
                target_id=review_task_id,
                after_state={"status": "REJECTED", "item_id": str(task["item_id"])},
                reason=reason,
                request_id=str(review_task_id),
                now=decided_at,
            )
        return ReviewDecisionResponse(
            review_task_id=review_task_id,
            status=ReviewStatus.REJECTED,
            publication_revision_id=None,
        )

    async def withdraw(
        self,
        *,
        publication_id: UUID,
        actor_id: UUID,
        evidence_id: UUID,
        reason: str,
        withdrawn_at: datetime,
    ) -> UUID:
        if not reason.strip():
            raise PublicationDenied(("WITHDRAW_REASON_REQUIRED",))
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT p.id, p.item_id, p.status, p.current_revision_id,
                                   item.item_type, membership.event_id,
                                   r.revision_number, r.document_version_id,
                                   r.source_policy_id, r.source_policy_sha256,
                                   r.review_task_id, r.snapshot, r.evaluation,
                                   task.submitted_by AS original_submitted_by
                            FROM publication p
                            JOIN publication_revision r ON r.id = p.current_revision_id
                            JOIN intelligence_item item ON item.id = p.item_id
                            JOIN review_task task ON task.id = r.review_task_id
                            LEFT JOIN event_item membership ON membership.item_id = p.item_id
                            WHERE p.id = :publication_id
                            FOR UPDATE OF p
                            """
                        ),
                        {"publication_id": publication_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None or row["status"] != "PUBLISHED":
                raise PublicationDenied(("PUBLICATION_NOT_PUBLISHED",))
            official_evidence = await connection.scalar(
                text(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM claim_evidence evidence
                        JOIN claim claim ON claim.id = evidence.claim_id
                        JOIN intelligence_item item ON item.id = claim.item_id
                        JOIN source source ON source.id = item.source_id
                        WHERE evidence.id = :evidence_id
                          AND evidence.document_version_id = :version_id
                          AND claim.item_id = :item_id
                          AND source.authority_level IN ('A0','A1')
                    )
                    """
                ),
                {
                    "evidence_id": evidence_id,
                    "version_id": row["document_version_id"],
                    "item_id": row["item_id"],
                },
            )
            if not official_evidence:
                raise PublicationDenied(("WITHDRAWAL_OFFICIAL_EVIDENCE_REQUIRED",))
            if row["original_submitted_by"] == actor_id:
                raise PublicationDenied(("DUTIES_NOT_SEPARATED",))
            revision_id = uuid7()
            withdrawal_task_id = uuid7()
            evaluation = dict(row["evaluation"])
            await connection.execute(
                text(
                    """
                    INSERT INTO review_task (
                        id, item_id, document_version_id, source_policy_id,
                        risk_level, status, submitted_by, submitted_at,
                        assigned_to, decided_by, decided_at, decision_reason,
                        created_at, task_type
                    ) VALUES (
                        :id, :item_id, :document_version_id, :source_policy_id,
                        'R3', 'APPROVED', :submitted_by, :now,
                        :actor_id, :actor_id, :now, :reason, :now, 'WITHDRAWAL_REVIEW'
                    )
                    """
                ),
                {
                    "id": withdrawal_task_id,
                    "item_id": row["item_id"],
                    "document_version_id": row["document_version_id"],
                    "source_policy_id": row["source_policy_id"],
                    "submitted_by": row["original_submitted_by"],
                    "actor_id": actor_id,
                    "reason": reason.strip(),
                    "now": withdrawn_at,
                },
            )
            await _append_review_decision(
                connection,
                review_task_id=withdrawal_task_id,
                action="WITHDRAW",
                submitted_by=row["original_submitted_by"],
                decided_by=actor_id,
                reason=reason,
                decided_at=withdrawn_at,
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO publication_revision (
                        id, publication_id, revision_number, document_version_id,
                        source_policy_id, source_policy_sha256, review_task_id,
                        snapshot, evaluation, evaluation_sha256, action, valid,
                        created_by, created_at
                    ) VALUES (
                        :id, :publication_id, :revision_number, :document_version_id,
                        :source_policy_id, :source_policy_sha256, :review_task_id,
                        CAST(:snapshot AS jsonb), CAST(:evaluation AS jsonb),
                        :evaluation_sha256, 'WITHDRAW', false, :actor_id, :withdrawn_at
                    )
                    """
                ),
                {
                    "id": revision_id,
                    "publication_id": publication_id,
                    "revision_number": row["revision_number"] + 1,
                    "document_version_id": row["document_version_id"],
                    "source_policy_id": row["source_policy_id"],
                    "source_policy_sha256": row["source_policy_sha256"],
                    "review_task_id": withdrawal_task_id,
                    "snapshot": _json(dict(row["snapshot"])),
                    "evaluation": _json(evaluation),
                    "evaluation_sha256": canonical_json_hash(evaluation),
                    "actor_id": actor_id,
                    "withdrawn_at": withdrawn_at,
                },
            )
            await connection.execute(
                text(
                    """
                    UPDATE publication
                    SET current_revision_id = :revision_id, status = 'WITHDRAWN',
                        withdrawn_at = :withdrawn_at, updated_at = :withdrawn_at
                    WHERE id = :publication_id
                    """
                ),
                {
                    "revision_id": revision_id,
                    "publication_id": publication_id,
                    "withdrawn_at": withdrawn_at,
                },
            )
            await _enqueue_projection_invalidations(
                connection,
                publication_id=publication_id,
                revision_id=revision_id,
                action="WITHDRAW",
                created_at=withdrawn_at,
            )
            await _append_audit(
                connection,
                event_type="PUBLICATION_WITHDRAWN",
                actor_id=actor_id,
                target_type="publication",
                target_id=publication_id,
                after_state={
                    "status": "WITHDRAWN",
                    "revision_id": str(revision_id),
                    "evidence_id": str(evidence_id),
                },
                reason=reason,
                request_id=str(publication_id),
                now=withdrawn_at,
            )
            for target_type, target_id in (
                ("PUBLICATION_REVISION", revision_id),
                ("ITEM", row["item_id"]),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO content_lifecycle_event (
                            id, item_id, target_type, target_id, state,
                            cause_version_change_id, actor_id, reason, metadata, created_at
                        ) VALUES (
                            :id, :item_id, :target_type, :target_id, 'WITHDRAWN',
                            NULL, :actor_id, :reason,
                            CAST(:metadata AS jsonb), :now
                        )
                        """
                    ),
                    {
                        "id": uuid7(),
                        "item_id": row["item_id"],
                        "target_type": target_type,
                        "target_id": target_id,
                        "actor_id": actor_id,
                        "reason": reason,
                        "metadata": _json({"evidence_id": str(evidence_id)}),
                        "now": withdrawn_at,
                    },
                )
            if row["item_type"] == "SAFETY_CASE":
                await _append_safety_case_audit(
                    connection,
                    item_id=row["item_id"],
                    event_id=cast(UUID | None, row["event_id"]),
                    target_type="SAFETY_CASE",
                    target_id=row["item_id"],
                    action="WITHDRAWN",
                    actor_id=actor_id,
                    reason=reason,
                    metadata={
                        "publication_id": str(publication_id),
                        "publication_revision_id": str(revision_id),
                        "evidence_id": str(evidence_id),
                    },
                    now=withdrawn_at,
                )
            return revision_id

    async def decide_candidate(
        self,
        *,
        candidate_kind: str,
        candidate_id: UUID,
        action: str,
        target_document_id: UUID | None,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None:
        if not reason.strip():
            raise PublicationDenied(("CANDIDATE_DECISION_REASON_REQUIRED",))
        async with self._engine.begin() as connection:
            if candidate_kind == "RELATION":
                await _decide_relation_candidate(
                    connection,
                    candidate_id=candidate_id,
                    action=action,
                    target_document_id=target_document_id,
                    reviewer_id=reviewer_id,
                    reason=reason,
                    decided_at=decided_at,
                )
            elif candidate_kind == "REGULATION_STATUS":
                await _decide_regulation_status_candidate(
                    connection,
                    candidate_id=candidate_id,
                    action=action,
                    target_document_id=target_document_id,
                    reviewer_id=reviewer_id,
                    reason=reason,
                    decided_at=decided_at,
                )
            elif candidate_kind == "EVENT_LINK":
                await _decide_event_item_candidate(
                    connection,
                    candidate_id=candidate_id,
                    action=action,
                    reviewer_id=reviewer_id,
                    reason=reason,
                    decided_at=decided_at,
                )
            elif candidate_kind == "EVENT_RELATION":
                await _decide_event_relation_candidate(
                    connection,
                    candidate_id=candidate_id,
                    action=action,
                    reviewer_id=reviewer_id,
                    reason=reason,
                    decided_at=decided_at,
                )
            elif candidate_kind == "CLAIM":
                await _decide_safety_case_claim(
                    connection,
                    claim_id=candidate_id,
                    action=action,
                    reviewer_id=reviewer_id,
                    reason=reason,
                    decided_at=decided_at,
                )
            elif candidate_kind == "PAPER_RELATION":
                await _decide_paper_relation_candidate(
                    connection,
                    candidate_id=candidate_id,
                    action=action,
                    reviewer_id=reviewer_id,
                    reason=reason,
                    decided_at=decided_at,
                )
            else:
                raise PublicationDenied(("UNKNOWN_CANDIDATE_KIND",))

    async def decide_product_normalization(
        self,
        *,
        candidate_id: UUID,
        action: str,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None:
        if not reason.strip():
            raise PublicationDenied(("PRODUCT_NORMALIZATION_REASON_REQUIRED",))
        if action not in {"MERGE_ALIAS", "LINK_AS_NEW_VERSION", "KEEP_DISTINCT"}:
            raise PublicationDenied(("PRODUCT_NORMALIZATION_DECISION_INVALID",))
        async with self._engine.begin() as connection:
            candidate = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id, incoming_version_id, candidate_version_id,
                                   candidate_type, status
                            FROM product_normalization_candidate
                            WHERE id = :candidate_id FOR UPDATE
                            """
                        ),
                        {"candidate_id": candidate_id},
                    )
                )
                .mappings()
                .first()
            )
            if candidate is None or candidate["status"] != "PENDING_REVIEW":
                raise PublicationDenied(("PRODUCT_NORMALIZATION_CANDIDATE_NOT_PENDING",))
            if (
                action == "LINK_AS_NEW_VERSION"
                and candidate["candidate_type"] != "VERSION_SUCCESSOR"
            ):
                raise PublicationDenied(("PRODUCT_VERSION_SUCCESSOR_CANDIDATE_REQUIRED",))
            if action == "LINK_AS_NEW_VERSION":
                await connection.execute(
                    text(
                        """
                        UPDATE technology_product_version
                        SET supersedes_version_id = :candidate_version_id
                        WHERE id = :incoming_version_id
                          AND supersedes_version_id IS NULL
                        """
                    ),
                    {
                        "incoming_version_id": candidate["incoming_version_id"],
                        "candidate_version_id": candidate["candidate_version_id"],
                    },
                )
            terminal_status = "REJECTED" if action == "KEEP_DISTINCT" else "ACCEPTED"
            await connection.execute(
                text(
                    """
                    UPDATE product_normalization_candidate
                    SET status = :status, decision = :decision, reason = :reason,
                        reviewed_by = :reviewer_id, reviewed_at = :decided_at
                    WHERE id = :candidate_id
                    """
                ),
                {
                    "status": terminal_status,
                    "decision": action,
                    "reason": reason.strip(),
                    "reviewer_id": reviewer_id,
                    "decided_at": decided_at,
                    "candidate_id": candidate_id,
                },
            )
            await _append_audit(
                connection,
                event_type=f"PRODUCT_NORMALIZATION_{action}",
                actor_id=reviewer_id,
                target_type="product_normalization_candidate",
                target_id=candidate_id,
                after_state={"status": terminal_status, "decision": action},
                reason=reason.strip(),
                request_id=str(candidate_id),
                now=decided_at,
            )

    async def resolve_claim_conflict(
        self,
        *,
        conflict_id: UUID,
        action: str,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> ClaimConflictDecisionResponse:
        if not reason.strip():
            raise PublicationDenied(("CLAIM_CONFLICT_DECISION_REASON_REQUIRED",))
        if action not in {"ACCEPT_CANDIDATE", "KEEP_CURRENT", "MARK_UNRESOLVED"}:
            raise PublicationDenied(("CLAIM_CONFLICT_DECISION_INVALID",))
        async with self._engine.begin() as connection:
            conflict = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT conflict.id, conflict.event_id, conflict.field_name,
                                   conflict.current_claim_id,
                                   conflict.candidate_claim_id, conflict.status,
                                   candidate_item.submitted_by
                            FROM claim_conflict conflict
                            JOIN claim candidate
                              ON candidate.id = conflict.candidate_claim_id
                            JOIN intelligence_item candidate_item
                              ON candidate_item.id = candidate.item_id
                            WHERE conflict.id = :conflict_id
                            FOR UPDATE OF conflict
                            """
                        ),
                        {"conflict_id": conflict_id},
                    )
                )
                .mappings()
                .first()
            )
            if conflict is None:
                raise PublicationDenied(("CLAIM_CONFLICT_NOT_FOUND",))
            if conflict["status"] != "PENDING_REVIEW":
                raise PublicationDenied(("CLAIM_CONFLICT_NOT_PENDING",))
            chosen_claim_id = (
                conflict["candidate_claim_id"]
                if action == "ACCEPT_CANDIDATE"
                else conflict["current_claim_id"]
                if action == "KEEP_CURRENT"
                else None
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO claim_conflict_decision (
                        id, conflict_id, action, chosen_claim_id, reviewer_id,
                        submitted_by, reason, created_at
                    ) VALUES (
                        :id, :conflict_id, :action, :chosen_claim_id, :reviewer_id,
                        :submitted_by, :reason, :now
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "conflict_id": conflict_id,
                    "action": action,
                    "chosen_claim_id": chosen_claim_id,
                    "reviewer_id": reviewer_id,
                    "submitted_by": conflict["submitted_by"],
                    "reason": reason,
                    "now": decided_at,
                },
            )
            conflict_status = ClaimConflictStatus.PENDING_REVIEW
            if chosen_claim_id is not None:
                await connection.execute(
                    text(
                        """
                        UPDATE claim_conflict
                        SET status = 'RESOLVED', public_value_available = true,
                            updated_at = :now
                        WHERE id = :conflict_id
                        """
                    ),
                    {"conflict_id": conflict_id, "now": decided_at},
                )
                await _restore_safety_case_profile_value(
                    connection,
                    claim_id=cast(UUID, chosen_claim_id),
                    decided_at=decided_at,
                )
                conflict_status = ClaimConflictStatus.RESOLVED
            else:
                await connection.execute(
                    text("UPDATE claim_conflict SET updated_at = :now WHERE id = :conflict_id"),
                    {"conflict_id": conflict_id, "now": decided_at},
                )
            await _append_safety_case_audit(
                connection,
                event_id=conflict["event_id"],
                item_id=None,
                target_type="CLAIM_CONFLICT",
                target_id=conflict_id,
                action=(
                    "CONFLICT_RESOLVED"
                    if conflict_status is ClaimConflictStatus.RESOLVED
                    else "UPDATED"
                ),
                actor_id=reviewer_id,
                reason=reason,
                metadata={"decision": action, "chosen_claim_id": str(chosen_claim_id or "")},
                now=decided_at,
            )
            return ClaimConflictDecisionResponse(
                conflict_id=conflict_id,
                status=conflict_status,
                action=ClaimConflictDecisionAction(action),
                resolved_claim_id=chosen_claim_id,
                resolved_at=(
                    decided_at if conflict_status is ClaimConflictStatus.RESOLVED else None
                ),
            )

    async def escalate_version_change(
        self,
        *,
        version_change_id: UUID,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None:
        if not reason.strip():
            raise PublicationDenied(("VERSION_CHANGE_REASON_REQUIRED",))
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT change.id, change.change_type, change.material,
                                   change.to_document_version_id, item.id AS item_id,
                                   item.current_document_version_id,
                                   task.source_policy_id, task.submitted_by
                            FROM version_change change
                            JOIN document document ON document.id = change.document_id
                            JOIN intelligence_item item
                              ON item.primary_document_id = document.id
                            JOIN LATERAL (
                                SELECT review.source_policy_id, review.submitted_by
                                FROM review_task review
                                WHERE review.item_id = item.id
                                ORDER BY review.submitted_at DESC, review.id DESC LIMIT 1
                            ) task ON true
                            WHERE change.id = :change_id
                            FOR UPDATE OF change, item
                            """
                        ),
                        {"change_id": version_change_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise PublicationDenied(("VERSION_CHANGE_NOT_FOUND",))
            if row["change_type"] != "METADATA_ONLY" or row["material"]:
                raise PublicationDenied(("VERSION_CHANGE_CANNOT_BE_DOWNGRADED",))
            if row["current_document_version_id"] != row["to_document_version_id"]:
                raise PublicationDenied(("VERSION_CHANGE_NOT_CURRENT",))
            latest_material = await connection.scalar(
                text(
                    """
                    SELECT material FROM version_change_state_event
                    WHERE version_change_id = :change_id
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """
                ),
                {"change_id": version_change_id},
            )
            if latest_material is True:
                raise PublicationDenied(("VERSION_CHANGE_ALREADY_MATERIAL",))
            await connection.execute(
                text(
                    """
                    INSERT INTO version_change_state_event (
                        id, version_change_id, state, change_type, material,
                        resolved_change_type, reviewer_id, reason, created_at
                    ) VALUES (
                        :id, :change_id, 'RE_REVIEW_PENDING', 'CONTENT_UPDATE', true,
                        NULL, :reviewer_id, :reason, :now
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "change_id": version_change_id,
                    "reviewer_id": reviewer_id,
                    "reason": reason,
                    "now": decided_at,
                },
            )
            task_id = uuid7()
            await connection.execute(
                text(
                    """
                    INSERT INTO review_task (
                        id, item_id, document_version_id, source_policy_id, risk_level,
                        status, submitted_by, submitted_at, created_at
                    ) VALUES (
                        :id, :item_id, :version_id, :policy_id, 'R3',
                        'PENDING', :submitted_by, :now, :now
                    )
                    """
                ),
                {
                    "id": task_id,
                    "item_id": row["item_id"],
                    "version_id": row["to_document_version_id"],
                    "policy_id": row["source_policy_id"],
                    "submitted_by": row["submitted_by"],
                    "now": decided_at,
                },
            )
            await connection.execute(
                text(
                    """
                    UPDATE intelligence_item
                    SET processing_status = 'READY_FOR_REVIEW', review_status = 'PENDING',
                        updated_at = :now
                    WHERE id = :item_id
                    """
                ),
                {"item_id": row["item_id"], "now": decided_at},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO outbox_event (
                        id, event_type, aggregate_type, aggregate_id, payload,
                        status, attempt_count, available_at, created_at
                    ) VALUES (
                        :id, 'DOCUMENT_VERSION_UPDATE_DETECTED', 'intelligence_item',
                        :item_id, CAST(:payload AS jsonb), 'PENDING', 0, :now, :now
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "item_id": row["item_id"],
                    "payload": _json(
                        {
                            "item_id": str(row["item_id"]),
                            "version_change_id": str(version_change_id),
                            "document_version_id": str(row["to_document_version_id"]),
                            "review_task_id": str(task_id),
                        }
                    ),
                    "now": decided_at,
                },
            )
            await _append_audit(
                connection,
                event_type="VERSION_CHANGE_ESCALATED",
                actor_id=reviewer_id,
                target_type="version_change",
                target_id=version_change_id,
                after_state={"material": True, "review_state": "RE_REVIEW_PENDING"},
                reason=reason,
                request_id=str(version_change_id),
                now=decided_at,
            )


async def _process_outbox_event(
    connection: AsyncConnection,
    *,
    event: RowMapping,
    now: datetime,
) -> None:
    payload = dict(event["payload"])
    event_type = cast(str, event["event_type"])
    item_id = UUID(str(payload["item_id"]))
    version_change_id = UUID(str(payload["version_change_id"]))
    document_version_id = UUID(str(payload["document_version_id"]))
    if event_type == "DOCUMENT_VERSION_UPDATE_DETECTED":
        await _append_update_lifecycle_events(
            connection,
            item_id=item_id,
            version_change_id=version_change_id,
            current_document_version_id=document_version_id,
            now=now,
        )
        return
    if event_type == "DOCUMENT_METADATA_REVISION_READY":
        metadata_published = await _publish_metadata_revision(
            connection,
            item_id=item_id,
            current_document_version_id=document_version_id,
            version_change_id=version_change_id,
            now=now,
        )
        if metadata_published:
            await _append_current_claim_lifecycle_events(
                connection,
                item_id=item_id,
                current_document_version_id=document_version_id,
                state="ACTIVE",
                reason="Metadata-only claims were re-anchored to the current version",
                version_change_id=version_change_id,
                now=now,
            )
        return
    raise RuntimeError("UNSUPPORTED_OUTBOX_EVENT")


class _PostgresPublicationTransaction:
    def __init__(self, connection: AsyncConnection, task: RowMapping) -> None:
        self._connection = connection
        self._task = task
        self._context: dict[str, Any] | None = None
        self._facts: RowMapping | None = None

    async def apply_digital_case_patch(self, patch: DigitalCaseReviewPatch) -> None:
        taxonomy_reasons = validate_taxonomy(
            engineering_domains=patch.engineering_domains,
            lifecycle_stages=patch.lifecycle_stages,
            technology_tags=patch.technology_tags,
            application_scenarios=patch.application_scenarios,
        )
        if taxonomy_reasons:
            raise PublicationDenied(taxonomy_reasons)
        profile = (
            (
                await self._connection.execute(
                    text(
                        """
                        SELECT profile.*, item.current_document_version_id
                        FROM digital_case_profile profile
                        JOIN intelligence_item item ON item.id = profile.item_id
                        WHERE profile.item_id = :item_id
                          AND item.item_type = 'DIGITAL_CASE'
                        FOR UPDATE
                        """
                    ),
                    {"item_id": self._task["item_id"]},
                )
            )
            .mappings()
            .first()
        )
        if profile is None:
            raise PublicationDenied(("DIGITAL_CASE_PROFILE_REQUIRED",))

        requested = {
            "ENGINEERING_DOMAIN": patch.engineering_domains,
            "LIFECYCLE_STAGE": patch.lifecycle_stages,
            "TECHNOLOGY_TAG": patch.technology_tags,
            "APPLICATION_SCENARIO": patch.application_scenarios,
        }
        claim_rows = list(
            (
                await self._connection.execute(
                    text(
                        """
                        SELECT id, literal_value
                        FROM claim
                        WHERE item_id = :item_id
                          AND document_version_id = :version_id
                          AND verification_status = 'ACCEPTED'
                        """
                    ),
                    {
                        "item_id": self._task["item_id"],
                        "version_id": profile["current_document_version_id"],
                    },
                )
            ).mappings()
        )
        authorized: dict[tuple[str, str], UUID] = {}
        for claim in claim_rows:
            value = claim["literal_value"]
            if isinstance(value, Mapping):
                facet = value.get("facet")
                code = value.get("code")
                if isinstance(facet, str) and isinstance(code, str):
                    authorized[(facet, code)] = claim["id"]
        missing = [
            f"{facet}:{code}"
            for facet, codes in requested.items()
            for code in codes
            if (facet, code) not in authorized
        ]
        if missing:
            raise PublicationDenied(("DIGITAL_CLASSIFICATION_EVIDENCE_REQUIRED",))

        maturity_evidence = set(patch.maturity_evidence_ids)
        if maturity_evidence:
            authorized_evidence = set(
                await self._connection.scalars(
                    text(
                        """
                        SELECT evidence.id
                        FROM claim_evidence evidence
                        JOIN claim ON claim.id = evidence.claim_id
                        WHERE claim.item_id = :item_id
                          AND claim.document_version_id = :version_id
                          AND claim.verification_status = 'ACCEPTED'
                          AND evidence.id = ANY(:evidence_ids)
                        """
                    ),
                    {
                        "item_id": self._task["item_id"],
                        "version_id": profile["current_document_version_id"],
                        "evidence_ids": list(maturity_evidence),
                    },
                )
            )
            if authorized_evidence != maturity_evidence:
                raise PublicationDenied(("DIGITAL_MATURITY_EVIDENCE_REQUIRED",))
        project_count = int(
            await self._connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM digital_case_entity_relation relation
                    JOIN digital_case_entity entity ON entity.id = relation.entity_id
                    WHERE relation.item_id = :item_id
                      AND entity.entity_type = 'PROJECT'
                    """
                ),
                {"item_id": self._task["item_id"]},
            )
            or 0
        )
        maturity_reasons = validate_maturity(
            patch.maturity_level.value,
            MaturityEvidence(
                named_project_count=project_count,
                deployment_count=None,
                operating_months=None,
                acceptance_evidence_count=len(maturity_evidence),
                enterprise_scope_confirmed=(
                    patch.maturity_level.value == "ENTERPRISE_SCALE"
                    and profile["maturity_level"] == "ENTERPRISE_SCALE"
                ),
            ),
        )
        if maturity_reasons:
            raise PublicationDenied(maturity_reasons)

        for outcome_patch in patch.outcome_attributions:
            outcome = (
                (
                    await self._connection.execute(
                        text(
                            """
                            SELECT independent_evidence_ids
                            FROM digital_case_outcome
                            WHERE id = :outcome_id AND item_id = :item_id
                            FOR UPDATE
                            """
                        ),
                        {
                            "outcome_id": outcome_patch.outcome_id,
                            "item_id": self._task["item_id"],
                        },
                    )
                )
                .mappings()
                .first()
            )
            entity_allowed = bool(
                await self._connection.scalar(
                    text(
                        """
                        SELECT EXISTS(
                          SELECT 1 FROM digital_case_entity_relation
                          WHERE item_id = :item_id AND entity_id = :entity_id
                        )
                        """
                    ),
                    {
                        "item_id": self._task["item_id"],
                        "entity_id": outcome_patch.attribution_entity_id,
                    },
                )
            )
            if outcome is None or not entity_allowed:
                raise PublicationDenied(("DIGITAL_OUTCOME_ATTRIBUTION_INVALID",))
            existing_independent = set(outcome["independent_evidence_ids"] or [])
            selected_independent = set(outcome_patch.independent_evidence_ids)
            if outcome_patch.verification.value == "VERIFIED" and (
                not selected_independent or not selected_independent.issubset(existing_independent)
            ):
                raise PublicationDenied(("INDEPENDENT_EVIDENCE_REQUIRED",))
            await self._connection.execute(
                text(
                    """
                    UPDATE digital_case_outcome
                    SET attribution_entity_id = :entity_id,
                        outcome_kind = :outcome_kind,
                        independent_evidence_ids = :independent_evidence_ids
                    WHERE id = :outcome_id AND item_id = :item_id
                    """
                ),
                {
                    "entity_id": outcome_patch.attribution_entity_id,
                    "outcome_kind": outcome_patch.verification.value,
                    "independent_evidence_ids": list(selected_independent),
                    "outcome_id": outcome_patch.outcome_id,
                    "item_id": self._task["item_id"],
                },
            )

        await self._connection.execute(
            text("DELETE FROM digital_case_taxonomy WHERE item_id = :item_id"),
            {"item_id": self._task["item_id"]},
        )
        selected_claim_ids: list[UUID] = []
        for facet, codes in requested.items():
            for code in codes:
                claim_id = authorized[(facet, code)]
                selected_claim_ids.append(claim_id)
                await self._connection.execute(
                    text(
                        """
                        INSERT INTO digital_case_taxonomy
                          (id, item_id, facet, code, claim_id, created_at)
                        VALUES (:id, :item_id, :facet, :code, :claim_id, now())
                        """
                    ),
                    {
                        "id": uuid7(),
                        "item_id": self._task["item_id"],
                        "facet": facet,
                        "code": code,
                        "claim_id": claim_id,
                    },
                )
        await self._connection.execute(
            text(
                """
                UPDATE digital_case_profile
                SET maturity_level = :maturity_level,
                    maturity_evidence_ids = :maturity_evidence_ids,
                    updated_at = now()
                WHERE item_id = :item_id
                """
            ),
            {
                "maturity_level": patch.maturity_level.value,
                "maturity_evidence_ids": list(maturity_evidence),
                "item_id": self._task["item_id"],
            },
        )
        direct_srbg = bool(
            await self._connection.scalar(
                text(
                    """
                    SELECT EXISTS(
                      SELECT 1 FROM digital_case_entity_relation
                      WHERE item_id = :item_id AND direct_srbg = true
                    )
                    """
                ),
                {"item_id": self._task["item_id"]},
            )
        )
        relevance = calculate_relevance(
            patch.engineering_domains,
            is_sichuan=bool(profile["is_sichuan"]),
            has_direct_srbg_relation=direct_srbg,
        )
        factor_points = {factor.code: factor.points for factor in relevance.factors}
        await self._connection.execute(
            text(
                """
                UPDATE digital_case_relevance
                SET score = :score, rule_version = :rule_version,
                    engineering_points = :engineering_points,
                    sichuan_points = :sichuan_points,
                    srbg_direct_points = :srbg_direct_points,
                    factor_claim_ids = :factor_claim_ids,
                    calculated_at = now()
                WHERE item_id = :item_id
                """
            ),
            {
                "score": relevance.score,
                "rule_version": relevance.rule_version,
                "engineering_points": factor_points["ENGINEERING_DOMAIN"],
                "sichuan_points": factor_points["SICHUAN"],
                "srbg_direct_points": factor_points["SRBG_DIRECT"],
                "factor_claim_ids": selected_claim_ids,
                "item_id": self._task["item_id"],
            },
        )

    async def authoritative_context(
        self,
        *,
        evaluation_id: UUID,
        policy_version: str,
        policy_sha256: str,
        evaluated_at: datetime,
    ) -> dict[str, Any]:
        facts = await _publication_facts(
            self._connection,
            self._task["id"],
            evaluated_at=evaluated_at,
        )
        if facts is None:
            raise PublicationDenied(("AUTHORITATIVE_FACTS_MISSING",))
        self._facts = facts

        source_policy = dict(facts["policy_document"])
        source_effective = _source_is_effectively_active(
            facts,
            evaluated_at=evaluated_at,
        )
        legacy_policy_valid = _legacy_source_policy_is_valid(
            facts,
            source_policy=source_policy,
            evaluated_at=evaluated_at,
        )
        allowed_domains = source_policy.get("access", {}).get("allowed_domains", [])
        hostname = urlsplit(str(facts["original_url"])).hostname
        url_allowed = hostname is not None and any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains
        )

        claims = list(
            (
                await self._connection.execute(
                    text(
                        """
                        SELECT c.id, c.item_id, c.claim_type,
                               c.verification_status, c.critical,
                               c.confidence_bps, c.literal_value,
                               e.id AS evidence_id, e.paragraph_id, e.char_start,
                               e.char_end, e.excerpt, e.excerpt_sha256,
                               e.locator_type, e.page_number, e.document_text_block_id,
                               e.x0_mpt, e.y0_mpt, e.x1_mpt, e.y1_mpt,
                               e.confidence_bps AS evidence_confidence_bps,
                               block.normalized_text AS block_text,
                               decision.action AS field_decision_action,
                               decision.evidence_id AS field_decision_evidence_id,
                               decision.evidence_authority_level
                                   AS field_decision_authority,
                               decision.evidence_report_stage AS field_decision_stage,
                               decision.evidence_role AS field_decision_evidence_role
                        FROM claim c
                        LEFT JOIN claim_evidence e ON e.claim_id = c.id
                        LEFT JOIN document_text_block block
                          ON block.id = e.document_text_block_id
                        LEFT JOIN LATERAL (
                            SELECT candidate.action, candidate.evidence_id,
                                   candidate.evidence_authority_level,
                                   candidate.evidence_report_stage, candidate.evidence_role
                            FROM claim_field_decision candidate
                            WHERE candidate.claim_id = c.id
                            ORDER BY candidate.created_at DESC, candidate.id DESC
                            LIMIT 1
                        ) decision ON true
                        WHERE c.item_id = :item_id
                          AND c.document_version_id = :version_id
                          AND NOT EXISTS (
                            SELECT 1
                            FROM claim_conflict resolved
                            JOIN LATERAL (
                                SELECT resolution.chosen_claim_id
                                FROM claim_conflict_decision resolution
                                WHERE resolution.conflict_id = resolved.id
                                  AND resolution.action IN (
                                    'ACCEPT_CANDIDATE','KEEP_CURRENT'
                                  )
                                ORDER BY resolution.created_at DESC, resolution.id DESC
                                LIMIT 1
                            ) resolution ON true
                            WHERE resolved.status = 'RESOLVED'
                              AND c.id IN (
                                resolved.current_claim_id,
                                resolved.candidate_claim_id
                              )
                              AND resolution.chosen_claim_id <> c.id
                          )
                        ORDER BY c.id, e.id
                        """
                    ),
                    {
                        "item_id": facts["item_id"],
                        "version_id": facts["document_version_id"],
                    },
                )
            ).mappings()
        )
        item_type = str(facts["item_type"])
        evidence_integrity = _evaluate_evidence(
            claims,
            facts["paragraphs"] or [],
            item_type=item_type,
        )
        if policy_version not in {
            "2.1.0",
            "3.0.0",
            "4.0.0",
            "5.0.0",
            "6.0.0",
            "7.0.0",
        }:
            evidence_integrity.pop("minimum_critical_ocr_confidence_bps", None)
        round03 = await _round03_gate_facts(
            self._connection,
            item_id=facts["item_id"],
            document_version_id=facts["document_version_id"],
            accepted_claim_count=cast(int, evidence_integrity["claim_count"]),
            regulation_status=str(facts["regulation_status"]),
            authority_level=str(facts["authority_level"]),
            minimum_summary_claim_count=(
                1
                if item_type
                in {
                    "SAFETY_CASE",
                    "DIGITAL_CASE",
                    "JOURNAL_PAPER",
                    "SOFTWARE_PRODUCT",
                    "IOT_PRODUCT",
                    "LOW_ALTITUDE_EQUIPMENT",
                    "AI_EQUIPMENT",
                }
                else 4
            ),
        )
        round04: dict[str, object] | None = None
        if item_type == "SAFETY_CASE":
            round04 = await _round04_gate_facts(
                self._connection,
                facts=facts,
                claims=claims,
            )
            evidence_integrity["unresolved_conflict_count"] = round04["unresolved_conflict_count"]
        round05: dict[str, object] | None = None
        if item_type == "DIGITAL_CASE":
            round05 = await _round05_gate_facts(
                self._connection,
                item_id=facts["item_id"],
                document_version_id=facts["document_version_id"],
            )
        round06: dict[str, object] | None = None
        if item_type == "JOURNAL_PAPER":
            round06 = await _round06_gate_facts(
                self._connection,
                item_id=facts["item_id"],
                document_version_id=facts["document_version_id"],
            )
        round07: dict[str, object] | None = None
        if item_type in {
            "SOFTWARE_PRODUCT",
            "IOT_PRODUCT",
            "LOW_ALTITUDE_EQUIPMENT",
            "AI_EQUIPMENT",
        }:
            round07 = await _round07_gate_facts(
                self._connection,
                item_id=facts["item_id"],
            )
        content_hash = str(facts["content_hash"])
        ai_pipeline = await _ai_pipeline_gate_facts(
            self._connection,
            document_version_id=facts["document_version_id"],
            accepted_claim_ids={str(row["id"]) for row in claims},
        )
        context: dict[str, Any] = {
            "evaluation_id": str(evaluation_id),
            "policy_version": policy_version,
            "policy_sha256": policy_sha256,
            "evaluated_at": evaluated_at.isoformat(),
            "item": {
                "item_id": str(facts["item_id"]),
                "item_type": facts["item_type"],
                "is_demo": facts["is_demo"],
                "publishable": facts["publishable"],
                "regulation_status": facts["regulation_status"],
            },
            "server": {
                "source": {
                    "source_id": str(facts["source_id"]),
                    "status": "ACTIVE" if source_effective else "INACTIVE",
                    "authority_level": facts["authority_level"],
                    "policy_version": facts["source_policy_version"],
                    "policy_status": "VALID" if legacy_policy_valid else "INVALID",
                    "excerpt_policy_pass": _excerpt_policy_pass(source_policy),
                    "attribution_policy_pass": _attribution_policy_pass(source_policy),
                },
                "document": {
                    "document_id": str(facts["document_id"]),
                    "document_version_id": str(facts["document_version_id"]),
                    "content_sha256": content_hash,
                    "is_current": facts["current_version_id"] == facts["document_version_id"],
                    "lifecycle_status": "ACTIVE",
                    "hash_verified": content_hash == facts["raw_sha256"],
                    "url_policy_pass": url_allowed,
                    "execution_domain": facts["document_version_execution_domain"],
                },
                "evidence_integrity": evidence_integrity,
                "security": {
                    "prompt_injection_detected": facts["prompt_injection_detected"],
                    "resolution_status": facts["security_resolution_status"],
                    "resolution_id": None,
                    "scanner_version": facts["security_scanner_version"],
                    "input_sha256": content_hash,
                },
                "privacy": _privacy_projection(
                    item_type=item_type,
                    privacy_status=cast(str | None, facts["safety_privacy_status"]),
                    reputational_risk_reviewed=cast(
                        bool | None,
                        facts["safety_reputational_risk_reviewed"],
                    ),
                ),
                "review": {
                    "risk_level": facts["risk_level"],
                    "required": True,
                    "decision_status": "APPROVED",
                    "decision_id": str(facts["review_task_id"]),
                    "submitted_by": str(facts["submitted_by"]),
                    "decided_by": str(facts["decided_by"]),
                    "duties_separated": facts["submitted_by"] != facts["decided_by"],
                    "decision_reason": str(facts["decision_reason"] or ""),
                },
                "pipeline": {
                    "candidate_schema_valid": _candidate_schema_valid(
                        claims,
                        item_type=item_type,
                    ),
                    "semantic_safety_scan_pass": facts["semantic_safety_scan_pass"],
                    "candidate_schema_version": (
                        "safety-case-candidate-1.0.0"
                        if item_type == "SAFETY_CASE"
                        else "safety-regulation-parser-1.0.0"
                    ),
                    **ai_pipeline,
                },
            },
        }
        if policy_version in {
            "2.1.0",
            "3.0.0",
            "4.0.0",
            "5.0.0",
            "6.0.0",
            "7.0.0",
        }:
            cast(dict[str, Any], context["server"])["round03"] = round03
            cast(dict[str, Any], cast(dict[str, Any], context["server"])["document"]).update(
                {
                    "processing_state": facts["processing_state"],
                    "raw_security_status": facts["raw_security_status"],
                }
            )
        if policy_version in {"2.1.0", "4.0.0", "5.0.0", "6.0.0", "7.0.0"} and round04 is not None:
            cast(dict[str, Any], context["server"])["round04"] = round04
        if policy_version in {"2.1.0", "5.0.0", "6.0.0", "7.0.0"} and round05 is not None:
            cast(dict[str, Any], context["server"])["round05"] = round05
        if policy_version in {"2.1.0", "6.0.0", "7.0.0"} and round06 is not None:
            cast(dict[str, Any], context["server"])["round06"] = round06
        if policy_version in {"2.1.0", "7.0.0"} and round07 is not None:
            cast(dict[str, Any], context["server"])["round07"] = round07
        self._context = context
        return context

    async def publish(
        self,
        *,
        action: str,
        revision_id: UUID,
        evaluation: dict[str, Any],
        evaluation_sha256: str,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> ReviewDecisionResponse:
        if self._context is None or self._facts is None:
            raise PublicationDenied(("AUTHORITATIVE_EVALUATION_REQUIRED",))
        facts = self._facts
        publication = (
            (
                await self._connection.execute(
                    text(
                        """
                        SELECT id, status, current_revision_id
                        FROM publication WHERE item_id = :item_id FOR UPDATE
                        """
                    ),
                    {"item_id": facts["item_id"]},
                )
            )
            .mappings()
            .first()
        )
        if publication is None:
            publication_id = uuid7()
            revision_number = 1
            await self._connection.execute(
                text(
                    """
                    INSERT INTO publication (
                        id, item_id, current_revision_id, status,
                        published_at, withdrawn_at, updated_at
                    ) VALUES (
                        :id, :item_id, NULL, 'PUBLISHED', :now, NULL, :now
                    )
                    """
                ),
                {"id": publication_id, "item_id": facts["item_id"], "now": decided_at},
            )
        else:
            publication_id = publication["id"]
            revision_number = int(
                await self._connection.scalar(
                    text(
                        """
                        SELECT COALESCE(MAX(revision_number), 0) + 1
                        FROM publication_revision WHERE publication_id = :publication_id
                        """
                    ),
                    {"publication_id": publication_id},
                )
            )
        snapshot = _publication_snapshot(facts)
        await self._connection.execute(
            text(
                """
                INSERT INTO publication_revision (
                    id, publication_id, revision_number, document_version_id,
                    source_policy_id, source_policy_sha256, review_task_id,
                    snapshot, evaluation, evaluation_sha256, action, valid,
                    created_by, created_at
                ) VALUES (
                    :id, :publication_id, :revision_number, :document_version_id,
                    :source_policy_id, :source_policy_sha256, :review_task_id,
                    CAST(:snapshot AS jsonb), CAST(:evaluation AS jsonb),
                    :evaluation_sha256, :action, true, :reviewer_id, :decided_at
                )
                """
            ),
            {
                "id": revision_id,
                "publication_id": publication_id,
                "revision_number": revision_number,
                "document_version_id": facts["document_version_id"],
                "source_policy_id": facts["source_policy_id"],
                "source_policy_sha256": facts["source_policy_sha256"],
                "review_task_id": facts["review_task_id"],
                "snapshot": _json(snapshot),
                "evaluation": _json(evaluation),
                "evaluation_sha256": evaluation_sha256,
                "action": action,
                "reviewer_id": reviewer_id,
                "decided_at": decided_at,
            },
        )
        await _enqueue_projection_invalidations(
            self._connection,
            publication_id=publication_id,
            revision_id=revision_id,
            action="UPSERT",
            created_at=decided_at,
        )
        await self._connection.execute(
            text(
                """
                UPDATE publication
                SET current_revision_id = :revision_id, status = 'PUBLISHED',
                    published_at = COALESCE(published_at, :decided_at),
                    withdrawn_at = NULL, updated_at = :decided_at
                WHERE id = :publication_id
                """
            ),
            {
                "revision_id": revision_id,
                "publication_id": publication_id,
                "decided_at": decided_at,
            },
        )
        await self._connection.execute(
            text(
                """
                UPDATE intelligence_item
                SET review_status = 'APPROVED', updated_at = :decided_at
                WHERE id = :item_id
                """
            ),
            {"item_id": facts["item_id"], "decided_at": decided_at},
        )
        version_change_id = await _append_reviewed_version_change_state(
            self._connection,
            document_version_id=facts["document_version_id"],
            state="APPROVED",
            reviewer_id=reviewer_id,
            reason=reason,
            now=decided_at,
        )
        if version_change_id is not None:
            await _append_current_claim_lifecycle_events(
                self._connection,
                item_id=facts["item_id"],
                current_document_version_id=facts["document_version_id"],
                state="ACTIVE",
                reason="Current document version passed publication review",
                version_change_id=version_change_id,
                now=decided_at,
            )
            await _supersede_prior_content(
                self._connection,
                item_id=facts["item_id"],
                current_document_version_id=facts["document_version_id"],
                current_revision_id=revision_id,
                version_change_id=version_change_id,
                reviewer_id=reviewer_id,
                now=decided_at,
            )
        summary_id = await _create_derived_summary(
            self._connection,
            facts=facts,
            created_at=decided_at,
        )
        if summary_id is not None and version_change_id is not None:
            await _append_candidate_lifecycle(
                self._connection,
                item_id=facts["item_id"],
                target_type="SUMMARY",
                target_id=summary_id,
                state="ACTIVE",
                reviewer_id=reviewer_id,
                reason="Deterministic summary inputs passed publication review",
                now=decided_at,
            )
        await _append_audit(
            self._connection,
            event_type=f"PUBLICATION_{action}",
            actor_id=reviewer_id,
            target_type="publication",
            target_id=publication_id,
            after_state={
                "status": "PUBLISHED",
                "revision_id": str(revision_id),
                "evaluation_sha256": evaluation_sha256,
            },
            reason=reason,
            request_id=str(facts["review_task_id"]),
            now=decided_at,
        )
        if facts["item_type"] == "SAFETY_CASE":
            await _append_safety_case_audit(
                self._connection,
                item_id=facts["item_id"],
                event_id=cast(UUID | None, facts["event_id"]),
                target_type="SAFETY_CASE",
                target_id=facts["item_id"],
                action="CONFIRMED",
                actor_id=reviewer_id,
                reason=reason,
                metadata={
                    "publication_revision_id": str(revision_id),
                    "evaluation_sha256": evaluation_sha256,
                },
                now=decided_at,
            )
        return ReviewDecisionResponse(
            review_task_id=facts["review_task_id"],
            status=ReviewStatus.APPROVED,
            publication_revision_id=revision_id,
        )


async def _append_review_decision(
    connection: AsyncConnection,
    *,
    review_task_id: UUID,
    action: str,
    submitted_by: UUID,
    decided_by: UUID,
    reason: str,
    decided_at: datetime,
) -> None:
    if submitted_by == decided_by:
        raise PublicationDenied(("DUTIES_NOT_SEPARATED",))
    if not reason.strip():
        raise PublicationDenied(("REVIEW_REASON_REQUIRED",))
    await connection.execute(
        text(
            """
            INSERT INTO review_decision (
                id, review_task_id, action, reason,
                submitted_by, decided_by, decided_at
            ) VALUES (
                :id, :review_task_id, :action, :reason,
                :submitted_by, :decided_by, :decided_at
            )
            """
        ),
        {
            "id": uuid7(),
            "review_task_id": review_task_id,
            "action": action,
            "reason": reason.strip(),
            "submitted_by": submitted_by,
            "decided_by": decided_by,
            "decided_at": decided_at,
        },
    )


async def _enqueue_projection_invalidations(
    connection: AsyncConnection,
    *,
    publication_id: UUID,
    revision_id: UUID,
    action: str,
    created_at: datetime,
) -> None:
    result = await connection.execute(
        text(
            """
            UPDATE published_v1.event_projection_revision projection
               SET state = 'INVALIDATED', invalidated_at = :created_at,
                   invalidation_reason = :reason
              FROM publication
             WHERE publication.id = :publication_id
               AND projection.item_id = publication.item_id
               AND projection.state = 'ACTIVE'
            """
        ),
        {
            "publication_id": publication_id,
            "created_at": created_at,
            "reason": f"PUBLICATION_{action}",
        },
    )
    logger.info(
        "internal_projection_invalidated",
        extra={
            "action": action,
            "invalidation_reason": f"PUBLICATION_{action}",
            "invalidated_count": int(result.rowcount or 0),
        },
    )
    generation = int(
        await connection.scalar(
            text(
                """
                SELECT COALESCE(MAX(generation), 0) + 1
                FROM publication_projection_invalidation
                WHERE publication_id = :publication_id
                """
            ),
            {"publication_id": publication_id},
        )
        or 1
    )
    for projection in ("SEARCH", "CACHE", "DAILY_DIGEST"):
        await connection.execute(
            text(
                """
                INSERT INTO publication_projection_state (
                    publication_id, projection, revision_id,
                    visible, generation, updated_at
                ) VALUES (
                    :publication_id, :projection, :revision_id,
                    :visible, :generation, :created_at
                )
                ON CONFLICT (publication_id, projection) DO UPDATE
                SET revision_id = EXCLUDED.revision_id,
                    visible = EXCLUDED.visible,
                    generation = EXCLUDED.generation,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "publication_id": publication_id,
                "projection": projection,
                "revision_id": revision_id,
                "visible": action != "WITHDRAW",
                "generation": generation,
                "created_at": created_at,
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO publication_projection_invalidation (
                    id, publication_id, revision_id, projection,
                    action, generation, status, created_at, applied_at
                ) VALUES (
                    :id, :publication_id, :revision_id, :projection,
                    :action, :generation, 'PENDING', :created_at, NULL
                )
                """
            ),
            {
                "id": uuid7(),
                "publication_id": publication_id,
                "revision_id": revision_id,
                "projection": projection,
                "action": action,
                "generation": generation,
                "created_at": created_at,
            },
        )


async def _append_reviewed_version_change_state(
    connection: AsyncConnection,
    *,
    document_version_id: UUID,
    state: str,
    reviewer_id: UUID,
    reason: str,
    now: datetime,
) -> UUID | None:
    change = (
        (
            await connection.execute(
                text(
                    """
                    SELECT change.id,
                           COALESCE(event.change_type, change.change_type) AS change_type,
                           COALESCE(event.material, change.material) AS material
                    FROM version_change change
                    LEFT JOIN LATERAL (
                        SELECT state.change_type, state.material
                        FROM version_change_state_event state
                        WHERE state.version_change_id = change.id
                        ORDER BY state.created_at DESC, state.id DESC LIMIT 1
                    ) event ON true
                    WHERE change.to_document_version_id = :version_id
                    """
                ),
                {"version_id": document_version_id},
            )
        )
        .mappings()
        .first()
    )
    if change is None:
        return None
    await connection.execute(
        text(
            """
            INSERT INTO version_change_state_event (
                id, version_change_id, state, change_type, material,
                resolved_change_type, reviewer_id, reason, created_at
            ) VALUES (
                :id, :change_id, :state, :change_type, :material,
                NULL, :reviewer_id, :reason, :now
            )
            """
        ),
        {
            "id": uuid7(),
            "change_id": change["id"],
            "state": state,
            "change_type": change["change_type"],
            "material": change["material"],
            "reviewer_id": reviewer_id,
            "reason": reason,
            "now": now,
        },
    )
    return cast(UUID, change["id"])


async def _create_derived_summary(
    connection: AsyncConnection,
    *,
    facts: RowMapping,
    created_at: datetime,
) -> UUID | None:
    if facts["item_type"] != "SAFETY_REGULATION":
        return None
    existing = await connection.scalar(
        text(
            """
            SELECT id FROM derived_summary
            WHERE item_id = :item_id AND document_version_id = :version_id
              AND template_version = 'safety-regulation-summary-1.0.0'
            """
        ),
        {"item_id": facts["item_id"], "version_id": facts["document_version_id"]},
    )
    if isinstance(existing, UUID):
        return existing
    claims = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT id, claim_type, confidence_bps
                    FROM claim
                    WHERE item_id = :item_id AND document_version_id = :version_id
                      AND verification_status = 'ACCEPTED'
                    ORDER BY claim_type, id
                    """
                ),
                {"item_id": facts["item_id"], "version_id": facts["document_version_id"]},
            )
        ).mappings()
    )
    required = {"title", "issuing_authority", "document_number", "published_at"}
    if not required.issubset({str(claim["claim_type"]) for claim in claims}):
        return None
    published = _shanghai_date(facts["source_published_at"])
    summary = (
        f"{facts['issuing_authority']}于{published}发布"
        f"《{facts['title']}》({facts['document_number']})"
    )
    has_high_confidence_effective = any(
        claim["claim_type"] == "effective_at" and int(claim["confidence_bps"] or 0) >= 9500
        for claim in claims
    )
    if has_high_confidence_effective and facts["effective_at"] is not None:
        summary += f", 实施日期为{_shanghai_date(facts['effective_at'])}"
    summary_id = uuid7()
    await connection.execute(
        text(
            """
            INSERT INTO derived_summary (
                id, item_id, document_version_id, template_version,
                text, claim_ids, derived_from_summary_id, created_at
            ) VALUES (
                :id, :item_id, :version_id, 'safety-regulation-summary-1.0.0',
                :summary, :claim_ids, NULL, :now
            )
            """
        ),
        {
            "id": summary_id,
            "item_id": facts["item_id"],
            "version_id": facts["document_version_id"],
            "summary": summary,
            "claim_ids": [claim["id"] for claim in claims],
            "now": created_at,
        },
    )
    return summary_id


def _shanghai_date(value: datetime) -> str:
    localized = value.astimezone(ZoneInfo("Asia/Shanghai"))
    return f"{localized.year}年{localized.month}月{localized.day}日"


async def _supersede_prior_content(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    current_document_version_id: UUID,
    current_revision_id: UUID,
    version_change_id: UUID,
    reviewer_id: UUID,
    now: datetime,
) -> None:
    targets: list[tuple[str, UUID]] = [
        ("CLAIM", value)
        for value in await connection.scalars(
            text(
                """
                SELECT id FROM claim
                WHERE item_id = :item_id AND document_version_id <> :version_id
                """
            ),
            {"item_id": item_id, "version_id": current_document_version_id},
        )
    ]
    targets.extend(
        ("SUMMARY", value)
        for value in await connection.scalars(
            text(
                """
                SELECT id FROM derived_summary
                WHERE item_id = :item_id AND document_version_id <> :version_id
                """
            ),
            {"item_id": item_id, "version_id": current_document_version_id},
        )
    )
    targets.extend(
        ("PUBLICATION_REVISION", value)
        for value in await connection.scalars(
            text(
                """
                SELECT revision.id
                FROM publication publication
                JOIN publication_revision revision
                  ON revision.publication_id = publication.id
                WHERE publication.item_id = :item_id AND revision.id <> :revision_id
                """
            ),
            {"item_id": item_id, "revision_id": current_revision_id},
        )
    )
    for target_type, target_id in targets:
        await connection.execute(
            text(
                """
                INSERT INTO content_lifecycle_event (
                    id, item_id, target_type, target_id, state,
                    cause_version_change_id, actor_id, reason, metadata, created_at
                ) VALUES (
                    :id, :item_id, :target_type, :target_id, 'SUPERSEDED',
                    :change_id, :reviewer_id, 'Replacement revision approved',
                    '{}'::jsonb, :now
                )
                """
            ),
            {
                "id": uuid7(),
                "item_id": item_id,
                "target_type": target_type,
                "target_id": target_id,
                "change_id": version_change_id,
                "reviewer_id": reviewer_id,
                "now": now,
            },
        )


_INCIDENT_STATUS_RANK = {
    "UNVERIFIED_LEAD": 0,
    "INITIAL_OFFICIAL_REPORT": 1,
    "UNDER_INVESTIGATION": 2,
    "FINAL_INVESTIGATION_REPORT": 3,
    "ENFORCEMENT_DECISION": 4,
    "RECTIFICATION_FOLLOW_UP": 5,
    "CLOSED": 6,
}


def _advanced_incident_status(current: str, candidate: str) -> str:
    current_rank = _INCIDENT_STATUS_RANK.get(current)
    candidate_rank = _INCIDENT_STATUS_RANK.get(candidate)
    if current_rank is None or candidate_rank is None or candidate_rank <= current_rank:
        return current
    return candidate


def _event_relation_stages_valid(
    relation_type: str,
    *,
    source_stage: str,
    target_stage: str,
    source_order_at: datetime | None = None,
    target_order_at: datetime | None = None,
) -> bool:
    if relation_type == "CORRECTS":
        return bool(
            source_order_at is not None
            and target_order_at is not None
            and source_order_at > target_order_at
        )
    allowed: dict[str, tuple[str, set[str] | None]] = {
        "FOLLOW_UP": (
            "FOLLOW_UP_REPORT",
            {"INITIAL_REPORT", "FOLLOW_UP_REPORT"},
        ),
        "INVESTIGATES": (
            "FINAL_INVESTIGATION",
            {"INITIAL_REPORT", "FOLLOW_UP_REPORT"},
        ),
        "PENALIZES": ("ENFORCEMENT", {"FINAL_INVESTIGATION"}),
        "RECTIFIES": (
            "RECTIFICATION",
            {"FINAL_INVESTIGATION", "ENFORCEMENT"},
        ),
    }
    expected = allowed.get(relation_type)
    if expected is None:
        return False
    expected_source, allowed_targets = expected
    return source_stage == expected_source and (
        allowed_targets is None or target_stage in allowed_targets
    )


async def _decide_event_item_candidate(
    connection: AsyncConnection,
    *,
    candidate_id: UUID,
    action: str,
    reviewer_id: UUID,
    reason: str,
    decided_at: datetime,
) -> None:
    if action not in {"ACCEPT", "REJECT"}:
        raise PublicationDenied(("EVENT_LINK_DECISION_INVALID",))
    await _lock_decision_key(connection, "event-item", candidate_id)
    candidate = (
        (
            await connection.execute(
                text(
                    """
                    SELECT candidate.id, candidate.event_id, candidate.item_id,
                           candidate.submitted_by, profile.incident_status,
                           profile.occurred_at, profile.region_code, profile.region_name,
                           profile.project_name, profile.subject_names, profile.accident_type,
                           profile.engineering_type
                    FROM event_item_candidate candidate
                    JOIN intelligence_item item ON item.id = candidate.item_id
                      AND item.item_type = 'SAFETY_CASE'
                    JOIN safety_case_profile profile ON profile.item_id = item.id
                    WHERE candidate.id = :candidate_id
                      AND NOT EXISTS (
                        SELECT 1 FROM event_item_decision decision
                        WHERE decision.candidate_id = candidate.id
                      )
                    """
                ),
                {"candidate_id": candidate_id},
            )
        )
        .mappings()
        .first()
    )
    if candidate is None:
        raise PublicationDenied(("EVENT_LINK_CANDIDATE_NOT_PENDING",))
    if candidate["submitted_by"] == reviewer_id:
        raise PublicationDenied(("DUTIES_NOT_SEPARATED",))
    await _lock_decision_key(connection, "event", cast(UUID, candidate["event_id"]))
    await connection.execute(
        text(
            """
            INSERT INTO event_item_decision (
                id, candidate_id, action, reviewer_id, submitted_by, reason, created_at
            ) VALUES (
                :id, :candidate_id, :action, :reviewer_id, :submitted_by, :reason, :now
            )
            """
        ),
        {
            "id": uuid7(),
            "candidate_id": candidate_id,
            "action": action,
            "reviewer_id": reviewer_id,
            "submitted_by": candidate["submitted_by"],
            "reason": reason,
            "now": decided_at,
        },
    )
    if action == "ACCEPT":
        current_incident_status = await connection.scalar(
            text("SELECT incident_status FROM event WHERE id = :event_id"),
            {"event_id": candidate["event_id"]},
        )
        if not isinstance(current_incident_status, str):
            raise PublicationDenied(("SAFETY_EVENT_NOT_FOUND",))
        advanced_incident_status = _advanced_incident_status(
            current_incident_status,
            str(candidate["incident_status"]),
        )
        await connection.execute(
            text(
                """
                INSERT INTO event_item (
                    id, candidate_id, event_id, item_id, confirmed_by, confirmed_at
                ) VALUES (
                    :id, :candidate_id, :event_id, :item_id, :reviewer_id, :now
                )
                """
            ),
            {
                "id": uuid7(),
                "candidate_id": candidate_id,
                "event_id": candidate["event_id"],
                "item_id": candidate["item_id"],
                "reviewer_id": reviewer_id,
                "now": decided_at,
            },
        )
        await connection.execute(
            text(
                """
                UPDATE event AS safety_event
                SET confirmation_status = 'CONFIRMED',
                    confirmed_by = COALESCE(confirmed_by, :reviewer_id),
                    confirmed_at = COALESCE(confirmed_at, :now),
                    incident_status = :incident_status,
                    occurred_at = COALESCE(:occurred_at, occurred_at),
                    region_code = COALESCE(:region_code, region_code),
                    region_name = COALESCE(:region_name, region_name),
                    project_name = COALESCE(:project_name, project_name),
                    subject_names = (
                        SELECT COALESCE(jsonb_agg(name ORDER BY name), '[]'::jsonb)
                        FROM (
                            SELECT DISTINCT subject_name AS name
                            FROM jsonb_array_elements_text(
                                safety_event.subject_names || CAST(:subject_names AS jsonb)
                            ) AS subject(subject_name)
                        ) AS merged_subjects
                    ),
                    accident_type = COALESCE(:accident_type, accident_type),
                    engineering_type = COALESCE(:engineering_type, engineering_type),
                    updated_at = :now
                WHERE id = :event_id
                  AND confirmation_status IN ('PENDING_REVIEW','CONFIRMED')
                """
            ),
            {
                "event_id": candidate["event_id"],
                "reviewer_id": reviewer_id,
                "incident_status": advanced_incident_status,
                "occurred_at": candidate["occurred_at"],
                "region_code": candidate["region_code"],
                "region_name": candidate["region_name"],
                "project_name": candidate["project_name"],
                "subject_names": _json(candidate["subject_names"] or []),
                "accident_type": candidate["accident_type"],
                "engineering_type": candidate["engineering_type"],
                "now": decided_at,
            },
        )
    await _append_safety_case_audit(
        connection,
        item_id=candidate["item_id"],
        event_id=candidate["event_id"],
        target_type="EVENT_ITEM",
        target_id=candidate_id,
        action="CONFIRMED" if action == "ACCEPT" else "REJECTED",
        actor_id=reviewer_id,
        reason=reason,
        metadata={"candidate_id": str(candidate_id)},
        now=decided_at,
    )


async def _decide_event_relation_candidate(
    connection: AsyncConnection,
    *,
    candidate_id: UUID,
    action: str,
    reviewer_id: UUID,
    reason: str,
    decided_at: datetime,
) -> None:
    if action not in {"ACCEPT", "REJECT"}:
        raise PublicationDenied(("EVENT_RELATION_DECISION_INVALID",))
    await _lock_decision_key(connection, "event-relation", candidate_id)
    candidate = (
        (
            await connection.execute(
                text(
                    """
                    SELECT candidate.id, candidate.event_id,
                           candidate.source_item_id, candidate.target_item_id,
                           candidate.relation_type, candidate.submitted_by,
                           source_item.item_type AS source_item_type,
                           target_item.item_type AS target_item_type,
                           source_item.submitted_by AS source_submitted_by,
                           target_item.submitted_by AS target_submitted_by,
                           source_profile.report_stage AS source_report_stage,
                           target_profile.report_stage AS target_report_stage,
                           COALESCE(
                               source_item.source_published_at,
                               source_item.first_discovered_at
                           ) AS source_order_at,
                           COALESCE(
                               target_item.source_published_at,
                               target_item.first_discovered_at
                           ) AS target_order_at,
                           EXISTS (
                               SELECT 1 FROM event_item membership
                               WHERE membership.event_id = candidate.event_id
                                 AND membership.item_id = candidate.source_item_id
                           ) AS source_confirmed_member,
                           EXISTS (
                               SELECT 1 FROM event_item membership
                               WHERE membership.event_id = candidate.event_id
                                 AND membership.item_id = candidate.target_item_id
                           ) AS target_confirmed_member
                    FROM event_relation_candidate candidate
                    JOIN intelligence_item source_item
                      ON source_item.id = candidate.source_item_id
                    JOIN intelligence_item target_item
                      ON target_item.id = candidate.target_item_id
                    LEFT JOIN safety_case_profile source_profile
                      ON source_profile.item_id = source_item.id
                    LEFT JOIN safety_case_profile target_profile
                      ON target_profile.item_id = target_item.id
                    WHERE candidate.id = :candidate_id
                      AND NOT EXISTS (
                        SELECT 1 FROM event_relation_decision decision
                        WHERE decision.candidate_id = candidate.id
                      )
                    """
                ),
                {"candidate_id": candidate_id},
            )
        )
        .mappings()
        .first()
    )
    if candidate is None:
        raise PublicationDenied(("EVENT_RELATION_CANDIDATE_NOT_PENDING",))
    if candidate["submitted_by"] != candidate["source_submitted_by"]:
        raise PublicationDenied(("EVENT_RELATION_CANDIDATE_SUBMITTER_INVALID",))
    if reviewer_id in {
        candidate["source_submitted_by"],
        candidate["target_submitted_by"],
    }:
        raise PublicationDenied(("DUTIES_NOT_SEPARATED",))
    if (
        candidate["source_item_type"] != "SAFETY_CASE"
        or candidate["target_item_type"] != "SAFETY_CASE"
        or candidate["source_confirmed_member"] is not True
        or candidate["target_confirmed_member"] is not True
    ):
        raise PublicationDenied(("EVENT_RELATION_ENDPOINT_NOT_CONFIRMED",))
    if not _event_relation_stages_valid(
        str(candidate["relation_type"]),
        source_stage=str(candidate["source_report_stage"]),
        target_stage=str(candidate["target_report_stage"]),
        source_order_at=cast(datetime | None, candidate["source_order_at"]),
        target_order_at=cast(datetime | None, candidate["target_order_at"]),
    ):
        raise PublicationDenied(("EVENT_RELATION_STAGE_INVALID",))
    await connection.execute(
        text(
            """
            INSERT INTO event_relation_decision (
                id, candidate_id, action, reviewer_id, submitted_by, reason, created_at
            ) VALUES (
                :id, :candidate_id, :action, :reviewer_id, :submitted_by, :reason, :now
            )
            """
        ),
        {
            "id": uuid7(),
            "candidate_id": candidate_id,
            "action": action,
            "reviewer_id": reviewer_id,
            "submitted_by": candidate["submitted_by"],
            "reason": reason,
            "now": decided_at,
        },
    )
    if action == "ACCEPT":
        await connection.execute(
            text(
                """
                INSERT INTO event_relation (
                    id, candidate_id, event_id, source_item_id, target_item_id,
                    relation_type, confirmed_by, confirmed_at
                ) VALUES (
                    :id, :candidate_id, :event_id, :source_item_id, :target_item_id,
                    :relation_type, :reviewer_id, :now
                )
                """
            ),
            {
                "id": uuid7(),
                "candidate_id": candidate_id,
                "event_id": candidate["event_id"],
                "source_item_id": candidate["source_item_id"],
                "target_item_id": candidate["target_item_id"],
                "relation_type": candidate["relation_type"],
                "reviewer_id": reviewer_id,
                "now": decided_at,
            },
        )
    audit_action = (
        "REJECTED"
        if action == "REJECT"
        else "CORRECTED"
        if candidate["relation_type"] == "CORRECTS"
        else "CONFIRMED"
    )
    await _append_safety_case_audit(
        connection,
        item_id=candidate["target_item_id"],
        event_id=candidate["event_id"],
        target_type="EVENT_RELATION",
        target_id=candidate_id,
        action=audit_action,
        actor_id=reviewer_id,
        reason=reason,
        metadata={"relation_type": candidate["relation_type"]},
        now=decided_at,
    )


async def _decide_safety_case_claim(
    connection: AsyncConnection,
    *,
    claim_id: UUID,
    action: str,
    reviewer_id: UUID,
    reason: str,
    decided_at: datetime,
) -> None:
    if action not in {"ACCEPT", "REJECT"}:
        raise PublicationDenied(("CLAIM_DECISION_INVALID",))
    await _lock_decision_key(connection, "safety-case-claim", claim_id)
    claim = (
        (
            await connection.execute(
                text(
                    """
                    SELECT claim.id, claim.item_id, claim.claim_type,
                           claim.literal_value, item.submitted_by,
                           source.authority_level, profile.report_stage,
                           evidence.id AS evidence_id, evidence.evidence_role
                    FROM claim
                    JOIN intelligence_item item ON item.id = claim.item_id
                    JOIN source ON source.id = item.source_id
                    JOIN safety_case_profile profile ON profile.item_id = item.id
                    JOIN LATERAL (
                        SELECT candidate.id, candidate.evidence_role
                        FROM claim_evidence candidate
                        WHERE candidate.claim_id = claim.id
                        ORDER BY (candidate.evidence_role = 'PRIMARY_OFFICIAL') DESC,
                                 candidate.created_at, candidate.id
                        LIMIT 1
                    ) evidence ON true
                    WHERE claim.id = :claim_id
                      AND claim.claim_type IN (
                        'deaths','injuries','loss_amount_minor',
                        'official_direct_causes','responsibility_findings'
                      )
                    """
                ),
                {"claim_id": claim_id},
            )
        )
        .mappings()
        .first()
    )
    if claim is None:
        raise PublicationDenied(("SAFETY_CASE_CLAIM_NOT_FOUND",))
    if claim["submitted_by"] == reviewer_id:
        raise PublicationDenied(("DUTIES_NOT_SEPARATED",))
    if action == "ACCEPT" and (
        claim["authority_level"] not in {"A0", "A1"} or claim["evidence_role"] != "PRIMARY_OFFICIAL"
    ):
        raise PublicationDenied(("OFFICIAL_EVIDENCE_REQUIRED",))
    if (
        action == "ACCEPT"
        and claim["claim_type"] in {"official_direct_causes", "responsibility_findings"}
        and claim["report_stage"] not in {"FINAL_INVESTIGATION", "ENFORCEMENT"}
    ):
        raise PublicationDenied(("FORMAL_OFFICIAL_EVIDENCE_REQUIRED",))
    event_id = await connection.scalar(
        text("SELECT event_id FROM event_item WHERE item_id = :item_id"),
        {"item_id": claim["item_id"]},
    )
    if action == "ACCEPT" and event_id is None:
        raise PublicationDenied(("SAFETY_CASE_EVENT_ASSIGNMENT_REQUIRED",))
    await _lock_decision_key(
        connection,
        f"safety-event-field:{claim['claim_type']}",
        cast(UUID, event_id or claim["item_id"]),
    )
    latest_action = await connection.scalar(
        text(
            """
            SELECT decision.action FROM claim_field_decision decision
            WHERE decision.claim_id = :claim_id
            ORDER BY decision.created_at DESC, decision.id DESC LIMIT 1
            """
        ),
        {"claim_id": claim_id},
    )
    if latest_action is not None:
        raise PublicationDenied(("CLAIM_ALREADY_DECIDED",))
    await connection.execute(
        text(
            """
            INSERT INTO claim_field_decision (
                id, claim_id, evidence_id, field_name, action,
                evidence_authority_level, evidence_report_stage, evidence_role,
                reviewer_id, submitted_by, reason, created_at
            ) VALUES (
                :id, :claim_id, :evidence_id, :field_name, :action,
                :authority_level, :report_stage, :evidence_role,
                :reviewer_id, :submitted_by, :reason, :now
            )
            """
        ),
        {
            "id": uuid7(),
            "claim_id": claim_id,
            "evidence_id": claim["evidence_id"],
            "field_name": claim["claim_type"],
            "action": action,
            "authority_level": claim["authority_level"],
            "report_stage": claim["report_stage"],
            "evidence_role": claim["evidence_role"],
            "reviewer_id": reviewer_id,
            "submitted_by": claim["submitted_by"],
            "reason": reason,
            "now": decided_at,
        },
    )
    conflict_opened = False
    if action == "ACCEPT" and event_id is not None:
        current = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT other.id, other.literal_value
                        FROM event_item membership
                        JOIN claim other ON other.item_id = membership.item_id
                        JOIN LATERAL (
                            SELECT decision.action, decision.created_at, decision.id
                            FROM claim_field_decision decision
                            WHERE decision.claim_id = other.id
                            ORDER BY decision.created_at DESC, decision.id DESC LIMIT 1
                        ) latest ON latest.action = 'ACCEPT'
                        WHERE membership.event_id = :event_id
                          AND other.claim_type = :field_name
                          AND other.id <> :claim_id
                          AND other.literal_value IS DISTINCT FROM CAST(:value AS jsonb)
                          AND NOT EXISTS (
                            SELECT 1
                            FROM claim_conflict resolved
                            JOIN LATERAL (
                                SELECT resolution.chosen_claim_id
                                FROM claim_conflict_decision resolution
                                WHERE resolution.conflict_id = resolved.id
                                  AND resolution.action IN (
                                    'ACCEPT_CANDIDATE','KEEP_CURRENT'
                                  )
                                ORDER BY resolution.created_at DESC, resolution.id DESC
                                LIMIT 1
                            ) resolution ON true
                            WHERE resolved.status = 'RESOLVED'
                              AND other.id IN (
                                resolved.current_claim_id,
                                resolved.candidate_claim_id
                              )
                              AND resolution.chosen_claim_id <> other.id
                          )
                        ORDER BY latest.created_at DESC, latest.id DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "event_id": event_id,
                        "field_name": claim["claim_type"],
                        "claim_id": claim_id,
                        "value": _json(claim["literal_value"]),
                    },
                )
            )
            .mappings()
            .first()
        )
        if current is not None:
            existing = await connection.scalar(
                text(
                    """
                    SELECT id FROM claim_conflict
                    WHERE current_claim_id = :current_claim_id
                      AND candidate_claim_id = :candidate_claim_id
                      AND field_name = :field_name
                    """
                ),
                {
                    "current_claim_id": current["id"],
                    "candidate_claim_id": claim_id,
                    "field_name": claim["claim_type"],
                },
            )
            if existing is None:
                conflict_id = uuid7()
                await connection.execute(
                    text(
                        """
                        INSERT INTO claim_conflict (
                            id, event_id, field_name, current_claim_id,
                            candidate_claim_id, current_value_snapshot,
                            candidate_value_snapshot, status, risk_level,
                            public_value_available, opened_by, detected_at, updated_at
                        ) VALUES (
                            :id, :event_id, :field_name, :current_claim_id,
                            :candidate_claim_id, CAST(:current_value AS jsonb),
                            CAST(:candidate_value AS jsonb), 'PENDING_REVIEW', 'R4',
                            false, :opened_by, :now, :now
                        )
                        """
                    ),
                    {
                        "id": conflict_id,
                        "event_id": event_id,
                        "field_name": claim["claim_type"],
                        "current_claim_id": current["id"],
                        "candidate_claim_id": claim_id,
                        "current_value": _json(current["literal_value"]),
                        "candidate_value": _json(claim["literal_value"]),
                        "opened_by": reviewer_id,
                        "now": decided_at,
                    },
                )
                await _append_safety_case_audit(
                    connection,
                    item_id=claim["item_id"],
                    event_id=cast(UUID, event_id),
                    target_type="CLAIM_CONFLICT",
                    target_id=conflict_id,
                    action="CONFLICT_OPENED",
                    actor_id=reviewer_id,
                    reason="Accepted official claims disagree",
                    metadata={"field_name": claim["claim_type"]},
                    now=decided_at,
                )
            conflict_opened = True
    if action == "ACCEPT" and not conflict_opened:
        await _restore_safety_case_profile_value(
            connection,
            claim_id=claim_id,
            decided_at=decided_at,
        )
    await _append_safety_case_audit(
        connection,
        item_id=claim["item_id"],
        event_id=cast(UUID | None, event_id),
        target_type="CLAIM_FIELD",
        target_id=claim_id,
        action="CONFIRMED" if action == "ACCEPT" else "REJECTED",
        actor_id=reviewer_id,
        reason=reason,
        metadata={"field_name": claim["claim_type"]},
        now=decided_at,
    )


async def _restore_safety_case_profile_value(
    connection: AsyncConnection,
    *,
    claim_id: UUID,
    decided_at: datetime,
) -> None:
    claim = (
        (
            await connection.execute(
                text(
                    """
                    SELECT claim.item_id, claim.claim_type, claim.literal_value,
                           evidence.excerpt
                    FROM claim
                    JOIN LATERAL (
                        SELECT decision.action, decision.evidence_id
                        FROM claim_field_decision decision
                        WHERE decision.claim_id = claim.id
                        ORDER BY decision.created_at DESC, decision.id DESC LIMIT 1
                    ) decision ON decision.action = 'ACCEPT'
                    JOIN claim_evidence evidence
                      ON evidence.id = decision.evidence_id
                     AND evidence.claim_id = claim.id
                    WHERE claim.id = :id
                    """
                ),
                {"id": claim_id},
            )
        )
        .mappings()
        .first()
    )
    if claim is None:
        raise PublicationDenied(("SAFETY_CASE_CLAIM_NOT_ACCEPTED",))
    field_name = str(claim["claim_type"])
    common_values = {
        "now": decided_at,
        "item_id": claim["item_id"],
    }
    if field_name == "deaths":
        statement = text(
            "UPDATE safety_case_profile SET deaths = :value, updated_at = :now "
            "WHERE item_id = :item_id"
        )
        values = common_values | {"value": int(claim["literal_value"])}
    elif field_name == "injuries":
        statement = text(
            "UPDATE safety_case_profile SET injuries = :value, updated_at = :now "
            "WHERE item_id = :item_id"
        )
        values = common_values | {"value": int(claim["literal_value"])}
    elif field_name == "loss_amount_minor":
        currency = _explicit_currency_from_evidence(str(claim["excerpt"] or ""))
        if currency is None:
            raise PublicationDenied(("LOSS_CURRENCY_EVIDENCE_REQUIRED",))
        statement = text(
            "UPDATE safety_case_profile "
            "SET loss_amount_minor = :value, loss_currency = :currency, updated_at = :now "
            "WHERE item_id = :item_id"
        )
        values = common_values | {
            "value": int(claim["literal_value"]),
            "currency": currency,
        }
    elif field_name == "official_direct_causes":
        statement = text(
            "UPDATE safety_case_profile "
            "SET official_direct_causes = CAST(:value AS jsonb), updated_at = :now "
            "WHERE item_id = :item_id"
        )
        values = common_values | {"value": _json(claim["literal_value"])}
    elif field_name == "responsibility_findings":
        statement = text(
            "UPDATE safety_case_profile "
            "SET responsibility_findings = CAST(:value AS jsonb), updated_at = :now "
            "WHERE item_id = :item_id"
        )
        values = common_values | {"value": _json(claim["literal_value"])}
    else:
        raise PublicationDenied(("SAFETY_CASE_FIELD_NOT_PROJECTABLE",))
    await connection.execute(statement, values)


def _explicit_currency_from_evidence(excerpt: str) -> str | None:
    upper = excerpt.upper()
    explicit: set[str] = set()
    if "USD" in upper or "美元" in excerpt:
        explicit.add("USD")
    if "EUR" in upper or "欧元" in excerpt:
        explicit.add("EUR")
    if "CNY" in upper or "RMB" in upper or "人民币" in excerpt:
        explicit.add("CNY")
    if len(explicit) == 1:
        return explicit.pop()
    if explicit:
        return None
    if re.search(r"(?:万|亿)?元", excerpt):
        return "CNY"
    return None


async def _append_safety_case_audit(
    connection: AsyncConnection,
    *,
    item_id: UUID | None,
    event_id: UUID | None,
    target_type: str,
    target_id: UUID,
    action: str,
    actor_id: UUID | None,
    reason: str,
    metadata: dict[str, Any],
    now: datetime,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO safety_case_audit_event (
                id, item_id, event_id, target_type, target_id, action,
                actor_id, reason, metadata, created_at
            ) VALUES (
                :id, :item_id, :event_id, :target_type, :target_id, :action,
                :actor_id, :reason, CAST(:metadata AS jsonb), :now
            )
            """
        ),
        {
            "id": uuid7(),
            "item_id": item_id,
            "event_id": event_id,
            "target_type": target_type,
            "target_id": target_id,
            "action": action,
            "actor_id": actor_id,
            "reason": reason,
            "metadata": _json(metadata),
            "now": now,
        },
    )


def _critical_conflict_field(field_name: str) -> CriticalSafetyField:
    return {
        "deaths": CriticalSafetyField.DEATH_COUNT,
        "injuries": CriticalSafetyField.INJURY_COUNT,
        "loss_amount_minor": CriticalSafetyField.LOSS_AMOUNT_MINOR,
        "official_direct_causes": CriticalSafetyField.OFFICIAL_DIRECT_CAUSES,
        "responsibility_findings": CriticalSafetyField.RESPONSIBILITY_FINDINGS,
    }[field_name]


async def _lock_decision_key(
    connection: AsyncConnection,
    namespace: str,
    target_id: UUID,
) -> None:
    """Serialize append-only decisions without requiring UPDATE on immutable inputs."""
    await connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"{namespace}:{target_id}"},
    )


async def _decide_paper_relation_candidate(
    connection: AsyncConnection,
    *,
    candidate_id: UUID,
    action: str,
    reviewer_id: UUID,
    reason: str,
    decided_at: datetime,
) -> None:
    candidate = (
        (
            await connection.execute(
                text(
                    """
                    SELECT id, source_item_id, target_item_id, relation_type, status
                    FROM item_relation_candidate
                    WHERE id = :candidate_id FOR UPDATE
                    """
                ),
                {"candidate_id": candidate_id},
            )
        )
        .mappings()
        .first()
    )
    if candidate is None:
        raise PublicationDenied(("PAPER_RELATION_CANDIDATE_NOT_FOUND",))
    if candidate["status"] != "PENDING_REVIEW":
        raise PublicationDenied(("PAPER_RELATION_CANDIDATE_ALREADY_DECIDED",))
    if action not in {"ACCEPT", "REJECT"}:
        raise PublicationDenied(("PAPER_RELATION_DECISION_INVALID",))
    if action == "ACCEPT" and candidate["target_item_id"] is None:
        raise PublicationDenied(("PAPER_RELATION_TARGET_REQUIRED",))
    await connection.execute(
        text("UPDATE item_relation_candidate SET status = :status WHERE id = :candidate_id"),
        {"status": "ACCEPTED" if action == "ACCEPT" else "REJECTED", "candidate_id": candidate_id},
    )
    if action == "ACCEPT":
        relation_id = uuid7()
        await connection.execute(
            text(
                """
                INSERT INTO item_relation (
                    id, source_item_id, target_item_id, relation_type,
                    candidate_id, reviewed_by, reviewed_at
                ) VALUES (
                    :id, :source_item_id, :target_item_id, :relation_type,
                    :candidate_id, :reviewed_by, :reviewed_at
                )
                """
            ),
            {
                "id": relation_id,
                "source_item_id": candidate["source_item_id"],
                "target_item_id": candidate["target_item_id"],
                "relation_type": candidate["relation_type"],
                "candidate_id": candidate_id,
                "reviewed_by": reviewer_id,
                "reviewed_at": decided_at,
            },
        )
        relation_status = {
            "RETRACTS": "RETRACTED",
            "CORRECTS": "CORRECTED",
            "SUPERSEDES": "WITHDRAWN",
        }.get(str(candidate["relation_type"]))
        if relation_status:
            await connection.execute(
                text(
                    """
                    UPDATE paper_profile
                    SET relation_status = :relation_status, updated_at = :decided_at
                    WHERE item_id = :target_item_id
                    """
                ),
                {
                    "relation_status": relation_status,
                    "decided_at": decided_at,
                    "target_item_id": candidate["target_item_id"],
                },
            )
    await _append_audit(
        connection,
        event_type=f"PAPER_RELATION_{action}",
        actor_id=reviewer_id,
        target_type="item_relation_candidate",
        target_id=candidate_id,
        after_state={"status": "ACCEPTED" if action == "ACCEPT" else "REJECTED"},
        reason=reason,
        request_id=str(candidate_id),
        now=decided_at,
    )


async def _decide_relation_candidate(
    connection: AsyncConnection,
    *,
    candidate_id: UUID,
    action: str,
    target_document_id: UUID | None,
    reviewer_id: UUID,
    reason: str,
    decided_at: datetime,
) -> None:
    await _lock_decision_key(connection, "document-relation", candidate_id)
    candidate = (
        (
            await connection.execute(
                text(
                    """
                    SELECT candidate.id, candidate.item_id, candidate.relation_type,
                           candidate.target_document_id, item.primary_document_id
                    FROM document_relation_candidate candidate
                    JOIN intelligence_item item ON item.id = candidate.item_id
                    LEFT JOIN document_relation_decision decision
                      ON decision.candidate_id = candidate.id
                    WHERE candidate.id = :candidate_id AND decision.id IS NULL
                    """
                ),
                {"candidate_id": candidate_id},
            )
        )
        .mappings()
        .first()
    )
    if candidate is None:
        raise PublicationDenied(("RELATION_CANDIDATE_NOT_PENDING",))
    resolved_target = target_document_id or candidate["target_document_id"]
    if action == "ACCEPT":
        if resolved_target is None:
            raise PublicationDenied(("RELATION_TARGET_REQUIRED",))
        if resolved_target == candidate["primary_document_id"]:
            raise PublicationDenied(("RELATION_TARGET_MUST_DIFFER",))
        target_exists = await connection.scalar(
            text("SELECT EXISTS(SELECT 1 FROM document WHERE id = :id)"),
            {"id": resolved_target},
        )
        if not target_exists:
            raise PublicationDenied(("RELATION_TARGET_NOT_FOUND",))
    elif action in {"REJECT", "CONFIRM_UNRESOLVED"}:
        if target_document_id is not None:
            raise PublicationDenied(("RELATION_TARGET_NOT_ALLOWED",))
        resolved_target = None
    else:
        raise PublicationDenied(("RELATION_DECISION_ACTION_INVALID",))
    await connection.execute(
        text(
            """
            INSERT INTO document_relation_decision (
                id, candidate_id, action, target_document_id,
                reviewer_id, reason, created_at
            ) VALUES (
                :id, :candidate_id, :action, :target_document_id,
                :reviewer_id, :reason, :now
            )
            """
        ),
        {
            "id": uuid7(),
            "candidate_id": candidate_id,
            "action": action,
            "target_document_id": resolved_target,
            "reviewer_id": reviewer_id,
            "reason": reason,
            "now": decided_at,
        },
    )
    if action == "ACCEPT" and resolved_target is not None:
        await connection.execute(
            text(
                """
                INSERT INTO document_relation (
                    id, candidate_id, source_document_id, target_document_id,
                    relation_type, confirmed_by, confirmed_at
                ) VALUES (
                    :id, :candidate_id, :source_document_id, :target_document_id,
                    :relation_type, :reviewer_id, :now
                )
                """
            ),
            {
                "id": uuid7(),
                "candidate_id": candidate_id,
                "source_document_id": candidate["primary_document_id"],
                "target_document_id": resolved_target,
                "relation_type": candidate["relation_type"],
                "reviewer_id": reviewer_id,
                "now": decided_at,
            },
        )
    await _append_candidate_lifecycle(
        connection,
        item_id=candidate["item_id"],
        target_type="RELATION_CANDIDATE",
        target_id=candidate_id,
        state=_candidate_lifecycle_state(action),
        reviewer_id=reviewer_id,
        reason=reason,
        now=decided_at,
    )
    await _append_audit(
        connection,
        event_type="DOCUMENT_RELATION_CANDIDATE_DECIDED",
        actor_id=reviewer_id,
        target_type="document_relation_candidate",
        target_id=candidate_id,
        after_state={
            "action": action,
            "target_document_id": str(resolved_target) if resolved_target else None,
        },
        reason=reason,
        request_id=str(candidate_id),
        now=decided_at,
    )


async def _decide_regulation_status_candidate(
    connection: AsyncConnection,
    *,
    candidate_id: UUID,
    action: str,
    target_document_id: UUID | None,
    reviewer_id: UUID,
    reason: str,
    decided_at: datetime,
) -> None:
    if action not in {"ACCEPT", "REJECT"} or target_document_id is not None:
        raise PublicationDenied(("REGULATION_STATUS_DECISION_INVALID",))
    await _lock_decision_key(connection, "regulation-status", candidate_id)
    candidate = (
        (
            await connection.execute(
                text(
                    """
                    SELECT candidate.id, candidate.item_id, candidate.candidate_status,
                           candidate.evidence_id, source.authority_level
                    FROM regulation_status_candidate candidate
                    JOIN intelligence_item item ON item.id = candidate.item_id
                    JOIN source source ON source.id = item.source_id
                    JOIN claim_evidence evidence ON evidence.id = candidate.evidence_id
                    LEFT JOIN regulation_status_decision decision
                      ON decision.candidate_id = candidate.id
                    WHERE candidate.id = :candidate_id
                      AND evidence.document_version_id = candidate.document_version_id
                      AND decision.id IS NULL
                    """
                ),
                {"candidate_id": candidate_id},
            )
        )
        .mappings()
        .first()
    )
    if candidate is None:
        raise PublicationDenied(("REGULATION_STATUS_CANDIDATE_NOT_PENDING",))
    if action == "ACCEPT" and candidate["authority_level"] != "A1":
        raise PublicationDenied(("REGULATION_STATUS_OFFICIAL_EVIDENCE_REQUIRED",))
    await connection.execute(
        text(
            """
            INSERT INTO regulation_status_decision (
                id, candidate_id, action, reviewer_id, reason, created_at
            ) VALUES (:id, :candidate_id, :action, :reviewer_id, :reason, :now)
            """
        ),
        {
            "id": uuid7(),
            "candidate_id": candidate_id,
            "action": action,
            "reviewer_id": reviewer_id,
            "reason": reason,
            "now": decided_at,
        },
    )
    if action == "ACCEPT":
        await connection.execute(
            text(
                """
                UPDATE safety_regulation_profile
                SET regulation_status = :status
                WHERE item_id = :item_id
                """
            ),
            {
                "status": candidate["candidate_status"],
                "item_id": candidate["item_id"],
            },
        )
    await _append_candidate_lifecycle(
        connection,
        item_id=candidate["item_id"],
        target_type="REGULATION_STATUS_CANDIDATE",
        target_id=candidate_id,
        state=_candidate_lifecycle_state(action),
        reviewer_id=reviewer_id,
        reason=reason,
        now=decided_at,
    )
    await _append_audit(
        connection,
        event_type="REGULATION_STATUS_CANDIDATE_DECIDED",
        actor_id=reviewer_id,
        target_type="regulation_status_candidate",
        target_id=candidate_id,
        after_state={"action": action, "status": candidate["candidate_status"]},
        reason=reason,
        request_id=str(candidate_id),
        now=decided_at,
    )


async def _append_candidate_lifecycle(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    target_type: str,
    target_id: UUID,
    state: str,
    reviewer_id: UUID,
    reason: str,
    now: datetime,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO content_lifecycle_event (
                id, item_id, target_type, target_id, state,
                cause_version_change_id, actor_id, reason, metadata, created_at
            ) VALUES (
                :id, :item_id, :target_type, :target_id, :state,
                NULL, :reviewer_id, :reason, '{}'::jsonb, :now
            )
            """
        ),
        {
            "id": uuid7(),
            "item_id": item_id,
            "target_type": target_type,
            "target_id": target_id,
            "state": state,
            "reviewer_id": reviewer_id,
            "reason": reason,
            "now": now,
        },
    )


def _candidate_lifecycle_state(action: str) -> str:
    return {
        "ACCEPT": "ACCEPTED",
        "REJECT": "REJECTED",
        "CONFIRM_UNRESOLVED": "CONFIRMED_UNRESOLVED",
    }[action]


async def _publish_metadata_revision(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    current_document_version_id: UUID,
    version_change_id: UUID,
    now: datetime,
) -> bool:
    row = (
        (
            await connection.execute(
                text(
                    """
                    SELECT publication.id AS publication_id,
                           publication.current_revision_id,
                           revision.revision_number, revision.source_policy_id,
                           revision.source_policy_sha256, revision.review_task_id,
                           revision.evaluation, revision.created_by,
                           item.title, item.original_url, item.source_published_at,
                           item.review_status, source.name AS source_name,
                           profile.document_number, profile.issuing_authority,
                           profile.regulation_status,
                           version.content_hash,
                           version.execution_domain,
                           raw.sha256 AS raw_sha256,
                           state.state AS processing_state,
                           security.status AS security_status
                    FROM intelligence_item item
                    JOIN publication publication ON publication.item_id = item.id
                    JOIN publication_revision revision
                      ON revision.id = publication.current_revision_id
                    JOIN source source ON source.id = item.source_id
                    JOIN safety_regulation_profile profile ON profile.item_id = item.id
                    JOIN document_version version ON version.id = :version_id
                    JOIN raw_object raw ON raw.id = version.raw_object_id
                    LEFT JOIN LATERAL (
                        SELECT event.state
                        FROM document_version_state_event event
                        WHERE event.document_version_id = version.id
                        ORDER BY event.created_at DESC, event.id DESC LIMIT 1
                    ) state ON true
                    LEFT JOIN LATERAL (
                        SELECT CASE
                          WHEN bool_or(fact.status IN ('REJECTED','QUARANTINED'))
                            THEN 'QUARANTINED'
                          WHEN bool_or(fact.status = 'CLEAN') THEN 'CLEAN'
                          ELSE NULL
                        END AS status
                        FROM raw_object_security_fact fact
                        WHERE fact.raw_object_id = raw.id
                    ) security ON true
                    WHERE item.id = :item_id
                      AND item.current_document_version_id = :version_id
                      AND item.review_status = 'APPROVED'
                      AND publication.status = 'PUBLISHED'
                    FOR UPDATE OF publication
                    """
                ),
                {"item_id": item_id, "version_id": current_document_version_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return False
    if row["execution_domain"] != "PRODUCTION":
        raise PublicationDenied(("NON_PRODUCTION_EXECUTION_DOMAIN",))
    if row["processing_state"] != "READY" or row["security_status"] != "CLEAN":
        raise PublicationDenied(("METADATA_REVISION_NOT_SAFE",))
    evaluation = dict(row["evaluation"])
    server = dict(evaluation.get("server", {}))
    document = dict(server.get("document", {}))
    document.update(
        {
            "document_version_id": str(current_document_version_id),
            "content_sha256": row["raw_sha256"],
            "is_current": True,
            "lifecycle_status": "ACTIVE",
            "hash_verified": row["content_hash"] == row["raw_sha256"],
            "execution_domain": row["execution_domain"],
        }
    )
    server["document"] = document
    round03 = dict(server.get("round03", {}))
    round03.update(
        {
            "current_processing_state": row["processing_state"],
            "raw_security_status": row["security_status"],
        }
    )
    server["round03"] = round03
    evaluation["server"] = server
    evaluation["evaluation_id"] = str(uuid7())
    evaluation["evaluated_at"] = now.isoformat().replace("+00:00", "Z")
    snapshot = {
        "item_id": str(item_id),
        "title": row["title"],
        "source_name": row["source_name"],
        "original_url": row["original_url"],
        "document_number": row["document_number"],
        "issuing_authority": row["issuing_authority"],
        "published_at": row["source_published_at"].isoformat(),
        "regulation_status": row["regulation_status"],
    }
    revision_id = uuid7()
    await connection.execute(
        text(
            """
            INSERT INTO publication_revision (
                id, publication_id, revision_number, document_version_id,
                source_policy_id, source_policy_sha256, review_task_id,
                snapshot, evaluation, evaluation_sha256, action, valid,
                created_by, created_at
            ) VALUES (
                :id, :publication_id, :revision_number, :version_id,
                :policy_id, :policy_sha256, :review_task_id,
                CAST(:snapshot AS jsonb), CAST(:evaluation AS jsonb),
                :evaluation_sha256, 'REVISE', true, :created_by, :now
            )
            """
        ),
        {
            "id": revision_id,
            "publication_id": row["publication_id"],
            "revision_number": int(row["revision_number"]) + 1,
            "version_id": current_document_version_id,
            "policy_id": row["source_policy_id"],
            "policy_sha256": row["source_policy_sha256"],
            "review_task_id": row["review_task_id"],
            "snapshot": _json(snapshot),
            "evaluation": _json(evaluation),
            "evaluation_sha256": canonical_json_hash(evaluation),
            "created_by": row["created_by"],
            "now": now,
        },
    )
    await connection.execute(
        text(
            """
            UPDATE publication
            SET current_revision_id = :revision_id, updated_at = :now
            WHERE id = :publication_id
            """
        ),
        {
            "revision_id": revision_id,
            "publication_id": row["publication_id"],
            "now": now,
        },
    )
    summary_id = await _derive_metadata_summary(
        connection,
        item_id=item_id,
        document_version_id=current_document_version_id,
        now=now,
    )
    await _supersede_prior_content(
        connection,
        item_id=item_id,
        current_document_version_id=current_document_version_id,
        current_revision_id=revision_id,
        version_change_id=version_change_id,
        reviewer_id=row["created_by"],
        now=now,
    )
    if summary_id is not None:
        await _append_candidate_lifecycle(
            connection,
            item_id=item_id,
            target_type="SUMMARY",
            target_id=summary_id,
            state="ACTIVE",
            reviewer_id=row["created_by"],
            reason="Metadata-only summary was derived from the prior accepted summary",
            now=now,
        )
    return True


async def _derive_metadata_summary(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    document_version_id: UUID,
    now: datetime,
) -> UUID | None:
    previous = (
        (
            await connection.execute(
                text(
                    """
                    SELECT id, text
                    FROM derived_summary
                    WHERE item_id = :item_id AND document_version_id <> :version_id
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """
                ),
                {"item_id": item_id, "version_id": document_version_id},
            )
        )
        .mappings()
        .first()
    )
    if previous is None:
        return None
    claim_ids = list(
        await connection.scalars(
            text(
                """
                SELECT id FROM claim
                WHERE item_id = :item_id AND document_version_id = :version_id
                  AND verification_status = 'ACCEPTED'
                ORDER BY claim_type, id
                """
            ),
            {"item_id": item_id, "version_id": document_version_id},
        )
    )
    if not claim_ids:
        return None
    summary_id = uuid7()
    await connection.execute(
        text(
            """
            INSERT INTO derived_summary (
                id, item_id, document_version_id, template_version,
                text, claim_ids, derived_from_summary_id, created_at
            ) VALUES (
                :id, :item_id, :version_id, 'safety-regulation-summary-1.0.0',
                :text, :claim_ids, :derived_from, :now
            )
            """
        ),
        {
            "id": summary_id,
            "item_id": item_id,
            "version_id": document_version_id,
            "text": previous["text"],
            "claim_ids": claim_ids,
            "derived_from": previous["id"],
            "now": now,
        },
    )
    return summary_id


async def _append_update_lifecycle_events(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    version_change_id: UUID,
    current_document_version_id: UUID,
    now: datetime,
) -> None:
    targets: list[tuple[str, UUID]] = [
        ("CLAIM", value)
        for value in await connection.scalars(
            text(
                """
                SELECT id FROM claim
                WHERE item_id = :item_id
                  AND document_version_id <> :current_version_id
                  AND verification_status = 'ACCEPTED'
                """
            ),
            {"item_id": item_id, "current_version_id": current_document_version_id},
        )
    ]
    targets.extend(
        ("SUMMARY", value)
        for value in await connection.scalars(
            text(
                """
                SELECT id FROM derived_summary
                WHERE item_id = :item_id
                  AND document_version_id <> :current_version_id
                """
            ),
            {"item_id": item_id, "current_version_id": current_document_version_id},
        )
    )
    targets.extend(
        ("PUBLICATION_REVISION", value)
        for value in await connection.scalars(
            text(
                """
                SELECT revision.id
                FROM publication publication
                JOIN publication_revision revision
                  ON revision.id = publication.current_revision_id
                WHERE publication.item_id = :item_id
                """
            ),
            {"item_id": item_id},
        )
    )
    for target_type, target_id in targets:
        for state in ("UPDATE_DETECTED", "RE_REVIEW_PENDING"):
            await connection.execute(
                text(
                    """
                    INSERT INTO content_lifecycle_event (
                        id, item_id, target_type, target_id, state,
                        cause_version_change_id, actor_id, reason, metadata, created_at
                    ) VALUES (
                        :id, :item_id, :target_type, :target_id, :state,
                        :change_id, NULL, 'Current document has a material update',
                        '{}'::jsonb, :now
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "item_id": item_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "state": state,
                    "change_id": version_change_id,
                    "now": now,
                },
            )
    await _append_current_claim_lifecycle_events(
        connection,
        item_id=item_id,
        current_document_version_id=current_document_version_id,
        state="RE_REVIEW_PENDING",
        reason="New current-version claims require human review",
        version_change_id=version_change_id,
        now=now,
    )


async def _append_current_claim_lifecycle_events(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    current_document_version_id: UUID,
    state: str,
    reason: str,
    version_change_id: UUID,
    now: datetime,
) -> None:
    claim_ids = list(
        await connection.scalars(
            text(
                """
                SELECT id FROM claim
                WHERE item_id = :item_id
                  AND document_version_id = :current_version_id
                """
            ),
            {"item_id": item_id, "current_version_id": current_document_version_id},
        )
    )
    for claim_id in claim_ids:
        await connection.execute(
            text(
                """
                INSERT INTO content_lifecycle_event (
                    id, item_id, target_type, target_id, state,
                    cause_version_change_id, actor_id, reason, metadata, created_at
                ) VALUES (
                    :id, :item_id, 'CLAIM', :target_id, :state,
                    :change_id, NULL, :reason, '{}'::jsonb, :now
                )
                """
            ),
            {
                "id": uuid7(),
                "item_id": item_id,
                "target_id": claim_id,
                "state": state,
                "change_id": version_change_id,
                "reason": reason,
                "now": now,
            },
        )


async def _locked_review_task(connection: AsyncConnection, task_id: UUID) -> RowMapping:
    row = (
        (
            await connection.execute(
                text(
                    """
                    SELECT id, item_id, document_version_id, source_policy_id,
                           status, submitted_by
                    FROM review_task WHERE id = :task_id FOR UPDATE
                    """
                ),
                {"task_id": task_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise PublicationDenied(("REVIEW_TASK_NOT_FOUND",))
    return row


def _validate_pending_review(task: RowMapping, reviewer_id: UUID, reason: str) -> None:
    reasons: list[str] = []
    if task["status"] != "PENDING":
        reasons.append("REVIEW_TASK_NOT_PENDING")
    if task["submitted_by"] == reviewer_id:
        reasons.append("DUTIES_NOT_SEPARATED")
    if not reason.strip():
        reasons.append("REVIEW_REASON_REQUIRED")
    if reasons:
        raise PublicationDenied(tuple(reasons))


async def _ai_pipeline_gate_facts(
    connection: AsyncConnection,
    *,
    document_version_id: UUID,
    accepted_claim_ids: set[str],
) -> dict[str, object]:
    run = (
        (
            await connection.execute(
                text(
                    """
                    SELECT id, status
                    FROM ai_pipeline_run
                    WHERE document_version_id = :document_version_id
                      AND mode = 'LIVE'
                    ORDER BY started_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"document_version_id": document_version_id},
            )
        )
        .mappings()
        .first()
    )
    if run is None or run["status"] in {"FAILED", "DEGRADED"}:
        return {
            "ai_status": "NOT_RUN_DEGRADED",
            "four_steps_completed": False,
            "accepted_summary_claim_refs_valid": False,
            "unauthorized_candidate_field_count": 0,
        }
    step_rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (step) step, status, validated_output
                    FROM ai_step_run
                    WHERE pipeline_run_id = :pipeline_run_id
                    ORDER BY step, attempt DESC
                    """
                ),
                {"pipeline_run_id": run["id"]},
            )
        ).mappings()
    )
    successful_steps = {str(row["step"]) for row in step_rows if row["status"] == "SUCCEEDED"}
    four_steps_completed = successful_steps == {
        "CLASSIFY",
        "EXTRACT",
        "SUMMARIZE",
        "VERIFY",
    }
    summary = next(
        (dict(row["validated_output"] or {}) for row in step_rows if row["step"] == "SUMMARIZE"),
        {},
    )
    used_claim_ids = summary.get("used_claim_ids")
    accepted_summary_claim_refs_valid = (
        isinstance(used_claim_ids, list)
        and bool(used_claim_ids)
        and all(isinstance(value, str) for value in used_claim_ids)
        and set(used_claim_ids).issubset(accepted_claim_ids)
    )
    forbidden = {
        "source_authority",
        "source_level",
        "review_status",
        "risk_level",
        "security_resolution",
        "publication_status",
        "publication_recommendation",
    }
    unauthorized_count = sum(
        _count_forbidden_candidate_fields(row["validated_output"], forbidden) for row in step_rows
    )
    return {
        "ai_status": "VALIDATED" if run["status"] == "SUCCEEDED" else "INVALID",
        "four_steps_completed": four_steps_completed,
        "accepted_summary_claim_refs_valid": accepted_summary_claim_refs_valid,
        "unauthorized_candidate_field_count": unauthorized_count,
    }


def _count_forbidden_candidate_fields(value: object, forbidden: set[str]) -> int:
    if isinstance(value, Mapping):
        return sum(
            (1 if str(key) in forbidden else 0)
            + _count_forbidden_candidate_fields(child, forbidden)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return sum(_count_forbidden_candidate_fields(child, forbidden) for child in value)
    return 0


async def _publication_facts(
    connection: AsyncConnection,
    review_task_id: UUID,
    *,
    evaluated_at: datetime,
) -> RowMapping | None:
    return (
        (
            await connection.execute(
                text(
                    """
                    SELECT r.id AS review_task_id, r.risk_level, r.submitted_by,
                           r.decided_by, r.decision_reason,
                           r.document_version_id, r.source_policy_id,
                           i.id AS item_id, i.item_type, i.is_demo, i.publishable,
                           i.title, i.original_url, i.source_published_at,
                           i.current_document_version_id,
                           s.id AS source_id, s.name AS source_name, s.authority_level,
                           s.lifecycle_state AS source_lifecycle_state_v2,
                           p.policy_version AS source_policy_version,
                           p.status AS source_policy_status, p.document AS policy_document,
                           p.document_sha256 AS source_policy_sha256,
                           p.valid_until AS source_policy_valid_until,
                           policy_v2.status AS source_policy_v2_status,
                           COALESCE(
                             policy_v2.document_sha256 = encode(digest(convert_to(
                               policy_v2.document::text, 'UTF8'
                             ), 'sha256'), 'hex'),
                             false
                           ) AS source_policy_v2_hash_verified,
                           policy_v2.valid_from AS source_policy_v2_valid_from,
                           policy_v2.valid_until AS source_policy_v2_valid_until,
                           COALESCE(source_v2_policy_compliance_approved(
                               s.id, policy_v2.id, :evaluated_at
                           ), false) AS source_policy_v2_compliance_approved,
                           config_v2.validation_status
                               AS source_connector_config_v2_status,
                           trial_v2.kind AS source_trial_v2_kind,
                           trial_v2.execution_domain AS source_trial_v2_execution_domain,
                           trial_result_v2.status AS source_trial_v2_result_status,
                           EXISTS (
                               SELECT 1
                               FROM source_governance_decision approval_v2
                               WHERE approval_v2.source_id = s.id
                                 AND approval_v2.policy_version_id = policy_v2.id
                                 AND approval_v2.connector_config_version_id = config_v2.id
                                 AND approval_v2.trial_run_id = trial_v2.id
                                 AND approval_v2.decision_type = 'PRODUCTION_APPROVAL'
                                 AND approval_v2.outcome = 'APPROVED'
                                 AND (
                                   approval_v2.valid_until IS NULL
                                   OR approval_v2.valid_until > :evaluated_at
                                 )
                           ) AS source_production_approval_current,
                           d.id AS document_id, d.current_version_id,
                           v.content_hash,
                           v.execution_domain AS document_version_execution_domain,
                           raw.sha256 AS raw_sha256,
                           regulation_profile.document_number,
                           regulation_profile.issuing_authority,
                           regulation_profile.effective_at,
                           COALESCE(regulation_profile.regulation_status, 'UNKNOWN')
                               AS regulation_status,
                           safety_profile.report_stage AS safety_report_stage,
                           safety_profile.incident_status AS safety_incident_status,
                           safety_profile.accident_type AS safety_accident_type,
                           safety_profile.engineering_type AS safety_engineering_type,
                           safety_profile.occurred_at AS safety_occurred_at,
                           safety_profile.region_code AS safety_region_code,
                           safety_profile.region_name AS safety_region_name,
                           safety_profile.project_name AS safety_project_name,
                           safety_profile.subject_names AS safety_subject_names,
                           safety_profile.deaths AS safety_deaths,
                           safety_profile.injuries AS safety_injuries,
                           safety_profile.missing_count AS safety_missing_count,
                           safety_profile.loss_amount_minor AS safety_loss_amount_minor,
                           safety_profile.loss_currency AS safety_loss_currency,
                           safety_profile.official_direct_causes
                               AS safety_official_direct_causes,
                           safety_profile.responsibility_findings
                               AS safety_responsibility_findings,
                           safety_profile.rectification_has_open_issues
                               AS safety_rectification_has_open_issues,
                           safety_profile.similar_scenario_tags
                               AS safety_similar_scenario_tags,
                           safety_profile.prevention_measure_tags
                               AS safety_prevention_measure_tags,
                           safety_profile.privacy_status AS safety_privacy_status,
                           safety_profile.reputational_risk_reviewed
                               AS safety_reputational_risk_reviewed,
                           membership.event_id,
                           safety_event.confirmation_status AS event_confirmation_status,
                           run.paragraphs, run.semantic_safety_scan_pass,
                           run.prompt_injection_detected,
                           run.security_resolution_status,
                           run.security_scanner_version,
                           state.state AS processing_state,
                           security.status AS raw_security_status
                    FROM review_task r
                    JOIN intelligence_item i ON i.id = r.item_id
                    JOIN source s ON s.id = i.source_id
                    JOIN source_policy p ON p.id = r.source_policy_id
                    LEFT JOIN source_policy_version policy_v2
                      ON policy_v2.id = s.current_policy_version_id
                     AND policy_v2.source_id = s.id
                    LEFT JOIN connector_config_version config_v2
                      ON config_v2.id = s.current_connector_config_version_id
                     AND config_v2.source_id = s.id
                     AND config_v2.policy_version_id = policy_v2.id
                    LEFT JOIN source_trial_run trial_v2
                      ON trial_v2.id = s.current_trial_run_id
                     AND trial_v2.source_id = s.id
                     AND trial_v2.policy_version_id = policy_v2.id
                     AND trial_v2.connector_config_version_id = config_v2.id
                    LEFT JOIN source_trial_run_result trial_result_v2
                      ON trial_result_v2.trial_run_id = trial_v2.id
                    JOIN document d ON d.id = i.primary_document_id
                    JOIN document_version v ON v.id = r.document_version_id
                    JOIN raw_object raw ON raw.id = v.raw_object_id
                    LEFT JOIN safety_regulation_profile regulation_profile
                      ON regulation_profile.item_id = i.id
                     AND i.item_type = 'SAFETY_REGULATION'
                    LEFT JOIN safety_case_profile safety_profile
                      ON safety_profile.item_id = i.id
                     AND i.item_type = 'SAFETY_CASE'
                    LEFT JOIN digital_case_profile digital_profile
                      ON digital_profile.item_id = i.id
                     AND i.item_type = 'DIGITAL_CASE'
                    LEFT JOIN event_item membership ON membership.item_id = i.id
                    LEFT JOIN event safety_event ON safety_event.id = membership.event_id
                    JOIN processing_run run ON run.document_version_id = v.id
                    LEFT JOIN LATERAL (
                        SELECT event.state
                        FROM document_version_state_event event
                        WHERE event.document_version_id = v.id
                        ORDER BY event.created_at DESC, event.id DESC LIMIT 1
                    ) state ON true
                    LEFT JOIN LATERAL (
                        SELECT CASE
                          WHEN bool_or(fact.status IN ('REJECTED','QUARANTINED'))
                            THEN 'QUARANTINED'
                          WHEN bool_or(fact.status = 'CLEAN') THEN 'CLEAN'
                          ELSE NULL
                        END AS status
                        FROM raw_object_security_fact fact
                        WHERE fact.raw_object_id = raw.id
                    ) security ON true
                    WHERE r.id = :review_task_id
                      AND (
                        (i.item_type = 'SAFETY_REGULATION'
                         AND regulation_profile.item_id IS NOT NULL)
                        OR
                        (i.item_type = 'SAFETY_CASE'
                         AND safety_profile.item_id IS NOT NULL)
                        OR
                        (i.item_type = 'DIGITAL_CASE'
                         AND digital_profile.item_id IS NOT NULL)
                      )
                    ORDER BY run.completed_at DESC, run.id DESC LIMIT 1
                    """
                ),
                {"review_task_id": review_task_id, "evaluated_at": evaluated_at},
            )
        )
        .mappings()
        .first()
    )


def _source_is_effectively_active(
    facts: RowMapping | Mapping[str, Any],
    *,
    evaluated_at: datetime,
) -> bool:
    valid_from = facts.get("source_policy_v2_valid_from")
    valid_until = facts.get("source_policy_v2_valid_until")
    return bool(
        facts.get("source_lifecycle_state_v2") == "ACTIVE"
        # Policy rows are immutable submissions and remain PENDING_REVIEW;
        # the current append-only COMPLIANCE decision is authoritative.
        and facts.get("source_policy_v2_status") == "PENDING_REVIEW"
        and facts.get("source_policy_v2_hash_verified") is True
        and isinstance(valid_from, datetime)
        and valid_from <= evaluated_at
        and isinstance(valid_until, datetime)
        and valid_until > evaluated_at
        and facts.get("source_policy_v2_compliance_approved") is True
        and facts.get("source_connector_config_v2_status") == "VALID"
        and facts.get("source_trial_v2_kind") == "LIVE_TRIAL"
        and facts.get("source_trial_v2_execution_domain") == "TRIAL"
        and facts.get("source_trial_v2_result_status") == "SUCCEEDED"
        and facts.get("source_production_approval_current") is True
    )


def _legacy_source_policy_is_valid(
    facts: RowMapping | Mapping[str, Any],
    *,
    source_policy: dict[str, Any],
    evaluated_at: datetime,
) -> bool:
    valid_until = facts.get("source_policy_valid_until")
    return bool(
        facts.get("source_policy_status") == "VALID"
        and isinstance(valid_until, datetime)
        and valid_until > evaluated_at
        and facts.get("source_policy_sha256") == canonical_json_hash(source_policy)
    )


def _excerpt_policy_pass(policy: dict[str, Any]) -> bool:
    copyright_policy = policy.get("copyright", {})
    return bool(
        copyright_policy.get("fulltext_allowed") is False
        and copyright_policy.get("display_policy") == "METADATA_EXCERPT_LINK"
        and 0 < int(copyright_policy.get("excerpt_max_chars", 0)) <= 1000
    )


def _attribution_policy_pass(policy: dict[str, Any]) -> bool:
    return bool(str(policy.get("copyright", {}).get("attribution_template", "")).strip())


def _privacy_projection(
    *,
    item_type: str,
    privacy_status: str | None,
    reputational_risk_reviewed: bool | None,
) -> dict[str, object]:
    if item_type != "SAFETY_CASE":
        return {
            "status": "CLEAR",
            "scanner_version": "rules-1.0.0",
            "reputational_risk_reviewed": True,
        }
    reviewed = reputational_risk_reviewed is True
    status = privacy_status or "PENDING_REVIEW"
    if status in {"CLEAR", "REDACTED_AND_APPROVED"} and not reviewed:
        status = "PENDING_REVIEW"
    return {
        "status": status,
        "scanner_version": "rules-1.0.0",
        "reputational_risk_reviewed": reviewed,
    }


def _formal_basis_state(value: object) -> str:
    if value is None:
        return "NO_FORMAL_BASIS"
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        return "INVALID_FORMAL_BASIS"
    return "FORMAL_REVIEWED_NO_FINDING" if not value else "FORMAL_REVIEWED_FINDINGS"


def _controlled_tags_only(similar: object, prevention: object) -> bool:
    if not isinstance(similar, list) or not isinstance(prevention, list):
        return False
    allowed_similar = {tag.value for tag in SimilarScenarioTag}
    allowed_prevention = {tag.value for tag in PreventionMeasureTag}
    return all(isinstance(tag, str) and tag in allowed_similar for tag in similar) and all(
        isinstance(tag, str) and tag in allowed_prevention for tag in prevention
    )


def _publication_snapshot(
    facts: Mapping[str, Any] | RowMapping,
) -> dict[str, object]:
    published_at = facts.get("source_published_at")
    published_value = published_at.isoformat() if isinstance(published_at, datetime) else None
    base: dict[str, object] = {
        "item_id": str(facts["item_id"]),
        "item_type": str(facts["item_type"]),
        "title": facts["title"],
        "source_name": facts["source_name"],
        "original_url": facts["original_url"],
        "published_at": published_value,
    }
    if facts["item_type"] == "DIGITAL_CASE":
        base["profile_type"] = "DIGITAL_CASE"
        return base
    if facts["item_type"] != "SAFETY_CASE":
        base.update(
            {
                "document_number": facts["document_number"],
                "issuing_authority": facts["issuing_authority"],
                "regulation_status": facts["regulation_status"],
            }
        )
        return base

    occurred_at = facts.get("safety_occurred_at")
    event_id = facts.get("event_id")
    base.update(
        {
            "profile_type": "SAFETY_CASE",
            "event_id": str(event_id) if event_id is not None else None,
            "report_stage": facts.get("safety_report_stage"),
            "incident_status": facts.get("safety_incident_status"),
            "hazard_type": facts.get("safety_accident_type"),
            "engineering_type": facts.get("safety_engineering_type"),
            "occurred_at": (occurred_at.isoformat() if isinstance(occurred_at, datetime) else None),
            "region": facts.get("safety_region_name"),
            "project_name": facts.get("safety_project_name"),
            "deaths": facts.get("safety_deaths"),
            "injuries": facts.get("safety_injuries"),
            "loss_amount_minor": facts.get("safety_loss_amount_minor"),
            "loss_currency": facts.get("safety_loss_currency"),
            "official_direct_causes": facts.get("safety_official_direct_causes"),
            "responsibility_findings": facts.get("safety_responsibility_findings"),
            "rectification_has_open_issues": facts.get("safety_rectification_has_open_issues"),
            "similar_scenario_tags": list(facts.get("safety_similar_scenario_tags") or []),
            "prevention_measure_tags": list(facts.get("safety_prevention_measure_tags") or []),
        }
    )
    return base


def _evaluate_evidence(
    rows: list[RowMapping] | list[dict[str, object]],
    paragraphs_value: object,
    *,
    item_type: str = "SAFETY_REGULATION",
) -> dict[str, object]:
    paragraphs = {
        str(item.get("paragraph_id")): str(item.get("text"))
        for item in cast(list[dict[str, object]], paragraphs_value)
        if isinstance(item, dict)
    }
    claim_ids = {row["id"] for row in rows}
    if item_type == "SAFETY_CASE":
        protected_claim_ids = {
            row["id"]
            for row in rows
            if row["claim_type"] in _SAFETY_PROTECTED_CLAIM_TYPES
            and row.get("field_decision_action") == "ACCEPT"
        }
        metadata_claim_ids = {
            row["id"]
            for row in rows
            if row["claim_type"] in _SAFETY_METADATA_CLAIM_TYPES
            and row["critical"] is False
            and row["verification_status"] == "ACCEPTED"
        }
        accepted_claim_ids = protected_claim_ids | metadata_claim_ids
        critical_claim_ids = set(accepted_claim_ids)
        evidence_rows = [
            row
            for row in rows
            if row["id"] in accepted_claim_ids
            and row["evidence_id"] is not None
            and (
                row["id"] in metadata_claim_ids
                or row["evidence_id"] == row.get("field_decision_evidence_id")
            )
        ]
    else:
        accepted_claim_ids = {row["id"] for row in rows if row["verification_status"] == "ACCEPTED"}
        critical_claim_ids = {row["id"] for row in rows if row["critical"] is True}
        evidence_rows = [row for row in rows if row["evidence_id"] is not None]
    claims_with_evidence = {row["id"] for row in evidence_rows}
    locators_valid = True
    excerpts_match = True
    critical_ocr_confidences: list[int] = []
    for row in evidence_rows:
        excerpt = str(row["excerpt"])
        if row["locator_type"] in {"PDF_TEXT", "PDF_OCR", "PDF_TABLE_CELL"}:
            x0_mpt = row["x0_mpt"]
            y0_mpt = row["y0_mpt"]
            x1_mpt = row["x1_mpt"]
            y1_mpt = row["y1_mpt"]
            valid_box = (
                row["page_number"] is not None
                and isinstance(x0_mpt, int)
                and isinstance(y0_mpt, int)
                and isinstance(x1_mpt, int)
                and isinstance(y1_mpt, int)
                and x1_mpt > x0_mpt
                and y1_mpt > y0_mpt
            )
            if not valid_box or excerpt not in str(row["block_text"] or ""):
                locators_valid = False
                excerpts_match = False
            if sha256(excerpt.encode()).hexdigest() != row["excerpt_sha256"]:
                excerpts_match = False
            if row["locator_type"] == "PDF_OCR" and row["critical"] is True:
                confidence = row["evidence_confidence_bps"]
                critical_ocr_confidences.append(confidence if isinstance(confidence, int) else 0)
            continue
        paragraph = paragraphs.get(str(row["paragraph_id"]))
        char_start = row["char_start"]
        char_end = row["char_end"]
        start = char_start if isinstance(char_start, int) else -1
        end = char_end if isinstance(char_end, int) else -1
        if paragraph is None or start < 0 or end <= start or end > len(paragraph):
            locators_valid = False
            excerpts_match = False
            continue
        if (
            paragraph[start:end] != excerpt
            or sha256(excerpt.encode()).hexdigest() != row["excerpt_sha256"]
        ):
            excerpts_match = False
    coverage = (
        100
        if not critical_claim_ids
        else int(100 * len(critical_claim_ids & accepted_claim_ids) / len(critical_claim_ids))
    )
    return {
        "claim_count": len(accepted_claim_ids),
        "evidence_count": len(evidence_rows),
        "bidirectional_refs_valid": bool(claim_ids and accepted_claim_ids <= claims_with_evidence),
        "locators_verified": locators_valid,
        "excerpts_match_source": excerpts_match,
        "accepted_critical_claim_coverage_percent": coverage,
        "unresolved_conflict_count": 0,
        "minimum_critical_ocr_confidence_bps": (
            min(critical_ocr_confidences) if critical_ocr_confidences else 10000
        ),
        "validator_version": "rules-1.0.0",
    }


async def _round03_gate_facts(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    document_version_id: UUID,
    accepted_claim_count: int,
    regulation_status: str,
    authority_level: str,
    minimum_summary_claim_count: int = 4,
) -> dict[str, object]:
    unresolved_relations = int(
        await connection.scalar(
            text(
                """
                SELECT count(*)
                FROM document_relation_candidate candidate
                WHERE candidate.item_id = :item_id
                  AND candidate.document_version_id = :version_id
                  AND NOT EXISTS (
                    SELECT 1 FROM document_relation relation
                    WHERE relation.candidate_id = candidate.id
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM content_lifecycle_event event
                    WHERE event.target_type = 'RELATION_CANDIDATE'
                      AND event.target_id = candidate.id
                      AND event.state IN ('REJECTED','CONFIRMED_UNRESOLVED')
                  )
                """
            ),
            {"item_id": item_id, "version_id": document_version_id},
        )
        or 0
    )
    unreviewed_status = int(
        await connection.scalar(
            text(
                """
                SELECT count(*)
                FROM regulation_status_candidate candidate
                WHERE candidate.item_id = :item_id
                  AND candidate.document_version_id = :version_id
                  AND NOT EXISTS (
                    SELECT 1 FROM content_lifecycle_event event
                    WHERE event.target_type = 'REGULATION_STATUS_CANDIDATE'
                      AND event.target_id = candidate.id
                      AND event.state IN ('ACCEPTED','REJECTED')
                  )
                """
            ),
            {"item_id": item_id, "version_id": document_version_id},
        )
        or 0
    )
    unsafe_attachment_count = int(
        await connection.scalar(
            text(
                """
                SELECT count(*) FROM document_attachment attachment
                WHERE attachment.document_version_id = :version_id
                  AND (
                    attachment.security_status <> 'CLEAN'
                    OR EXISTS (
                      SELECT 1 FROM raw_object_security_fact negative
                       WHERE negative.raw_object_id=attachment.raw_object_id
                         AND negative.status IN ('REJECTED','QUARANTINED')
                    )
                  )
                """
            ),
            {"version_id": document_version_id},
        )
        or 0
    )
    accepted_status_decision = bool(
        await connection.scalar(
            text(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM regulation_status_candidate candidate
                    JOIN content_lifecycle_event event
                      ON event.target_type = 'REGULATION_STATUS_CANDIDATE'
                     AND event.target_id = candidate.id
                     AND event.state = 'ACCEPTED'
                    WHERE candidate.item_id = :item_id
                      AND candidate.document_version_id = :version_id
                )
                """
            ),
            {"item_id": item_id, "version_id": document_version_id},
        )
    )
    return {
        "unresolved_relation_candidate_count": unresolved_relations,
        "unreviewed_regulation_status_candidate_count": unreviewed_status,
        "unsafe_attachment_count": unsafe_attachment_count,
        "summary_claim_refs_valid": accepted_claim_count >= minimum_summary_claim_count,
        "official_status_evidence": (
            regulation_status != "UNKNOWN"
            and authority_level in {"A0", "A1"}
            and accepted_status_decision
        ),
        "status_reviewer_decision": accepted_status_decision,
    }


async def _round05_gate_facts(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    document_version_id: UUID,
) -> dict[str, object]:
    profile = (
        (
            await connection.execute(
                text(
                    """
                    SELECT source_nature, maturity_level, maturity_evidence_ids
                    FROM digital_case_profile
                    WHERE item_id = :item_id
                    """
                ),
                {"item_id": item_id},
            )
        )
        .mappings()
        .one()
    )
    classification_count = int(
        await connection.scalar(
            text("SELECT count(*) FROM digital_case_taxonomy WHERE item_id = :item_id"),
            {"item_id": item_id},
        )
        or 0
    )
    unauthorized_classifications = int(
        await connection.scalar(
            text(
                """
                SELECT count(*)
                FROM digital_case_taxonomy taxonomy
                JOIN claim ON claim.id = taxonomy.claim_id
                WHERE taxonomy.item_id = :item_id
                  AND (
                    claim.item_id <> :item_id
                    OR claim.document_version_id <> :version_id
                    OR claim.verification_status <> 'ACCEPTED'
                  )
                """
            ),
            {"item_id": item_id, "version_id": document_version_id},
        )
        or 0
    )
    invalid_outcomes = int(
        await connection.scalar(
            text(
                """
                SELECT count(*)
                FROM digital_case_outcome outcome
                WHERE outcome.item_id = :item_id
                  AND (
                    cardinality(outcome.evidence_ids) = 0
                    OR NOT EXISTS (
                      SELECT 1 FROM digital_case_entity_relation relation
                      WHERE relation.item_id = outcome.item_id
                        AND relation.entity_id = outcome.attribution_entity_id
                    )
                    OR NOT EXISTS (
                      SELECT 1 FROM claim
                      WHERE claim.id = outcome.claim_id
                        AND claim.item_id = outcome.item_id
                        AND claim.document_version_id = :version_id
                        AND claim.verification_status = 'ACCEPTED'
                    )
                  )
                """
            ),
            {"item_id": item_id, "version_id": document_version_id},
        )
        or 0
    )
    invalid_verified = int(
        await connection.scalar(
            text(
                """
                SELECT count(*)
                FROM digital_case_outcome
                WHERE item_id = :item_id
                  AND outcome_kind = 'VERIFIED'
                  AND cardinality(independent_evidence_ids) = 0
                """
            ),
            {"item_id": item_id},
        )
        or 0
    )
    maturity_ids = list(profile["maturity_evidence_ids"] or [])
    authorized_maturity_count = 0
    if maturity_ids:
        authorized_maturity_count = int(
            await connection.scalar(
                text(
                    """
                    SELECT count(DISTINCT evidence.id)
                    FROM claim_evidence evidence
                    JOIN claim ON claim.id = evidence.claim_id
                    WHERE claim.item_id = :item_id
                      AND claim.document_version_id = :version_id
                      AND claim.verification_status = 'ACCEPTED'
                      AND evidence.id = ANY(:evidence_ids)
                    """
                ),
                {
                    "item_id": item_id,
                    "version_id": document_version_id,
                    "evidence_ids": maturity_ids,
                },
            )
            or 0
        )
    project_count = int(
        await connection.scalar(
            text(
                """
                SELECT count(*)
                FROM digital_case_entity_relation relation
                JOIN digital_case_entity entity ON entity.id = relation.entity_id
                WHERE relation.item_id = :item_id
                  AND entity.entity_type = 'PROJECT'
                """
            ),
            {"item_id": item_id},
        )
        or 0
    )
    maturity_reasons = validate_maturity(
        str(profile["maturity_level"]),
        MaturityEvidence(
            named_project_count=project_count,
            deployment_count=None,
            operating_months=None,
            acceptance_evidence_count=authorized_maturity_count,
            enterprise_scope_confirmed=str(profile["maturity_level"]) == "ENTERPRISE_SCALE",
        ),
    )
    relevance = (
        (
            await connection.execute(
                text(
                    """
                    SELECT score, rule_version
                    FROM digital_case_relevance
                    WHERE item_id = :item_id
                    """
                ),
                {"item_id": item_id},
            )
        )
        .mappings()
        .first()
    )
    return {
        "source_nature": profile["source_nature"],
        "classification_claims_authorized": (
            classification_count > 0 and unauthorized_classifications == 0
        ),
        "outcome_attribution_valid": invalid_outcomes == 0,
        "verified_outcomes_have_independent_evidence": invalid_verified == 0,
        "maturity_evidence_valid": (
            authorized_maturity_count == len(set(maturity_ids)) and not maturity_reasons
        ),
        "relevance_rule_version": relevance["rule_version"] if relevance else None,
        "relevance_score": int(relevance["score"]) if relevance else None,
        "recommended_actions_valid": True,
    }


async def _round06_gate_facts(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    document_version_id: UUID,
) -> dict[str, object]:
    profile = (
        (
            await connection.execute(
                text(
                    """
                    SELECT normalized_doi, access_level, open_license,
                           open_fulltext_url, abstract, maturity_level,
                           research_interpretation, relation_status
                    FROM paper_profile WHERE item_id = :item_id
                    """
                ),
                {"item_id": item_id},
            )
        )
        .mappings()
        .one()
    )
    pending_duplicates = int(
        await connection.scalar(
            text(
                """
                SELECT count(*) FROM paper_duplicate_candidate
                WHERE candidate_item_id = :item_id AND status = 'PENDING_REVIEW'
                """
            ),
            {"item_id": item_id},
        )
        or 0
    )
    unreviewed_updates = int(
        await connection.scalar(
            text(
                """
                SELECT count(*) FROM item_relation_candidate
                WHERE source_item_id = :item_id
                  AND relation_type IN ('CORRECTS','SUPERSEDES','RETRACTS')
                  AND status = 'PENDING_REVIEW'
                """
            ),
            {"item_id": item_id},
        )
        or 0
    )
    interpretation = profile["research_interpretation"]
    research_refs_valid = True
    if interpretation:
        valid_ref_count = int(
            await connection.scalar(
                text(
                    """
                    SELECT count(DISTINCT claim.id)
                    FROM claim
                    JOIN claim_evidence evidence ON evidence.claim_id = claim.id
                    WHERE claim.item_id = :item_id
                      AND claim.document_version_id = :version_id
                      AND claim.verification_status = 'ACCEPTED'
                      AND claim.id = ANY(CAST(:claim_ids AS uuid[]))
                      AND evidence.id = ANY(CAST(:evidence_ids AS uuid[]))
                    """
                ),
                {
                    "item_id": item_id,
                    "version_id": document_version_id,
                    "claim_ids": interpretation.get("claim_ids", []),
                    "evidence_ids": interpretation.get("evidence_ids", []),
                },
            )
            or 0
        )
        research_refs_valid = valid_ref_count == len(set(interpretation.get("claim_ids", [])))
    access_level = str(profile["access_level"])
    abstract_present = bool(profile["abstract"])
    return {
        "identity_resolved": bool(profile["normalized_doi"]) or pending_duplicates == 0,
        "access_level": access_level,
        "access_policy_valid": (
            (access_level != "METADATA_ONLY" or not abstract_present)
            and (access_level == "OPEN_FULLTEXT" or profile["open_fulltext_url"] is None)
        ),
        "abstract_permitted": access_level in {"ABSTRACT_ALLOWED", "OPEN_FULLTEXT"},
        "abstract_present": abstract_present,
        "fulltext_storage_count": 0,
        "fulltext_link_licensed": bool(
            access_level == "OPEN_FULLTEXT"
            and profile["open_fulltext_url"]
            and profile["open_license"]
        ),
        "research_claim_refs_valid": research_refs_valid,
        "maturity_evidence_valid": str(profile["maturity_level"])
        not in {"SINGLE_PROJECT_PRODUCTION", "MULTI_PROJECT_REPLICATION", "ENTERPRISE_SCALE"},
        "unreviewed_update_relation_count": unreviewed_updates,
        "relation_status": profile["relation_status"],
    }


async def _round07_gate_facts(
    connection: AsyncConnection,
    *,
    item_id: UUID,
) -> dict[str, object]:
    profile = (
        (
            await connection.execute(
                text(
                    """
                    SELECT profile.version_id, profile.item_type, profile.permit_status,
                           profile.image_downloaded, profile.limitations,
                           vendor.name AS vendor_name,
                           product_document.source_id AS product_source_id
                    FROM technology_product_profile profile
                    JOIN intelligence_item item ON item.id = profile.item_id
                    JOIN document_version product_version
                      ON product_version.id = item.current_document_version_id
                    JOIN document product_document
                      ON product_document.id = product_version.document_id
                    JOIN technology_product_version version ON version.id = profile.version_id
                    JOIN technology_product_model model ON model.id = version.model_id
                    JOIN technology_product product ON product.id = model.product_id
                    JOIN technology_vendor vendor ON vendor.id = product.vendor_id
                    WHERE profile.item_id = :item_id
                    """
                ),
                {"item_id": item_id},
            )
        )
        .mappings()
        .one()
    )
    capabilities = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT kind, statement, attribution, evidence_ids, independent_evidence_ids
                    FROM technology_product_capability
                    WHERE item_id = :item_id
                    ORDER BY id
                    """
                ),
                {"item_id": item_id},
            )
        ).mappings()
    )
    pending_identity_candidates = int(
        await connection.scalar(
            text(
                """
                SELECT count(*) FROM product_normalization_candidate
                WHERE status = 'PENDING_REVIEW'
                  AND (
                    incoming_version_id = :version_id
                    OR candidate_version_id = :version_id
                  )
                """
            ),
            {"version_id": profile["version_id"]},
        )
        or 0
    )
    permit_evidence_authorized = bool(
        await connection.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM technology_product_capability capability
                    CROSS JOIN LATERAL unnest(
                        capability.evidence_ids || capability.independent_evidence_ids
                    ) AS permit_evidence(evidence_id)
                    JOIN claim_evidence evidence ON evidence.id = permit_evidence.evidence_id
                      AND evidence.claim_id = capability.claim_id
                    JOIN claim ON claim.id = capability.claim_id
                    JOIN document_version version ON version.id = evidence.document_version_id
                    JOIN document ON document.id = version.document_id
                    JOIN source ON source.id = document.source_id
                    WHERE capability.item_id = :item_id
                      AND claim.verification_status = 'ACCEPTED'
                      AND evidence.evidence_role = 'PRIMARY_OFFICIAL'
                      AND source.authority_level IN ('A0','A1')
                )
                """
            ),
            {"item_id": item_id},
        )
    )
    known_capability_count = sum(
        capability["kind"] in {"PROMOTIONAL_CLAIM", "VERIFIED_CAPABILITY"}
        for capability in capabilities
    )
    invalid_verified_capabilities = int(
        await connection.scalar(
            text(
                """
                SELECT count(*)
                FROM technology_product_capability capability
                WHERE capability.item_id = :item_id
                  AND capability.kind = 'VERIFIED_CAPABILITY'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM unnest(capability.independent_evidence_ids)
                      AS independent(evidence_id)
                    JOIN claim_evidence evidence ON evidence.id = independent.evidence_id
                      AND evidence.claim_id = capability.claim_id
                    JOIN document_version version
                      ON version.id = evidence.document_version_id
                    JOIN document ON document.id = version.document_id
                    WHERE evidence.evidence_role = 'INDEPENDENT_CONFIRMATION'
                      AND document.source_id <> :product_source_id
                  )
                """
            ),
            {"item_id": item_id, "product_source_id": profile["product_source_id"]},
        )
        or 0
    )
    promotional_claims_attributed = all(
        capability["kind"] != "PROMOTIONAL_CLAIM" or bool(str(capability["attribution"]).strip())
        for capability in capabilities
    )
    public_text = [str(capability["statement"]) for capability in capabilities]
    public_text.extend(str(value) for value in profile["limitations"] or [])
    return {
        "identity_safe": pending_identity_candidates == 0,
        "capability_groups_separated": known_capability_count == len(capabilities),
        "verified_capabilities_have_independent_evidence": invalid_verified_capabilities == 0,
        "promotional_claims_vendor_attributed": promotional_claims_attributed,
        "procurement_conclusion_count": sum(
            contains_procurement_conclusion(value) for value in public_text
        ),
        "vendor_image_download_count": int(bool(profile["image_downloaded"])),
        "permit_status": str(profile["permit_status"]),
        "permit_evidence_authorized": permit_evidence_authorized,
    }


def _profile_metadata_claims_authorized(
    facts: Mapping[str, object] | RowMapping,
    rows: list[RowMapping] | list[dict[str, object]],
    paragraphs_value: object,
) -> bool:
    """Authorize each populated public profile field from a located accepted claim."""

    expected_item_id = facts.get("item_id")
    for field_name, fact_key in _SAFETY_PROFILE_METADATA_FACT_KEYS.items():
        profile_value = facts.get(fact_key)
        required = field_name in _ALWAYS_REQUIRED_SAFETY_PROFILE_METADATA_FIELDS
        if not _profile_metadata_value_is_present(profile_value):
            if required:
                logger.debug(
                    "Safety profile metadata authorization failed: %s is missing",
                    field_name,
                )
                return False
            continue

        authorized = False
        for row in rows:
            if row.get("claim_type") != field_name:
                continue
            if expected_item_id is not None and row.get("item_id") != expected_item_id:
                continue
            if row.get("verification_status") != "ACCEPTED" or row.get("critical") is not False:
                continue
            if field_name not in _SAFETY_METADATA_CLAIM_TYPES:
                continue
            if not _profile_metadata_values_equal(
                field_name,
                profile_value=profile_value,
                claim_value=row.get("literal_value"),
            ):
                continue
            if not _located_evidence_is_valid(row, paragraphs_value):
                continue
            excerpt = row.get("excerpt")
            if not isinstance(excerpt, str) or not _profile_metadata_evidence_semantically_supports(
                field_name,
                row.get("literal_value"),
                excerpt,
            ):
                continue
            authorized = True
            break
        if not authorized:
            logger.debug(
                "Safety profile metadata authorization failed: %s lacks matching evidence",
                field_name,
            )
            return False
    return True


def _profile_metadata_value_is_present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return True


def _profile_metadata_values_equal(
    field_name: str,
    *,
    profile_value: object,
    claim_value: object,
) -> bool:
    if field_name == SafetyCaseProfileMetadataField.OCCURRED_AT.value:
        if not isinstance(claim_value, str):
            return False
        profile_instant = _rfc3339_utc_instant(profile_value)
        claim_instant = _rfc3339_utc_instant(claim_value)
        return profile_instant is not None and profile_instant == claim_instant

    if field_name == SafetyCaseProfileMetadataField.RECTIFICATION_HAS_OPEN_ISSUES.value:
        return (
            isinstance(profile_value, bool)
            and isinstance(claim_value, bool)
            and profile_value is claim_value
        )

    if field_name in {
        SafetyCaseProfileMetadataField.SIMILAR_SCENARIO_TAGS.value,
        SafetyCaseProfileMetadataField.PREVENTION_MEASURE_TAGS.value,
    }:
        if not isinstance(profile_value, list) or not isinstance(claim_value, list):
            return False
        if not all(isinstance(tag, str) for tag in profile_value + claim_value):
            return False
        profile_tags = cast(list[str], profile_value)
        claim_tags = cast(list[str], claim_value)
        if len(profile_tags) != len(set(profile_tags)) or len(claim_tags) != len(set(claim_tags)):
            return False
        controlled = (
            _controlled_tags_only(profile_tags, []) and _controlled_tags_only(claim_tags, [])
            if field_name == SafetyCaseProfileMetadataField.SIMILAR_SCENARIO_TAGS.value
            else _controlled_tags_only([], profile_tags) and _controlled_tags_only([], claim_tags)
        )
        return controlled and set(profile_tags) == set(claim_tags)

    return (
        isinstance(profile_value, str)
        and isinstance(claim_value, str)
        and profile_value == claim_value
    )


def _rfc3339_utc_instant(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
        value,
    ):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _profile_metadata_evidence_semantically_supports(
    field_name: str,
    claim_value: object,
    excerpt: str,
) -> bool:
    normalized_excerpt = _normalized_source_visible_text(excerpt)
    if not normalized_excerpt:
        return False

    if field_name == SafetyCaseProfileMetadataField.REPORT_STAGE.value:
        supported = _normalized_excerpt_contains_any(
            normalized_excerpt,
            _REPORT_STAGE_EVIDENCE_TERMS.get(str(claim_value), ()),
        )
        return supported or (
            claim_value == "INITIAL_REPORT"
            and _initial_report_cutoff_is_source_visible(normalized_excerpt)
        )
    if field_name == SafetyCaseProfileMetadataField.INCIDENT_STATUS.value:
        supported = _normalized_excerpt_contains_any(
            normalized_excerpt,
            _INCIDENT_STATUS_EVIDENCE_TERMS.get(str(claim_value), ()),
        )
        return (
            supported
            or (
                claim_value == "INITIAL_OFFICIAL_REPORT"
                and _initial_report_cutoff_is_source_visible(normalized_excerpt)
            )
            or (
                claim_value == "UNDER_INVESTIGATION"
                and "继续" in normalized_excerpt
                and "救援" in normalized_excerpt
            )
        )
    if field_name == SafetyCaseProfileMetadataField.ACCIDENT_TYPE.value:
        return _normalized_excerpt_contains_any(
            normalized_excerpt,
            _ACCIDENT_TYPE_EVIDENCE_TERMS.get(str(claim_value), ()),
        )
    if field_name == SafetyCaseProfileMetadataField.ENGINEERING_TYPE.value:
        return _normalized_excerpt_contains_any(
            normalized_excerpt,
            _ENGINEERING_TYPE_EVIDENCE_TERMS.get(str(claim_value), ()),
        )
    if field_name == SafetyCaseProfileMetadataField.OCCURRED_AT.value:
        return _occurred_at_is_source_visible(claim_value, normalized_excerpt)
    if field_name in {
        SafetyCaseProfileMetadataField.REGION_NAME.value,
        SafetyCaseProfileMetadataField.PROJECT_NAME.value,
    }:
        normalized_value = (
            _normalized_source_visible_text(claim_value) if isinstance(claim_value, str) else ""
        )
        return len(normalized_value) >= 2 and normalized_value in normalized_excerpt
    if field_name == SafetyCaseProfileMetadataField.RECTIFICATION_HAS_OPEN_ISSUES.value:
        if not isinstance(claim_value, bool):
            return False
        return _normalized_excerpt_contains_any(
            normalized_excerpt,
            _RECTIFICATION_BOOLEAN_EVIDENCE_TERMS[claim_value],
        )
    if field_name == SafetyCaseProfileMetadataField.SIMILAR_SCENARIO_TAGS.value:
        return _all_controlled_values_source_visible(
            claim_value,
            normalized_excerpt,
            _SIMILAR_TAG_EVIDENCE_TERM_GROUPS,
        )
    if field_name == SafetyCaseProfileMetadataField.PREVENTION_MEASURE_TAGS.value:
        return _all_controlled_values_source_visible(
            claim_value,
            normalized_excerpt,
            _PREVENTION_TAG_EVIDENCE_TERM_GROUPS,
        )
    return False


def _normalized_source_visible_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(normalized.split())


def _normalized_excerpt_contains_any(normalized_excerpt: str, terms: tuple[str, ...]) -> bool:
    return any(_normalized_source_visible_text(term) in normalized_excerpt for term in terms)


def _initial_report_cutoff_is_source_visible(normalized_excerpt: str) -> bool:
    return bool(
        re.search(
            r"截至(?:(?:\d{4}年)?\d{1,2}月\d{1,2}日|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
            normalized_excerpt,
        )
    )


def _all_controlled_values_source_visible(
    claim_value: object,
    normalized_excerpt: str,
    mappings: Mapping[str, tuple[tuple[str, ...], ...]],
) -> bool:
    if (
        not isinstance(claim_value, list)
        or not claim_value
        or not all(isinstance(value, str) for value in claim_value)
    ):
        return False
    values = cast(list[str], claim_value)
    if len(values) != len(set(values)):
        return False
    for value in values:
        term_groups = mappings.get(value)
        if term_groups is None or not all(
            _normalized_excerpt_contains_any(normalized_excerpt, terms) for terms in term_groups
        ):
            return False
    return True


def _occurred_at_is_source_visible(claim_value: object, normalized_excerpt: str) -> bool:
    canonical_instant = _rfc3339_utc_instant(claim_value)
    if canonical_instant is None:
        return False
    local_value = canonical_instant.astimezone(ZoneInfo("Asia/Shanghai"))
    year, month, day = local_value.year, local_value.month, local_value.day
    date_terms = (
        f"{year}-{month:02d}-{day:02d}",
        f"{year}/{month:02d}/{day:02d}",
        f"{year}年{month}月{day}日",
    )
    if not _normalized_excerpt_contains_any(normalized_excerpt, date_terms):
        return False
    if (local_value.hour, local_value.minute, local_value.second) == (0, 0, 0):
        return True
    hour, minute = local_value.hour, local_value.minute
    time_terms = (
        f"{hour:02d}:{minute:02d}",
        f"{hour}:{minute:02d}",
        f"{hour}时{minute}分",
        f"{hour}点{minute}分",
    )
    return _normalized_excerpt_contains_any(normalized_excerpt, time_terms)


def _located_evidence_is_valid(
    row: Mapping[str, object] | RowMapping,
    paragraphs_value: object,
) -> bool:
    if row.get("evidence_id") is None:
        return False
    excerpt = row.get("excerpt")
    excerpt_hash = row.get("excerpt_sha256")
    if (
        not isinstance(excerpt, str)
        or not excerpt
        or not isinstance(excerpt_hash, str)
        or sha256(excerpt.encode()).hexdigest() != excerpt_hash
    ):
        return False

    locator_type = row.get("locator_type")
    if locator_type in {"PDF_TEXT", "PDF_OCR", "PDF_TABLE_CELL"}:
        coordinates = [
            row.get("x0_mpt"),
            row.get("y0_mpt"),
            row.get("x1_mpt"),
            row.get("y1_mpt"),
        ]
        if (
            not isinstance(row.get("page_number"), int)
            or isinstance(row.get("page_number"), bool)
            or not all(
                isinstance(value, int) and not isinstance(value, bool) for value in coordinates
            )
        ):
            return False
        x0_mpt, y0_mpt, x1_mpt, y1_mpt = cast(list[int], coordinates)
        return x1_mpt > x0_mpt and y1_mpt > y0_mpt and excerpt in str(row.get("block_text") or "")

    if locator_type != "HTML_PARAGRAPH":
        return False
    if not isinstance(paragraphs_value, list):
        return False
    paragraphs = {
        str(item.get("paragraph_id")): item.get("text")
        for item in paragraphs_value
        if isinstance(item, Mapping)
        and isinstance(item.get("paragraph_id"), str)
        and isinstance(item.get("text"), str)
    }
    paragraph = paragraphs.get(str(row.get("paragraph_id")))
    char_start = row.get("char_start")
    char_end = row.get("char_end")
    if (
        not isinstance(paragraph, str)
        or not isinstance(char_start, int)
        or isinstance(char_start, bool)
        or not isinstance(char_end, int)
        or isinstance(char_end, bool)
        or char_start < 0
        or char_end <= char_start
        or char_end > len(paragraph)
    ):
        return False
    return paragraph[char_start:char_end] == excerpt


async def _round04_gate_facts(
    connection: AsyncConnection,
    *,
    facts: RowMapping,
    claims: list[RowMapping],
) -> dict[str, object]:
    conflict_counts = (
        (
            await connection.execute(
                text(
                    """
                    SELECT count(*)::integer AS unresolved_count,
                           count(*) FILTER (
                               WHERE conflict.field_name IN (
                                   'deaths','injuries','loss_amount_minor'
                               )
                           )::integer AS casualty_loss_count
                    FROM claim_conflict conflict
                    JOIN event_item membership ON membership.event_id = conflict.event_id
                    WHERE membership.item_id = :item_id
                      AND conflict.status = 'PENDING_REVIEW'
                    """
                ),
                {"item_id": facts["item_id"]},
            )
        )
        .mappings()
        .one()
    )
    unique_claims: dict[object, RowMapping] = {}
    evidence_by_claim: dict[object, list[RowMapping]] = {}
    for claim in claims:
        unique_claims.setdefault(claim["id"], claim)
        if (
            claim["evidence_id"] is not None
            and claim["evidence_id"] == claim["field_decision_evidence_id"]
        ):
            evidence_by_claim.setdefault(claim["id"], []).append(claim)

    effective_claims = list(unique_claims.values())
    unreviewed = _unreviewed_protected_claim_count(effective_claims)
    accepted_by_field: dict[str, list[RowMapping]] = {}
    for claim in effective_claims:
        if claim["field_decision_action"] == "ACCEPT":
            accepted_by_field.setdefault(str(claim["claim_type"]), []).append(claim)

    def qualified(field: str, value: object, *, formal: bool = False) -> bool:
        for claim in accepted_by_field.get(field, []):
            if claim["literal_value"] != value:
                continue
            if claim["field_decision_authority"] not in {"A0", "A1"}:
                continue
            if claim["field_decision_evidence_role"] != "PRIMARY_OFFICIAL":
                continue
            if formal and claim["field_decision_stage"] not in {
                "FINAL_INVESTIGATION",
                "ENFORCEMENT",
            }:
                continue
            return True
        return False

    consequence_fields = {
        "deaths": facts["safety_deaths"],
        "injuries": facts["safety_injuries"],
        "loss_amount_minor": facts["safety_loss_amount_minor"],
    }
    consequence_authorized = True
    for field, value in consequence_fields.items():
        accepted = accepted_by_field.get(field, [])
        if value is None:
            consequence_authorized = consequence_authorized and not accepted
        else:
            consequence_authorized = consequence_authorized and qualified(field, value)
    if facts["safety_loss_amount_minor"] is not None:
        currency = facts["safety_loss_currency"]
        loss_claims = accepted_by_field.get("loss_amount_minor", [])
        consequence_authorized = (
            consequence_authorized
            and isinstance(currency, str)
            and any(
                _evidence_explicitly_supports_currency(
                    evidence_by_claim.get(claim["id"], []), currency
                )
                for claim in loss_claims
                if claim["literal_value"] == facts["safety_loss_amount_minor"]
            )
        )

    causes = facts["safety_official_direct_causes"]
    responsibilities = facts["safety_responsibility_findings"]
    cause_state = _formal_basis_state(causes)
    responsibility_state = _formal_basis_state(responsibilities)
    cause_authorized = causes is not None and qualified(
        "official_direct_causes", causes, formal=True
    )
    responsibility_authorized = responsibilities is not None and qualified(
        "responsibility_findings", responsibilities, formal=True
    )
    if causes is None and accepted_by_field.get("official_direct_causes"):
        cause_state = "FORMAL_BASIS_UNPROJECTED"
    if responsibilities is None and accepted_by_field.get("responsibility_findings"):
        responsibility_state = "FORMAL_BASIS_UNPROJECTED"

    operational_count = sum(
        1
        for claim in effective_claims
        if claim["claim_type"] in _SAFETY_OPERATIONAL_CLAIM_TYPES
        and (
            claim["verification_status"] == "ACCEPTED" or claim["field_decision_action"] == "ACCEPT"
        )
    )
    return {
        "event_assignment_confirmed": bool(
            facts["event_id"] is not None and facts["event_confirmation_status"] == "CONFIRMED"
        ),
        "unreviewed_critical_claim_count": unreviewed,
        "unresolved_conflict_count": int(conflict_counts["unresolved_count"] or 0),
        "unresolved_casualty_loss_conflict_count": int(conflict_counts["casualty_loss_count"] or 0),
        "casualty_loss_claims_authorized": consequence_authorized,
        "cause_basis_state": cause_state,
        "responsibility_basis_state": responsibility_state,
        "formal_cause_evidence_authorized": cause_authorized,
        "formal_responsibility_evidence_authorized": responsibility_authorized,
        "profile_metadata_claims_authorized": _profile_metadata_claims_authorized(
            facts,
            claims,
            facts["paragraphs"] or [],
        ),
        "controlled_prevention_tags_only": _controlled_tags_only(
            facts["safety_similar_scenario_tags"],
            facts["safety_prevention_measure_tags"],
        ),
        "operational_instruction_count": operational_count,
    }


def _unreviewed_protected_claim_count(
    rows: list[RowMapping] | list[dict[str, object]],
) -> int:
    unique = {row["id"]: row for row in rows}.values()
    return sum(
        1
        for row in unique
        if row["claim_type"] in _SAFETY_PROTECTED_CLAIM_TYPES
        and row.get("field_decision_action") not in {"ACCEPT", "REJECT"}
    )


def _evidence_explicitly_supports_currency(rows: list[RowMapping], currency: str) -> bool:
    expected = currency.upper()
    for row in rows:
        excerpt = str(row["excerpt"] or "")
        upper = excerpt.upper()
        if expected in upper:
            return True
        if expected == "CNY" and ("人民币" in excerpt or "元" in excerpt):
            return True
        if expected == "USD" and "美元" in excerpt:
            return True
        if expected == "EUR" and "欧元" in excerpt:
            return True
    return False


def _candidate_schema_valid(
    rows: list[RowMapping] | list[dict[str, object]],
    *,
    item_type: str = "SAFETY_REGULATION",
) -> bool:
    if item_type in {"DIGITAL_CASE", "JOURNAL_PAPER"}:
        accepted = [row for row in rows if row["verification_status"] == "ACCEPTED"]
        return bool(accepted) and all(
            row.get("evidence_id") is not None and row.get("critical") is False for row in accepted
        )
    if item_type == "SAFETY_CASE":
        grouped: dict[object, list[RowMapping | dict[str, object]]] = {}
        for candidate_row in rows:
            grouped.setdefault(candidate_row["id"], []).append(candidate_row)
        consequence_fields = {"deaths", "injuries", "loss_amount_minor"}
        formal_fields = {"official_direct_causes", "responsibility_findings"}
        eligible_claim_count = 0
        for claim_rows in grouped.values():
            row = claim_rows[0]
            claim_type = str(row["claim_type"])
            value = row["literal_value"]
            if claim_type in _SAFETY_PROTECTED_CLAIM_TYPES:
                if row["critical"] is not True:
                    return False
                if claim_type in consequence_fields:
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        return False
                elif claim_type in formal_fields and (
                    not isinstance(value, list)
                    or any(not isinstance(item, str) or not item.strip() for item in value)
                ):
                    return False
                if row.get("field_decision_action") == "ACCEPT":
                    if not any(
                        evidence_row["evidence_id"] is not None
                        and evidence_row["evidence_id"] == row.get("field_decision_evidence_id")
                        for evidence_row in claim_rows
                    ):
                        return False
                    eligible_claim_count += 1
                continue
            if row["critical"] is True:
                return False
            if row["verification_status"] != "ACCEPTED":
                continue
            if claim_type not in _SAFETY_METADATA_CLAIM_TYPES:
                return False
            if not any(
                evidence_row["evidence_id"] is not None for evidence_row in claim_rows
            ) or not _safety_metadata_value_valid(claim_type, value):
                return False
            eligible_claim_count += 1
        return eligible_claim_count > 0
    accepted_types = {row["claim_type"] for row in rows if row["verification_status"] == "ACCEPTED"}
    return {
        "title",
        "issuing_authority",
        "document_number",
        "published_at",
    }.issubset(accepted_types)


def _safety_metadata_value_valid(claim_type: str, value: object) -> bool:
    if claim_type == "rectification_has_open_issues":
        return isinstance(value, bool)
    if claim_type == "missing_count":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if claim_type == "similar_scenario_tags":
        return isinstance(value, list) and _controlled_tags_only(value, [])
    if claim_type == "prevention_measure_tags":
        return isinstance(value, list) and _controlled_tags_only([], value)
    if claim_type == "enforcement_actions":
        return (isinstance(value, str) and bool(value.strip())) or (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value)
        )
    return isinstance(value, str) and bool(value.strip())


async def _apply_event_identity_change(
    connection: AsyncConnection, *, request_id: UUID, operation: str
) -> None:
    targets = list(
        (
            await connection.execute(
                text(
                    "SELECT event_id,target_role FROM event_identity_change_target "
                    "WHERE request_id=:request_id"
                ),
                {"request_id": request_id},
            )
        ).mappings()
    )
    if operation == "MERGE":
        canonical = next(row["event_id"] for row in targets if row["target_role"] == "CANONICAL")
        aliases = [row["event_id"] for row in targets if row["target_role"] == "ALIAS"]
        await connection.execute(
            text(
                "UPDATE event SET status='MERGED',canonical_event_id=:canonical,"
                "version=version+1,updated_at=now() WHERE id=ANY(CAST(:aliases AS uuid[]))"
            ),
            {"canonical": canonical, "aliases": aliases},
        )
        await connection.execute(
            text("UPDATE event SET version=version+1,updated_at=now() WHERE id=:canonical"),
            {"canonical": canonical},
        )
    elif operation == "SPLIT":
        source = next(row["event_id"] for row in targets if row["target_role"] == "SOURCE")
        await connection.execute(
            text(
                "UPDATE event SET status='SPLIT',canonical_event_id=id,"
                "version=version+1,updated_at=now() WHERE id=:source"
            ),
            {"source": source},
        )
    elif operation == "ROLLBACK":
        ids = [row["event_id"] for row in targets]
        await connection.execute(
            text(
                "UPDATE event SET status='ACTIVE',canonical_event_id=id,"
                "version=version+1,updated_at=now() WHERE id=ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )


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
            """
            SELECT append_audit_event(
                :id, :event_type, :actor_id, :target_type, :target_id, NULL,
                CAST(:after_state AS jsonb), :reason, :request_id, :created_at
            )
            """
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
