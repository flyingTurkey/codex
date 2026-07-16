import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE = ROOT / "docs/acceptance/phase-2/round-17-20-source-pilot.md"
READINESS = ROOT / "docs/acceptance/phase-2/round-17-readiness.json"


def test_round17_make_targets_are_separate_and_eval_is_not_a_ci_dependency() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    test_recipe = makefile.split("phase2-round17-test:", 1)[1].split(
        "phase2-round17-eval:", 1
    )[0]

    assert "phase2-round17-test:" in makefile
    assert "tests/infrastructure/test_round17_eval.py" in makefile
    assert "apps/api/tests/test_round17_governance.py" in makefile
    assert "apps/api/tests/test_round17_governance_migration.py" in makefile
    assert "apps/worker/tests/test_round17_worker.py" in makefile
    assert "apps/api/tests/test_round17_operations_service.py" in makefile
    assert "apps/api/tests/test_round17_replay_origin.py" in makefile
    assert "tests/infrastructure/test_round17_observability.py" in makefile
    assert "tests/infrastructure/test_round17_readiness_assets.py" in makefile
    assert "apps/api/tests/test_round14_event_unification.py" in test_recipe
    assert "apps/api/tests/test_round14_identity_changes.py" in test_recipe
    assert "apps/api/tests/test_round13_access_boundary.py" in test_recipe
    assert "apps/api/tests/test_round13_projection_permissions.py" in test_recipe
    assert "apps/api/tests/test_round09_publication_paths.py" in test_recipe
    assert "apps/api/tests/test_round16_replay_integration.py" in test_recipe
    assert "apps/api/tests/test_round15_http_security.py" in test_recipe
    assert "python scripts/audit_publication_paths.py" in test_recipe
    assert "phase2-round17-eval:" in makefile
    assert "python scripts/round17_eval.py" not in test_recipe
    eval_recipe = makefile.split("phase2-round17-eval:", 1)[1].split("\n\n", 1)[0]
    assert "round17_eval.py" in eval_recipe
    assert "curl" not in eval_recipe
    assert "http://" not in eval_recipe
    assert "https://" not in eval_recipe


def test_makefiles_remain_byte_for_byte_synchronized() -> None:
    assert (ROOT / "Makefile").read_bytes() == (ROOT / "makefile").read_bytes()


def test_round17_eval_source_has_no_network_client_imports() -> None:
    source = (ROOT / "scripts/round17_eval.py").read_text(encoding="utf-8")

    forbidden = ("requests", "httpx", "urllib", "socket", "playwright", "selenium")
    assert all(f"import {name}" not in source for name in forbidden)
    assert all(f"from {name}" not in source for name in forbidden)


def test_round17_acceptance_is_machine_readable_and_honestly_blocked() -> None:
    record = json.loads(READINESS.read_text(encoding="utf-8"))

    assert record["schema_version"] == "1.0.0"
    assert record["round"] == 17
    assert record["decision"] == "BLOCKED"
    assert record["observation_window"]["state"] == "NOT_STARTED"
    assert record["observation_window"]["started_at"] is None
    assert record["real_evidence"]["authority"] is False
    assert record["real_evidence"]["evidence_manifest_present"] is False
    assert record["real_evidence"]["gold_manifest_present"] is False

    people = {person["display_name"]: person for person in record["people"]}
    assert people["LEO"]["confirmed_role"] == "SOLE_APPROVER"
    assert people["yinzi"]["confirmed_role"] == "OPERATIONS_ADMIN"
    assert people["baixuejiao"]["confirmed_role"] == "BUSINESS_STANDARD_B"

    sources = record["sources"]
    assert len(sources) == len({source["source_code"] for source in sources}) == 20
    assert all(source["pilot_state"] == "PENDING_HUMAN_ADMISSION" for source in sources)
    assert all(source["real_chain_evidence"] == "ABSENT" for source in sources)

    blocker_codes = {blocker["code"] for blocker in record["blockers"]}
    assert {
        "SOURCE_ROSTER_APPROVAL_MISSING",
        "SOURCE_COMPLIANCE_APPROVALS_MISSING",
        "SOURCE_ACCESS_SLO_APPROVALS_MISSING",
        "OIDC_STAFF_BINDINGS_MISSING",
        "LEO_ACTOR_ATTESTATION_MISSING",
        "GOLD_LABELS_MISSING",
        "METRICS_APPROVAL_MISSING",
        "OBSERVATION_WINDOW_NOT_CONFIRMED",
        "REAL_EVIDENCE_EXPORT_MISSING",
    }.issubset(blocker_codes)

    acceptance = ACCEPTANCE.read_text(encoding="utf-8")
    assert "需求—实现—测试—证据矩阵" in acceptance
    assert "第17轮未完成/BLOCKED" in acceptance
    assert "第17轮验收通过，20来源真实试运行门禁成立，可以进入第18轮。" not in acceptance  # noqa: RUF001
