from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0055_phase3_trustworthy_event.py")


def test_phase3_trustworthy_event_is_the_single_linear_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_heads() == ["0059_phase5_extract_prompt_v2"]
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0055_phase3_trustworthy_event"' in source
    assert 'down_revision = "0054_policy_optimization"' in source


def test_automatic_publication_has_one_authority_and_reader_revision_guard() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "automatic_publication_authority_v2" in source
    assert "event_publication_control_event_v2" in source
    assert "automatic_authority_id" in source
    assert "num_nonnulls(review_task_id,automatic_authority_id)=1" in source
    assert "publication_revision_id" in source
    assert "accepted_claim_set_sha256" in source
    assert "authority_epoch" in source
    assert "projection.publication_revision_id=publication.current_revision_id" in source
    assert "COALESCE(control.owner_veto,false)=false" in source
    assert "revision.review_task_id IS NOT NULL" in source
    assert "LEFT JOIN automatic_publication_authority_v2" in source


def test_verify_registry_is_immutable_and_downgrade_is_data_safe() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ai01-verify-v1" in source
    assert "verify-output-v1" in source
    assert "PHASE3_TRUSTWORTHY_EVENT_DOWNGRADE_BLOCKED" in source
    assert "DISABLE TRIGGER USER" in source
    assert "ENABLE TRIGGER USER" in source


def test_every_phase3_model_step_can_reserve_and_settle_budget() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION reserve_ai_budget" in source
    assert "('CLASSIFY','EXTRACT','SUMMARIZE','VERIFY')" in source
    assert "_PREVIOUS_RESERVE_AI_BUDGET" in source


def test_worker_locks_handoff_through_a_narrow_authoritative_command() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "lock_source_content_ai_handoff(uuid,uuid)" in source
    assert "GRANT EXECUTE ON FUNCTION lock_source_content_ai_handoff(uuid,uuid)" in source
    assert '"TO srbg_worker_role"' in source
    assert "GRANT SELECT ON source_content_outbox TO srbg_worker_role" not in source


def test_publisher_locks_automatic_authority_through_a_narrow_command() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "load_automatic_publication_context(uuid,uuid,timestamptz)" in source
    assert "TO srbg_publication_writer" in source
    assert "GRANT UPDATE ON document_version TO srbg_publication_writer" not in source
    assert "source_stream_config_version_id" in source
    assert "config.config_sha256=stream.config_sha256" in source
    assert "definition.schema_version=config.schema_version" in source
