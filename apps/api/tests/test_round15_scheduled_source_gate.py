import logging

import pytest
from srbg_api.safety_regulations.runner import _enabled_mem_connectors


class _Engine:
    def __init__(self) -> None:
        self.connect_called = False

    def connect(self) -> None:
        self.connect_called = True
        raise AssertionError("Round 15 must not query a legacy production target")


async def test_round15_never_schedules_unbound_legacy_production_executor(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine = _Engine()

    with caplog.at_level(logging.INFO, logger="srbg.worker.safety_regulations"):
        assert await _enabled_mem_connectors(engine) == []  # type: ignore[arg-type]

    assert engine.connect_called is False
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "source_production_scheduling_blocked"
    )
    assert record.event_name == "source_production_scheduling_blocked"  # type: ignore[attr-defined]
    assert record.action == "SCHEDULE_SOURCE"  # type: ignore[attr-defined]
    assert record.outcome == "BLOCKED"  # type: ignore[attr-defined]
    assert record.reason_code == "EXECUTOR_BINDING_UNAVAILABLE"  # type: ignore[attr-defined]
