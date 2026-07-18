# ruff: noqa: E501, S608
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    OwnerRelationshipCorrectionRequest,
    OwnerRelationshipCorrectionResponse,
)

from srbg_api.identifiers import uuid7
from srbg_api.intelligence_resolution.automatic_relationships import (
    AutomaticRelationshipInput,
    RelationshipKind,
    RelationshipSuppression,
    decide_automatic_relationship,
)
from srbg_api.observability import (
    PERSONAL_AUTOMATIC_RELATIONSHIPS,
    PERSONAL_RELATIONSHIP_CORRECTIONS,
)
from srbg_api.publication.personal_signals import (
    PersonalSignalInput,
    build_personal_signal_projections,
)
from srbg_api.publication.service import PublicationDenied

logger = logging.getLogger(__name__)


class PostgresPublicationRepository:
    """The only repository configured with the dedicated publication writer role."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

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
