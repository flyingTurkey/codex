from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.source_registry.controlled_stream import (
    AdmissionGates,
    PostgresControlledStreamRepository,
    SourceResearchDisposition,
)

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
SOURCE_ID = UUID("019f8500-0000-7000-8000-000000000001")
STREAM_ID = UUID("019f8500-0000-7000-8000-000000000002")
OWNER_ID = UUID("019f8500-0000-7000-8000-000000000003")


class _Result:
    def __init__(self, scalar: object = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> object:
        return self._scalar


class _Connection:
    def __init__(self, scalars: list[object]) -> None:
        self.scalars = scalars
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []

    async def execute(self, statement: object, parameters: dict[str, object]) -> _Result:
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return _Result(self.scalars.pop(0) if self.scalars else None)

    async def scalar(self, statement: object, parameters: dict[str, object]) -> object:
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return self.scalars.pop(0) if self.scalars else None


class _Context(AbstractAsyncContextManager[_Connection]):
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.disposed = False

    def begin(self) -> _Context:
        return _Context(self.connection)

    async def dispose(self) -> None:
        self.disposed = True


def _gates(**changes: bool | None) -> AdmissionGates:
    values = {name: True for name in AdmissionGates.__dataclass_fields__}
    values.update(changes)
    return AdmissionGates(**values)


@pytest.mark.asyncio
async def test_repository_records_research_intent_and_server_derived_admission_separately() -> None:
    connection = _Connection([])
    repository = PostgresControlledStreamRepository(
        cast(AsyncEngine, _Engine(connection)), now=lambda: NOW
    )

    await repository.record_research_disposition(
        source_id=SOURCE_ID,
        source_stream_id=STREAM_ID,
        disposition=SourceResearchDisposition.ADMISSION_READY,
        research_sha256="a" * 64,
        actor_id=OWNER_ID,
    )
    await repository.record_owner_intent(
        source_id=SOURCE_ID,
        source_stream_id=STREAM_ID,
        desired_enabled=True,
        actor_id=OWNER_ID,
        request_id="t07-owner-intent-1",
    )
    verdict = await repository.record_admission_decision(
        source_id=SOURCE_ID,
        source_stream_id=STREAM_ID,
        gates=_gates(),
        evidence_sha256="b" * 64,
        actor_id=OWNER_ID,
        valid_for=timedelta(hours=1),
    )

    assert verdict == "ADMIT"
    assert "source_research_disposition_v2" in connection.statements[0]
    assert "source_owner_intent_v2" in connection.statements[1]
    assert "UPDATE source SET desired_enabled" in connection.statements[1]
    assert "source_stream_admission_decision_v2" in connection.statements[2]
    assert connection.parameters[2]["verdict"] == "ADMIT"


@pytest.mark.asyncio
async def test_repository_never_records_admit_when_any_gate_is_unknown_or_failed() -> None:
    connection = _Connection([])
    repository = PostgresControlledStreamRepository(
        cast(AsyncEngine, _Engine(connection)), now=lambda: NOW
    )

    verdict = await repository.record_admission_decision(
        source_id=SOURCE_ID,
        source_stream_id=STREAM_ID,
        gates=_gates(robots_allowed=None),
        evidence_sha256="b" * 64,
        actor_id=OWNER_ID,
        valid_for=timedelta(hours=1),
    )

    assert verdict == "PAUSE"
    assert connection.parameters[0]["verdict"] == "PAUSE"
    assert connection.parameters[0]["reason_codes"] == ["ROBOTS_ALLOWED_UNKNOWN"]


@pytest.mark.asyncio
async def test_authorize_and_start_use_only_security_definer_commands() -> None:
    authorization_id = UUID("019f8500-0000-7000-8000-000000000004")
    running_id = UUID("019f8500-0000-7000-8000-000000000005")
    run_id = UUID("019f8500-0000-7000-8000-000000000006")
    connection = _Connection([authorization_id, running_id])
    engine = _Engine(connection)
    repository = PostgresControlledStreamRepository(
        cast(AsyncEngine, engine), now=lambda: NOW
    )

    authorized = await repository.authorize_shadow(
        source_id=SOURCE_ID, source_stream_id=STREAM_ID
    )
    started = await repository.start_shadow(
        authorization_event_id=authorization_id, run_id=run_id
    )
    await repository.close()

    assert authorized == authorization_id
    assert started == running_id
    assert "authorize_source_stream_shadow_v2" in connection.statements[0]
    assert "start_source_stream_shadow_v2" in connection.statements[1]
    assert all(
        "INSERT INTO source_stream_runtime_event_v2" not in value
        for value in connection.statements
    )
    assert engine.disposed is True
