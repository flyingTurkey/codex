from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0021_personal_source_core.py")


def test_pers01_is_the_single_head_after_round20() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0021_personal_source_core"
    revision = script.get_revision("0021_personal_source_core")
    assert revision is not None
    assert revision.down_revision == "0020_ai_content_preparation"


def test_pers01_adds_personal_source_state_without_dropping_governance() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for token in (
        "desired_enabled",
        "runtime_state",
        "manual_disabled_at",
        "personal_automation_setting",
        "source_key_activity_event",
        "PENDING_CONFIGURATION",
        "MANUAL_DISABLED",
        "prevent_personal_source_override",
    ):
        assert token in sql
    assert "drop_table(\"source_policy\")" not in sql
    assert "drop_table(\"source_onboarding_record\")" not in sql
