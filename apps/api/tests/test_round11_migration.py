import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REQUIRED_TABLES = {
    'failed_task',
    'replay_request',
    'usage_metric_bucket',
    'item_feedback',
    'recovery_exercise',
}


def test_round11_migration_follows_round10_and_declares_operations_tables() -> None:
    script = ScriptDirectory.from_config(Config('apps/api/alembic.ini'))
    assert script.get_current_head() == "0058_phase5_technical_exception_acl"
    revision = script.get_revision('0012_operations_readiness')
    assert revision.down_revision == '0011_feed_search_daily'
    migration = runpy.run_path('apps/api/migrations/versions/0012_operations_readiness.py')
    assert set(migration['TABLES']) == REQUIRED_TABLES


def test_round11_migration_restricts_replay_and_feedback_updates() -> None:
    source = Path('apps/api/migrations/versions/0012_operations_readiness.py').read_text(
        encoding='utf-8',
    )
    assert 'GRANT INSERT ON replay_request TO srbg_api_role' in source
    assert 'GRANT UPDATE (status) ON replay_request TO srbg_worker_role' in source
    assert 'GRANT INSERT, UPDATE ON usage_metric_bucket TO srbg_api_role' in source
    assert 'GRANT INSERT, UPDATE ON item_feedback TO srbg_api_role' in source
    assert 'GRANT INSERT ON failed_task TO srbg_worker_role' in source
    assert 'GRANT UPDATE ON replay_request TO srbg_runtime' not in source
    assert "value IN ('USEFUL', 'NOT_USEFUL')" in source


def test_round11_migration_stores_no_personal_browsing_or_failed_payload_material() -> None:
    source = Path('apps/api/migrations/versions/0012_operations_readiness.py').read_text(
        encoding='utf-8',
    )
    usage_block = source.split('"usage_metric_bucket"', 1)[1].split('op.create_table', 1)[0]
    failed_block = source.split('"failed_task"', 1)[1].split('op.create_index', 1)[0]
    assert 'actor_id' not in usage_block
    assert 'target_id' not in usage_block
    assert 'payload' not in failed_block.lower()
    assert 'body' not in failed_block.lower()
    assert 'model_input' not in failed_block.lower()
