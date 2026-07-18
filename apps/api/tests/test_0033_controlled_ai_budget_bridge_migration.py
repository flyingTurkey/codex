from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0033_controlled_ai_budget_bridge.py")


def test_migration_bridges_existing_ai_and_controlled_run_ledgers() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for marker in (
        'revision = "0033_controlled_ai_budget_bridge"',
        'down_revision = "0032_controlled_run_worker_read"',
        '"controlled_run_id"',
        '"controlled_cost_reserved_microusd"',
        '"controlled_cost_settled_microusd"',
        "reserve_controlled_ai_budget",
        "settle_controlled_ai_budget",
        "release_controlled_ai_budget",
        "CONTROLLED_AI_RUN_NOT_RUNNING",
        "CONTROLLED_AI_COST_LIMIT",
        "ai_cost_reserved_microusd",
        "ai_cost_settled_microusd",
        "ai_budget_month",
        "ai_budget_reservation",
        "TO srbg_worker_role",
    ):
        assert marker in source


def test_downgrade_refuses_unsettled_controlled_ai_reservations() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "CONTROLLED_AI_BRIDGE_DOWNGRADE_BLOCKED" in source
    assert "billing_status='RESERVED'" in source
