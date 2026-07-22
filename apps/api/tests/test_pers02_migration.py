from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0022_personal_source_streams.py")


def test_pers02_is_the_single_head_after_pers01() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0050_autonomous_handoff_state_order"
    revision = script.get_revision("0022_personal_source_streams")
    assert revision is not None
    assert revision.down_revision == "0021_personal_source_core"


def test_pers02_extends_existing_streams_without_starting_schedules() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "stream_probe_run",
        "stream_config_version",
        "stream_type",
        "allowed_hosts",
        "config_sha256",
        "discovery_method",
        "PROBE_FAILED",
        "READY",
    ):
        assert token in sql
    assert 'create_table(\n        "source_stream"' not in sql
    assert "INSERT INTO fetch_schedule" not in sql
