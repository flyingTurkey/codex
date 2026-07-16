"""PostgreSQL-authoritative replay queue and payload-free reconstruction guards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from srbg_api.acquisition.contracts import ExecutionDomain
from srbg_api.connectors.config import ConnectorKind
from srbg_api.connectors.replay import (
    FixedFixtureTransport,
    FixedReplayExecutor,
    FixtureExchange,
    InMemoryEvidenceStore,
)
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


class ReplayObjectReader(Protocol):
    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes: ...


@dataclass(frozen=True, slots=True)
class SourceFetchReplayOutcome:
    replay_run_id: UUID
    discovery_records: int
    document_versions: int
    raw_objects: int


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
                    AND p.document->>'storage_policy'='RAW_EVIDENCE_ALLOWED'
                    AND c.validation_status='VALID'
                    AND c.policy_version_id=p.id
                    AND EXISTS (
                      SELECT 1 FROM source_governance_decision decision
                       WHERE decision.source_id=s.id
                         AND decision.policy_version_id=p.id
                         AND decision.connector_config_version_id=c.id
                         AND decision.trial_run_id=s.current_trial_run_id
                         AND decision.decision_type='PRODUCTION_APPROVAL'
                         AND decision.outcome='APPROVED'
                         AND (decision.valid_until IS NULL OR decision.valid_until > :now)
                    )
                    AND EXISTS (
                      SELECT 1 FROM raw_object_capture capture
                      JOIN raw_object raw ON raw.id=capture.raw_object_id
                     WHERE capture.fetch_run_id=r.id
                       AND capture.execution_domain='PRODUCTION'
                       AND EXISTS (
                         SELECT 1 FROM raw_object_security_fact fact
                          WHERE fact.raw_object_id=raw.id AND fact.status='CLEAN'
                       )
                       AND NOT EXISTS (
                         SELECT 1 FROM raw_object_security_fact fact
                          WHERE fact.raw_object_id=raw.id
                            AND fact.status IN ('REJECTED','QUARANTINED')
                       )
                    )"""
            ),
            {"run": row["run_id"], "source": row["source_id"], "now": now},
        )
        return None if valid else "SOURCE_POLICY_RUN_OR_RAW_EVIDENCE_STALE"
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
    replay_run_id = uuid7()
    async with engine.begin() as connection:
        inserted = await connection.execute(
            text(
                """INSERT INTO fetch_run (
                       id,source_connector_id,trigger,status,started_at,request_id,
                       source_id,schedule_id,policy_version_id,
                       connector_config_version_id,idempotency_key,attempt_count,
                       execution_domain,run_origin,replayed_from_run_id,
                       pilot_window_source_id
                     )
                     SELECT :replay_run,source_connector_id,'FIXTURE',
                            'RUNNING',now(),:request_id,source_id,
                            schedule_id,policy_version_id,connector_config_version_id,
                            :idempotency_key,1,'FIXTURE','REPLAY',id,NULL
                       FROM fetch_run
                      WHERE id=:original_run AND source_id=:source
                        AND run_origin='SCHEDULED'
                        AND execution_domain='PRODUCTION'"""
            ),
            {
                "replay_run": replay_run_id,
                "original_run": replay.run_id,
                "source": replay.source_id,
                "request_id": f"replay:{replay.id}",
                "idempotency_key": f"replay:{replay.id}",
            },
        )
        if not inserted.rowcount:
            raise RuntimeError("SOURCE_FETCH_RUN_MISSING")
    return replay.source_id, replay_run_id


