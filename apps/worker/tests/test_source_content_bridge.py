from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import pytest
import srbg_worker.app as worker
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_worker.source_content_bridge import (
    ContentPipelineHandoff,
    PostgresSourceContentGateway,
    SourceContentOutboxExecutor,
)

OUTBOX_ID = UUID("019d2000-0000-7000-8000-000000000001")
VERSION_ID = UUID("019d2000-0000-7000-8000-000000000002")
PIPELINE_ID = UUID("019d2000-0000-7000-8000-000000000003")


class _RecordingGateway:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self._failure = failure
        self._handoff: ContentPipelineHandoff | None = None
        self.failed: list[tuple[UUID, str]] = []
        self.pipeline_ids: list[UUID] = []

    async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]:
        assert limit == 50
        return (OUTBOX_ID,)

    async def handoff(
        self,
        outbox_id: UUID,
        *,
        pipeline_run_id: UUID,
    ) -> ContentPipelineHandoff | None:
        assert outbox_id == OUTBOX_ID
        self.pipeline_ids.append(pipeline_run_id)
        if self._failure is not None:
            raise self._failure
        if self._handoff is None:
            self._handoff = ContentPipelineHandoff(
                outbox_id=OUTBOX_ID,
                document_version_id=VERSION_ID,
                pipeline_run_id=pipeline_run_id,
                status="WAITING_AI",
                queued=True,
            )
            return self._handoff
        return ContentPipelineHandoff(
            outbox_id=self._handoff.outbox_id,
            document_version_id=self._handoff.document_version_id,
            pipeline_run_id=self._handoff.pipeline_run_id,
            status="WAITING_AI",
            queued=False,
        )

    async def mark_failed(self, outbox_id: UUID, *, reason_code: str) -> None:
        self.failed.append((outbox_id, reason_code))

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_ready_version_handoff_is_idempotent_and_stops_at_queued_ai() -> None:
    gateway = _RecordingGateway()
    executor = SourceContentOutboxExecutor(gateway=gateway)

    first = await executor.run(OUTBOX_ID)
    replay = await executor.run(OUTBOX_ID)

    assert first.status == "WAITING_AI"
    assert first.queued is True
    assert replay == ContentPipelineHandoff(
        outbox_id=OUTBOX_ID,
        document_version_id=VERSION_ID,
        pipeline_run_id=first.pipeline_run_id,
        status="WAITING_AI",
        queued=False,
    )
    assert gateway.failed == []


@pytest.mark.asyncio
async def test_handoff_failure_records_only_a_bounded_reason_code() -> None:
    gateway = _RecordingGateway(
        failure=RuntimeError("https://secret.invalid/path?token=must-not-persist")
    )
    executor = SourceContentOutboxExecutor(gateway=gateway)

    with pytest.raises(RuntimeError):
        await executor.run(OUTBOX_ID)

    assert gateway.failed == [(OUTBOX_ID, "RUNTIMEERROR")]


@dataclass
class _Result:
    rows: list[Mapping[str, object]]

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[Mapping[str, object]]:
        return self.rows

    def one_or_none(self) -> Mapping[str, object] | None:
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self, results: list[list[Mapping[str, object]]]) -> None:
        self._results = list(results)
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []

    async def execute(self, statement: object, parameters: dict[str, object]) -> _Result:
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return _Result(self._results.pop(0))


class _Context(AbstractAsyncContextManager[_Connection]):
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    async def __aenter__(self) -> _Connection:
        return self._connection


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        self.disposed = False

    def connect(self) -> _Context:
        return _Context(self._connection)

    def begin(self) -> _Context:
        return _Context(self._connection)

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_postgres_gateway_uses_only_security_definer_commands() -> None:
    connection = _Connection(
        [
            [{"id": OUTBOX_ID}],
            [
                {
                    "outbox_id": OUTBOX_ID,
                    "document_version_id": VERSION_ID,
                    "pipeline_run_id": PIPELINE_ID,
                    "status": "WAITING_AI",
                    "queued": True,
                }
            ],
            [],
        ]
    )
    engine = _Engine(connection)
    gateway = PostgresSourceContentGateway(engine=cast(AsyncEngine, engine))

    assert await gateway.pending_ids(limit=50) == (OUTBOX_ID,)
    handoff = await gateway.handoff(OUTBOX_ID, pipeline_run_id=PIPELINE_ID)
    await gateway.mark_failed(OUTBOX_ID, reason_code="DATABASEERROR")
    await gateway.close()

    assert handoff == ContentPipelineHandoff(
        outbox_id=OUTBOX_ID,
        document_version_id=VERSION_ID,
        pipeline_run_id=PIPELINE_ID,
        status="WAITING_AI",
        queued=True,
    )
    assert "list_pending_source_content_ids" in connection.statements[0]
    assert "handoff_source_content_to_ai" in connection.statements[1]
    assert "fail_source_content_handoff" in connection.statements[2]
    for statement in connection.statements:
        assert " FROM source_content_outbox" not in statement
        assert "INSERT INTO ai_pipeline_run" not in statement
        assert "UPDATE source_content_outbox" not in statement
    assert set(connection.parameters[1]) == {"outbox_id", "pipeline_run_id", "now"}
    assert connection.parameters[1]["outbox_id"] == OUTBOX_ID
    assert connection.parameters[1]["pipeline_run_id"] == PIPELINE_ID
    assert engine.disposed is True


def test_bridge_module_has_no_publication_or_claim_write_dependency() -> None:
    import inspect

    import srbg_worker.source_content_bridge as bridge

    source = inspect.getsource(bridge)
    assert "PublicationService" not in source
    assert "publication" not in source.casefold()
    assert "accepted_claim" not in source.casefold()
    assert "INSERT INTO claim" not in source


def test_celery_content_handoff_payload_is_outbox_id_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_drain(outbox_id: UUID | None) -> dict[str, object]:
        assert outbox_id == OUTBOX_ID
        return {
            "outbox_id": str(OUTBOX_ID),
            "document_version_id": str(VERSION_ID),
            "pipeline_run_id": str(PIPELINE_ID),
            "status": "WAITING_AI",
            "queued": True,
        }

    monkeypatch.setattr(worker, "_drain_source_content_outbox", fake_drain)
    task = worker.celery_app.tasks["srbg.source_content.outbox"]

    result = task.run(outbox_id=str(OUTBOX_ID))

    assert set(result) == {
        "outbox_id",
        "document_version_id",
        "pipeline_run_id",
        "status",
        "queued",
    }
    with pytest.raises(TypeError):
        task.run(
            outbox_id=str(OUTBOX_ID),
            document_version_id=str(VERSION_ID),
        )
    with pytest.raises(TypeError):
        task.run(outbox_id=str(OUTBOX_ID), content="must-not-enter-broker")


@pytest.mark.asyncio
async def test_content_dispatcher_sends_only_pending_outbox_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, dict[str, str]]] = []

    class PendingGateway:
        async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]:
            assert limit == 50
            return (OUTBOX_ID,)

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        worker,
        "PostgresSourceContentGateway",
        lambda *, engine: PendingGateway(),
    )
    monkeypatch.setattr(worker, "create_database_engine", lambda settings: object())
    monkeypatch.setattr(
        worker.celery_app,
        "send_task",
        lambda name, *, kwargs, **_options: sent.append((name, kwargs)),
    )

    result = await worker._drain_source_content_outbox(None)

    assert result == {"dispatched": 1}
    assert sent == [("srbg.source_content.outbox", {"outbox_id": str(OUTBOX_ID)})]
