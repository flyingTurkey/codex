from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path(
    "apps/api/migrations/versions/0058_phase5_technical_exception_acl.py"
)


def test_phase5_acl_repair_is_the_single_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_heads() == ["0058_phase5_technical_exception_acl"]


def test_phase5_acl_repair_grants_only_the_required_api_read() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0058_phase5_technical_exception_acl"' in source
    assert 'down_revision = "0057_phase5_formal_reconciliation"' in source
    assert (
        "GRANT SELECT ON ai_compensation_run_v2 TO srbg_api_role" in source
    )
    assert (
        "REVOKE SELECT ON ai_compensation_run_v2 FROM srbg_api_role" in source
    )
    assert "GRANT INSERT" not in source
    assert "GRANT UPDATE" not in source
    assert "GRANT DELETE" not in source
