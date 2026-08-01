from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

LEGACY_ANCHOR = Path(
    "apps/api/migrations/versions/0055_crossref_formal_compatibility_anchor.py"
)
MIGRATION = Path(
    "apps/api/migrations/versions/0057_phase5_formal_reconciliation.py"
)
VERIFIER = Path("scripts/verify_phase5_formal_reconciliation_migration.py")


def test_formal_crossref_sibling_reconciles_to_one_forward_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_heads() == ["0057_phase5_formal_reconciliation"]
    assert script.get_revision("0055_crossref_metadata_admission") is not None
    assert script.get_revision("0056_phase4_controlled_handoff") is not None

    anchor = LEGACY_ANCHOR.read_text(encoding="utf-8")
    assert 'revision = "0055_crossref_metadata_admission"' in anchor
    assert 'down_revision = "0054_policy_optimization"' in anchor

    migration = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0057_phase5_formal_reconciliation"' in migration
    assert (
        'down_revision = (\n'
        '    "0056_phase4_controlled_handoff",\n'
        '    "0055_crossref_metadata_admission",\n'
        ")"
    ) in migration


def test_formal_reconciliation_verifier_uses_the_disposable_legacy_seam() -> None:
    source = VERIFIER.read_text(encoding="utf-8")

    assert '_LEGACY = "0055_crossref_metadata_admission"' in source
    assert '_HEAD = "0057_phase5_formal_reconciliation"' in source
    assert "command.upgrade(config, _HEAD)" in source
    assert "command.downgrade(config, _BASE)" in source
    assert "command.stamp(config, _LEGACY)" in source
    assert "0057_CROSSREF_PROVENANCE_PRESERVATION_FAILED" in source
    assert "0057_PHASE3_AUTHORITY_MISSING" in source
    assert "0057_PHASE4_HANDOFF_MISSING" in source
