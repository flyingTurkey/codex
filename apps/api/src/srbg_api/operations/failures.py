"""Privacy-safe task failure records persisted outside Redis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.identifiers import uuid7

TASK_POLICIES = {
    "srbg.safety_regulations.discover": ("SOURCE_FETCH", True),
    "srbg.source.fetch": ("SOURCE_FETCH", True),
    "srbg.publication.outbox": ("PUBLICATION_OUTBOX", True),
    "srbg.publication.projections": ("PROJECTION", True),
    "srbg.ai.generate": ("AI", False),
}


@dataclass(frozen=True, slots=True)
class FailureRecord:
    id: UUID
    task_kind: str
    execution_id: UUID
    replayable: bool
    error_code: str
    priority: int
    failed_at: datetime
    source_id: UUID | None = None
    run_id: UUID | None = None
    document_version_id: UUID | None = None
    event_id: UUID | None = None
    processing_version: str | None = None
    reconstruction_status: str = "NON_REPLAYABLE"
    blocked_reason: str | None = None


def failure_record(
    *,
    task_name: str,
    task_id: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    exception: BaseException,
    priority: int = 5,
) -> FailureRecord:
    del args
    try:
        execution_id = UUID(task_id)
    except ValueError:
        execution_id = uuid7()
    task_kind, policy_replayable = TASK_POLICIES.get(task_name, ("UNKNOWN", False))
    source_id = _safe_uuid(kwargs.get("source_id"))
    run_id = _safe_uuid(kwargs.get("run_id"))
    document_version_id = _safe_uuid(kwargs.get("document_version_id"))
    event_id = _safe_uuid(kwargs.get("event_id"))
    has_authoritative_reference = any((run_id, document_version_id, event_id))
    requires_reference = task_name == "srbg.source.fetch"
    replayable = policy_replayable and (has_authoritative_reference or not requires_reference)
    if run_id is not None:
        execution_id = run_id
    error_code = re.sub(r"[^A-Z0-9_]", "_", type(exception).__name__.upper())[:80]
    return FailureRecord(
        id=uuid7(),
        task_kind=task_kind,
        execution_id=execution_id,
        replayable=replayable,
        error_code=error_code or "UNKNOWN",
        priority=max(0, min(priority, 9)),
        failed_at=datetime.now(UTC),
        source_id=source_id,
        run_id=run_id,
        document_version_id=document_version_id,
        event_id=event_id,
        processing_version=_bounded_version(kwargs.get("processing_version")),
        reconstruction_status="REPLAYABLE" if replayable else "NON_REPLAYABLE",
        blocked_reason=(
            None if replayable else "LEGACY_TASK_ID_ONLY" if requires_reference else None
        ),
    )


def _safe_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value is not None else None
    except ValueError:
        return None


def _bounded_version(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value)
    return candidate[:100] if re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", candidate) else None


async def persist_failure(engine: AsyncEngine, record: FailureRecord) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """INSERT INTO failed_task
                   (id, task_kind, execution_id, replayable, error_code,
                    priority, attempts, failed_at, source_id, run_id,
                    document_version_id, event_id, processing_version,
                    reconstruction_status, blocked_reason)
                   VALUES (:id, :task_kind, :execution_id, :replayable,
                           :error_code, :priority, 1, :failed_at, :source_id, :run_id,
                           :document_version_id, :event_id, :processing_version,
                           :reconstruction_status, :blocked_reason)"""
            ),
            record.__dict__
            if hasattr(record, "__dict__")
            else {
                "id": record.id,
                "task_kind": record.task_kind,
                "execution_id": record.execution_id,
                "replayable": record.replayable,
                "error_code": record.error_code,
                "priority": record.priority,
                "failed_at": record.failed_at,
                "source_id": record.source_id,
                "run_id": record.run_id,
                "document_version_id": record.document_version_id,
                "event_id": record.event_id,
                "processing_version": record.processing_version,
                "reconstruction_status": record.reconstruction_status,
                "blocked_reason": record.blocked_reason,
            },
        )
