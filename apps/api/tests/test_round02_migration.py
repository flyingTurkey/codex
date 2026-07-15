import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    "source_checkpoint",
    "fetch_run",
    "fetch_record",
    "processing_run",
    "intelligence_item",
    "safety_regulation_profile",
    "claim",
    "claim_evidence",
    "review_task",
    "publication",
    "publication_revision",
}


def test_round02_migration_follows_source_vault_and_declares_all_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_current_head() == "0010_ai_editorial_governance"
    assert script.get_revision("0003_safety_publication").down_revision == ("0002_source_vault")
    assert script.get_revision("0004_pdf_ocr_versioning").down_revision == (
        "0003_safety_publication"
    )
    assert script.get_revision("0005_safety_case_lifecycle").down_revision == (
        "0004_pdf_ocr_versioning"
    )
    assert script.get_revision("0006_digital_cases").down_revision == (
        "0005_safety_case_lifecycle"
    )

    migration_path = Path("apps/api/migrations/versions/0003_safety_regulation_publication.py")
    migration = runpy.run_path(str(migration_path))
    assert set(migration["ROUND02_TABLES"]) == REQUIRED_TABLES
    migration_source = migration_path.read_text(encoding="utf-8")
    assert '"admission_fixture"' in migration_source


def test_migration_revokes_publication_writes_from_runtime_roles() -> None:
    migration = Path(
        "apps/api/migrations/versions/0003_safety_regulation_publication.py"
    ).read_text(encoding="utf-8")

    assert "srbg_publication_writer" in migration
    assert "REVOKE INSERT, UPDATE, DELETE ON publication" in migration
    assert "REVOKE INSERT, UPDATE, DELETE ON publication_revision" in migration
    assert "GRANT SELECT, INSERT, UPDATE ON publication TO srbg_publication_writer" in migration
    assert "GRANT SELECT, INSERT ON publication_revision TO srbg_publication_writer" in migration
    for denied_role in (
        "srbg_api_role",
        "srbg_worker_role",
        "srbg_admin_role",
        "srbg_model_role",
    ):
        assert denied_role in migration
