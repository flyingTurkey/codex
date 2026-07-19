import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    "technology_vendor",
    "technology_product",
    "technology_product_model",
    "technology_product_version",
    "technology_product_profile",
    "technology_product_capability",
    "technology_product_taxonomy",
    "product_normalization_candidate",
}


def test_round07_migration_follows_round06_and_declares_product_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0036_ai_content_result_lifecycle"
    revision = script.get_revision("0008_technology_products")
    assert revision.down_revision == "0007_papers"
    migration = runpy.run_path("apps/api/migrations/versions/0008_technology_products.py")
    assert set(migration["ROUND07_TABLES"]) == REQUIRED_TABLES


def test_round07_migration_preserves_identity_evidence_and_safe_downgrade() -> None:
    source = Path("apps/api/migrations/versions/0008_technology_products.py").read_text(
        encoding="utf-8"
    )
    assert "uq_technology_model_identity" in source
    assert "uq_technology_version_identity" in source
    assert "VERIFIED_CAPABILITY" in source and "independent_evidence_ids" in source
    assert "LOW_ALTITUDE_EQUIPMENT" in source and "permit_status" in source
    source_registry = Path("docs/codex-kit/assets/source_registry.csv").read_text(encoding="utf-8")
    assert "ENT-007,广联达" in source_registry
    assert "ENT-008,大疆行业应用" in source_registry
    assert "refusing Round07 downgrade while technology product data exists" in source


def test_round07_has_an_isolated_upgrade_downgrade_replay() -> None:
    source = Path("scripts/verify_round07_migration.py").read_text(encoding="utf-8")
    assert 'command.upgrade(config, "0008_technology_products")' in source
    assert 'command.downgrade(config, "0007_papers")' in source
    assert "_DISPOSABLE_DATABASE" in source
