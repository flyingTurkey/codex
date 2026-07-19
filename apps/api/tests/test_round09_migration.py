import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    "ai_prompt_version",
    "ai_schema_version",
    "ai_model_profile",
    "ai_pipeline_run",
    "ai_step_run",
    "ai_security_scan",
    "security_review_decision",
    "review_decision",
    "ai_replay_run",
    "ai_shadow_result",
    "ai_quality_report",
    "publication_projection_state",
    "publication_projection_invalidation",
}


def test_round09_migration_follows_round08_and_declares_governance_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0036_ai_content_result_lifecycle"
    revision = script.get_revision("0010_ai_editorial_governance")
    assert revision.down_revision == "0009_dedup_events_scoring"
    migration = runpy.run_path(
        "apps/api/migrations/versions/0010_ai_editorial_governance.py"
    )
    assert set(migration["ROUND09_TABLES"]) == REQUIRED_TABLES


def test_round09_migration_enforces_append_only_and_least_privilege() -> None:
    source = Path(
        "apps/api/migrations/versions/0010_ai_editorial_governance.py"
    ).read_text(encoding="utf-8")
    for token in (
        "prompt_sha256",
        "input_sha256",
        "raw_output",
        "validated_output",
        "cost_microusd",
        "latency_ms",
        "srbg_publication_writer",
        "REVOKE srbg_runtime FROM srbg_model_role",
        "publication_projection_invalidation",
        "prevent_round09_audit_mutation",
    ):
        assert token in source
    assert "GRANT INSERT, UPDATE, DELETE ON publication TO srbg_runtime" not in source
    assert "GRANT INSERT ON review_decision TO srbg_publication_writer" in source


def test_round09_downgrade_refuses_to_destroy_audit_history() -> None:
    source = Path(
        "apps/api/migrations/versions/0010_ai_editorial_governance.py"
    ).read_text(encoding="utf-8")
    assert "refusing Round09 downgrade while governed AI or review records exist" in source
