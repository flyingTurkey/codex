import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    "search_projection",
    "search_identifier",
    "daily_report",
    "daily_report_item",
    "saved_item",
    "user_collection",
    "collection_item",
    "idempotency_record",
}


def test_round10_migration_follows_round09_and_declares_portal_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0045_t12_media_delivery"
    revision = script.get_revision("0011_feed_search_daily")
    assert revision.down_revision == "0010_ai_editorial_governance"
    migration = runpy.run_path("apps/api/migrations/versions/0011_feed_search_daily.py")
    assert set(migration["ROUND10_TABLES"]) == REQUIRED_TABLES


def test_round10_migration_has_required_search_indexes_acl_and_downgrade_guard() -> None:
    source = Path("apps/api/migrations/versions/0011_feed_search_daily.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE EXTENSION IF NOT EXISTS vector",
        "gin_trgm_ops",
        "to_tsvector('simple'",
        "vector(1536)",
        "vector_cosine_ops",
        "DOCUMENT_NUMBER",
        "STANDARD_NUMBER",
        "DOI",
        "owner_id",
        "srbg_publication_writer",
        "refusing Round10 downgrade while daily reports or personal library records exist",
    ):
        assert token in source
    assert "GRANT INSERT, UPDATE ON daily_report TO srbg_runtime" not in source
    assert "GRANT INSERT, UPDATE ON search_projection TO srbg_runtime" not in source


def test_postgres_image_preserves_pinned_postgres_and_adds_pgvector() -> None:
    dockerfile = Path("infra/compose/Dockerfile.postgres").read_text(encoding="utf-8")
    compose = Path("infra/compose/compose.yaml").read_text(encoding="utf-8")
    assert "pgvector/pgvector:0.8.2-pg17-bookworm" in dockerfile
    assert "postgres:17.10-bookworm" in dockerfile
    assert "USER postgres" in dockerfile
    assert "Dockerfile.postgres" in compose
