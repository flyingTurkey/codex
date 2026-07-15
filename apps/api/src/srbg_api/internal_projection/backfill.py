"""Idempotent Round 13 shadow backfill owned by the publication writer boundary."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import PublishedEventDetailV1, PublishedEventSummaryV1

from srbg_api.identifiers import uuid7
from srbg_api.internal_projection.domain import ProjectionInput, decide_projection
from srbg_api.observability import INTERNAL_PROJECTION_RECORDS, INTERNAL_PROJECTION_RUNS

LOGGER = logging.getLogger(__name__)
PROJECTION_VERSION = "1.0.0"
SYSTEM_ACTOR = UUID("019b0000-0000-7000-8000-000000001300")


@dataclass(frozen=True, slots=True)
class BackfillReport:
    build_run_id: UUID
    generation: int
    source_count: int
    projected_count: int
    metadata_only_count: int
    full_count: int
    r4_count: int
    invalidated_count: int
    difference_count: int


class ProjectionBackfillError(RuntimeError):
    """The shadow generation failed and was rolled back."""


async def backfill_internal_projection(
    engine: AsyncEngine,
    *,
    actor_id: UUID = SYSTEM_ACTOR,
    now: datetime | None = None,
) -> BackfillReport:
    """Build one complete shadow generation without switching any consumer."""

    try:
        return await _build_internal_projection(
            engine,
            actor_id=actor_id,
            now=now,
        )
    except Exception:
        INTERNAL_PROJECTION_RUNS.labels("failed").inc()
        LOGGER.exception("internal_projection_backfill_failed")
        raise


async def _build_internal_projection(
    engine: AsyncEngine,
    *,
    actor_id: UUID,
    now: datetime | None,
) -> BackfillReport:

    generated_at = now or datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('round13_backfill'))"))
        generation = int(
            await connection.scalar(
                text(
                    "SELECT COALESCE(max(generation), 0) + 1 FROM published_v1.projection_build_run"
                )
            )
        )
        build_run_id = uuid7()
        await connection.execute(
            text(
                """
                INSERT INTO published_v1.projection_build_run
                    (id, generation, projection_version, status, started_at)
                VALUES (:id, :generation, :version, 'RUNNING', :now)
                """
            ),
            {
                "id": build_run_id,
                "generation": generation,
                "version": PROJECTION_VERSION,
                "now": generated_at,
            },
        )
        rows = list((await connection.execute(text(_SOURCE_QUERY))).mappings())
        projected_event_ids: set[UUID] = set()
        metadata_only_count = 0
        full_count = 0
        r4_count = sum(row["publication_risk_tier"] == "R4" for row in rows)

        for row in rows:
            decision = decide_projection(
                ProjectionInput(
                    publication_risk_tier=row["publication_risk_tier"],
                    review_status=row["review_status"],
                    publication_status=row["publication_status"],
                    official_source=row["official_source"],
                    content_severity=row["content_severity"],
                )
            )
            if decision.level == "NONE":
                continue
            event_id = await _stable_event_id(connection, row, actor_id, generated_at)
            if event_id in projected_event_ids:
                continue
            projected_event_ids.add(event_id)
            summary = _summary_payload(row, event_id, generation, decision.level)
            detail: dict[str, Any] | None = None
            claims: list[dict[str, Any]] = []
            if decision.level == "FULL":
                claims = await _accepted_claims(connection, row["item_id"])
                projected_claims = [
                    {key: value for key, value in claim.items() if key != "_sources"}
                    for claim in claims
                ]
                evidence = {
                    str(source["evidence_id"]): {
                        "evidence_id": str(source["evidence_id"]),
                        "locator": f"paragraph:{source['paragraph_id']}",
                        "content_sha256": source["excerpt_sha256"],
                    }
                    for claim in claims
                    for source in claim["_sources"]
                }
                detail = {
                    "summary": summary,
                    "claims": projected_claims,
                    "evidence": list(evidence.values()),
                }
                full_count += 1
            else:
                metadata_only_count += 1
            PublishedEventSummaryV1.model_validate(summary)
            if detail is not None:
                PublishedEventDetailV1.model_validate(detail)

            audit_id = await connection.scalar(
                text(
                    "SELECT append_audit_event(:audit_id, :event_type, :actor_id, :target_type, "
                    ":target_id, NULL, CAST(:after_state AS jsonb), :reason, :request_id, :now)"
                ),
                {
                    "audit_id": uuid7(),
                    "event_type": "INTERNAL_PROJECTION_GENERATED",
                    "actor_id": actor_id,
                    "target_type": "EVENT",
                    "target_id": event_id,
                    "after_state": _json(
                        {"generation": generation, "projection_level": str(decision.level)}
                    ),
                    "reason": decision.reason,
                    "request_id": f"round13-backfill-{build_run_id}",
                    "now": generated_at,
                },
            )
            projection_revision_id = uuid7()
            await connection.execute(
                text(_INSERT_PROJECTION),
                {
                    "id": projection_revision_id,
                    "event_id": event_id,
                    "item_id": row["item_id"],
                    "publication_revision_id": row["publication_revision_id"],
                    "build_run_id": build_run_id,
                    "generation": generation,
                    "version": PROJECTION_VERSION,
                    "risk": row["publication_risk_tier"],
                    "severity": row["content_severity"],
                    "level": str(decision.level),
                    "surfaces": sorted(decision.allowed_surfaces),
                    "summary": _json(summary),
                    "detail": _json(detail) if detail is not None else None,
                    "now": generated_at,
                    "audit_id": audit_id,
                },
            )
            await _record_field_sources(connection, projection_revision_id, row, claims)
            await connection.execute(
                text("UPDATE intelligence_item SET projection_level = :level WHERE id = :item_id"),
                {"level": str(decision.level), "item_id": row["item_id"]},
            )

        invalidated_count = await _invalidate_absent(
            connection, projected_event_ids, generation, generated_at
        )
        differences = await _reconcile_generation(
            connection, build_run_id, generation, generated_at
        )
        projected_count = metadata_only_count + full_count
        await connection.execute(
            text(
                """
                UPDATE published_v1.projection_build_run
                   SET status = 'SUCCEEDED', completed_at = :now, source_count = :source_count,
                       projected_count = :projected_count, difference_count = :difference_count
                 WHERE id = :id
                """
            ),
            {
                "id": build_run_id,
                "now": generated_at,
                "source_count": len(rows),
                "projected_count": projected_count,
                "difference_count": differences,
            },
        )
    LOGGER.info(
        "internal_projection_backfill_completed",
        extra={
            "generation": generation,
            "source_count": len(rows),
            "projected_count": projected_count,
            "metadata_only_count": metadata_only_count,
            "full_count": full_count,
            "r4_count": r4_count,
            "invalidated_count": invalidated_count,
            "difference_count": differences,
        },
    )
    INTERNAL_PROJECTION_RUNS.labels("succeeded").inc()
    INTERNAL_PROJECTION_RECORDS.labels("metadata_only").inc(metadata_only_count)
    INTERNAL_PROJECTION_RECORDS.labels("full").inc(full_count)
    INTERNAL_PROJECTION_RECORDS.labels("r4_isolated").inc(r4_count)
    return BackfillReport(
        build_run_id=build_run_id,
        generation=generation,
        source_count=len(rows),
        projected_count=projected_count,
        metadata_only_count=metadata_only_count,
        full_count=full_count,
        r4_count=r4_count,
        invalidated_count=invalidated_count,
        difference_count=differences,
    )


async def _stable_event_id(connection: Any, row: Any, actor_id: UUID, now: datetime) -> UUID:
    existing = await connection.scalar(
        text("SELECT event_id FROM event_identity_binding WHERE item_id = :item_id"),
        {"item_id": row["item_id"]},
    )
    if existing is not None:
        return UUID(str(existing))
    confirmed = await connection.scalar(
        text(
            "SELECT event_id FROM event_item WHERE item_id = :item_id ORDER BY confirmed_at LIMIT 1"
        ),
        {"item_id": row["item_id"]},
    )
    event_id = confirmed or uuid7()
    binding_kind = "CONFIRMED_MEMBERSHIP" if confirmed else "ROUND13_ONE_TO_ONE"
    if confirmed is None:
        await connection.execute(
            text(
                """
                INSERT INTO event
                    (id, event_type, title, subject_names, confirmation_status,
                     created_at, updated_at)
                VALUES (:id, :event_type, :title, '[]'::jsonb, 'PENDING_REVIEW', :now, :now)
                """
            ),
            {
                "id": event_id,
                "event_type": _event_type(row["item_type"]),
                "title": row["title"],
                "now": now,
            },
        )
        await connection.execute(
            text(
                "UPDATE event SET confirmation_status = 'CONFIRMED', confirmed_by = :actor, "
                "confirmed_at = :now, updated_at = :now WHERE id = :id"
            ),
            {"id": event_id, "actor": actor_id, "now": now},
        )
    await connection.execute(
        text(
            """
            INSERT INTO event_identity_binding
                (event_id, item_id, binding_kind, created_by, created_at)
            VALUES (:event_id, :item_id, :kind, :actor, :now)
            ON CONFLICT (item_id) DO NOTHING
            """
        ),
        {
            "event_id": event_id,
            "item_id": row["item_id"],
            "kind": binding_kind,
            "actor": actor_id,
            "now": now,
        },
    )
    return event_id


def _summary_payload(row: Any, event_id: UUID, generation: int, level: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": str(event_id),
        "publication_revision_id": str(row["publication_revision_id"])
        if row["publication_revision_id"]
        else None,
        "projection_version": PROJECTION_VERSION,
        "generation": generation,
        "domain": row["channel"],
        "content_type": row["item_type"],
        "title": row["title"],
        "source_name": row["source_name"],
        "source_published_at": _iso(row["source_published_at"]),
        "first_discovered_at": _iso(row["first_discovered_at"]),
        "original_url": row["original_url"],
        "review_status": row["review_status"],
        "discovery_status": "MACHINE_DISCOVERED",
        "fact_review_status": "HUMAN_REVIEWED" if level == "FULL" else "PENDING_HUMAN_REVIEW",
        "publication_risk_tier": row["publication_risk_tier"],
        "content_severity": row["content_severity"],
        "projection_level": level,
        "one_sentence_fact": None,
        "type_summary": None,
    }
    if level == "FULL" and row["snapshot"]:
        snapshot = dict(row["snapshot"])
        summary["one_sentence_fact"] = snapshot.get("one_sentence_fact")
        summary["type_summary"] = snapshot.get("type_summary")
    return summary


async def _accepted_claims(connection: Any, item_id: UUID) -> list[dict[str, Any]]:
    rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT claim.id, claim.claim_type, claim.literal_value,
                           evidence.id AS evidence_id, evidence.excerpt_sha256,
                           evidence.paragraph_id
                      FROM claim
                      JOIN claim_evidence evidence ON evidence.claim_id = claim.id
                     WHERE claim.item_id = :item_id
                       AND claim.verification_status = 'ACCEPTED'
                     ORDER BY claim.id, evidence.id
                    """
                ),
                {"item_id": item_id},
            )
        ).mappings()
    )
    grouped: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        claim = grouped.setdefault(
            row["id"],
            {
                "claim_id": str(row["id"]),
                "field_name": row["claim_type"],
                "value": (
                    row["literal_value"]
                    if isinstance(row["literal_value"], str)
                    else _json(row["literal_value"])
                ),
                "evidence_ids": [],
                "_sources": [],
            },
        )
        claim["evidence_ids"].append(str(row["evidence_id"]))
        claim["_sources"].append(dict(row))
    return list(grouped.values())


