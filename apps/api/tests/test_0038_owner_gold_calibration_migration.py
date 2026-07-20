from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0038_owner_gold_calibration.py")


def test_migration_adds_append_only_versioned_calibration_facts() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for marker in (
        'revision = "0038_owner_gold_calibration"',
        'down_revision = "0037_engineering_closeout_campaign"',
        '"owner_gold_calibration_v2"',
        "HUMAN_OWNER",
        "prevent_owner_gold_calibration_mutation",
        "OWNER_GOLD_CALIBRATION_DOWNGRADE_BLOCKED",
        "srbg_api_role",
        "srbg_worker_role",
        "srbg_publication_writer",
    ):
        assert marker in source


def test_migration_cannot_seed_go_or_change_publication_and_source_state() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "INSERT INTO owner_gold_calibration_v2" not in source
    assert "UPDATE source SET" not in source
    assert "INSERT INTO intelligence_projection_v2" not in source
    assert "UPDATE publication" not in source
