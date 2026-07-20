from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0042_t07_controlled_stream.py")


def test_t07_migration_is_single_head_and_separates_four_control_facts() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_revision("0042_t07_controlled_stream").revision == (
        "0042_t07_controlled_stream"
    )
    assert script.get_revision("0042_t07_controlled_stream").down_revision == (
        "0041_t06_ai_runtime_projection"
    )
    source = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "source_research_disposition_v2",
        "source_owner_intent_v2",
        "source_stream_admission_decision_v2",
        "source_stream_runtime_event_v2",
    ):
        assert f'"{table}"' in source
    assert "T07_APPEND_ONLY_FACT" in source


def test_admit_and_runtime_functions_fail_closed_on_stream_level_authority() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ck_t07_admission_admit_complete" in source
    assert "authorize_source_stream_shadow_v2" in source
    assert "start_source_stream_shadow_v2" in source
    assert "source_stream_id" in source
    assert "desired_enabled=true" in source
    assert "manual_disabled_at IS NULL" in source
    assert "valid_until>p_now" in source
    assert source.count("SELECT latest.id FROM source_stream_admission_decision_v2 latest") == 2
    authorize_body = source[
        source.index("CREATE FUNCTION authorize_source_stream_shadow_v2") :
        source.index("CREATE FUNCTION start_source_stream_shadow_v2")
    ]
    assert "research_disposition" not in authorize_body


def test_t07_migration_uses_minimal_roles_and_blocks_destructive_downgrade() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "GRANT SELECT,INSERT ON source_research_disposition_v2,source_owner_intent_v2," in source
    assert "TO srbg_api_role" in source
    assert "GRANT SELECT ON source_stream_admission_decision_v2," in source
    assert "GRANT EXECUTE ON FUNCTION authorize_source_stream_shadow_v2" in source
    assert "TO srbg_worker_role" in source
    assert "T07_DOWNGRADE_BLOCKED" in source
