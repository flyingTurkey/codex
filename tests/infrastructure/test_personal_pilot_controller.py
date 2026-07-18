from pathlib import Path
from runpy import run_path

SCRIPT = Path("scripts/run_personal_pilot.ps1")
CONTROLLER = Path("scripts/run_controlled_personal_pilot.py")
MAKEFILE = Path("Makefile")
_CONTROLLER_GLOBALS = run_path(str(CONTROLLER))
POST_STOP_OBSERVATION_SECONDS = _CONTROLLER_GLOBALS["POST_STOP_OBSERVATION_SECONDS"]
classify_pilot_verdict = _CONTROLLER_GLOBALS["classify_pilot_verdict"]


def test_controller_has_no_network_preflight_and_releases_sleep_state() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "PreflightOnly",
        "SetThreadExecutionState",
        "ES_CONTINUOUS",
        "finally",
        "SRBG_SOURCE_DISCOVERY_ENABLED=false",
        "D:\\SRBGData",
        "'reports'",
        "PILOT_PREFLIGHT_ACTIVE_RUN",
        "PILOT_PREFLIGHT_UNSETTLED_ATTEMPTS",
        "PILOT_PREFLIGHT_SOURCE_NOT_STOPPED",
        "pers10-d-drive-migration-20260718.md",
    ):
        assert marker in source


def test_make_exposes_controlled_pilot_gate() -> None:
    assert "personal-pilot-control-test:" in MAKEFILE.read_text(encoding="utf-8")


def test_controller_drains_reservations_and_never_enables_ai_without_ledger() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")
    for marker in (
        "RESERVED",
        "CONTROLLED_RUN_DRAIN_TIMEOUT",
        '"ai_state": "DEGRADED_DISABLED"',
        "wall_deadline",
        "active_seconds",
        "CONTROLLER_FAILURE",
        "fail_closed_cleanup",
        "source_outcomes",
        "content_evidence",
        "publication_invariant",
        "post_stop_network_attempts",
        "source_change_observation",
        "baseline_exceptions",
    ):
        assert marker in source


def test_verdict_keeps_four_source_final_gate_and_three_source_limited_gate() -> None:
    assert classify_pilot_verdict(4, content_chain_ok=True, invariants_ok=True) == "PASS"
    assert (
        classify_pilot_verdict(3, content_chain_ok=True, invariants_ok=True)
        == "LIMITED_PASS"
    )
    assert classify_pilot_verdict(2, content_chain_ok=True, invariants_ok=True) == "FAIL"
    assert classify_pilot_verdict(5, content_chain_ok=False, invariants_ok=True) == "FAIL"
    assert classify_pilot_verdict(5, content_chain_ok=True, invariants_ok=False) == "FAIL"


def test_stop_observation_exceeds_one_complete_domain_rate_limit_slot() -> None:
    assert POST_STOP_OBSERVATION_SECONDS >= 90
