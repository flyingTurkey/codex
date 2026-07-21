from pathlib import Path

MIGRATION = Path(
    "apps/api/migrations/versions/0048_autonomous_policy_foundation.py"
)


def test_0048_expands_after_owner_gold_history_without_rewriting_it() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for marker in (
        'revision = "0048_autonomous_policy_foundation"',
        'down_revision = "0047_owner_gold_override_go"',
        '"qualification_policy_bundle_v2"',
        '"automated_qualification_decision_v2"',
        '"owner_exception_v2"',
        '"owner_exception_event_v2"',
        '"feed_suppression_rule_v2"',
        '"qualification_policy_evaluation_v2"',
        '"qualification_shadow_decision_v2"',
        "AUTONOMOUS_POLICY_GATE",
        "prevent_autonomous_policy_fact_mutation",
        "AUTONOMOUS_POLICY_DOWNGRADE_BLOCKED",
    ):
        assert marker in source

    assert "OWNER_OVERRIDE_GO" not in source
    assert "UPDATE owner_gold_calibration_v2" not in source
    assert "INSERT INTO intelligence_projection_v2" not in source
    assert "UPDATE source SET" not in source


def test_0048_freezes_all_shared_dispositions_and_suppression_scopes() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for value in (
        "AUTO_ACCEPTED",
        "AUTO_FILTERED",
        "TECHNICAL_RETRY",
        "TECHNICAL_FAILED",
        "SAFETY_HOLD",
        "OWNER_SUPPRESSED",
        "EVENT",
        "PRIMARY_TYPE",
        "ENGINEERING_OBJECT",
        "SPECIALTY_FACET",
        "EQUIPMENT_DOMAIN",
        "SOURCE",
        "CUSTOM_TOPIC",
        "OFFLINE_REPLAY",
        "SHADOW",
    ):
        assert value in source


def test_0048_binds_policy_identity_and_stores_only_aggregate_evaluation_counts() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert '"global_rule_version"' in source
    for column in (
        "technical_retry_count",
        "technical_failed_count",
        "safety_hold_count",
        "owner_suppressed_count",
    ):
        assert column in source
    assert 'sa.Column("aggregate_metrics"' not in source
    assert "precision_bps>=9000" in source
    assert "recall_bps>=9000" in source
    assert "locked_negative_leaks=0" in source
    assert "schema_valid_bps=10000" in source
    assert "OWNER_OVERRIDE_GO" not in source
