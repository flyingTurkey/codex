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


def failure_record(
    *,
    task_name: str,
    task_id: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    exception: BaseException,
    priority: int = 5,
) -> FailureRecord:
    del args, kwargs
    try:
        execution_id = UUID(task_id)
    except ValueError:
        execution_id = uuid7()
    task_kind, replayable = TASK_POLICIES.get(task_name, ("UNKNOWN", False))
    error_code = re.sub(r"[^A-Z0-9_]", "_", type(exception).__name__.upper())[:80]
    return FailureRecord(
        id=uuid7(),
        task_kind=task_kind,
        execution_id=execution_id,
        replayable=replayable,
        error_code=error_code or "UNKNOWN",
        priority=max(0, min(priority, 9)),
        failed_at=datetime.now(UTC),
    )


async def persist_failure(engine: AsyncEngine, record: FailureRecord) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """INSERT INTO failed_task
                   (id, task_kind, execution_id, replayable, error_code,
                    priority, attempts, failed_at)
                   VALUES (:id, :task_kind, :execution_id, :replayable,
                           :error_code, :priority, 1, :failed_at)"""
            ),
            record.__dict__ if hasattr(record, "__dict__") else {
                "id": record.id,
                "task_kind": record.task_kind,
                "execution_id": record.execution_id,
                "replayable": record.replayable,
                "error_code": record.error_code,
                "priority": record.priority,
                "failed_at": record.failed_at,
            },
        )
