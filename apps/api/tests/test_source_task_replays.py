from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.operations.failures import failure_record
from srbg_api.operations.replays import (
    ClaimedReplay,
    ReplayTaskRedelivery,
    claim_replay,
    prepare_task_redelivery,
)

QUALIFICATION_RUN_ID = UUID("019d1800-0000-7000-8000-000000000001")
OUTBOX_ID = UUID("019d1800-0000-7000-8000-000000000002")
FAILED_TASK_ID = UUID("019d1800-0000-7000-8000-000000000003")
REPLAY_ID = UUID("019d1800-0000-7000-8000-000000000004")
LEASE_TOKEN = UUID("019d1800-0000-7000-8000-000000000005")
NOW = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("task_name", "argument_name", "authoritative_id", "task_kind"),
    [
        (
            "srbg.sources.qualify",
            "qualification_run_id",
            QUALIFICATION_RUN_ID,
            "SOURCE_QUALIFICATION",
        ),
        (
            "srbg.sources.activation_outbox",
            "outbox_id",
            OUTBOX_ID,
            "SOURCE_ACTIVATION_OUTBOX",
        ),
        (
            "srbg.source_content.outbox",
            "outbox_id",
            OUTBOX_ID,
            "SOURCE_CONTENT_OUTBOX",
        ),
    ],
)
def test_source_task_failure_preserves_only_its_authoritative_identifier(
    task_name: str,
    argument_name: str,
    authoritative_id: UUID,
    task_kind: str,
) -> None:
    record = failure_record(
        task_name=task_name,
        task_id="019d1800-0000-7000-8000-000000000099",
        args=({"body": "must-not-survive"},),
        kwargs={
            argument_name: str(authoritative_id),
            "source_id": "019d1800-0000-7000-8000-000000000011",
            "run_id": "019d1800-0000-7000-8000-000000000012",
            "document_version_id": "019d1800-0000-7000-8000-000000000013",
            "event_id": "019d1800-0000-7000-8000-000000000014",
            "processing_version": "secret-version",
            "query": "secret-query",
            "url": "https://example.invalid/?token=secret",
            "body": "secret-body",
            "api_key": "secret-key",
        },
        exception=RuntimeError("secret-exception"),
    )

    assert record.task_kind == task_kind
    assert record.execution_id == authoritative_id
    assert record.replayable is True
    assert record.reconstruction_status == "REPLAYABLE"
    assert (
        record.source_id,
        record.run_id,
        record.document_version_id,
        record.event_id,
        record.processing_version,
    ) == (None, None, None, None, None)
    rendered = repr(record)
    for forbidden in (
        "secret-query",
        "example.invalid",
        "secret-body",
        "secret-key",
        "secret-exception",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    "task_name",
    [
        "srbg.sources.qualify",
        "srbg.sources.activation_outbox",
        "srbg.source_content.outbox",
    ],
)
def test_source_task_failure_without_authoritative_identifier_is_not_replayable(
    task_name: str,
) -> None:
    record = failure_record(
        task_name=task_name,
        task_id="019d1800-0000-7000-8000-000000000099",
        args=(),
        kwargs={"query": "must-not-survive"},
        exception=RuntimeError("bounded"),
    )

    assert record.replayable is False
    assert record.reconstruction_status == "NON_REPLAYABLE"
    assert record.blocked_reason == "AUTHORITATIVE_REFERENCE_MISSING"
    assert "must-not-survive" not in repr(record)


def _replay(task_kind: str, execution_id: UUID) -> ClaimedReplay:
    return ClaimedReplay(
        id=REPLAY_ID,
        failed_task_id=FAILED_TASK_ID,
        task_kind=task_kind,
        priority=9,
        source_id=None,
        run_id=None,
        document_version_id=None,
        event_id=None,
        processing_version=None,
        lease_token=LEASE_TOKEN,
        execution_id=execution_id,
    )


class _StatusConnection:
    def __init__(self, status: str | None) -> None:
        self.status = status
        self.sql = ""
        self.params: dict[str, object] = {}

    async def scalar(self, statement: object, params: dict[str, object]) -> str | None:
        self.sql = str(statement)
        self.params = params
        return self.status


