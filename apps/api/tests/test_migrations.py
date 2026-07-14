import csv
import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_source_vault_migration_follows_foundation() -> None:
    config_path = Path("apps/api/alembic.ini")
    assert config_path.is_file()

    script = ScriptDirectory.from_config(Config(config_path))
    source_vault = script.get_revision("0002_source_vault")

    assert source_vault.down_revision == "0001_foundation"


def test_migration_seed_rows_match_the_canonical_disabled_candidate_registry() -> None:
    registry_path = Path("docs/codex-kit/assets/source_registry.csv")
    with registry_path.open(encoding="utf-8-sig", newline="") as stream:
        registry = list(csv.DictReader(stream))
    round02_migration = runpy.run_path("apps/api/migrations/versions/0002_source_vault.py")
    round04_migration = runpy.run_path("apps/api/migrations/versions/0005_safety_case_lifecycle.py")
    round04_codes = {row[0] for row in round04_migration["ROUND04_SOURCE_SEEDS"]}

    def canonical_rows(rows: list[dict[str, str]]) -> tuple[tuple[object, ...], ...]:
        return tuple(
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
            for row in rows
        )

    round02_registry = [row for row in registry if row["source_id"] not in round04_codes]
    round04_registry = [row for row in registry if row["source_id"] in round04_codes]

    assert len(round02_registry) == 42
    assert len(round04_registry) == 4
    assert round02_migration["SEED_SOURCES"] == canonical_rows(round02_registry)
    assert round04_migration["ROUND04_SOURCE_SEEDS"] == canonical_rows(round04_registry)
    assert {row["status"] for row in registry} == {"CANDIDATE"}
    assert {row["enabled"] for row in registry} == {"false"}
