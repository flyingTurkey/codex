from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0031_controlled_personal_runs.py")


def test_migration_defines_fail_closed_controlled_run_authority() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for marker in (
        'revision = "0031_controlled_personal_runs"',
        'down_revision = "0030_pers10_role_archive_repair"',
        '"personal_controlled_run"',
        '"personal_controlled_run_source"',
        '"personal_controlled_http_attempt"',
        "reserve_personal_controlled_http_attempt",
        "settle_personal_controlled_http_attempt",
        "CONTROLLED_RUN_DOWNGRADE_BLOCKED",
        "failure_rate_min_samples = 10",
        "request_limit = 80",
        "byte_limit = 157286400",
        "ai_cost_limit_microusd = 1250000",
        "CONTROLLED_RUN_PATH_DENIED",
        "CONTROLLED_RUN_DOMAIN_RATE_LIMIT",
        "interval '1 minute'",
    ):
        assert marker in source


def test_migration_grants_no_control_tables_to_api_or_projection_roles() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "REVOKE ALL ON personal_controlled_run" in source
    assert "GRANT SELECT,INSERT,UPDATE ON personal_controlled_run" not in source


def test_migration_reservation_is_path_aware_and_worker_only() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "p_path text" in source
    assert "s.path_prefix" in source
    assert "p_path='/robots.txt'" in source
    assert "TO srbg_worker_role" in source
