import importlib.util
from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0049_autonomous_content_switch.py")


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_0049_is_forward_only_from_the_preserved_0048_head() -> None:
    spec = importlib.util.spec_from_file_location("migration_0049", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0049_autonomous_content_switch"
    assert module.down_revision == "0048_autonomous_policy_foundation"


def test_0049_registers_the_production_prompt_schema_and_worker_append_rights() -> None:
    source = _source()

    assert "autonomous-classify-2.1.0" in source
    assert "autonomous-classify-output-2.1.0" in source
    assert "GRANT SELECT,INSERT ON qualification_policy_bundle_v2" in source
    assert "automated_qualification_decision_v2 TO srbg_worker_role" in source
    assert "0046" not in source and "0047" not in source


def test_0049_does_not_turn_owner_gold_or_offline_replay_into_authority() -> None:
    source = _source()

    assert "OWNER_OVERRIDE_GO" not in source
    assert "owner_gold_calibration_v2" not in source
    assert "authorizes_production=true" not in source
