"""PostgreSQL replay queue claimed in priority order without Redis authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True, slots=True)
class ClaimedReplay:
    id: UUID
    failed_task_id: UUID
    task_kind: str
    priority: int


async def claim_replay(engine: AsyncEngine) -> ClaimedReplay | None:
    async with engine.begin() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        """WITH candidate AS (
                             SELECT id FROM replay_request
                              WHERE status = 'QUEUED'
                              ORDER BY priority DESC, requested_at
                              LIMIT 1 FOR UPDATE SKIP LOCKED
                           )
                           UPDATE replay_request AS replay
                              SET status = 'RUNNING'
                             FROM candidate, failed_task AS failed
                            WHERE replay.id = candidate.id
                              AND failed.id = replay.failed_task_id
                           RETURNING replay.id, replay.failed_task_id, failed.task_kind,
                                     replay.priority"""
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
    return ClaimedReplay(**row) if row is not None else None


async def finish_replay(engine: AsyncEngine, replay: ClaimedReplay, *, succeeded: bool) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE replay_request SET status = :status WHERE id = :id"),
            {"id": replay.id, "status": "SUCCEEDED" if succeeded else "FAILED"},
        )
        if succeeded:
            await connection.execute(
                text("UPDATE failed_task SET resolved_at = :now WHERE id = :id"),
                {"id": replay.failed_task_id, "now": datetime.now(UTC)},
            )
