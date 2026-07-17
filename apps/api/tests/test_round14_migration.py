import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_round14_is_expand_only_and_separates_relation_responsibilities() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0021_personal_source_core"
    completion = script.get_revision("0014b_event_consumer_switch")
    assert completion.down_revision == "0014_event_unification"
    revision = script.get_revision("0014_event_unification")
    assert revision.down_revision == "0013_internal_projection"
    migration = runpy.run_path("apps/api/migrations/versions/0014_event_unification.py")
    assert set(migration["ROUND14_TABLES"]) >= {
        "document_event_membership",
        "event_entity_relation",
        "topic_event",
        "event_taxonomy_assignment",
        "event_migration_run",
        "event_migration_checkpoint",
        "event_migration_blocker",
        "event_consumer_parity_difference",
        "event_identity_change_request",
        "event_identity_change_decision",
        "event_identity_change_target",
        "event_split_allocation",
    }


def test_round14_has_no_unbounded_backfill_or_provisional_event() -> None:
    source = Path("apps/api/migrations/versions/0014_event_unification.py").read_text(
        encoding="utf-8"
    )
    assert "PROVISIONAL_EVENT" not in source
    assert "INSERT INTO event" not in source
    assert "DELETE FROM intelligence_item" not in source
    assert "DROP TABLE intelligence_item" not in source
    assert "canonical_event_id" in source
    assert "source_event_id" in source and "target_event_id" in source
    assert "auto_merge" in source and 'server_default=sa.text("false")' in source
    assert "prevent_event_identity_binding_mutation" in source


def test_round14_source_roles_and_event_types_are_closed_sets() -> None:
    source = Path("apps/api/migrations/versions/0014_event_unification.py").read_text(
        encoding="utf-8"
    )
    for role in ("ORIGINAL", "REPRINT", "MIRROR", "INDEPENDENT_REPORT"):
        assert role in source
    for event_type in (
        "SAFETY_INCIDENT",
        "REGULATION_CHANGE",
        "DIGITAL_PROJECT",
        "RESEARCH_RESULT",
        "PRODUCT_RELEASE",
    ):
        assert event_type in source
    assert 'server_default="SAFETY_INCIDENT"' not in source
