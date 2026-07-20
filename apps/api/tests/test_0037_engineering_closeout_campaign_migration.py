from pathlib import Path

MIGRATION = Path(
    "apps/api/migrations/versions/0037_engineering_closeout_campaign.py"
)


def test_campaign_migration_adds_append_only_campaign_facts() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for marker in (
        'revision = "0037_engineering_closeout_campaign"',
        'down_revision = "0036_ai_content_result_lifecycle"',
        '"engineering_closeout_campaign_v2"',
        '"engineering_closeout_campaign_event_v2"',
        "ENGINEERING_CLOSEOUT",
        "prevent_engineering_campaign_fact_mutation",
        "ENGINEERING_CLOSEOUT_CAMPAIGN_DOWNGRADE_BLOCKED",
        "REVOKE ALL",
        "GRANT SELECT ON source_admission_assessment_v2 TO srbg_worker_role",
    ):
        assert marker in source


def test_campaign_migration_does_not_activate_sources_or_publish() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "UPDATE source SET" not in source
    assert "INSERT INTO intelligence_projection_v2" not in source
    assert "UPDATE publication" not in source