async def _record_field_sources(
    connection: Any, projection_revision_id: UUID, row: Any, claims: list[dict[str, Any]]
) -> None:
    for field in (
        "title",
        "source_name",
        "source_published_at",
        "first_discovered_at",
        "original_url",
    ):
        await connection.execute(
            text(_INSERT_FIELD_SOURCE),
            {
                "projection_id": projection_revision_id,
                "field": field,
                "claim_id": None,
                "evidence_id": None,
                "document_version_id": row["current_document_version_id"],
                "publication_revision_id": row["publication_revision_id"],
                "sha256": row["content_hash"],
            },
        )
    for claim in claims:
        for index, source in enumerate(claim.pop("_sources")):
            await connection.execute(
                text(_INSERT_FIELD_SOURCE),
                {
                    "projection_id": projection_revision_id,
                    "field": f"claim:{claim['claim_id']}:{index}",
                    "claim_id": source["id"],
                    "evidence_id": source["evidence_id"],
                    "document_version_id": row["current_document_version_id"],
                    "publication_revision_id": row["publication_revision_id"],
                    "sha256": source["excerpt_sha256"],
                },
            )


async def _invalidate_absent(
    connection: Any, current_event_ids: set[UUID], generation: int, now: datetime
) -> int:
    result = await connection.execute(
        text(
            """
            UPDATE published_v1.event_projection_revision
               SET state = 'INVALIDATED', invalidated_at = :now,
                   invalidation_reason = CASE
                     WHEN event_id = ANY(:current_ids) THEN 'SUPERSEDED_GENERATION'
                     ELSE 'SOURCE_NOT_PUBLISHABLE' END
             WHERE state = 'ACTIVE' AND generation < :generation
            """
        ),
        {"now": now, "current_ids": list(current_event_ids), "generation": generation},
    )
    return int(result.rowcount or 0)


