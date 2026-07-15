import pytest

from scripts.recovery_drill import validate_drill_environment
from scripts.runbook_verify import runbook_scenarios


def test_recovery_drill_refuses_production_and_requires_explicit_isolation() -> None:
    with pytest.raises(RuntimeError):
        validate_drill_environment("production", "ISOLATED_ONLY")
    with pytest.raises(RuntimeError):
        validate_drill_environment("test", "")
    validate_drill_environment("test", "ISOLATED_ONLY")


def test_runbook_verifier_covers_required_incidents() -> None:
    assert set(runbook_scenarios()) == {
        "release",
        "rollback",
        "withdrawal",
        "source_failure",
        "model_anomaly",
        "redis_rebuild",
    }
