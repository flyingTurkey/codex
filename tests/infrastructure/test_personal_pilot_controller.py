from pathlib import Path

SCRIPT = Path("scripts/run_personal_pilot.ps1")
CONTROLLER = Path("scripts/run_controlled_personal_pilot.py")
MAKEFILE = Path("Makefile")


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
    ):
        assert marker in source
