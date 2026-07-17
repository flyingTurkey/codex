from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.operations.replays import (
    ClaimedReplay,
    _current_reference_error,
    _load_source_fetch_replay,
    prepare_source_fetch_replay,
)

SOURCE_ID = UUID("019b1700-0000-7000-8000-000000000201")
ORIGINAL_RUN_ID = UUID("019b1700-0000-7000-8000-000000000202")


class _Result:
    rowcount = 1


class _Connection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: dict[str, object] = {}

    async def execute(self, statement: object, params: dict[str, object]) -> _Result:
        self.sql = str(statement)
        self.params = params
        return _Result()


class _Engine:
    def __init__(self) -> None:
        self.connection = _Connection()

    @asynccontextmanager
    async def begin(self):  # type: ignore[no-untyped-def]
        yield self.connection


@pytest.mark.asyncio
async def test_source_fetch_replay_clones_provenance_and_never_reuses_original_run() -> None:
    engine = _Engine()
    replay = ClaimedReplay(
        id=UUID("019b1700-0000-7000-8000-000000000203"),
        failed_task_id=UUID("019b1700-0000-7000-8000-000000000204"),
        task_kind="SOURCE_FETCH",
        priority=9,
        source_id=SOURCE_ID,
        run_id=ORIGINAL_RUN_ID,
        document_version_id=None,
        event_id=None,
        processing_version=None,
        lease_token=UUID("019b1700-0000-7000-8000-000000000205"),
    )

    source_id, replay_run_id = await prepare_source_fetch_replay(  # type: ignore[arg-type]
        engine, replay
    )

    assert source_id == SOURCE_ID
    assert replay_run_id != ORIGINAL_RUN_ID
    assert "INSERT INTO fetch_run" in engine.connection.sql
    assert "run_origin" in engine.connection.sql
    assert "replayed_from_run_id" in engine.connection.sql
    assert "'REPLAY'" in engine.connection.sql
    assert "'FIXTURE'" in engine.connection.sql
    assert "'RUNNING'" in engine.connection.sql
    assert "'PENDING_DISPATCH'" not in engine.connection.sql
    assert engine.connection.params["original_run"] == ORIGINAL_RUN_ID
    assert engine.connection.params["replay_run"] == replay_run_id
    assert engine.connection.params["source"] == SOURCE_ID


def test_source_fetch_replay_is_network_free_and_cannot_be_scheduled_as_live_fetch() -> None:
    source = "\n".join(
        value for value in prepare_source_fetch_replay.__code__.co_consts if isinstance(value, str)
    )

    assert "PRODUCTION" in source
    assert "FIXTURE" in source
    assert "PENDING_DISPATCH" not in source


class _ScalarConnection:
    def __init__(self) -> None:
        self.sql = ""

    async def scalar(self, statement: object, params: dict[str, object]) -> int:
        del params
        self.sql = str(statement)
        return 1


@pytest.mark.asyncio
async def test_source_fetch_replay_rechecks_current_policy_and_production_approval() -> None:
    connection = _ScalarConnection()

    error = await _current_reference_error(  # type: ignore[arg-type]
        connection,
        {
            "task_kind": "SOURCE_FETCH",
            "run_id": ORIGINAL_RUN_ID,
            "source_id": SOURCE_ID,
        },
        datetime(2026, 7, 16, tzinfo=UTC),
    )

    assert error is None
    assert "source_private_evidence_capture_allowed(p.document)" in connection.sql
    assert "source_policy_compliance_current(s.id,p.id,:now)" in connection.sql
    assert "source_governance_decision" in connection.sql
    assert "decision_type='PRODUCTION_APPROVAL'" in connection.sql
    assert "decision.outcome='APPROVED'" in connection.sql
    assert "decision.trial_run_id=s.current_trial_run_id" in connection.sql
    assert "decision.valid_until" in connection.sql


class _Mappings:
    def __init__(self, value: object) -> None:
        self.value = value

    def mappings(self) -> _Mappings:
        return self

    def one_or_none(self) -> object:
        return self.value

    def all(self) -> list[object]:
        return self.value if isinstance(self.value, list) else []


class _ReplayLoadConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[dict[str, object]] = []

    async def execute(
        self, statement: object, params: dict[str, object]
    ) -> _Mappings:
        self.sql.append(str(statement))
        self.params.append(params)
        if len(self.sql) == 1:
            return _Mappings(
                {
                    "connector_type": "LIST_DETAIL",
                    "config_document": {},
                    "allowed_hosts": ["example.invalid"],
                }
            )
        return _Mappings([])


class _ReplayLoadEngine:
    def __init__(self) -> None:
        self.connection = _ReplayLoadConnection()

    @asynccontextmanager
    async def connect(self):  # type: ignore[no-untyped-def]
        yield self.connection


@pytest.mark.asyncio
async def test_source_fetch_replay_execution_closes_claim_to_use_policy_race() -> None:
    engine = _ReplayLoadEngine()
    observed_at = datetime(2026, 7, 16, tzinfo=UTC)
    replay = ClaimedReplay(
        id=UUID("019b1700-0000-7000-8000-000000000213"),
        failed_task_id=UUID("019b1700-0000-7000-8000-000000000214"),
        task_kind="SOURCE_FETCH",
        priority=9,
        source_id=SOURCE_ID,
        run_id=ORIGINAL_RUN_ID,
        document_version_id=None,
        event_id=None,
        processing_version=None,
        lease_token=UUID("019b1700-0000-7000-8000-000000000215"),
    )

    await _load_source_fetch_replay(  # type: ignore[arg-type]
        engine,
        replay=replay,
        replay_run_id=UUID("019b1700-0000-7000-8000-000000000216"),
        now=observed_at,
    )

    binding_sql = engine.connection.sql[0]
    assert "source_policy_version policy" in binding_sql
    assert "source_private_evidence_capture_allowed(policy.document)" in binding_sql
    assert "source_policy_compliance_current(" in binding_sql
    assert "source_governance_decision decision" in binding_sql
    assert "decision.decision_type='PRODUCTION_APPROVAL'" in binding_sql
    assert "decision.trial_run_id=source_row.current_trial_run_id" in binding_sql
    assert engine.connection.params[0]["now"] == observed_at
