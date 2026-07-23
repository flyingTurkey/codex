import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path(
    "apps/api/migrations/versions/0050_autonomous_handoff_state_order.py"
)


def test_handoff_state_order_does_not_depend_on_random_uuid_suffix() -> None:
    migration = runpy.run_path(str(MIGRATION))
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_current_head() == "0051_technical_exception_recovery"
    assert migration["down_revision"] == "0049_autonomous_content_switch"
    assert "state.created_at DESC,CASE state.state" in migration["STATE_ORDER"]
    assert "WHEN 'FAILED' THEN 90" in migration["STATE_ORDER"]
    assert "WHEN 'QUARANTINED' THEN 90" in migration["STATE_ORDER"]
    assert "WHEN 'READY' THEN 80" in migration["STATE_ORDER"]
    assert "WHEN 'SECURITY_PASSED' THEN 60" in migration["STATE_ORDER"]
