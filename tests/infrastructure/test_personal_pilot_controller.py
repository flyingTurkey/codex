import inspect
from pathlib import Path
from runpy import run_path

SCRIPT = Path("scripts/run_personal_pilot.ps1")
CONTROLLER = Path("scripts/run_controlled_personal_pilot.py")
MAKEFILE = Path("Makefile")
_CONTROLLER_GLOBALS = run_path(str(CONTROLLER))
POST_STOP_OBSERVATION_SECONDS = _CONTROLLER_GLOBALS["POST_STOP_OBSERVATION_SECONDS"]
classify_pilot_verdict = _CONTROLLER_GLOBALS["classify_pilot_verdict"]
source_outcomes = _CONTROLLER_GLOBALS["_source_outcomes"]
FIXED_FIVE_POLICY_VERSION = _CONTROLLER_GLOBALS["FIXED_FIVE_POLICY_VERSION"]


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
        "PILOT_PREFLIGHT_WORKER_RUN_PRIVILEGE",
        "has_table_privilege('srbg_worker_role','personal_controlled_run','SELECT')",
        "NOT has_table_privilege('srbg_worker_role','personal_controlled_run','UPDATE')",
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
        "DATA_INTEGRITY_GATE",
        "RAW_OBJECT_HASH_MISMATCH",
        "controlled pilot stopped fail-closed",
    ):
        assert marker in source


def test_verdict_allows_three_source_pass_only_for_the_versioned_fixed_five_policy() -> None:
    assert classify_pilot_verdict(4, content_chain_ok=True, invariants_ok=True) == "PASS"
    assert (
        classify_pilot_verdict(3, content_chain_ok=True, invariants_ok=True)
        == "LIMITED_PASS"
    )
    assert (
        classify_pilot_verdict(
            3,
            content_chain_ok=True,
            invariants_ok=True,
            policy_version=FIXED_FIVE_POLICY_VERSION,
            exact_fixed_source_set=True,
        )
        == "PASS"
    )
    assert (
        classify_pilot_verdict(
            3,
            content_chain_ok=True,
            invariants_ok=True,
            policy_version=FIXED_FIVE_POLICY_VERSION,
            exact_fixed_source_set=False,
        )
        == "LIMITED_PASS"
    )
    assert classify_pilot_verdict(2, content_chain_ok=True, invariants_ok=True) == "FAIL"
    assert classify_pilot_verdict(5, content_chain_ok=False, invariants_ok=True) == "FAIL"
    assert classify_pilot_verdict(5, content_chain_ok=True, invariants_ok=False) == "FAIL"


def test_stop_observation_exceeds_one_complete_domain_rate_limit_slot() -> None:
    assert POST_STOP_OBSERVATION_SECONDS >= 90


def test_source_success_uses_a_persisted_profile_snapshot_and_executed_schedule() -> None:
    source = inspect.getsource(source_outcomes)

    assert "FROM source_profile_snapshot" in source
    assert "generated_at>=run.wall_started_at" in source
    assert "controlled_schedules" in source
    assert "active_schedules>0 OR controlled_schedules>0" in source


def test_completed_run_can_be_reassessed_without_starting_network_work() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")

    assert 'parser.add_argument("--reassess-run")' in source
    assert '"report_kind": "POST_RUN_REASSESSMENT"' in source
    assert "PILOT_REASSESS_REQUIRES_COMPLETED_RUN" in source
    assert "started_at>=(SELECT min(source.manual_disabled_at)" in source
    assert '"reassessment_network_io_performed": False' in source
    assert '"pilot_policy_version": FIXED_FIVE_POLICY_VERSION' in source
    assert '"source_failure_diagnosis"' in source
