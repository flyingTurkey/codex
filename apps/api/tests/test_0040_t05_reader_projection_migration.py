from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0040_t05_reader_projection.py")


def test_t05_migration_is_single_head_with_rebuildable_append_only_facts() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_revision("0040_t05_reader_projection").revision == (
        "0040_t05_reader_projection"
    )
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision = "0039_t04_content_candidates"' in source
    for table in (
        "qualification_acceptance_v2",
        "publication_decision_v2",
        "projection_archive_row_v2",
    ):
        assert f'"{table}"' in source
    assert "T05_APPEND_ONLY_FACT" in source
    assert "srbg_worker_role" in source
    assert "srbg_publication_writer" in source
    assert "srbg_projection_reader" in source


def test_t05_migration_blocks_downgrade_when_durable_facts_exist() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "T05_DOWNGRADE_BLOCKED" in source
    assert "projection_archive_row_v2" in source
    assert "publication_decision_v2" in source
    assert "qualification_acceptance_v2" in source
