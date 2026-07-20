from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from srbg_api.source_registry.controlled_stream import (
    AdmissionGates,
    SourceResearchDisposition,
    StreamControlFacts,
    StreamRuntimeState,
    decide_shadow_authorization,
)

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
SOURCE_ID = UUID("019f8500-0000-7000-8000-000000000001")
STREAM_ID = UUID("019f8500-0000-7000-8000-000000000002")


def _passing_gates(**changes: bool | None) -> AdmissionGates:
    values: dict[str, bool | None] = {
        "public_network_safe": True,
        "robots_allowed": True,
        "terms_allowed": True,
        "copyright_allowed": True,
        "access_boundary_allowed": True,
        "rate_limit_configured": True,
        "budget_available": True,
        "quality_passed": True,
        "circuit_closed": True,
        "runtime_gate_open": True,
    }
    values.update(changes)
    return AdmissionGates(**values)


def _facts(**changes: object) -> StreamControlFacts:
    values: dict[str, object] = {
        "source_id": SOURCE_ID,
        "source_stream_id": STREAM_ID,
        "disposition": SourceResearchDisposition.ADMISSION_READY,
        "desired_enabled": True,
        "admission_verdict": "ADMIT",
        "gates": _passing_gates(),
        "admission_decided_at": NOW,
        "admission_valid_until": NOW + timedelta(hours=1),
    }
    values.update(changes)
    return StreamControlFacts(**values)


@pytest.mark.parametrize(
    "disposition",
    list(SourceResearchDisposition),
)
def test_research_disposition_never_grants_runtime_by_itself(
    disposition: SourceResearchDisposition,
) -> None:
    decision = decide_shadow_authorization(
        _facts(
            disposition=disposition,
            desired_enabled=False,
            admission_verdict=None,
            gates=AdmissionGates.unknown(),
            admission_decided_at=None,
            admission_valid_until=None,
        ),
        now=NOW,
    )

    assert decision.state is StreamRuntimeState.PAUSED
    assert decision.actual_running is False
    assert "OWNER_INTENT_DISABLED" in decision.reason_codes
    assert "SOURCE_ADMISSION_MISSING" in decision.reason_codes


@pytest.mark.parametrize(
    "gate",
    [
        "public_network_safe",
        "robots_allowed",
        "terms_allowed",
        "copyright_allowed",
        "access_boundary_allowed",
        "rate_limit_configured",
        "budget_available",
        "quality_passed",
        "circuit_closed",
        "runtime_gate_open",
    ],
)
@pytest.mark.parametrize("value", [None, False])
def test_unknown_or_failed_gate_keeps_stream_paused(gate: str, value: bool | None) -> None:
    decision = decide_shadow_authorization(
        _facts(gates=_passing_gates(**{gate: value})),
        now=NOW,
    )

    assert decision.state is StreamRuntimeState.PAUSED
    assert decision.actual_running is False
    assert decision.reason_codes == (f"{gate.upper()}_{'UNKNOWN' if value is None else 'FAILED'}",)


def test_only_current_stream_level_admission_can_authorize_shadow_collection() -> None:
    decision = decide_shadow_authorization(_facts(), now=NOW)

    assert decision.state is StreamRuntimeState.SHADOW_AUTHORIZED
    assert decision.actual_running is False
    assert decision.reason_codes == ()


def test_expired_admission_and_naive_times_fail_closed() -> None:
    expired = decide_shadow_authorization(
        _facts(
            admission_decided_at=NOW - timedelta(hours=1),
            admission_valid_until=NOW,
        ),
        now=NOW + timedelta(microseconds=1),
    )
    assert expired.reason_codes == ("SOURCE_ADMISSION_EXPIRED",)

    with pytest.raises(ValueError, match="timezone"):
        decide_shadow_authorization(_facts(), now=datetime(2026, 7, 20, 8, 0))


def test_server_start_transition_is_separate_from_eligibility() -> None:
    authorized = decide_shadow_authorization(_facts(), now=NOW)
    running = authorized.start(run_id=UUID("019f8500-0000-7000-8000-000000000003"))

    assert authorized.actual_running is False
    assert running.state is StreamRuntimeState.SHADOW_RUNNING
    assert running.actual_running is True
    assert running.run_id is not None
