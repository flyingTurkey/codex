import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

MIGRATION = Path("apps/api/migrations/versions/0034_intelligence_v2.py")


def test_migration_creates_empty_v2_projection_and_append_only_review() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for marker in (
        'revision = "0034_intelligence_v2"',
        'down_revision = "0033_controlled_ai_budget_bridge"',
        '"intelligence_projection_v2"',
        '"owner_review_case_v2"',
        '"owner_review_decision_v2"',
        '"ai_summary_version_v2"',
        '"ai_runtime_health_v2"',
        '"hotspot_award_v2"',
        '"media_rights_v2"',
        '"search_projection_v2"',
        '"projection_archive_manifest"',
        "prevent_v2_append_only_mutation",
        "R4",
        "SCHEMA_REJECTED",
        "INSUFFICIENT_EVIDENCE",
        "REVOKE ALL",
    ):
        assert marker in source


def test_downgrade_is_blocked_after_durable_v2_facts_exist() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "INTELLIGENCE_V2_DOWNGRADE_BLOCKED" in source
    assert "SELECT EXISTS" in source


@pytest.mark.skipif(
    not os.environ.get("SRBG_TEST_ADMIN_DATABASE_URL"),
    reason="requires an isolated PostgreSQL database",
)
def test_v2_migration_upgrades_the_full_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.environ["SRBG_TEST_ADMIN_DATABASE_URL"]
    monkeypatch.setenv("SRBG_DATABASE_URL", database_url)
    config = Config("apps/api/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
