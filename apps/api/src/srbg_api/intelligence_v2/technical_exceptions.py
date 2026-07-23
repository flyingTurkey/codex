"""Owner-safe projection and commands for autonomous technical exceptions."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import (
    OwnerExceptionCommand,
    OwnerExceptionEventType,
    OwnerExceptionEventView,
    OwnerExceptionView,
)

from srbg_api.auth import Principal, require_local_owner
from srbg_api.identifiers import uuid7
from srbg_api.observability import (
    OWNER_TECHNICAL_EXCEPTION_BACKLOG,
    OWNER_TECHNICAL_EXCEPTION_COMMANDS,
)

TECHNICAL_RETRY_QUEUE_KEY = "srbg:owner:technical-retry-requests:v1"
TECHNICAL_RETRY_PROCESSING_KEY = "srbg:owner:technical-retry-processing:v1"
TECHNICAL_RETRY_DEDUPE_KEY = "srbg:owner:technical-retry-dedupe:v1"
_SYSTEM_ACTOR = UUID("019b0000-0000-7000-8000-000000009002")


class OwnerTechnicalExceptionService(Protocol):
    async def reconcile(self) -> None: ...

    async def list_exceptions(
        self,
        *,
        kind: str | None,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> list[OwnerExceptionView]: ...

    async def get_exception(self, exception_id: UUID) -> OwnerExceptionView: ...

    async def command(
        self,
        *,
        exception_id: UUID,
        command: OwnerExceptionCommand,
        owner_id: UUID,
        idempotency_key: UUID,
    ) -> OwnerExceptionEventView: ...


class TechnicalExceptionNotFound(LookupError):
    pass


class TechnicalExceptionConflict(RuntimeError):
    pass


OwnerPrincipal = Annotated[Principal, Depends(require_local_owner)]
router = APIRouter(prefix="/api/v2/owner/exceptions", tags=["owner-technical-exceptions"])


def _service(request: Request) -> OwnerTechnicalExceptionService:
    value = getattr(request.app.state, "technical_exception_service", None)
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "TECHNICAL_EXCEPTION_SERVICE_UNAVAILABLE",
                "title": "Technical exception service unavailable",
            },
        )
    return cast(OwnerTechnicalExceptionService, value)


@router.get("", response_model=list[OwnerExceptionView])
async def list_owner_exceptions(
    request: Request,
    _: OwnerPrincipal,
    kind: str | None = Query(default="TECHNICAL", max_length=20),
    exception_status: str | None = Query(default=None, alias="status", max_length=20),
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[OwnerExceptionView]:
    try:
        return await _service(request).list_exceptions(
            kind=kind, status=exception_status, cursor=cursor, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_EXCEPTION_FILTER", "title": "Invalid exception filter"},
        ) from exc


@router.get("/{exception_id}", response_model=OwnerExceptionView)
async def get_owner_exception(
    exception_id: UUID, request: Request, _: OwnerPrincipal
) -> OwnerExceptionView:
    try:
        return await _service(request).get_exception(exception_id)
    except TechnicalExceptionNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "TECHNICAL_EXCEPTION_NOT_FOUND", "title": "Exception not found"},
        ) from exc


@router.post(
    "/{exception_id}/commands",
    response_model=OwnerExceptionEventView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def command_owner_exception(
    exception_id: UUID,
    payload: OwnerExceptionCommand,
    request: Request,
    principal: OwnerPrincipal,
    if_match: Annotated[str, Header(alias="If-Match")],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> OwnerExceptionEventView:
    if payload.event_type is not OwnerExceptionEventType.RETRY_REQUESTED:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TECHNICAL_EXCEPTION_COMMAND_UNSUPPORTED",
                "title": "Technical exceptions only support retry requests",
            },
        )
    if if_match != f'"{payload.expected_version}"':
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "code": "TECHNICAL_EXCEPTION_VERSION_HEADER_MISMATCH",
                "title": "Exception version header mismatch",
            },
        )
    try:
        return await _service(request).command(
            exception_id=exception_id,
            command=payload,
            owner_id=principal.user_id,
            idempotency_key=idempotency_key,
        )
    except TechnicalExceptionNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "TECHNICAL_EXCEPTION_NOT_FOUND", "title": "Exception not found"},
        ) from exc
    except TechnicalExceptionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "code": "TECHNICAL_EXCEPTION_VERSION_CONFLICT",
                "title": "Exception has changed",
                "detail": "Refresh the exception and retry with its current version",
            },
        ) from exc


class PostgresOwnerTechnicalExceptionService:
    """Project technical decisions into the API-owned Owner control surface."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        retry_queue: Redis | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine = engine
        self._retry_queue = retry_queue
        self._clock = clock or (lambda: datetime.now(UTC))

    async def close(self) -> None:
        await self._engine.dispose()
        if self._retry_queue is not None:
            await self._retry_queue.aclose()

    async def reconcile(self) -> None:
        now = self._clock()
        async with self._engine.begin() as connection:
            failures = list(
                (
                    await connection.execute(
                        text(
                            "SELECT decision.id AS decision_id,decision.document_version_id,"
                            "decision.attempt_number,document.source_id,fetch_row.source_stream_id,"
                            "COALESCE((SELECT replace(signal #>> '{}','TECHNICAL_REASON:','') "
                            "FROM jsonb_array_elements(decision.rule_signals) signal "
                            "WHERE signal #>> '{}' LIKE 'TECHNICAL_REASON:%' LIMIT 1),"
                            "'TECHNICAL_EXHAUSTED') AS technical_reason_code,"
                            "run.id AS pipeline_run_id FROM automated_qualification_decision_v2 "
                            "decision JOIN document_version version "
                            "ON version.id=decision.document_version_id JOIN document "
                            "ON document.id=version.document_id LEFT JOIN "
                            "raw_object_capture capture "
                            "ON capture.id=version.raw_object_capture_id "
                            "LEFT JOIN fetch_run fetch_row ON fetch_row.id=capture.fetch_run_id "
                            "LEFT JOIN LATERAL("
                            "SELECT pipeline.id FROM ai_pipeline_run pipeline "
                            "WHERE pipeline.document_version_id=version.id "
                            "ORDER BY pipeline.started_at DESC,pipeline.id DESC "
                            "LIMIT 1) run ON true "
                            "WHERE decision.disposition='TECHNICAL_FAILED' "
                            "ORDER BY decision.decided_at,decision.id"
                        )
                    )
                ).mappings()
            )
            for failure in failures:
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {"key": f"owner-technical:{failure['document_version_id']}"},
                )
                already_projected = await connection.scalar(
                    text(
                        "SELECT id FROM owner_exception_v2 WHERE decision_id=:decision OR "
                        "COALESCE(safe_metadata->'projected_decision_ids','[]'::jsonb) "
                        "? :decision_text"
                    ),
                    {
                        "decision": failure["decision_id"],
                        "decision_text": str(failure["decision_id"]),
                    },
                )
                if already_projected is not None:
                    continue
                existing = await connection.scalar(
                    text(
                        "SELECT id FROM owner_exception_v2 WHERE kind='TECHNICAL' "
                        "AND status='OPEN' AND document_version_id=:document"
                    ),
                    {"document": failure["document_version_id"]},
                )
                if existing is not None:
                    updated = (
                        (
                            await connection.execute(
                                text(
                                    "UPDATE owner_exception_v2 SET decision_id=:decision,"
                                    "attempt_count=GREATEST(attempt_count,:attempt),"
                                    "updated_at=:now,version=version+1,"
                                    "safe_metadata=safe_metadata || jsonb_build_object("
                                    "'pipeline_run_id',CAST(:run_id AS text),"
                                    "'technical_reason_code',CAST(:reason AS text),"
                                    "'projected_decision_ids',COALESCE(safe_metadata->"
                                    "'projected_decision_ids','[]'::jsonb) || "
                                    "jsonb_build_array(CAST(:decision_text AS text))) "
                                    "WHERE id=:id RETURNING version"
                                ),
                                {
                                    "id": existing,
                                    "decision": failure["decision_id"],
                                    "decision_text": str(failure["decision_id"]),
                                    "attempt": failure["attempt_number"],
                                    "run_id": str(failure["pipeline_run_id"]),
                                    "reason": failure["technical_reason_code"],
                                    "now": now,
                                },
                            )
                        )
                        .mappings()
                        .one()
                    )
                    await connection.execute(
                        text(
                            "INSERT INTO owner_exception_event_v2("
                            "id,exception_id,event_type,expected_version,idempotency_key,"
                            "safe_metadata,created_at) VALUES("
                            ":id,:exception,'CREATED',:version,:key,"
                            "jsonb_build_object('transition','TECHNICAL_REEXHAUSTED',"
                            "'attempt_count',CAST(:attempt AS integer)),:now)"
                        ),
                        {
                            "id": uuid7(),
                            "exception": existing,
                            "version": updated["version"],
                            "key": uuid7(),
                            "attempt": failure["attempt_number"],
                            "now": now,
                        },
                    )
                    await connection.execute(
                        text(
                            "SELECT append_audit_event(:audit_id,"
                            "'TECHNICAL_EXCEPTION_REEXHAUSTED',:actor,'OWNER_EXCEPTION',"
                            ":target,NULL,jsonb_build_object('status','OPEN','attempt_count',"
                            "CAST(:attempt AS integer),'version',CAST(:version AS integer)),"
                            "'TECHNICAL_RETRY_REEXHAUSTED',:request_id,:now)"
                        ),
                        {
                            "audit_id": uuid7(),
                            "actor": _SYSTEM_ACTOR,
                            "target": existing,
                            "attempt": failure["attempt_number"],
                            "version": updated["version"],
                            "request_id": str(failure["decision_id"]),
                            "now": now,
                        },
                    )
                    continue
                exception_id = uuid7()
                await connection.execute(
                    text(
                        "INSERT INTO owner_exception_v2("
                        "id,kind,status,overrideability,source_id,source_stream_id,"
                        "document_version_id,decision_id,reason_codes,safe_metadata,attempt_count,"
                        "version,opened_at,updated_at,resolved_at) VALUES("
                        ":id,'TECHNICAL','OPEN',NULL,:source,:stream,:document,:decision,"
                        "ARRAY['TECHNICAL_EXHAUSTED'],jsonb_build_object("
                        "'pipeline_run_id',CAST(:run_id AS text),'technical_reason_code',"
                        "CAST(:reason AS text),'projected_decision_ids',"
                        "jsonb_build_array(CAST(:decision_text AS text))) "
                        ",:attempt,1,:now,:now,NULL)"
                    ),
                    {
                        "id": exception_id,
                        "source": failure["source_id"],
                        "stream": failure["source_stream_id"],
                        "document": failure["document_version_id"],
                        "decision": failure["decision_id"],
                        "decision_text": str(failure["decision_id"]),
                        "run_id": str(failure["pipeline_run_id"]),
                        "reason": failure["technical_reason_code"],
                        "attempt": failure["attempt_number"],
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO owner_exception_event_v2("
                        "id,exception_id,event_type,expected_version,idempotency_key,safe_metadata,"
                        "created_at) VALUES(:id,:exception,'CREATED',1,:key,'{}'::jsonb,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "exception": exception_id,
                        "key": uuid7(),
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "SELECT append_audit_event(:audit_id,'TECHNICAL_EXCEPTION_OPENED',"
                        ":actor,'OWNER_EXCEPTION',:target,NULL,"
                        "jsonb_build_object('status','OPEN','attempt_count',"
                        "CAST(:attempt AS integer)),'TECHNICAL_RETRY_EXHAUSTED',:request_id,:now)"
                    ),
                    {
                        "audit_id": uuid7(),
                        "actor": _SYSTEM_ACTOR,
                        "target": exception_id,
                        "attempt": failure["attempt_number"],
                        "request_id": str(failure["decision_id"]),
                        "now": now,
                    },
                )
            fetch_failures = list(
                (
                    await connection.execute(
                        text(
                            "SELECT run.id AS work_id,run.source_id,run.source_stream_id,"
                            "run.attempt_count,run.completed_at,CASE run.failure_class "
                            "WHEN 'TIMEOUT' THEN 'NETWORK_TIMEOUT' "
                            "WHEN 'HTTP_5XX' THEN 'TRANSIENT_UNAVAILABLE' "
                            "WHEN 'RATE_LIMITED' THEN 'TRANSIENT_UNAVAILABLE' "
                            "WHEN 'OBJECT_STORAGE_FAILED' THEN "
                            "'OBJECT_STORE_TEMPORARILY_UNAVAILABLE' "
                            "WHEN 'DATABASE_FAILED' THEN "
                            "'DATABASE_TEMPORARILY_UNAVAILABLE' "
                            "WHEN 'PARSE_FAILED' THEN 'DOCUMENT_VALIDATION_FAILED' "
                            "ELSE 'RUNTIME_EXECUTION_FAILED' END AS technical_reason_code "
                            "FROM fetch_run run WHERE run.status='FAILED' "
                            "AND run.source_stream_id IS NOT NULL "
                            "AND run.failure_class IS NOT NULL "
                            "AND NOT EXISTS(SELECT 1 FROM owner_exception_v2 exception WHERE "
                            "exception.kind='TECHNICAL' AND "
                            "exception.safe_metadata->>'technical_work_kind'='SOURCE_FETCH' AND "
                            "exception.safe_metadata->>'technical_work_id'=run.id::text) "
                            "ORDER BY run.completed_at,run.id"
                        )
                    )
                ).mappings()
            )
            for failure in fetch_failures:
                exception_id = uuid7()
                await connection.execute(
                    text(
                        "INSERT INTO owner_exception_v2("
                        "id,kind,status,overrideability,source_id,source_stream_id,"
                        "document_version_id,decision_id,reason_codes,safe_metadata,attempt_count,"
                        "version,opened_at,updated_at,resolved_at) VALUES("
                        ":id,'TECHNICAL','OPEN',NULL,:source,:stream,NULL,NULL,"
                        "ARRAY['TECHNICAL_EXHAUSTED'],jsonb_build_object("
                        "'technical_work_kind','SOURCE_FETCH','technical_work_id',"
                        "CAST(:work_id AS text),'technical_reason_code',CAST(:reason AS text)),"
                        ":attempt,1,:opened,:now,NULL)"
                    ),
                    {
                        "id": exception_id,
                        "source": failure["source_id"],
                        "stream": failure["source_stream_id"],
                        "work_id": str(failure["work_id"]),
                        "reason": failure["technical_reason_code"],
                        "attempt": failure["attempt_count"],
                        "opened": failure["completed_at"] or now,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO owner_exception_event_v2("
                        "id,exception_id,event_type,expected_version,idempotency_key,safe_metadata,"
                        "created_at) VALUES(:id,:exception,'CREATED',1,:key,'{}'::jsonb,:now)"
                    ),
                    {"id": uuid7(), "exception": exception_id, "key": uuid7(), "now": now},
                )
                await connection.execute(
                    text(
                        "SELECT append_audit_event(:audit_id,'TECHNICAL_EXCEPTION_OPENED',"
                        ":actor,'OWNER_EXCEPTION',:target,NULL,"
                        "jsonb_build_object('status','OPEN','attempt_count',"
                        "CAST(:attempt AS integer)),'SOURCE_FETCH_RETRY_EXHAUSTED',"
                        ":request_id,:now)"
                    ),
                    {
                        "audit_id": uuid7(),
                        "actor": _SYSTEM_ACTOR,
                        "target": exception_id,
                        "attempt": failure["attempt_count"],
                        "request_id": str(failure["work_id"]),
                        "now": now,
                    },
                )
            open_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT exception.id,exception.version,exception.document_version_id,"
                            "failed.decided_at,failed_version.document_id "
                            "FROM owner_exception_v2 exception JOIN "
                            "automated_qualification_decision_v2 failed "
                            "ON failed.id=exception.decision_id JOIN document_version "
                            "failed_version "
                            "ON failed_version.id=exception.document_version_id "
                            "WHERE exception.kind='TECHNICAL' "
                            "AND exception.status='OPEN' FOR UPDATE OF exception"
                        )
                    )
                ).mappings()
            )
            for row in open_rows:
                recovered = await connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM automated_qualification_decision_v2 decision "
                        "JOIN document_version successful_version "
                        "ON successful_version.id=decision.document_version_id "
                        "WHERE successful_version.document_id=:document "
                        "AND decision.decided_at>=:failed_at AND decision.disposition IN "
                        "('AUTO_ACCEPTED','AUTO_FILTERED'))"
                    ),
                    {"document": row["document_id"], "failed_at": row["decided_at"]},
                )
                if not recovered:
                    continue
                await connection.execute(
                    text(
                        "UPDATE owner_exception_v2 SET status='RESOLVED',version=version+1,"
                        "updated_at=:now,resolved_at=:now WHERE id=:id AND status='OPEN'"
                    ),
                    {"id": row["id"], "now": now},
                )
                await connection.execute(
                    text(
                        "INSERT INTO owner_exception_event_v2("
                        "id,exception_id,event_type,expected_version,idempotency_key,safe_metadata,"
                        "created_at) VALUES(:id,:exception,'AUTO_RESOLVED',:version,:key,"
                        "'{}'::jsonb,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "exception": row["id"],
                        "version": row["version"],
                        "key": uuid7(),
                        "now": now,
                    },
                )
            fetch_open_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT exception.id,exception.version,"
                            "CAST(exception.safe_metadata->>'technical_work_id' AS uuid) work_id "
                            "FROM owner_exception_v2 exception WHERE exception.kind='TECHNICAL' "
                            "AND exception.status='OPEN' AND "
                            "exception.safe_metadata->>'technical_work_kind'='SOURCE_FETCH' "
                            "FOR UPDATE OF exception"
                        )
                    )
                ).mappings()
            )
            for row in fetch_open_rows:
                recovered = await connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM fetch_run recovery WHERE "
                        "(recovery.id=:work_id OR recovery.replayed_from_run_id=:work_id) "
                        "AND recovery.status IN ('SUCCEEDED','NOT_MODIFIED'))"
                    ),
                    {"work_id": row["work_id"]},
                )
                if recovered:
                    await self._resolve_exception(
                        connection,
                        exception_id=row["id"],
                        version=row["version"],
                        now=now,
                    )
                await connection.execute(
                    text(
                        "SELECT append_audit_event(:audit_id,'TECHNICAL_EXCEPTION_AUTO_RESOLVED',"
                        ":actor,'OWNER_EXCEPTION',:target,"
                        "jsonb_build_object('status','OPEN'),"
                        "jsonb_build_object('status','RESOLVED'),"
                        "'TECHNICAL_RETRY_RECOVERED',:request_id,:now)"
                    ),
                    {
                        "audit_id": uuid7(),
                        "actor": _SYSTEM_ACTOR,
                        "target": row["id"],
                        "request_id": str(row["id"]),
                        "now": now,
                    },
                )
            open_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM owner_exception_v2 "
                    "WHERE kind='TECHNICAL' AND status='OPEN'"
                )
            )
        OWNER_TECHNICAL_EXCEPTION_BACKLOG.set(int(open_count or 0))
        await self._publish_open_retry_requests()

    async def _resolve_exception(
        self,
        connection: Any,
        *,
        exception_id: UUID,
        version: int,
        now: datetime,
    ) -> None:
        updated = await connection.execute(
            text(
                "UPDATE owner_exception_v2 SET status='RESOLVED',version=version+1,"
                "updated_at=:now,resolved_at=:now WHERE id=:id AND status='OPEN'"
            ),
            {"id": exception_id, "now": now},
        )
        if updated.rowcount != 1:
            return
        await connection.execute(
            text(
                "INSERT INTO owner_exception_event_v2("
                "id,exception_id,event_type,expected_version,idempotency_key,safe_metadata,"
                "created_at) VALUES(:id,:exception,'AUTO_RESOLVED',:version,:key,"
                "'{}'::jsonb,:now)"
            ),
            {
                "id": uuid7(),
                "exception": exception_id,
                "version": version,
                "key": uuid7(),
                "now": now,
            },
        )
        await connection.execute(
            text(
                "SELECT append_audit_event(:audit_id,'TECHNICAL_EXCEPTION_AUTO_RESOLVED',"
                ":actor,'OWNER_EXCEPTION',:target,jsonb_build_object('status','OPEN'),"
                "jsonb_build_object('status','RESOLVED'),'TECHNICAL_RETRY_RECOVERED',"
                ":request_id,:now)"
            ),
            {
                "audit_id": uuid7(),
                "actor": _SYSTEM_ACTOR,
                "target": exception_id,
                "request_id": str(exception_id),
                "now": now,
            },
        )

    async def _publish_open_retry_requests(self) -> None:
        if self._retry_queue is None:
            return
        async with self._engine.connect() as connection:
            events = list(
                (
                    await connection.execute(
                        text(
                            "SELECT event.id,event.created_at,"
                            "COALESCE(exception.safe_metadata->>'technical_work_kind',"
                            "'AI_PIPELINE') AS work_kind,COALESCE("
                            "exception.safe_metadata->>'technical_work_id',"
                            "exception.safe_metadata->>'pipeline_run_id') AS work_id "
                            "FROM owner_exception_event_v2 event JOIN owner_exception_v2 exception "
                            "ON exception.id=event.exception_id WHERE event.event_type="
                            "'RETRY_REQUESTED' AND exception.kind='TECHNICAL' "
                            "AND exception.status='OPEN' AND (("
                            "exception.safe_metadata->>'technical_work_kind' IS NULL AND "
                            "EXISTS(SELECT 1 FROM ai_compensation_run_v2 compensation WHERE "
                            "compensation.original_pipeline_run_id=CAST("
                            "exception.safe_metadata->>'pipeline_run_id' AS uuid) AND "
                            "compensation.status='DEAD_LETTER' AND "
                            "event.created_at>compensation.completed_at)) OR ("
                            "exception.safe_metadata->>'technical_work_kind'='SOURCE_FETCH' AND "
                            "EXISTS(SELECT 1 FROM fetch_run failed WHERE failed.id=CAST("
                            "exception.safe_metadata->>'technical_work_id' AS uuid) AND "
                            "failed.status='FAILED' AND event.created_at>failed.completed_at)))"
                        )
                    )
                ).mappings()
            )
        for event in events:
            work_id = event["work_id"]
            if work_id:
                await self._enqueue_retry(
                    event_id=event["id"],
                    work_kind=str(event["work_kind"]),
                    work_id=work_id,
                    requested_at=event["created_at"],
                )

    async def _enqueue_retry(
        self,
        *,
        event_id: UUID,
        work_kind: str,
        work_id: str,
        requested_at: datetime,
    ) -> None:
        if self._retry_queue is None:
            return
        await self._retry_queue.eval(
            "if redis.call('SADD',KEYS[2],ARGV[1]) == 1 then "
            "redis.call('RPUSH',KEYS[1],ARGV[2]); return 1 else return 0 end",
            2,
            TECHNICAL_RETRY_QUEUE_KEY,
            TECHNICAL_RETRY_DEDUPE_KEY,
            str(event_id),
            json.dumps(
                {
                    "event_id": str(event_id),
                    "work_kind": work_kind,
                    "work_id": work_id,
                    "requested_at": requested_at.isoformat(),
                },
                sort_keys=True,
            ),
        )

    async def list_exceptions(
        self,
        *,
        kind: str | None,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> list[OwnerExceptionView]:
        if kind not in {None, "TECHNICAL"}:
            return []
        if status not in {None, "OPEN", "RESOLVED"}:
            raise ValueError("owner exception status is invalid")
        if not 1 <= limit <= 100:
            raise ValueError("owner exception limit must be between 1 and 100")
        try:
            cursor_id = None if cursor is None else UUID(cursor)
        except ValueError as exc:
            raise ValueError("owner exception cursor must be an exception UUID") from exc
        await self.reconcile()
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT id,kind,status,overrideability,source_id,source_stream_id,"
                            "document_version_id,decision_id,reason_codes,"
                            "safe_metadata->>'technical_reason_code' AS technical_reason_code,"
                            "attempt_count,version,"
                            "opened_at,updated_at,resolved_at FROM owner_exception_v2 "
                            "WHERE kind='TECHNICAL' AND (CAST(:status AS text) IS NULL "
                            "OR status=:status) AND (CAST(:cursor_id AS uuid) IS NULL OR "
                            "(updated_at,id)<(SELECT updated_at,id FROM owner_exception_v2 "
                            "WHERE id=CAST(:cursor_id AS uuid))) "
                            "ORDER BY updated_at DESC,id DESC LIMIT :limit"
                        ),
                        {"status": status, "cursor_id": cursor_id, "limit": limit},
                    )
                ).mappings()
            )
        return [_view(row) for row in rows]

    async def get_exception(self, exception_id: UUID) -> OwnerExceptionView:
        await self.reconcile()
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,kind,status,overrideability,source_id,source_stream_id,"
                            "document_version_id,decision_id,reason_codes,"
                            "safe_metadata->>'technical_reason_code' AS technical_reason_code,"
                            "attempt_count,version,"
                            "opened_at,updated_at,resolved_at FROM owner_exception_v2 "
                            "WHERE id=:id AND kind='TECHNICAL'"
                        ),
                        {"id": exception_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise TechnicalExceptionNotFound(str(exception_id))
        return _view(row)

    async def command(
        self,
        *,
        exception_id: UUID,
        command: OwnerExceptionCommand | dict[str, Any],
        owner_id: UUID,
        idempotency_key: UUID,
    ) -> OwnerExceptionEventView:
        payload = OwnerExceptionCommand.model_validate(command)
        if payload.exception_id != exception_id:
            raise ValueError("owner exception command target does not match path")
        if payload.event_type is not OwnerExceptionEventType.RETRY_REQUESTED:
            raise ValueError("technical exception only supports retry requested")
        now = self._clock()
        pipeline_run_id: str | None = None
        technical_work_kind = "AI_PIPELINE"
        retry_event_id: UUID | None = None
        retry_requested_at: datetime | None = None
        row: Any
        async with self._engine.begin() as connection:
            duplicate = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,exception_id,event_type,expected_version,idempotency_key,"
                            "created_at FROM owner_exception_event_v2 WHERE idempotency_key=:key"
                        ),
                        {"key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if duplicate is not None:
                if (
                    duplicate["exception_id"] != exception_id
                    or duplicate["event_type"] != payload.event_type.value
                    or duplicate["expected_version"] != payload.expected_version
                ):
                    raise TechnicalExceptionConflict("idempotency key belongs to another command")
                exception_metadata = await connection.scalar(
                    text("SELECT safe_metadata FROM owner_exception_v2 WHERE id=:id"),
                    {"id": exception_id},
                )
                if isinstance(exception_metadata, dict):
                    technical_work_kind = str(
                        exception_metadata.get("technical_work_kind") or "AI_PIPELINE"
                    )
                    value = exception_metadata.get("technical_work_id") or exception_metadata.get(
                        "pipeline_run_id"
                    )
                    pipeline_run_id = value if isinstance(value, str) else None
                row = duplicate
                retry_event_id = duplicate["id"]
                retry_requested_at = duplicate["created_at"]
            else:
                exception = (
                    (
                        await connection.execute(
                            text(
                                "SELECT id,status,version,safe_metadata FROM owner_exception_v2 "
                                "WHERE id=:id AND kind='TECHNICAL' FOR UPDATE"
                            ),
                            {"id": exception_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if exception is None:
                    raise TechnicalExceptionNotFound(str(exception_id))
                if (
                    exception["status"] != "OPEN"
                    or exception["version"] != payload.expected_version
                ):
                    raise TechnicalExceptionConflict(str(exception_id))
                event_id = uuid7()
                await connection.execute(
                    text(
                        "INSERT INTO owner_exception_event_v2("
                        "id,exception_id,event_type,expected_version,idempotency_key,safe_metadata,"
                        "created_at) VALUES(:id,:exception,'RETRY_REQUESTED',:version,:key,"
                        "'{}'::jsonb,:now)"
                    ),
                    {
                        "id": event_id,
                        "exception": exception_id,
                        "version": payload.expected_version,
                        "key": idempotency_key,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "SELECT append_audit_event(:audit_id,"
                        "'OWNER_TECHNICAL_RETRY_REQUESTED',:actor,'OWNER_EXCEPTION',:target,NULL,"
                        "jsonb_build_object('event_type','RETRY_REQUESTED','expected_version',"
                        "CAST(:version AS integer)),"
                        "'OWNER_REQUESTED_TECHNICAL_RETRY',:request_id,:now)"
                    ),
                    {
                        "audit_id": uuid7(),
                        "actor": owner_id,
                        "target": exception_id,
                        "version": payload.expected_version,
                        "request_id": str(idempotency_key),
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "UPDATE owner_exception_v2 SET version=version+1,updated_at=:now "
                        "WHERE id=:id"
                    ),
                    {"id": exception_id, "now": now},
                )
                technical_work_kind = str(
                    exception["safe_metadata"].get("technical_work_kind") or "AI_PIPELINE"
                )
                value = exception["safe_metadata"].get("technical_work_id") or exception[
                    "safe_metadata"
                ].get("pipeline_run_id")
                if not isinstance(value, str):
                    raise RuntimeError("technical exception has no retryable pipeline run")
                pipeline_run_id = value
                retry_event_id = event_id
                retry_requested_at = now
                row = {
                    "id": event_id,
                    "exception_id": exception_id,
                    "event_type": "RETRY_REQUESTED",
                    "expected_version": payload.expected_version,
                    "idempotency_key": idempotency_key,
                    "created_at": now,
                }
        if (
            self._retry_queue is not None
            and pipeline_run_id is not None
            and retry_event_id is not None
            and retry_requested_at is not None
        ):
            await self._enqueue_retry(
                event_id=retry_event_id,
                work_kind=technical_work_kind,
                work_id=pipeline_run_id,
                requested_at=retry_requested_at,
            )
        OWNER_TECHNICAL_EXCEPTION_COMMANDS.labels(outcome="RETRY_REQUESTED").inc()
        return _event_view(row)


def _view(row: Any) -> OwnerExceptionView:
    return OwnerExceptionView.model_validate(dict(row))


def _event_view(row: Any) -> OwnerExceptionEventView:
    return OwnerExceptionEventView.model_validate(dict(row))
