from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0053_safety_exception_lifecycle.py")
VERIFIER = Path("scripts/verify_autonomous_policy_migration.py")


def test_safety_exception_lifecycle_is_the_single_linear_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_heads() == ["0060_phase5_extract_prompt_v3"]
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0053_safety_exception_lifecycle"' in source
    assert 'down_revision = "0052_feed_suppression_projection"' in source


def test_migration_reuses_owner_exception_and_suppression_ledgers() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE owner_exception_v2" not in source
    assert "CREATE TABLE feed_suppression_rule_v2" not in source
    assert "CREATE FUNCTION record_safety_exception_v2" in source
    assert "decision.disposition='SAFETY_HOLD'" in source
    assert "v_decision.model_candidate->'security_signals'" in source
    assert "v_decision.rule_signals" in source
    assert "SAFETY_SIGNAL:%" in source
    assert "p_overrideability" not in source.split("CREATE FUNCTION", 1)[1].split(
        "RETURNS uuid", 1
    )[0]
    assert "UNRECOGNIZED_SECURITY_SIGNAL" in source
    assert "GRANT EXECUTE ON FUNCTION record_safety_exception_v2" in source
    assert "TO srbg_worker_role" in source
    assert '"uq_owner_safety_exception_decision_v2"' in source
    assert "unique=True" in source
    assert "document_text_block evidence_block" in source
    assert "evidence_page.document_version_id=v_decision.document_version_id" in source


def test_open_safety_hold_is_filtered_before_every_reader_surface() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE VIEW visible_intelligence_projection_v2" in source
    assert "exception.kind='SAFETY'" in source
    assert "exception.status='OPEN'" in source
    assert "exception.document_version_id=projection.document_version_id" in source
    assert "feed_suppression_effective_v2" in source
    assert "SAFETY_EXCEPTION_DOWNGRADE_BLOCKED" in source


def test_autonomous_policy_replay_covers_safety_lifecycle_upgrade_and_rollback() -> None:
    source = VERIFIER.read_text(encoding="utf-8")

    assert '"0053_safety_exception_lifecycle"' in source
    assert "record_safety_exception_v2" in source
    assert "0052 -> 0053 -> 0052 -> 0053" in source
