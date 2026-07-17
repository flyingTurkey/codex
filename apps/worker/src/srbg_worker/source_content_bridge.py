"""Durable ID-only handoff from source documents to the governed AI queue."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.identifiers import uuid7

logger = logging.getLogger("srbg.worker.source_content_bridge")


@dataclass(frozen=True, slots=True)
class ContentPipelineHandoff:
    outbox_id: UUID
    document_version_id: UUID
    pipeline_run_id: UUID
    status: str
    queued: bool

    def __post_init__(self) -> None:
        if self.status != "WAITING_AI":
            raise ValueError("source content handoff status is invalid")


class SourceContentGateway(Protocol):
    async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]: ...

    async def handoff(
        self,
        outbox_id: UUID,
        *,
        pipeline_run_id: UUID,
    ) -> ContentPipelineHandoff | None: ...

    async def mark_failed(self, outbox_id: UUID, *, reason_code: str) -> None: ...

    async def close(self) -> None: ...


class SourceContentOutboxExecutor:
    """Move one durable outbox fact to ``ai_pipeline_run=QUEUED`` exactly once."""

    def __init__(self, *, gateway: SourceContentGateway) -> None:
        self._gateway = gateway

    async def run(self, outbox_id: UUID) -> ContentPipelineHandoff | None:
        try:
            return await self._gateway.handoff(
                outbox_id,
                pipeline_run_id=uuid7(),
            )
        except Exception as error:
            reason_code = _exception_reason_code(error)
            try:
                await self._gateway.mark_failed(outbox_id, reason_code=reason_code)
            except Exception:
                logger.exception(
                    "source_content_failure_recording_failed",
                    extra={
                        "event_name": "source_content_failure_recording_failed",
                        "outbox_id": str(outbox_id),
                        "reason_code": reason_code,
                    },
                )
            raise


class PostgresSourceContentGateway:
    """Call only the narrow database commands owned by the bridge migration."""

    def __init__(self, *, engine: AsyncEngine) -> None:
        self._engine = engine

    async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("source content pending limit must be between 1 and 100")
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(_LIST_PENDING_SQL),
                        {"now": datetime.now(UTC), "limit": limit},
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_required_uuid(row.get("id"), "outbox id") for row in rows)

    async def handoff(
        self,
        outbox_id: UUID,
        *,
        pipeline_run_id: UUID,
    ) -> ContentPipelineHandoff | None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_HANDOFF_SQL),
                        {
                            "outbox_id": outbox_id,
                            "pipeline_run_id": pipeline_run_id,
                            "now": datetime.now(UTC),
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return ContentPipelineHandoff(
            outbox_id=_required_uuid(row.get("outbox_id"), "outbox id"),
            document_version_id=_required_uuid(
                row.get("document_version_id"), "document version id"
            ),
            pipeline_run_id=_required_uuid(row.get("pipeline_run_id"), "pipeline run id"),
            status=str(row.get("status")),
            queued=row.get("queued") is True,
        )

    async def mark_failed(self, outbox_id: UUID, *, reason_code: str) -> None:
        if re.fullmatch(r"[A-Z0-9_]{1,80}", reason_code) is None:
            raise ValueError("source content failure reason is invalid")
        async with self._engine.begin() as connection:
            await connection.execute(
                text(_FAIL_SQL),
                {
                    "outbox_id": outbox_id,
                    "reason_code": reason_code,
                    "now": datetime.now(UTC),
                },
            )

    async def close(self) -> None:
        await self._engine.dispose()


def _required_uuid(value: object, field: str) -> UUID:
    if not isinstance(value, UUID):
        raise RuntimeError(f"source content command returned no {field}")
    return value


def _exception_reason_code(error: Exception) -> str:
    value = re.sub(r"[^A-Z0-9_]", "_", type(error).__name__.upper()).strip("_")
    return (value or "UNKNOWN")[:80]


_LIST_PENDING_SQL = """
SELECT outbox_id AS id FROM list_pending_source_content_ids(:now,:limit)
"""

_HANDOFF_SQL = """
SELECT outbox_id,document_version_id,pipeline_run_id,status,queued
  FROM handoff_source_content_to_ai(:outbox_id,:pipeline_run_id,:now)
"""

_FAIL_SQL = """
SELECT fail_source_content_handoff(:outbox_id,:reason_code,:now)
"""
