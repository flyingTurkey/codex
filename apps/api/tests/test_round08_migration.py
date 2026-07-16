import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    "item_identity_key",
    "document_fingerprint",
    "duplicate_candidate",
    "duplicate_decision",
    "duplicate_link",
    "source_affiliation",
    "source_lineage",
    "topic_cluster",
    "topic_cluster_event",
    "cluster_decision",
    "score_set",
    "score_dimension",
    "score_override",
    "resolution_regression_sample",
}


def test_round08_migration_follows_round07_and_declares_resolution_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0017c_round17_flat_pilot"
    revision = script.get_revision("0009_dedup_events_scoring")
    assert revision.down_revision == "0008_technology_products"
    migration = runpy.run_path("apps/api/migrations/versions/0009_dedup_events_scoring.py")
    assert set(migration["ROUND08_TABLES"]) == REQUIRED_TABLES


def test_round08_migration_encodes_governance_and_safe_downgrade() -> None:
    source = Path("apps/api/migrations/versions/0009_dedup_events_scoring.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "PROJECT",
        "CONTRACT_SECTION",
        "MODEL_NO",
        "DOCUMENT_NUMBER",
        "ACCIDENT_STAGE",
        "scoring-v1.0.0",
        "srbg_publication_writer",
        "refusing Round08 downgrade",
    ):
        assert token in source
    assert "GRANT INSERT, UPDATE ON duplicate_decision" in source
    assert (
        "TO srbg_runtime"
        not in source.split("GRANT INSERT, UPDATE ON duplicate_decision")[1].split("\n")[0]
    )
