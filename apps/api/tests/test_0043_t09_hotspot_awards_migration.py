from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0043_t09_hotspot_awards.py")


def test_t09_is_the_single_head_after_t07() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_current_head() == "0053_safety_exception_lifecycle"
    assert script.get_revision("0043_t09_hotspot_awards").down_revision == (
        "0042_t07_controlled_stream"
    )


def test_t09_migration_makes_candidates_evaluations_and_awards_append_only() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for marker in (
        '"hotspot_candidate_v2"',
        '"hotspot_evaluation_v2"',
        '"hotspot_award_v2"',
        "evaluation_id",
        "document_version_id",
        "evaluation_inputs",
        "evidence_sha256",
        "T09_APPEND_ONLY_FACT",
        "prevent_t09_append_only_mutation",
        "REVOKE UPDATE,DELETE ON hotspot_award_v2",
        "T09_DOWNGRADE_BLOCKED",
    ):
        assert marker in source

    assert 'sa.UniqueConstraint("event_id", "rule_version"' not in source
    assert "GRANT SELECT,INSERT ON hotspot_award_v2" in source
    assert "GRANT SELECT ON source_admission_assessment_v2" in source
    assert "REVOKE SELECT ON source_admission_assessment_v2" in source


def test_t09_new_awards_cannot_carry_revocation_fields() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "evaluation_id IS NULL OR (revoked_at IS NULL AND revocation_reason IS NULL)" in source
