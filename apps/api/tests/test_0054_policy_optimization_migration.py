from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0054_policy_optimization.py")


def test_policy_optimization_is_the_single_linear_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_heads() == ["0054_policy_optimization"]
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0054_policy_optimization"' in source
    assert 'down_revision = "0053_safety_exception_lifecycle"' in source


def test_pipeline_runs_freeze_policy_and_activation_is_append_only() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert '"policy_bundle_id"' in source
    assert "qualification_policy_activation_v2" in source
    assert "active_qualification_policy_v2" in source
    assert "qualification_policy_evaluation_invariant_v2" in source
    assert "qualification_policy_health_v2" in source
    assert "authorizes_production<>false" in source
    assert "affects_production<>false" in source
    assert "v_shadow.window_started_at" in source
    assert "v_shadow.window_ended_at" in source
    assert "v_shadow.evaluated_at" not in source
    assert "v_current.previous_activation_id=p_previous_activation_id" in source
    assert "WHEN 'READY' THEN 80" in source
    assert "policy runtime identity unsupported" in source
    assert "UPDATE qualification_policy_bundle_v2" not in source
    assert "UPDATE qualification_policy_evaluation_v2" not in source
    assert "UPDATE qualification_shadow_decision_v2" not in source


def test_recovery_runs_inherit_the_original_policy_bundle() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "pipeline.policy_bundle_id" in source
    assert "POLICY_BUNDLE_REQUIRED_AT_RUN_CREATION" in source
    assert "POLICY_ACTIVATION_DOWNGRADE_BLOCKED" in source


def test_shadow_projection_guard_is_policy_causal_not_document_global() -> None:
    implementation = Path(
        "apps/api/src/srbg_api/intelligence_v2/policy_optimization.py"
    ).read_text(encoding="utf-8")

    assert "production.policy_bundle_id=shadow.policy_bundle_id" in implementation
    assert "production.normalized_input_sha256=" in implementation
    assert "shadow.decision_trace->>'normalized_input_sha256'" in implementation
    assert "FROM intelligence_item item" not in implementation