async def execute_source_fetch_replay(
    engine: AsyncEngine,
    replay: ClaimedReplay,
    object_reader: ReplayObjectReader,
    *,
    max_bytes: int,
    now: datetime | None = None,
) -> SourceFetchReplayOutcome:
    """Replay immutable production responses through the current parser without sockets.

    The replay run is explicitly FIXTURE/REPLAY and never enters the Round 17 pilot
    segment.  The parent replay is allowed to succeed only after every referenced
    object has been hash-verified and the deterministic connector replay finishes.
    """

    observed_at = now or datetime.now(UTC)
    _source_id, replay_run_id = await prepare_source_fetch_replay(engine, replay)
    try:
        header, capture_rows = await _load_source_fetch_replay(
            engine,
            replay=replay,
            replay_run_id=replay_run_id,
            now=observed_at,
        )
        exchanges: list[FixtureExchange] = []
        for capture in capture_rows:
            content = await object_reader.get_bytes(
                str(capture["object_key"]),
                max_bytes=max_bytes,
            )
            if len(content) != _required_int(capture, "byte_size"):
                raise RuntimeError("SOURCE_FETCH_REPLAY_BYTE_SIZE_MISMATCH")
            if sha256(content).hexdigest() != capture["sha256"]:
                raise RuntimeError("SOURCE_FETCH_REPLAY_CONTENT_HASH_MISMATCH")
            headers = {"content-type": str(capture["detected_mime"])}
            if capture["etag"] is not None:
                headers["etag"] = str(capture["etag"])
            if capture["last_modified"] is not None:
                headers["last-modified"] = str(capture["last_modified"])
            exchanges.append(
                FixtureExchange(
                    url=str(capture["requested_url"]),
                    status_code=_required_int(capture, "http_status"),
                    headers=headers,
                    content=content,
                )
            )
        if not exchanges:
            raise RuntimeError("SOURCE_FETCH_REPLAY_RAW_EVIDENCE_MISSING")
        transport = FixedFixtureTransport(tuple(exchanges))
        store = InMemoryEvidenceStore()
        executor = FixedReplayExecutor(
            transport=transport,
            store=store,
            now=lambda: observed_at,
        )
        result = await executor.run(
            ConnectorKind(str(header["connector_type"])),
            header["config_document"],
            source_allowed_hosts=_required_string_tuple(header, "allowed_hosts"),
            domain=ExecutionDomain.FIXTURE,
        )
        await _finish_source_fetch_replay_run(
            engine,
            replay_run_id,
            succeeded=True,
            discovered_count=len(result.discovery_records),
            document_count=len(result.document_versions),
            reason=None,
            now=observed_at,
        )
        return SourceFetchReplayOutcome(
            replay_run_id=replay_run_id,
            discovery_records=len(result.discovery_records),
            document_versions=len(result.document_versions),
            raw_objects=len(result.raw_objects),
        )
    except Exception as error:
        await _finish_source_fetch_replay_run(
            engine,
            replay_run_id,
            succeeded=False,
            discovered_count=0,
            document_count=0,
            reason=_bounded_replay_error(error),
            now=observed_at,
        )
        raise


