from pathlib import Path


def test_migration_allows_only_explicit_owner_override_to_bypass_quality_metrics() -> None:
    source = (
        Path(__file__).parents[1]
        / "migrations/versions/0047_owner_gold_override_go.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "0046_owner_gold_prediction_seal"' in source
    assert "OWNER_OVERRIDE_GO" in source
    assert "precision_bps>=9000" in source
    assert "recall_bps>=9000" in source
    assert "locked_negative_leaks=0" in source
    assert "reasons ? 'OWNER_OVERRIDE_GO'" in source
    assert "ALTER TABLE owner_gold_calibration_v2" in source