async def _reconcile_generation(
    connection: Any, build_run_id: UUID, generation: int, now: datetime
) -> int:
    rows = list((await connection.execute(text(_RECONCILIATION_QUERY))).mappings())
    for row in rows:
        await connection.execute(
            text(
                """
                INSERT INTO projection_reconciliation_difference
                    (id, build_run_id, event_id, item_id, difference_code, details, detected_at)
                VALUES
                    (:id, :run_id, :event_id, :item_id, :code,
                     CAST(:details AS jsonb), :now)
                ON CONFLICT (build_run_id, item_id, difference_code) DO NOTHING
                """
            ),
            {
                "id": uuid7(),
                "run_id": build_run_id,
                "event_id": row["event_id"],
                "item_id": row["item_id"],
                "code": row["difference_code"],
                "details": _json(
                    {
                        "generation": generation,
                        "projection_version": PROJECTION_VERSION,
                    }
                ),
                "now": now,
            },
        )
    return len(rows)


def _event_type(item_type: str) -> str:
    return {
        "SAFETY_CASE": "SAFETY_INCIDENT",
        "SAFETY_REGULATION": "REGULATION_CHANGE",
        "DIGITAL_CASE": "DIGITAL_PROJECT",
        "JOURNAL_PAPER": "RESEARCH_RESULT",
    }.get(item_type, "PRODUCT_RELEASE")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_SOURCE_QUERY = """
SELECT item.id AS item_id, item.item_type, item.channel, item.title, item.original_url,
       item.source_published_at, item.first_discovered_at, item.review_status,
       item.publication_risk_tier, item.content_severity,
       item.current_document_version_id, version.content_hash,
       source.name AS source_name,
       (source.source_type IN ('government','standards') AND source.authority_level IN ('A0','A1'))
         AS official_source,
       publication.status AS publication_status,
       publication.current_revision_id AS publication_revision_id,
       revision.snapshot
  FROM intelligence_item item
  JOIN source ON source.id = item.source_id
  JOIN document_version version ON version.id = item.current_document_version_id
  LEFT JOIN publication ON publication.item_id = item.id
  LEFT JOIN publication_revision revision ON revision.id = publication.current_revision_id
 WHERE item.publication_risk_tier = 'R4'
    OR (item.publication_risk_tier = 'R3' AND item.review_status = 'PENDING'
        AND source.source_type IN ('government','standards')
        AND source.authority_level IN ('A0','A1'))
    OR (item.publication_risk_tier <> 'R4' AND item.review_status = 'APPROVED'
        AND publication.status = 'PUBLISHED' AND revision.valid)
 ORDER BY item.id
"""

