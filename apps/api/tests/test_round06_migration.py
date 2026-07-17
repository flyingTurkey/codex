import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    "paper_profile",
    "paper_author",
    "paper_authorship",
    "paper_institution",
    "paper_author_affiliation",
    "paper_source_record",
    "paper_taxonomy",
    "paper_duplicate_candidate",
    "item_relation_candidate",
    "item_relation",
}


def test_round06_migration_follows_round05_and_declares_paper_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0024_automatic_source_profiles"
    revision = script.get_revision("0007_papers")
    assert revision.down_revision == "0006_digital_cases"
    migration = runpy.run_path("apps/api/migrations/versions/0007_papers.py")
    assert set(migration["ROUND06_TABLES"]) == REQUIRED_TABLES


def test_round06_migration_enforces_doi_access_and_safe_downgrade() -> None:
    source = Path("apps/api/migrations/versions/0007_papers.py").read_text(encoding="utf-8")
    assert "uq_paper_profile_normalized_doi" in source
    assert "METADATA_ONLY" in source and "ABSTRACT_ALLOWED" in source
    assert "OPEN_FULLTEXT" in source
    assert "RETRACTS" in source
    assert "refusing Round06 downgrade while JOURNAL_PAPER data exists" in source
