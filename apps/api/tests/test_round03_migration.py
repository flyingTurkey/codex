import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    "raw_object_security_fact",
    "document_version_state_event",
    "document_page",
    "document_text_block",
    "document_table_cell",
    "version_change",
    "version_change_state_event",
    "document_relation_candidate",
    "document_relation_decision",
    "document_relation",
    "regulation_status_candidate",
    "regulation_status_decision",
    "content_lifecycle_event",
    "derived_summary",
    "source_url_check",
    "outbox_event",
}


def test_round03_migration_is_additive_and_declares_evidence_lifecycle_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_current_head() == "0054_policy_optimization"
    revision = script.get_revision("0004_pdf_ocr_versioning")
    assert revision.down_revision == "0003_safety_publication"

    migration_path = Path("apps/api/migrations/versions/0004_pdf_ocr_versioning.py")
    migration = runpy.run_path(str(migration_path))
    assert set(migration["ROUND03_TABLES"]) == REQUIRED_TABLES


def test_round03_migration_keeps_publication_writes_out_of_parser_role() -> None:
    source = Path("apps/api/migrations/versions/0004_pdf_ocr_versioning.py").read_text(
        encoding="utf-8"
    )

    assert "parent_attachment_id" in source
    assert "srbg_publication_writer" in source
    assert "srbg_worker_role" in source
    assert "REVOKE INSERT, UPDATE, DELETE ON content_lifecycle_event" in source
    assert "GRANT SELECT, INSERT ON content_lifecycle_event TO srbg_publication_writer" in source
    assert "GRANT INSERT ON version_change_state_event" in source
    assert "document_relation_decision" in source
    assert "regulation_status_decision" in source
    assert "CREATE TRIGGER" in source
