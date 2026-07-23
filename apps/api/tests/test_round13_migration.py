import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_round13_migration_declares_projection_schema_roles_and_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0052_feed_suppression_projection"
    revision = script.get_revision("0013_internal_projection")
    assert revision.down_revision == "0012_operations_readiness"
    migration = runpy.run_path("apps/api/migrations/versions/0013_internal_projection.py")
    assert set(migration["ROUND13_TABLES"]) == {
        "event_identity_binding",
        "projection_build_run",
        "event_projection_revision",
        "event_projection_field_source",
        "projection_reconciliation_difference",
        "audit_chain_anchor",
    }


def test_round13_migration_enforces_reader_and_audit_boundaries() -> None:
    source = Path("apps/api/migrations/versions/0013_internal_projection.py").read_text(
        encoding="utf-8"
    )
    assert "CREATE SCHEMA published_v1" in source
    assert "CREATE ROLE srbg_projection_reader NOLOGIN" in source
    assert "GRANT USAGE ON SCHEMA published_v1 TO srbg_projection_reader" in source
    assert "GRANT SELECT ON published_v1.current_event_summary" in source
    assert "REVOKE ALL ON SCHEMA public FROM srbg_projection_reader" in source
    assert "REVOKE INSERT, UPDATE, DELETE ON audit_log FROM srbg_runtime" in source
    assert "CREATE FUNCTION append_audit_event" in source
    assert "pg_advisory_xact_lock" in source
