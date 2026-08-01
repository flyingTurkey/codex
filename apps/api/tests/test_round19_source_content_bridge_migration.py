import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0019_source_content_bridge.py")


def test_round19_is_single_head_and_adds_a_dedicated_id_only_outbox() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0057_phase5_formal_reconciliation"
    revision = script.get_revision("0019_source_content_bridge")
    assert revision.down_revision == "0018_source_automation"

    module = runpy.run_path(str(MIGRATION))
    assert module["SOURCE_CONTENT_TABLES"] == ("source_content_outbox",)


def test_ready_trigger_and_backfill_select_only_scheduled_production_versions() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for required in (
        "document_version_state_event",
        "AFTER INSERT",
        "NEW.state='READY'",
        "execution_domain='PRODUCTION'",
        "run_origin='SCHEDULED'",
        "pilot_window_source_id IS NULL",
        "admission_fixture=false",
        "ON CONFLICT (document_version_id) DO NOTHING",
    ):
        assert required in source
    assert "payload" not in source.casefold()
    assert "document_text" not in source.casefold()


def test_handoff_revalidates_evidence_and_stops_at_queued_ai() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for required in (
        "handoff_source_content_to_ai",
        "FOR UPDATE",
        "document.current_version_id=version.id",
        "latest_state.state='READY'",
        "fact.status='CLEAN'",
        "fact.status IN ('REJECTED','QUARANTINED')",
        "INSERT INTO ai_pipeline_run",
        "'LIVE','QUEUED'",
        "status='WAITING_AI'",
        "pipeline_run_id",
    ):
        assert required in source
    for forbidden in (
        "INSERT INTO claim",
        "INSERT INTO claim_evidence",
        "INSERT INTO review_task",
        "INSERT INTO publication",
        "UPDATE publication",
    ):
        assert forbidden not in source


def test_worker_has_execute_only_and_failure_retry_is_bounded() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for command in (
        "list_pending_source_content_ids",
        "handoff_source_content_to_ai",
        "fail_source_content_handoff",
    ):
        assert f"CREATE FUNCTION {command}" in source
        assert f"GRANT EXECUTE ON FUNCTION {command}" in source
    assert "SECURITY DEFINER" in source
    assert "attempt_count<5" in source
    assert "THEN 'DEAD_LETTER' ELSE 'FAILED' END" in source
    worker_grants = [
        line
        for line in source.splitlines()
        if "srbg_worker_role" in line and "GRANT" in line
    ]
    assert worker_grants
    assert all("EXECUTE ON FUNCTION" in line for line in worker_grants)
    assert (
        "GRANT SELECT ON source_content_outbox "
        "TO srbg_api_role,srbg_publication_writer,srbg_admin_role"
    ) in source
    assert "GRANT SELECT ON source_content_outbox TO srbg_worker_role" not in source


def test_downgrade_refuses_to_delete_durable_handoffs() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ROUND19_DOWNGRADE_BLOCKED" in source
    assert "SELECT 1 FROM source_content_outbox" in source