_INSERT_PROJECTION = """
INSERT INTO published_v1.event_projection_revision
    (id, event_id, item_id, publication_revision_id, build_run_id, generation,
     projection_version, publication_risk_tier, content_severity, projection_level,
     allowed_surfaces, summary_payload, detail_payload, state, generated_at, audit_log_id)
VALUES
    (:id, :event_id, :item_id, :publication_revision_id, :build_run_id, :generation,
     :version, :risk, :severity, :level, :surfaces, CAST(:summary AS jsonb),
     CAST(:detail AS jsonb), 'ACTIVE', :now, :audit_id)
"""

_INSERT_FIELD_SOURCE = """
INSERT INTO published_v1.event_projection_field_source
    (projection_revision_id, field_name, claim_id, evidence_id, document_version_id,
     publication_revision_id, source_sha256)
VALUES
    (:projection_id, :field, :claim_id, :evidence_id, :document_version_id,
     :publication_revision_id, :sha256)
"""

_RECONCILIATION_QUERY = """
WITH eligible AS (
    SELECT item.id
      FROM intelligence_item item
      JOIN source ON source.id = item.source_id
      LEFT JOIN publication ON publication.item_id = item.id
      LEFT JOIN publication_revision revision ON revision.id = publication.current_revision_id
     WHERE (item.publication_risk_tier = 'R3' AND item.review_status = 'PENDING'
            AND source.source_type IN ('government','standards')
            AND source.authority_level IN ('A0','A1'))
        OR (item.publication_risk_tier <> 'R4' AND item.review_status = 'APPROVED'
            AND publication.status = 'PUBLISHED' AND revision.valid)
)
SELECT NULL::uuid event_id, eligible.id item_id, 'MISSING_EVENT_IDENTITY' difference_code
  FROM eligible LEFT JOIN event_identity_binding binding ON binding.item_id = eligible.id
 WHERE binding.item_id IS NULL
UNION ALL
SELECT projection.event_id, projection.item_id, 'R4_PROJECTED'
  FROM published_v1.event_projection_revision projection
 WHERE projection.state = 'ACTIVE' AND projection.publication_risk_tier = 'R4'
UNION ALL
SELECT projection.event_id, projection.item_id, 'STALE_PUBLICATION_REVISION'
  FROM published_v1.event_projection_revision projection
  JOIN publication ON publication.item_id = projection.item_id
 WHERE projection.state = 'ACTIVE' AND projection.projection_level = 'FULL'
   AND projection.publication_revision_id IS DISTINCT FROM publication.current_revision_id
UNION ALL
SELECT projection.event_id, projection.item_id, 'UNACCEPTED_CLAIM_SOURCE'
  FROM published_v1.event_projection_revision projection
  JOIN published_v1.event_projection_field_source field_source
    ON field_source.projection_revision_id = projection.id
  JOIN claim ON claim.id = field_source.claim_id
 WHERE projection.state = 'ACTIVE' AND claim.verification_status <> 'ACCEPTED'
UNION ALL
SELECT projection.event_id, projection.item_id, 'METADATA_DETAIL_PRESENT'
  FROM published_v1.event_projection_revision projection
 WHERE projection.state = 'ACTIVE' AND projection.projection_level = 'METADATA_ONLY'
   AND projection.detail_payload IS NOT NULL
"""
