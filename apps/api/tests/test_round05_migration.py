import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    "digital_case_profile",
    "digital_case_taxonomy",
    "digital_case_entity",
    "digital_case_entity_relation",
    "digital_case_outcome",
    "digital_case_relevance",
}


def test_round05_migration_follows_round04_and_declares_digital_case_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_current_head() == "0008_technology_products"
    revision = script.get_revision("0006_digital_cases")
    assert revision.down_revision == "0005_safety_case_lifecycle"
    migration = runpy.run_path("apps/api/migrations/versions/0006_digital_cases.py")
    assert set(migration["ROUND05_TABLES"]) == REQUIRED_TABLES


def test_round05_migration_expands_types_risks_and_preserves_claim_multiplicity() -> None:
    source = Path("apps/api/migrations/versions/0006_digital_cases.py").read_text(encoding="utf-8")

    assert "DIGITAL_CASE" in source
    assert "risk_level IN ('R1','R2','R3','R4')" in source
    assert "GOVERNMENT_CASE_COLLECTION" in source
    assert "ENTERPRISE_SELF_REPORT" in source
    assert "CLAIMED" in source and "VERIFIED" in source
    assert "independent_evidence_ids" in source
    assert "relevance-v1.0.0" in source
    assert "uq_claim_item_version_type" in source
    assert "refusing Round05 downgrade while DIGITAL_CASE data exists" in source
