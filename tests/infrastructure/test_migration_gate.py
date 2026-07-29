from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ci.check_migration_heads import validate_single_head  # noqa: E402


def test_migration_head_check_rejects_zero_or_multiple_heads() -> None:
    with pytest.raises(RuntimeError, match="exactly one Alembic head"):
        validate_single_head(())
    with pytest.raises(RuntimeError, match="exactly one Alembic head"):
        validate_single_head(("0054_policy_optimization", "9999_other"))


def test_migration_gate_combines_single_head_and_existing_round_trip_verifier() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts/verify_autonomous_policy_migration.py").read_text(
        encoding="utf-8"
    )

    assert "migration-test: migration-head-check autonomous-content-integration-test" in makefile
    for token in (
        'command.upgrade(config, "0054_policy_optimization")',
        'command.downgrade(config, "0053_safety_exception_lifecycle")',
        'command.downgrade(config, "0047_owner_gold_override_go")',
        "revision_0054_acl",
        "revision_0047_acl",
    ):
        assert token in verifier