class _StatusEngine:
    def __init__(self, status: str | None) -> None:
        self.connection = _StatusConnection(status)

    @asynccontextmanager
    async def connect(self):  # type: ignore[no-untyped-def]
        yield self.connection


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_kind", "execution_id", "status", "task_name", "argument_name"),
    [
        (
            "SOURCE_QUALIFICATION",
            QUALIFICATION_RUN_ID,
            "PENDING",
            "srbg.sources.qualify",
            "qualification_run_id",
        ),
        (
            "SOURCE_ACTIVATION_OUTBOX",
            OUTBOX_ID,
            "FAILED",
            "srbg.sources.activation_outbox",
            "outbox_id",
        ),
        (
            "SOURCE_CONTENT_OUTBOX",
            OUTBOX_ID,
            "FAILED",
            "srbg.source_content.outbox",
            "outbox_id",
        ),
    ],
)
async def test_replay_execution_revalidates_object_and_reconstructs_id_only_task(
    task_kind: str,
    execution_id: UUID,
    status: str,
    task_name: str,
    argument_name: str,
) -> None:
    engine = _StatusEngine(status)

    redelivery = await prepare_task_redelivery(  # type: ignore[arg-type]
        engine,
        _replay(task_kind, execution_id),
    )

    assert redelivery == ReplayTaskRedelivery(
        task_name=task_name,
        argument_name=argument_name,
        argument_id=execution_id,
    )
    assert redelivery.task_kwargs() == {argument_name: str(execution_id)}
    assert engine.connection.params == {"execution_id": execution_id}
    assert "query" not in engine.connection.sql.casefold()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_kind", "execution_id", "terminal_status"),
    [
        ("SOURCE_QUALIFICATION", QUALIFICATION_RUN_ID, "SUCCEEDED"),
        ("SOURCE_ACTIVATION_OUTBOX", OUTBOX_ID, "SUCCEEDED"),
        ("SOURCE_CONTENT_OUTBOX", OUTBOX_ID, "WAITING_AI"),
    ],
)
async def test_replay_execution_turns_terminal_object_into_safe_noop(
    task_kind: str,
    execution_id: UUID,
    terminal_status: str,
) -> None:
    engine = _StatusEngine(terminal_status)

    redelivery = await prepare_task_redelivery(  # type: ignore[arg-type]
        engine,
        _replay(task_kind, execution_id),
    )

    assert redelivery is None


class _ClaimResult:
    rowcount = 1

    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row

    def mappings(self) -> _ClaimResult:
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self.row


class _ClaimConnection:
    def __init__(self, status: str) -> None:
        self.status = status
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []
        self.candidate = {
            "id": REPLAY_ID,
            "failed_task_id": FAILED_TASK_ID,
            "priority": 9,
            "task_kind": "SOURCE_QUALIFICATION",
            "execution_id": QUALIFICATION_RUN_ID,
            "source_id": None,
            "run_id": None,
            "document_version_id": None,
            "event_id": None,
            "processing_version": None,
            "reconstruction_status": "REPLAYABLE",
        }

    async def execute(
        self,
        statement: object,
        params: dict[str, object],
    ) -> _ClaimResult:
        sql = str(statement)
        self.statements.append(sql)
        self.parameters.append(params)
        return _ClaimResult(self.candidate if sql.lstrip().startswith("SELECT r.id") else None)

    async def scalar(self, statement: object, params: dict[str, object]) -> str:
        self.statements.append(str(statement))
        self.parameters.append(params)
        return self.status


class _ClaimEngine:
    def __init__(self, status: str) -> None:
        self.connection = _ClaimConnection(status)

    @asynccontextmanager
    async def begin(self):  # type: ignore[no-untyped-def]
        yield self.connection


@pytest.mark.asyncio
async def test_claim_marks_terminal_source_task_for_noop_without_revoking_replayability() -> None:
    engine = _ClaimEngine("SUCCEEDED")

    replay = await claim_replay(engine, now=NOW)  # type: ignore[arg-type]

    assert replay is not None
    assert replay.execution_id == QUALIFICATION_RUN_ID
    assert replay.noop_reason == "QUALIFICATION_TERMINAL_NOOP"
    sql = "\n".join(engine.connection.statements)
    assert "SET status='RUNNING'" in sql
    assert "SET replayable=false" not in sql
