from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0052_feed_suppression_projection.py")


def test_feed_suppression_projection_is_the_single_linear_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_heads() == ["0052_feed_suppression_projection"]
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0052_feed_suppression_projection"' in source
    assert 'down_revision = "0051_technical_exception_recovery"' in source


def test_feed_suppression_projection_reuses_the_append_only_ledger() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'create_table(\n        "event_suppression_match_v2"' in source
    assert "CREATE VIEW feed_suppression_effective_v2" in source
    assert "FROM feed_suppression_rule_v2 activation" in source
    assert "revoke.supersedes_rule_id=activation.id" in source
    assert "CREATE TABLE feed_suppression_rule_v2" not in source
    assert "DROP TABLE feed_suppression_rule_v2" not in source
    assert "GRANT SELECT ON event_suppression_match_v2" in source
    assert "GRANT SELECT ON feed_suppression_effective_v2" in source
    assert "GRANT INSERT ON feed_suppression_rule_v2" in source
    assert "CREATE VIEW visible_intelligence_projection_v2" in source
    assert "projection.projected_at<=rule.revoked_at" in source
    assert "INSERT INTO event_suppression_match_v2" in source
    assert "qualification.cross_type_tags" in source


def test_feed_suppression_projection_preserves_media_event_authority() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE VIEW media_delivery_reader_v2" in source
    assert "binding.event_id" in source
    assert "DROP VIEW IF EXISTS media_delivery_reader_v2" in source
    assert "def downgrade()" in source
