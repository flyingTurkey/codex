from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.operations.service import PostgresOperationsService
from srbg_contracts import SourceLifecycleActionRequest

SOURCE_ID = UUID("019b1800-0000-7000-8000-00000000a001")
SCHEDULE_ID = UUID("019b1800-0000-7000-8000-00000000a002")
ACTOR_ID = UUID("019b1800-0000-7000-8000-00000000a003")
NOW = datetime(2026, 7, 17, tzinfo=UTC)


def _schedule_row(*, repaired: bool) -> dict[str, object]:
    return {
        "id": SCHEDULE_ID,
        "source_id": SOURCE_ID,
        "authority_level": "A1",
        "status": "ACTIVE",
        "interval_seconds": 3600,
        "next_run_at": NOW,
        "circuit_state": "CLOSED" if repaired else "OPEN",
        "circuit_open_until": None if repaired else NOW,
        "consecutive_failures": 0 if repaired else 5,
        "freshness_slo_seconds": 86400,
        "rate_limit_per_minute": 1,
        "daily_request_budget": 24,
        "daily_byte_budget": 10_000_000,
        "requests_used": 5,
        "bytes_used": 100,
        "version": 2 if repaired else 1,
        "last_idempotency_key": "previous-command",
        "updated_at": NOW,
    }


class _Result:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self._row

    def one(self) -> dict[str, object]:
        assert self._row is not None
        return self._row


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []

    async def execute(self, statement: object, parameters: dict[str, object]) -> _Result:
        sql = str(statement)
        self.statements.append(sql)
        self.parameters.append(parameters)
        if sql.lstrip().startswith("SELECT schedule.*"):
            return _Result(_schedule_row(repaired=False))
        if sql.lstrip().startswith("UPDATE fetch_schedule"):
            return _Result(_schedule_row(repaired=True))
        return _Result(None)


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def begin(self) -> Any:
        yield self.connection


@pytest.mark.asyncio
async def test_schedule_repair_revalidates_authority_resets_only_circuit_and_audits() -> None:
    connection = _Connection()
    service = PostgresOperationsService(
        cast(AsyncEngine, _Engine(connection)),
        now=lambda: NOW,
    )

    result = await service.repair_schedule(
        SOURCE_ID,
        SourceLifecycleActionRequest(
            reason="verified connector repair before resetting the source circuit"
        ),
        actor_id=ACTOR_ID,
        idempotency_key="round18-repair-command",
    )

    assert result.circuit_state.value == "CLOSED"
    assert result.consecutive_failures == 0
    assert "source_policy_compliance_current" in connection.statements[0]
    assert "candidate.status='ENABLED'" in connection.statements[0]
    assert "execution_lease_until>=:now" in connection.statements[0]
    assert "circuit_state='CLOSED'" in connection.statements[1]
    assert "consecutive_failures=0" in connection.statements[1]
    assert "FETCH_SCHEDULE_REPAIRED" in connection.statements[2]
    assert all("canonical_url" not in parameters for parameters in connection.parameters)
