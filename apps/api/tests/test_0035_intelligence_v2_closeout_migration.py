from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0035_intelligence_v2_closeout.py")


def test_closeout_migration_adds_durable_evidence_and_reprocessing_boundaries() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for marker in (
        'revision = "0035_intelligence_v2_closeout"',
        'down_revision = "0034_intelligence_v2"',
        '"owner_review_reprocessing_outbox_v2"',
        '"ai_runtime_observation_v2"',
        '"ai_compensation_run_v2"',
        '"source_admission_assessment_v2"',
        "prevent_v2_closeout_append_only_mutation",
        "INTELLIGENCE_V2_CLOSEOUT_DOWNGRADE_BLOCKED",
        "REVOKE ALL",
    ):
        assert marker in source


def test_closeout_migration_keeps_production_activation_out_of_scope() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "UPDATE source SET state='ACTIVE'" not in source
    assert "UPDATE projection_generation SET active=true" not in source
