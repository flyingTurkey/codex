from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0027_ai_judgment_versions.py")


def test_pers07_is_the_single_head_after_pers06() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0027_ai_judgment_versions"
    revision = script.get_revision("0027_ai_judgment_versions")
    assert revision is not None
    assert revision.down_revision == "0026_automatic_evidence_facts"


def test_pers07_persists_versioned_results_and_isolated_projections() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "ai_judgment_version",
        "evidence_fact_set_sha256",
        "summarize_prompt_version",
        "verify_prompt_version",
        "schema_version",
        "model_version",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "cost_microusd",
        "verification_result",
        "failure_reason_codes",
        "invalidation_reason",
        "personal_signal_projection",
        "personal_primary_search_projection",
        "unverified_ai_search_projection",
        "personal_daily_report_projection",
        "ai_judgment_projection_reference",
    ):
        assert token in sql


def test_pers07_projection_tables_are_publisher_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "TO srbg_publication_writer" in sql
    assert "GRANT SELECT,INSERT,UPDATE ON ai_judgment_version TO srbg_worker_role" in sql
    assert "GRANT INSERT" not in "\n".join(
        line
        for line in sql.splitlines()
        if "personal_signal_projection" in line and "srbg_worker_role" in line
    )