async def _load_source_fetch_replay(
    engine: AsyncEngine,
    *,
    replay: ClaimedReplay,
    replay_run_id: UUID,
    now: datetime,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if replay.run_id is None or replay.source_id is None:
        raise RuntimeError("SOURCE_FETCH_AUTHORITATIVE_REFERENCE_MISSING")
    async with engine.connect() as connection:
        header_row = (
            (
                await connection.execute(
                    text(
                        """SELECT definition.connector_type,config.config_document,
                                  config.allowed_hosts
                             FROM fetch_run replay_run
                             JOIN source source_row ON source_row.id=replay_run.source_id
                             JOIN source_policy_version policy
                               ON policy.id=source_row.current_policy_version_id
                              AND policy.id=replay_run.policy_version_id
                             JOIN connector_config_version config
                               ON config.id=replay_run.connector_config_version_id
                              AND config.id=source_row.current_connector_config_version_id
                              AND config.policy_version_id=policy.id
                             JOIN connector_definition definition
                               ON definition.id=config.connector_definition_id
                            WHERE replay_run.id=:replay_run
                              AND replay_run.source_id=:source
                              AND replay_run.replayed_from_run_id=:original_run
                              AND replay_run.run_origin='REPLAY'
                              AND replay_run.execution_domain='FIXTURE'
                              AND replay_run.status='RUNNING'
                              AND source_row.lifecycle_state='ACTIVE'
                              AND policy.status='APPROVED'
                              AND policy.valid_from <= :now AND policy.valid_until > :now
                              AND policy.document->>'storage_policy'='RAW_EVIDENCE_ALLOWED'
                              AND config.validation_status='VALID'
                              AND EXISTS (
                                SELECT 1 FROM source_governance_decision decision
                                 WHERE decision.source_id=source_row.id
                                   AND decision.policy_version_id=policy.id
                                   AND decision.connector_config_version_id=config.id
                                   AND decision.trial_run_id=source_row.current_trial_run_id
                                   AND decision.decision_type='PRODUCTION_APPROVAL'
                                   AND decision.outcome='APPROVED'
                                   AND (decision.valid_until IS NULL
                                        OR decision.valid_until > :now)
                              )"""
                    ),
                    {
                        "replay_run": replay_run_id,
                        "source": replay.source_id,
                        "original_run": replay.run_id,
                        "now": now,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if header_row is None:
            raise RuntimeError("SOURCE_FETCH_REPLAY_BINDING_STALE")
        capture_rows = (
            (
                await connection.execute(
                    text(
                        """SELECT capture.requested_url,capture.http_status,capture.etag,
                                  capture.last_modified,raw.object_key,raw.sha256,
                                  raw.detected_mime,raw.byte_size
                             FROM raw_object_capture capture
                             JOIN raw_object raw ON raw.id=capture.raw_object_id
                            WHERE capture.fetch_run_id=:original_run
                              AND capture.source_id=:source
                              AND capture.execution_domain='PRODUCTION'
                              AND EXISTS (
                                SELECT 1 FROM raw_object_security_fact fact
                                 WHERE fact.raw_object_id=raw.id AND fact.status='CLEAN'
                              )
                              AND NOT EXISTS (
                                SELECT 1 FROM raw_object_security_fact fact
                                 WHERE fact.raw_object_id=raw.id
                                   AND fact.status IN ('REJECTED','QUARANTINED')
                              )
                            ORDER BY capture.captured_at,capture.id"""
                    ),
                    {"original_run": replay.run_id, "source": replay.source_id},
                )
            )
            .mappings()
            .all()
        )
    return dict(header_row), [dict(row) for row in capture_rows]


async def _finish_source_fetch_replay_run(
    engine: AsyncEngine,
    replay_run_id: UUID,
    *,
    succeeded: bool,
    discovered_count: int,
    document_count: int,
    reason: str | None,
    now: datetime,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """UPDATE fetch_run
                      SET status=:status,completed_at=:now,
                          discovered_count=:discovered,fetched_count=:documents,
                          failed_count=:failed,error_code=:reason,
                          transport_status=:transport,discovery_status=:discovery_status,
                          parse_status=:parse_status,quality_status=:quality_status
                    WHERE id=:run AND run_origin='REPLAY'
                      AND execution_domain='FIXTURE' AND status='RUNNING'"""
            ),
            {
                "run": replay_run_id,
                "status": "SUCCEEDED" if succeeded else "FAILED",
                "now": now,
                "discovered": discovered_count,
                "documents": document_count,
                "failed": 0 if succeeded else 1,
                "reason": reason,
                "transport": "OK" if succeeded else "REPLAY_FAILED",
                "discovery_status": "OK" if succeeded else "REPLAY_FAILED",
                "parse_status": "OK" if succeeded else "REPLAY_FAILED",
                "quality_status": "OK" if succeeded else "REPLAY_FAILED",
            },
        )


def _bounded_replay_error(error: Exception) -> str:
    code = re.sub(r"[^A-Z0-9_]", "_", str(error).upper()).strip("_")
    if not code:
        code = type(error).__name__.upper()
    return code[:100]


def _required_int(values: dict[str, object], key: str) -> int:
    value = values.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"SOURCE_FETCH_REPLAY_{key.upper()}_INVALID")
    return value


def _required_string_tuple(values: dict[str, object], key: str) -> tuple[str, ...]:
    value = values.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise RuntimeError(f"SOURCE_FETCH_REPLAY_{key.upper()}_INVALID")
    return tuple(value)
