import csv
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_round15_make_target_is_isolated_and_complete() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("phase2-round15-test:", 1)[1].split("\n\n", 1)[0]

    assert "verify_round15_migration.py" in target
    for required in (
        "test_round15_migration.py",
        "test_round15_source_lifecycle.py",
        "test_round15_source_api.py",
        "test_round15_source_metrics.py",
        "test_logging.py",
        "test_round15_scheduled_source_gate.py",
        "test_round15_connector_contracts.py",
        "test_round15_connector_replay.py",
        "test_round15_http_security.py",
        "test_acquisition_security.py",
        "test_upload_security.py",
        "test_round15_object_store_security.py",
        "test_source_admin_api.py",
        "test_source_fixture_integration.py",
        "packages/contracts/tests",
        "tests/infrastructure/test_round15_observability.py",
        "round15-source-center.spec.ts --grep-invert @a11y",
        "round15-source-center.spec.ts --grep @a11y",
    ):
        assert required in target

    fixture_target = makefile.split("source-fixture-test:", 1)[1].split("\n\n", 1)[0]
    assert "run_isolated_integration.py" in fixture_target
    assert "SOURCE_TEST_ENV" not in fixture_target

    replay_target = makefile.split("fixture-replay:", 1)[1].split("\n\n", 1)[0]
    for required in (
        "test_round15_connector_contracts.py",
        "test_round15_connector_replay.py",
        "test_round15_http_security.py",
    ):
        assert required in replay_target


def test_isolated_runner_enables_source_suite_and_round15_migration() -> None:
    runner = (ROOT / "scripts/run_isolated_integration.py").read_text(encoding="utf-8")

    assert '"SRBG_RUN_SOURCE_INTEGRATION": "1"' in runner
    assert '"verify_round15_migration.py"' in runner


def test_round15_acceptance_and_changelog_record_honest_scope() -> None:
    acceptance = (
        ROOT / "docs/acceptance/phase-2/round-15-source-center-connectors.md"
    ).read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for required in (
        "状态兼容映射",
        "连接器能力",
        "配置 Schema",
        "覆盖矩阵",
        "RBAC",
        "Fixture",
        "真实外网请求: 0",
    ):
        assert required in acceptance
    assert "Round 15" in changelog
    assert "未批准任何具体来源" in changelog


def test_seed_registry_cannot_self_authorize_and_taxonomy_covers_rail_transit() -> None:
    with (ROOT / "docs/codex-kit/assets/source_registry.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    taxonomy = (ROOT / "docs/codex-kit/assets/taxonomy.yaml").read_text(encoding="utf-8")

    assert len(rows) == 46
    assert all(row["status"] == "CANDIDATE" and row["enabled"] == "false" for row in rows)
    assert "RAIL_TRANSIT" in taxonomy
