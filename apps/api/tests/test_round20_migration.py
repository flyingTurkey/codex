from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0020_ai_content_preparation.py")


def test_round20_remains_in_the_single_head_chain_after_round19() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0051_technical_exception_recovery"
    revision = script.get_revision("0020_ai_content_preparation")
    assert revision is not None
    assert revision.down_revision == "0019_source_content_bridge"


def test_round20_contains_authoritative_budget_and_shadow_pilot_guards() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "ai_budget_policy",
        "ai_budget_reservation",
        "20000",
        "16000",
        "100",
        "WAITING_CLAIM_REVIEW",
        "CLAIM_REVIEW",
        "GOV-ROUND05-MOT",
        "GOV-003",
        "P020250627753815314372.pdf",
        "SHADOW",
    ):
        assert token in sql
    assert "0018_" not in sql


def test_round20_schema_seed_is_self_contained_for_runtime_image() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "SCHEMA_DOCUMENTS" in sql
    assert "docs/codex-kit/assets/schemas" not in sql
    assert "Path(__file__)" not in sql
