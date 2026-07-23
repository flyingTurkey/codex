"""Durable ID-only handoff from source documents to the governed AI queue."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_api.ai_pipeline.content_preparation import production_policy_for_stream
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.qualification_decisions import (
    persist_qualification_policy_bundle,
)

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
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            policy_bundle_id = await self._active_policy_bundle(
                connection,
                outbox_id=outbox_id,
                now=now,
            )
            row = (
                (
                    await connection.execute(
                        text(_HANDOFF_SQL),
                        {
                            "outbox_id": outbox_id,
                            "pipeline_run_id": pipeline_run_id,
                            "policy_bundle_id": policy_bundle_id,
                            "now": now,
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

    async def _active_policy_bundle(
        self,
        connection: AsyncConnection,
        *,
        outbox_id: UUID,
        now: datetime,
    ) -> UUID:
        policy_context = (
            (
                await connection.execute(
                    text(_POLICY_CONTEXT_SQL),
                    {"outbox_id": outbox_id},
                )
            )
            .mappings()
            .one()
        )
        stream_version = str(policy_context["source_stream_policy_version"])
        active_bundle_id = policy_context.get("policy_bundle_id")
        if isinstance(active_bundle_id, UUID):
            return active_bundle_id
        policy = production_policy_for_stream(stream_version)
        bundle_id = await persist_qualification_policy_bundle(
            connection,
            policy=policy,
            created_at=now,
        )
        await connection.execute(
            text(_BOOTSTRAP_POLICY_SQL),
            {
                "activation_id": uuid7(),
                "stream_version": stream_version,
                "bundle_id": bundle_id,
                "now": now,
            },
        )
        resolved = await connection.scalar(
            text(
                "SELECT policy_bundle_id FROM active_qualification_policy_v2 "
                "WHERE source_stream_policy_version=:stream_version"
            ),
            {"stream_version": stream_version},
        )
        if not isinstance(resolved, UUID):
            raise RuntimeError("ACTIVE_QUALIFICATION_POLICY_NOT_PERSISTED")
        return resolved

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
  FROM handoff_source_content_to_ai(
    :outbox_id,:pipeline_run_id,:policy_bundle_id,:now
  )
"""

_POLICY_CONTEXT_SQL = """
SELECT source_stream_policy_version,policy_bundle_id
  FROM source_content_policy_context_v2(:outbox_id)
"""

_BOOTSTRAP_POLICY_SQL = """
SELECT append_qualification_policy_activation_v2(
  :activation_id,:stream_version,:bundle_id,NULL,'BOOTSTRAP',
  'ADR_0005_PRODUCTION_BASELINE',NULL,NULL,:now
)
"""

_FAIL_SQL = """
SELECT fail_source_content_handoff(:outbox_id,:reason_code,:now)
"""
