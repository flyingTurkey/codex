from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0016_scheduling_health_replay.py")


def test_round16_migration_has_authoritative_scheduler_and_safe_replay_schema() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "fetch_schedule",
        "source_health_snapshot",
        "source_anomaly",
        "retention_execution",
    ):
        assert f'"{table}"' in source
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "LEGACY_TASK_ID_ONLY" in source
    assert "ADD COLUMN IF NOT EXISTS replayable" in source
    assert "ADD COLUMN IF NOT EXISTS execution_id" in source
    assert "srbg_projection_reader" in source
    assert "REVOKE ALL" in source
    assert "0016_DOWNGRADE_BLOCKED" in source


def test_round16_migration_grants_retention_to_the_publication_role() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert (
        "GRANT SELECT, INSERT, UPDATE ON retention_execution TO srbg_publication_writer"
        in source
    )
    assert "TO srbg_publisher_login" not in source
