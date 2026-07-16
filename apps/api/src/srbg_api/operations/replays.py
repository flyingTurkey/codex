"""PostgreSQL-authoritative replay queue and payload-free reconstruction guards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from srbg_api.identifiers import uuid7


@dataclass(frozen=True, slots=True)
class ClaimedReplay:
    id: UUID
    failed_task_id: UUID
    task_kind: str
    priority: int
    source_id: UUID | None
    run_id: UUID | None
    document_version_id: UUID | None
    event_id: UUID | None
    processing_version: str | None
    lease_token: UUID


async def _current_reference_error(
    connection: AsyncConnection, row: dict[str, object], now: datetime
) -> str | None:
    kind = row["task_kind"]
    if kind == "AI":
        return "AI_DISABLED"
    if kind == "SOURCE_FETCH":
        valid = await connection.scalar(
            text(
                """SELECT 1 FROM fetch_run r
                   JOIN source s ON s.id=r.source_id
                   JOIN source_policy_version p ON p.id=s.current_policy_version_id
                   JOIN connector_config_version c
                     ON c.id=s.current_connector_config_version_id
                  WHERE r.id=:run AND r.source_id=:source
                    AND r.policy_version_id=p.id
                    AND r.connector_config_version_id=c.id
                    AND s.lifecycle_state='ACTIVE'
                    AND p.status='APPROVED'
                    AND p.valid_from <= :now AND p.valid_until > :now
                    AND c.validation_status='VALID'"""
            ),
            {"run": row["run_id"], "source": row["source_id"], "now": now},
        )
        return None if valid else "SOURCE_POLICY_OR_RUN_STALE"
    if kind == "PARSER":
        valid = await connection.scalar(
            text(
                """SELECT 1 FROM document_version v
                   JOIN raw_object raw ON raw.id=v.raw_object_id
                  WHERE v.id=:version AND raw.scan_status='CLEAN'"""
            ),
            {"version": row["document_version_id"]},
        )
        return None if valid else "EVIDENCE_DELETED_OR_UNAVAILABLE"
    if kind == "PUBLICATION_OUTBOX":
        return None
    if kind == "PROJECTION":
        if row["event_id"] is None:
            return None
        valid = await connection.scalar(
            text("SELECT 1 FROM event WHERE id=:event"), {"event": row["event_id"]}
        )
        return None if valid else "EVENT_REFERENCE_MISSING"
    return "UNKNOWN_TASK_KIND"


async def claim_replay(engine: AsyncEngine, *, now: datetime | None = None) -> ClaimedReplay | None:
    observed_at = now or datetime.now(UTC)
    token = uuid7()
    async with engine.begin() as connection:
        candidate = (
            (
                await connection.execute(
                    text(
                        """SELECT r.id,r.failed_task_id,r.priority,f.task_kind,
                                  f.source_id,f.run_id,f.document_version_id,f.event_id,
                                  f.processing_version,f.reconstruction_status
                           FROM replay_request r
                           JOIN failed_task f ON f.id=r.failed_task_id
                          WHERE (r.status='QUEUED'
                             OR (r.status='RUNNING' AND r.leased_until <= :now))
                            AND f.resolved_at IS NULL
                          ORDER BY r.priority DESC,r.requested_at
                          LIMIT 1 FOR UPDATE OF r SKIP LOCKED"""
                    ),
                    {"now": observed_at},
                )
            )
            .mappings()
            .one_or_none()
        )
        if candidate is None:
            return None
        row = dict(candidate)
        error = (
            "RECONSTRUCTION_NOT_APPROVED"
            if row["reconstruction_status"] != "REPLAYABLE"
            and row["task_kind"] not in {"PUBLICATION_OUTBOX", "PROJECTION"}
            else await _current_reference_error(connection, row, observed_at)
        )
        if error is not None:
            status = "BLOCKED" if error == "AI_DISABLED" else "NON_REPLAYABLE"
            await connection.execute(
                text(
                    """UPDATE replay_request
                          SET status=:status,outcome_reason=:reason,completed_at=:now
                        WHERE id=:id"""
                ),
                {"id": row["id"], "status": status, "reason": error, "now": observed_at},
            )
            await connection.execute(
                text(
                    """UPDATE failed_task
                          SET replayable=false,reconstruction_status=:status,
                              blocked_reason=:reason
                        WHERE id=:id"""
                ),
                {
                    "id": row["failed_task_id"],
                    "status": status,
                    "reason": error,
                },
            )
            return None
        await connection.execute(
            text(
                """UPDATE replay_request
                      SET status='RUNNING',lease_token=:token,leased_until=:until
                    WHERE id=:id"""
            ),
            {
                "id": row["id"],
                "token": token,
                "until": observed_at + timedelta(minutes=10),
            },
        )
    return ClaimedReplay(
        id=row["id"],
        failed_task_id=row["failed_task_id"],
        task_kind=str(row["task_kind"]),
        priority=int(row["priority"]),
        source_id=row["source_id"],
        run_id=row["run_id"],
        document_version_id=row["document_version_id"],
        event_id=row["event_id"],
        processing_version=(
            str(row["processing_version"]) if row["processing_version"] is not None else None
        ),
        lease_token=token,
    )


async def finish_replay(
    engine: AsyncEngine,
    replay: ClaimedReplay,
    *,
    succeeded: bool,
    outcome_reason: str | None = None,
    now: datetime | None = None,
) -> None:
    observed_at = now or datetime.now(UTC)
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                """UPDATE replay_request
                      SET status=:status,completed_at=:now,outcome_reason=:reason,
                          lease_token=NULL,leased_until=NULL
                    WHERE id=:id AND status='RUNNING' AND lease_token=:token"""
            ),
            {
                "id": replay.id,
                "token": replay.lease_token,
                "status": "SUCCEEDED" if succeeded else "FAILED",
                "reason": outcome_reason,
                "now": observed_at,
            },
        )
        if succeeded and result.rowcount:
            await connection.execute(
                text("UPDATE failed_task SET resolved_at=:now WHERE id=:id"),
                {"id": replay.failed_task_id, "now": observed_at},
            )


async def prepare_source_fetch_replay(
    engine: AsyncEngine, replay: ClaimedReplay
) -> tuple[UUID, UUID]:
    if replay.source_id is None or replay.run_id is None:
        raise RuntimeError("SOURCE_FETCH_AUTHORITATIVE_REFERENCE_MISSING")
    async with engine.begin() as connection:
        updated = await connection.execute(
            text(
                """UPDATE fetch_run
                      SET status='PENDING_DISPATCH',execution_lease_token=NULL,
                          execution_lease_until=NULL,next_retry_at=NULL
                    WHERE id=:run AND source_id=:source"""
            ),
            {"run": replay.run_id, "source": replay.source_id},
        )
        if not updated.rowcount:
            raise RuntimeError("SOURCE_FETCH_RUN_MISSING")
    return replay.source_id, replay.run_id
