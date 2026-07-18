from __future__ import annotations

from pathlib import Path

MIGRATION = Path(
    "apps/api/migrations/versions/0032_controlled_run_worker_read.py"
)


def test_worker_gets_only_the_controlled_run_read_needed_for_dispatch() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0032_controlled_run_worker_read"' in source
    assert 'down_revision = "0031_controlled_personal_runs"' in source
    assert "GRANT SELECT ON personal_controlled_run TO srbg_worker_role" in source
    assert "GRANT INSERT" not in source
    assert "GRANT UPDATE" not in source
    assert "GRANT DELETE" not in source
    assert "REVOKE SELECT ON personal_controlled_run FROM srbg_worker_role" in source
