from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0024_automatic_source_profiles.py")


def test_pers04_is_the_single_head_after_pers03() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0027_ai_judgment_versions"
    revision = script.get_revision("0024_automatic_source_profiles")
    assert revision is not None
    assert revision.down_revision == "0023_personal_source_runtime"


def test_pers04_has_immutable_profiles_overrides_and_durable_queue() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "source_profile_snapshot",
        "source_profile_override",
        "source_profile_run",
        "source_profile_model_attempt",
        "input_sha256",
        "prompt_version",
        "schema_version",
        "model_version",
        "COMPLETE",
        "PARTIAL",
        "AUTO_INFERRED",
        "prevent_round09_audit_mutation",
        "INSERT INTO source_profile_run",
    ):
        assert token in sql
    assert "DROP TABLE source_governance_decision" not in sql
    assert "DROP TABLE source_authority_assessment" not in sql
