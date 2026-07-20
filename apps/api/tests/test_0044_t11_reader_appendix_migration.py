from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0044_t11_reader_appendix.py")
VERIFIER = Path("scripts/verify_t11_migration.py")


def test_t11_migration_exposes_only_a_full_projection_security_view() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "reader_appendix_governance_v2" in source
    assert "security_barrier=true" in source
    assert "projection.projection_kind='FULL'" in source
    assert "projection.risk_tier IN ('R1','R2')" in source
    assert "GRANT SELECT ON reader_appendix_governance_v2 TO srbg_projection_reader" in source
    assert "GRANT SELECT ON claim_evidence" not in source
    assert "GRANT SELECT ON event_relation" not in source


def test_t11_migration_keeps_relationship_mutations_on_the_v1_boundary() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE VIEW reader_appendix_governance_v2" in source
    assert "INSERT INTO event_relation" not in source
    assert "UPDATE event_relation" not in source
    assert "DELETE FROM event_relation" not in source
    assert "relationship-corrections" not in source


def test_t11_migration_remains_on_the_single_linear_head_path() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    revision = script.get_revision("0044_t11_reader_appendix")
    head = script.get_current_head()
    path = {
        item.revision
        for item in script.iterate_revisions(head, "0043_t09_hotspot_awards")
    }

    assert revision.down_revision == "0043_t09_hotspot_awards"
    assert "0044_t11_reader_appendix" in path


def test_t11_has_an_isolated_forward_and_rollback_verifier() -> None:
    source = VERIFIER.read_text(encoding="utf-8")

    assert 'command.upgrade(config, "0044_t11_reader_appendix")' in source
    assert 'command.downgrade(config, "0043_t09_hotspot_awards")' in source
    assert "reader_appendix_governance_v2" in source
    assert "srbg_projection_reader" in source
