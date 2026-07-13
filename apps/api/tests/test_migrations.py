import csv
import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_source_vault_migration_follows_foundation() -> None:
    config_path = Path("apps/api/alembic.ini")
    assert config_path.is_file()

    script = ScriptDirectory.from_config(Config(config_path))
    head = script.get_current_head()

    assert head == "0002_source_vault"
    assert script.get_revision(head).down_revision == "0001_foundation"


def test_migration_seed_rows_match_the_canonical_disabled_candidate_registry() -> None:
    registry_path = Path("docs/codex-kit/assets/source_registry.csv")
    with registry_path.open(encoding="utf-8-sig", newline="") as stream:
        registry = list(csv.DictReader(stream))
    migration = runpy.run_path("apps/api/migrations/versions/0002_source_vault.py")
    seeds = migration["SEED_SOURCES"]
    expected = tuple(
        (
            row["source_id"],
            row["name"],
            row["base_url"],
            row["channel"],
            row["source_type"],
            row["authority_level"],
            row["priority"],
            row["collection_method"],
            int(row["poll_interval_minutes"]),
        )
        for row in registry
    )

    assert len(registry) == 42
    assert seeds == expected
    assert {row["status"] for row in registry} == {"CANDIDATE"}
    assert {row["enabled"] for row in registry} == {"false"}
