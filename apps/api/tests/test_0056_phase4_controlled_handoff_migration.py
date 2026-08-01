from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0056_phase4_controlled_handoff.py")
LIVE_ACCEPTANCE = Path("tests/live/test_phase4_real_event_acceptance.py")
VERIFIER = Path("scripts/verify_phase4_controlled_handoff_migration.py")


def test_phase4_controlled_handoff_is_the_single_linear_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_heads() == ["0056_phase4_controlled_handoff"]
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0056_phase4_controlled_handoff"' in source
    assert 'down_revision = "0055_phase3_trustworthy_event"' in source


def test_source_handoff_propagates_the_authoritative_controlled_run() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "run.controlled_run_id" in source
    assert "v_controlled_run_id" in source
    assert 'controlled_run_column = ",controlled_run_id"' in source
    assert 'controlled_run_value = ",v_controlled_run_id"' in source
    assert "handoff_source_content_to_ai(uuid,uuid,uuid,timestamptz)" in source
    assert "TO srbg_worker_role" in source


def test_phase4_source_display_fails_closed_before_fetch_if_control_link_is_lost() -> None:
    source = LIVE_ACCEPTANCE.read_text(encoding="utf-8")

    assert 'report["fetch_controlled_run_id"]' in source
    assert "FETCH_CONTROLLED_RUN_MISMATCH" in source


def test_controlled_handoff_downgrade_restores_the_previous_function() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "def upgrade()" in source
    assert "_replace_handoff(propagate_controlled_run=True)" in source
    assert "def downgrade()" in source
    assert "_replace_handoff(propagate_controlled_run=False)" in source


def test_controlled_handoff_verifier_replays_only_the_new_linear_edge() -> None:
    source = VERIFIER.read_text(encoding="utf-8")

    assert '_HEAD = "0056_phase4_controlled_handoff"' in source
    assert '_PREVIOUS = "0055_phase3_trustworthy_event"' in source
    assert "run.controlled_run_id" in source
    assert "0055 -> 0056 -> 0055 -> 0056" in source
