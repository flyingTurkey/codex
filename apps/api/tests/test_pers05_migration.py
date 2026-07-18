from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0025_personal_source_discovery.py")


def test_pers05_is_the_single_head_after_pers04() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0032_controlled_run_worker_read"
    revision = script.get_revision("0025_personal_source_discovery")
    assert revision is not None
    assert revision.down_revision == "0024_automatic_source_profiles"


def test_pers05_contains_bounded_ledgers_topics_and_append_only_scores() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "discovery_topic",
        "discovery_occurrence",
        "personal_probe_daily_ledger",
        "personal_auto_enable_daily_ledger",
        "source_auto_score_run",
        "source_auto_score_snapshot",
        "reserve_personal_probe_budget",
        "reserve_personal_auto_enable_budget",
        "prevent_round09_audit_mutation",
        "AUTO_ENABLED",
        "Asia/Shanghai",
        "INSERT INTO source_auto_score_run",
    ):
        assert token in sql
    assert "requests." not in sql
    assert "HttpxTransport" not in sql
    assert "claim" not in sql.casefold()


def test_pers05_seeds_exactly_the_seven_personal_topics() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for code in (
        "HIGHWAY",
        "BRIDGE",
        "TUNNEL",
        "RAIL",
        "DIGITAL",
        "AI_IOT_LOW_ALTITUDE",
        "SAFETY",
    ):
        assert f'"{code}"' in sql
