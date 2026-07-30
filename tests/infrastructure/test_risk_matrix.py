from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ci.risk_matrix import (  # noqa: E402
    ALL_RISK_GATES,
    ChangeSet,
    classify_changes,
    collect_changes,
    plan_for_mode,
    resolve_base_ref,
)


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", *arguments],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.mark.parametrize(
    ("path", "category"),
    [
        ("packages/contracts/src/index.ts", "contract"),
        ("tests/contract/test_public_api.py", "contract"),
        ("apps/api/alembic/versions/9999_example.py", "migration"),
        ("infra/compose/compose.yaml", "docker"),
        ("pnpm-lock.yaml", "dependency"),
        ("apps/api/src/srbg_api/acquisition/http.py", "acquisition"),
        ("apps/api/src/srbg_api/document_vault/service.py", "content"),
        ("apps/api/src/srbg_api/ai_pipeline/gateway.py", "ai"),
        ("apps/api/src/srbg_api/publication/service.py", "publication"),
        ("apps/api/src/srbg_api/document_vault/security.py", "security"),
        ("apps/api/tests/test_upload_security.py", "security"),
        ("apps/web/pages/index.vue", "frontend"),
        (".github/workflows/ci.yml", "orchestration"),
    ],
)
def test_each_high_risk_path_has_an_independent_category(path: str, category: str) -> None:
    result = classify_changes(ChangeSet.from_paths([path]))

    assert category in result.categories


