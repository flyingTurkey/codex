from __future__ import annotations

from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0051_technical_exception_recovery.py")


def test_migration_adds_one_narrow_owner_retry_command() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0051_technical_exception_recovery"' in source
    assert 'down_revision = "0050_autonomous_handoff_state_order"' in source
    assert "reopen_source_content_ai_run" in source
    assert "SECURITY DEFINER" in source
    assert "SET search_path=pg_catalog,public" in source
    assert "owner_exception_event_v2" in source
    assert "event.event_type='RETRY_REQUESTED'" in source
    assert "compensation.status='DEAD_LETTER'" in source
    assert "pipeline.status='FAILED'" in source
    assert "content.status='DEAD_LETTER'" in source
    assert "GRANT EXECUTE ON FUNCTION" in source
    assert "TO srbg_worker_role" in source
    assert "reopen_failed_source_fetch" in source
    assert "'SOURCE_FETCH'" in source
    assert "replayed_from_run_id" in source
    assert "p_recovery_pipeline_run_id" in source
    assert "recovery_pipeline_run_id=p_recovery_pipeline_run_id" in source
    assert "p_now>p_requested_at" not in source


def test_migration_does_not_grant_direct_shared_table_writes() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "GRANT UPDATE ON source_content_outbox" not in source
    assert "GRANT UPDATE ON owner_exception_v2" not in source
    assert "GRANT UPDATE ON owner_exception_event_v2" not in source
