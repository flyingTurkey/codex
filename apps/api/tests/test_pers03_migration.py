from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0023_personal_source_runtime.py")


def test_pers03_is_the_single_head_after_pers02() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0048_autonomous_policy_foundation"
    revision = script.get_revision("0023_personal_source_runtime")
    assert revision is not None
    assert revision.down_revision == "0022_personal_source_streams"


def test_pers03_adds_stream_authority_without_deleting_legacy_governance() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "source_stream_id",
        "stream_config_version_id",
        "PERSONAL_STREAM",
        "self_heal_state",
        "next_self_heal_at",
        "access_state",
        "consecutive_zero_discovery",
        "claim_due_fetch_schedule",
    ):
        assert token in sql
    assert "DROP TABLE source_governance_decision" not in sql
    assert "DROP TABLE source_qualification_bundle" not in sql
    assert "PRODUCTION_APPROVAL" in sql
