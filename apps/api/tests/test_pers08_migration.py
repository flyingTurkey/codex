from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0028_automatic_relationships.py")


def test_pers08_is_the_single_head_after_pers07() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0056_phase4_controlled_handoff"
    revision = script.get_revision("0028_automatic_relationships")
    assert revision is not None
    assert revision.down_revision == "0027_ai_judgment_versions"


def test_pers08_persists_reversible_versioned_relationships() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "automatic_relationship_decision_version",
        "automatic_relationship_member",
        "owner_relationship_correction",
        "owner_relationship_withdrawal",
        "automatic_relationship_invalidation",
        "algorithm_version",
        "model_version",
        "score_bps",
        "reason_codes",
        "input_fingerprint_sha256",
        "supersedes_decision_id",
        "VENDOR_STATEMENT",
        "MEDIA_REPORT",
        "INDEPENDENT_VERIFICATION",
    ):
        assert token in sql


def test_pers08_never_cascades_into_preserved_evidence_objects() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in ("intelligence_item", "document", "document_version", "claim", "claim_evidence"):
        assert f'sa.ForeignKey("{table}.id", ondelete="RESTRICT")' in sql


def test_pers08_freezes_legacy_candidate_writes_without_dropping_apis_or_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "PERS08_LEGACY_CANDIDATE_FROZEN" in sql
    assert "DROP TABLE duplicate_candidate" not in sql
    assert "DROP TABLE product_normalization_candidate" not in sql
