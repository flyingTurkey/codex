from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0039_t04_content_candidates.py")


def test_t04_migration_precedes_t05_and_has_append_only_candidate_facts() -> None:
    config = Config("apps/api/alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_revision("0039_t04_content_candidates").revision == (
        "0039_t04_content_candidates"
    )
    assert script.get_revision("0040_t05_reader_projection").down_revision == (
        "0039_t04_content_candidates"
    )
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0039_t04_content_candidates"' in source
    assert 'down_revision = "0038_owner_gold_calibration"' in source
    assert '"content_preparation_candidate_v2"' in source
    assert '"content_preparation_invalidation_v2"' in source
    assert '"claims_payload"' in source
    assert '"source_excerpt_claim_ids"' in source
    assert "prevent_t04_append_only_mutation" in source
    assert "srbg_worker_role" in source
    assert "srbg_projection_reader" in source


def test_t04_migration_grants_each_runtime_only_its_required_write_boundary() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert '"GRANT SELECT,INSERT ON content_preparation_invalidation_v2 "' in source
    assert '"GRANT SELECT ON content_preparation_candidate_v2 TO srbg_publication_writer"' in source
    assert (
        "GRANT INSERT ON content_preparation_candidate_v2 TO srbg_publication_writer"
        not in source
    )
