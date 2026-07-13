from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_foundation_migration_is_reversible_baseline() -> None:
    config_path = Path("apps/api/alembic.ini")
    assert config_path.is_file()

    script = ScriptDirectory.from_config(Config(config_path))
    head = script.get_current_head()

    assert head == "0001_foundation"
    assert script.get_revision(head).down_revision is None
