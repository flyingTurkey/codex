"""Publisher-role repository and authoritative publication evaluation transaction."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from hashlib import sha256
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import ReviewDecisionResponse, ReviewStatus

from srbg_api.identifiers import uuid7
from srbg_api.publication.service import PublicationDenied, PublicationTransaction
from srbg_api.source_registry.repository import canonical_json_hash, fixture_set_hash


class PostgresPublicationRepository:
    """The only repository configured with the dedicated publication writer role."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

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
                                   r.revision_number, r.document_version_id,
                                   r.source_policy_id, r.source_policy_sha256,
                                   r.review_task_id, r.snapshot, r.evaluation
                            FROM publication p
                            JOIN publication_revision r ON r.id = p.current_revision_id
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
                          AND source.authority_level = 'A1'
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
            revision_id = uuid7()
            evaluation = dict(row["evaluation"])
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
                    "review_task_id": row["review_task_id"],
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
            else:
                raise PublicationDenied(("UNKNOWN_CANDIDATE_KIND",))

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

    async def authoritative_context(
        self,
        *,
        evaluation_id: UUID,
        policy_version: str,
        policy_sha256: str,
        evaluated_at: datetime,
    ) -> dict[str, Any]:
        facts = await _publication_facts(self._connection, self._task["id"])
        if facts is None:
            raise PublicationDenied(("AUTHORITATIVE_FACTS_MISSING",))
        self._facts = facts

        source_policy = dict(facts["policy_document"])
        onboarding = dict(facts["onboarding_record"] or {})
        fixture_hashes = list(
            await self._connection.scalars(
                text(
                    """
                    SELECT DISTINCT v.content_hash
                    FROM document_version v
                    JOIN document d ON d.id = v.document_id
                    WHERE d.source_id = :source_id
                      AND d.admission_fixture = true
                    ORDER BY v.content_hash
                    """
                ),
                {"source_id": facts["source_id"]},
            )
        )
        source_effective = _source_is_effectively_active(
            facts,
            source_policy=source_policy,
            onboarding=onboarding,
            fixture_hashes=fixture_hashes,
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
                        SELECT c.id, c.claim_type, c.verification_status, c.critical,
                               c.confidence_bps,
                               e.id AS evidence_id, e.paragraph_id, e.char_start,
                               e.char_end, e.excerpt, e.excerpt_sha256,
                               e.locator_type, e.page_number, e.document_text_block_id,
                               e.x0_mpt, e.y0_mpt, e.x1_mpt, e.y1_mpt,
                               e.confidence_bps AS evidence_confidence_bps,
                               block.normalized_text AS block_text
                        FROM claim c
                        LEFT JOIN claim_evidence e ON e.claim_id = c.id
                        LEFT JOIN document_text_block block
                          ON block.id = e.document_text_block_id
                        WHERE c.item_id = :item_id
                          AND c.document_version_id = :version_id
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
        evidence_integrity = _evaluate_evidence(claims, facts["paragraphs"] or [])
        if policy_version != "3.0.0":
            evidence_integrity.pop("minimum_critical_ocr_confidence_bps", None)
        round03 = await _round03_gate_facts(
            self._connection,
            item_id=facts["item_id"],
            document_version_id=facts["document_version_id"],
            accepted_claim_count=cast(int, evidence_integrity["claim_count"]),
            regulation_status=str(facts["regulation_status"]),
            authority_level=str(facts["authority_level"]),
        )
        content_hash = str(facts["content_hash"])
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
                    "policy_status": "VALID" if source_effective else "INVALID",
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
                },
                "evidence_integrity": evidence_integrity,
                "security": {
                    "prompt_injection_detected": facts["prompt_injection_detected"],
                    "resolution_status": facts["security_resolution_status"],
                    "resolution_id": None,
                    "scanner_version": facts["security_scanner_version"],
                    "input_sha256": content_hash,
                },
                "privacy": {
                    "status": "CLEAR",
                    "scanner_version": "rules-1.0.0",
                    "reputational_risk_reviewed": True,
                },
                "review": {
                    "risk_level": facts["risk_level"],
                    "required": True,
                    "decision_status": "APPROVED",
                    "decision_id": str(facts["review_task_id"]),
                    "submitted_by": str(facts["submitted_by"]),
                    "decided_by": str(facts["decided_by"]),
                    "duties_separated": facts["submitted_by"] != facts["decided_by"],
                },
                "pipeline": {
                    "candidate_schema_valid": _candidate_schema_valid(claims),
                    "semantic_safety_scan_pass": facts["semantic_safety_scan_pass"],
                    "candidate_schema_version": "safety-regulation-parser-1.0.0",
                },
            },
        }
        if policy_version == "3.0.0":
            cast(dict[str, Any], context["server"])["round03"] = round03
            cast(dict[str, Any], cast(dict[str, Any], context["server"])["document"]).update(
                {
                    "processing_state": facts["processing_state"],
                    "raw_security_status": facts["raw_security_status"],
                }
            )
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
        snapshot = {
            "item_id": str(facts["item_id"]),
            "title": facts["title"],
            "source_name": facts["source_name"],
            "original_url": facts["original_url"],
            "document_number": facts["document_number"],
            "issuing_authority": facts["issuing_authority"],
            "published_at": facts["source_published_at"].isoformat(),
            "regulation_status": facts["regulation_status"],
        }
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
        return ReviewDecisionResponse(
            review_task_id=facts["review_task_id"],
            status=ReviewStatus.APPROVED,
            publication_revision_id=revision_id,
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
                    FOR UPDATE OF candidate
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
                    FOR UPDATE OF candidate
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
                           version.content_hash, raw.sha256 AS raw_sha256,
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
                        SELECT fact.status
                        FROM raw_object_security_fact fact
                        WHERE fact.raw_object_id = raw.id
                        ORDER BY fact.created_at DESC, fact.id DESC LIMIT 1
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


async def _publication_facts(
    connection: AsyncConnection, review_task_id: UUID
) -> RowMapping | None:
    return (
        (
            await connection.execute(
                text(
                    """
                    SELECT r.id AS review_task_id, r.risk_level, r.submitted_by,
                           r.decided_by, r.document_version_id, r.source_policy_id,
                           i.id AS item_id, i.item_type, i.is_demo, i.publishable,
                           i.title, i.original_url, i.source_published_at,
                           i.current_document_version_id,
                           s.id AS source_id, s.name AS source_name, s.state AS source_state,
                           s.enabled AS source_enabled, s.authority_level,
                           p.policy_version AS source_policy_version,
                           p.status AS source_policy_status, p.document AS policy_document,
                           p.document_sha256 AS source_policy_sha256,
                           p.valid_until AS source_policy_valid_until,
                           o.source_policy_id AS onboarding_policy_id,
                           o.record AS onboarding_record,
                           o.record_sha256 AS onboarding_sha256,
                           o.fixture_count AS onboarding_fixture_count,
                           o.fixture_set_sha256 AS onboarding_fixture_sha256,
                           o.valid_until AS onboarding_valid_until,
                           d.id AS document_id, d.current_version_id,
                           v.content_hash, raw.sha256 AS raw_sha256,
                           profile.document_number, profile.issuing_authority,
                           profile.effective_at, profile.regulation_status,
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
                    LEFT JOIN LATERAL (
                        SELECT * FROM source_onboarding_record candidate
                        WHERE candidate.source_id = s.id
                        ORDER BY candidate.created_at DESC, candidate.id DESC LIMIT 1
                    ) o ON true
                    JOIN document d ON d.id = i.primary_document_id
                    JOIN document_version v ON v.id = r.document_version_id
                    JOIN raw_object raw ON raw.id = v.raw_object_id
                    JOIN safety_regulation_profile profile ON profile.item_id = i.id
                    JOIN processing_run run ON run.document_version_id = v.id
                    LEFT JOIN LATERAL (
                        SELECT event.state
                        FROM document_version_state_event event
                        WHERE event.document_version_id = v.id
                        ORDER BY event.created_at DESC, event.id DESC LIMIT 1
                    ) state ON true
                    LEFT JOIN LATERAL (
                        SELECT fact.status
                        FROM raw_object_security_fact fact
                        WHERE fact.raw_object_id = raw.id
                        ORDER BY fact.created_at DESC, fact.id DESC LIMIT 1
                    ) security ON true
                    WHERE r.id = :review_task_id
                    ORDER BY run.completed_at DESC, run.id DESC LIMIT 1
                    """
                ),
                {"review_task_id": review_task_id},
            )
        )
        .mappings()
        .first()
    )


def _source_is_effectively_active(
    facts: RowMapping,
    *,
    source_policy: dict[str, Any],
    onboarding: dict[str, Any],
    fixture_hashes: list[str],
    evaluated_at: datetime,
) -> bool:
    return bool(
        facts["source_state"] == "ACTIVE"
        and facts["source_enabled"] is True
        and facts["source_policy_status"] == "VALID"
        and facts["source_policy_valid_until"] > evaluated_at
        and facts["source_policy_sha256"] == canonical_json_hash(source_policy)
        and facts["onboarding_policy_id"] == facts["source_policy_id"]
        and facts["onboarding_valid_until"] is not None
        and facts["onboarding_valid_until"] > evaluated_at
        and onboarding.get("decision") == "APPROVED"
        and facts["onboarding_sha256"] == canonical_json_hash(onboarding)
        and len(set(fixture_hashes)) >= 30
        and facts["onboarding_fixture_count"] == len(set(fixture_hashes))
        and facts["onboarding_fixture_sha256"] == fixture_set_hash(fixture_hashes)
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


def _evaluate_evidence(rows: list[RowMapping], paragraphs_value: object) -> dict[str, object]:
    paragraphs = {
        str(item.get("paragraph_id")): str(item.get("text"))
        for item in cast(list[dict[str, object]], paragraphs_value)
        if isinstance(item, dict)
    }
    claim_ids = {row["id"] for row in rows}
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
            valid_box = (
                row["page_number"] is not None
                and row["x0_mpt"] is not None
                and row["y0_mpt"] is not None
                and row["x1_mpt"] is not None
                and row["y1_mpt"] is not None
                and row["x1_mpt"] > row["x0_mpt"]
                and row["y1_mpt"] > row["y0_mpt"]
            )
            if not valid_box or excerpt not in str(row["block_text"] or ""):
                locators_valid = False
                excerpts_match = False
            if sha256(excerpt.encode()).hexdigest() != row["excerpt_sha256"]:
                excerpts_match = False
            if row["locator_type"] == "PDF_OCR" and row["critical"] is True:
                confidence = row["evidence_confidence_bps"]
                critical_ocr_confidences.append(int(confidence or 0))
            continue
        paragraph = paragraphs.get(str(row["paragraph_id"]))
        start = int(row["char_start"]) if row["char_start"] is not None else -1
        end = int(row["char_end"]) if row["char_end"] is not None else -1
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
                SELECT count(*) FROM document_attachment
                WHERE document_version_id = :version_id
                  AND security_status <> 'CLEAN'
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
        "summary_claim_refs_valid": accepted_claim_count >= 4,
        "official_status_evidence": (
            regulation_status != "UNKNOWN"
            and authority_level in {"A0", "A1"}
            and accepted_status_decision
        ),
        "status_reviewer_decision": accepted_status_decision,
    }


def _candidate_schema_valid(rows: list[RowMapping]) -> bool:
    accepted_types = {row["claim_type"] for row in rows if row["verification_status"] == "ACCEPTED"}
    return {
        "title",
        "issuing_authority",
        "document_number",
        "published_at",
    }.issubset(accepted_types)


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
) -> None:
    await connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('audit_log'))"))
    previous_hash = await connection.scalar(
        text("SELECT entry_hash FROM audit_log ORDER BY created_at DESC, id DESC LIMIT 1")
    )
    audit_id = uuid7()
    canonical = {
        "id": str(audit_id),
        "event_type": event_type,
        "actor_id": str(actor_id),
        "target_type": target_type,
        "target_id": str(target_id),
        "before_state": None,
        "after_state": after_state,
        "reason": reason,
        "request_id": request_id,
        "previous_hash": previous_hash,
        "created_at": now.isoformat(),
    }
    entry_hash = sha256(_json(canonical).encode()).hexdigest()
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                id, event_type, actor_id, target_type, target_id, before_state,
                after_state, reason, request_id, previous_hash, entry_hash, created_at
            ) VALUES (
                :id, :event_type, :actor_id, :target_type, :target_id, NULL,
                CAST(:after_state AS jsonb), :reason, :request_id,
                :previous_hash, :entry_hash, :created_at
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
            "previous_hash": previous_hash,
            "entry_hash": entry_hash,
            "created_at": now,
        },
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