def test_change_collection_includes_branch_staged_unstaged_and_untracked(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "config", "user.name", "Risk Matrix Test")

    tracked = repository / "README.md"
    tracked.write_text("baseline\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "baseline")
    base = _git(repository, "rev-parse", "HEAD")

    branch_path = repository / "apps/api/src/srbg_api/publication/service.py"
    branch_path.parent.mkdir(parents=True)
    branch_path.write_text("branch\n", encoding="utf-8")
    _git(repository, "add", branch_path.relative_to(repository).as_posix())
    _git(repository, "commit", "-m", "branch change")

    staged_path = repository / "packages/contracts/schema.json"
    staged_path.parent.mkdir(parents=True)
    staged_path.write_text("{}\n", encoding="utf-8")
    _git(repository, "add", staged_path.relative_to(repository).as_posix())

    tracked.write_text("unstaged\n", encoding="utf-8")
    untracked_path = repository / "unexpected/new.kind"
    untracked_path.parent.mkdir(parents=True)
    untracked_path.write_text("untracked\n", encoding="utf-8")

    changes = collect_changes(repository, base_ref=base)

    assert changes.sources["apps/api/src/srbg_api/publication/service.py"] == frozenset(
        {"branch"}
    )
    assert changes.sources["packages/contracts/schema.json"] == frozenset({"staged"})
    assert changes.sources["README.md"] == frozenset({"unstaged"})
    assert changes.sources["unexpected/new.kind"] == frozenset({"untracked"})


def test_unknown_paths_fail_closed_to_every_risk_gate() -> None:
    result = classify_changes(ChangeSet.from_paths(["unexpected/new.kind"]))
    plan = plan_for_mode("pr", result)

    assert result.unknown_paths == ("unexpected/new.kind",)
    assert set(ALL_RISK_GATES) <= set(plan.gates)


@pytest.mark.parametrize(
    ("path", "expected_gates"),
    [
        (
            "apps/api/src/srbg_api/document_vault/service.py",
            {"fixture-replay", "isolated-integration-test"},
        ),
        (
            "apps/api/src/srbg_api/document_vault/security.py",
            {"fixture-replay", "security-check"},
        ),
        (
            ".github/workflows/ci.yml",
            {"orchestration-test", "compose-config"},
        ),
        (
            "infra/compose/compose.yaml",
            {"orchestration-test", "compose-config", "compose-smoke"},
        ),
    ],
)
def test_boundary_and_orchestration_risks_select_the_required_gates(
    path: str,
    expected_gates: set[str],
) -> None:
    result = classify_changes(ChangeSet.from_paths([path]))

    assert expected_gates <= set(plan_for_mode("pr", result).gates)


def test_security_scan_has_one_authoritative_gate_even_for_overlapping_risks() -> None:
    result = classify_changes(
        ChangeSet.from_paths(
            [
                "uv.lock",
                "apps/api/src/srbg_api/document_vault/security.py",
            ]
        )
    )

    assert plan_for_mode("pr", result).gates.count("security-check") == 1


def test_fast_plan_never_contains_docker_browser_network_or_live_gates() -> None:
    result = classify_changes(
        ChangeSet.from_paths(
            [
                "infra/compose/compose.yaml",
                "apps/web/pages/index.vue",
                "uv.lock",
                "unexpected/new.kind",
            ]
        )
    )

    plan = plan_for_mode("fast", result)

    assert not (
        {
            "compose-smoke",
            "web-e2e",
            "web-a11y",
            "security-check",
            "live-acceptance",
        }
        & set(plan.gates)
    )
    assert {
        "lint",
        "typecheck",
        "python-unit-test",
        "web-unit-test",
        "contract-fast",
        "frontend-fast",
    } <= set(plan.gates)


def test_default_base_ref_does_not_collapse_to_head_and_lose_committed_changes(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "config", "user.name", "Risk Matrix Test")

    baseline = repository / "README.md"
    baseline.write_text("baseline\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "baseline")
    _git(repository, "branch", "baseline")
    _git(repository, "checkout", "-b", "phase")

    first = repository / "docs/first.md"
    first.parent.mkdir()
    first.write_text("first\n", encoding="utf-8")
    _git(repository, "add", "docs/first.md")
    _git(repository, "commit", "-m", "first change")

    second = repository / "scripts/second.py"
    second.parent.mkdir()
    second.write_text("SECOND = True\n", encoding="utf-8")
    _git(repository, "add", "scripts/second.py")
    _git(repository, "commit", "-m", "second change")

    base_ref = resolve_base_ref(repository, explicit=None)
    changes = collect_changes(repository, base_ref=None)

    assert base_ref != "HEAD"
    assert {"docs/first.md", "scripts/second.py"} <= set(changes.paths)


@pytest.mark.parametrize(
    ("path", "expected_gate"),
    [
        ("tests/integration/new_flow.py", "isolated-integration-test"),
        ("infra/monitoring/prometheus.yml", "compose-config"),
    ],
)
def test_integration_and_infrastructure_paths_trigger_orchestration_gates(
    path: str,
    expected_gate: str,
) -> None:
    result = classify_changes(ChangeSet.from_paths([path]))

    assert expected_gate in plan_for_mode("pr", result).gates


@pytest.mark.parametrize(
    "path",
    [
        "apps/api/migrations/versions/0055_phase3_trustworthy_event.py",
        "apps/api/src/srbg_api/ai_pipeline/gateway.py",
        "apps/api/src/srbg_api/publication/service.py",
        "tests/integration/t41_autonomous_content_integration.py",
    ],
)
def test_phase3_authority_changes_trigger_trustworthy_event_slice(
    path: str,
) -> None:
    result = classify_changes(ChangeSet.from_paths([path]))

    assert "phase3-trustworthy-event-test" in plan_for_mode("pr", result).gates


def test_phase3_trustworthy_event_target_uses_isolated_verifier_and_business_test() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("phase3-trustworthy-event-test:", 1)[1].split(
        "\n\n", 1
    )[0]

    assert "scripts/run_isolated_integration.py" in target
    assert "verify_phase3_trustworthy_event_migration.py" in target
    assert "test_phase3_minimal_trustworthy_event_slice" in target
    for target_name in (
        "isolated-integration-test",
        "autonomous-content-integration-test",
    ):
        shared_target = makefile.split(f"{target_name}:", 1)[1].split("\n\n", 1)[0]
        assert "verify_phase3_trustworthy_event_migration.py" in shared_target


@pytest.mark.parametrize(
    ("path", "expected_category"),
    [
        ("scripts/run_isolated_integration.py", "integration"),
        ("scripts/verify_phase3_trustworthy_event_migration.py", "migration"),
    ],
)
def test_isolated_gate_scripts_are_risk_classified(
    path: str,
    expected_category: str,
) -> None:
    result = classify_changes(ChangeSet.from_paths([path]))

    assert result.unknown_paths == ()
    assert expected_category in result.categories
    assert "phase3-trustworthy-event-test" in plan_for_mode("pr", result).gates


def test_classifier_cli_emits_machine_readable_sources_and_gates() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ci/risk_matrix.py",
            "classify-paths",
            "--mode",
            "pr",
            "apps/api/src/srbg_api/publication/service.py",
            "apps/web/pages/index.vue",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["categories"] == ["frontend", "publication", "python"]
    assert "publication-adversarial" in payload["gates"]
    assert "web-e2e" in payload["gates"]


def test_makefile_and_ci_expose_the_four_stable_entries_without_duplicate_full_installs() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    for target in ("check-fast", "check-pr", "check-release", "check-live"):
        assert f"{target}:" in makefile

    assert workflow.count("uv sync --frozen --all-packages") == 1
    assert workflow.count("pnpm install --frozen-lockfile") == 1
    assert "make check-pr" in workflow
    assert workflow.count("make security-check") == 0
    assert "BASE_REF ?= HEAD" not in makefile
    assert 'BASE_REF="${{ steps.base.outputs.base_ref }}"' in workflow
    assert "> risk-plan.json" not in workflow
    assert '"$RUNNER_TEMP/risk-plan.json"' in workflow


def test_ci_frontend_gates_prepare_and_always_clean_the_ephemeral_docker_root() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    docker_gate_block = workflow.split("docker_gates = {", 1)[1].split("}", 1)[0]
    assert '"web-e2e"' in docker_gate_block
    assert '"web-a11y"' in docker_gate_block
    assert "if: always() && steps.risk.outputs.docker == 'true'" in workflow
