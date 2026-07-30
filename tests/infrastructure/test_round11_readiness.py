import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from srbg_api.config import Settings

from scripts.evaluate_readiness import evaluate_gold_manifest, manifest_sha256, validate_readiness

ROOT = Path(__file__).parents[2]


def test_readiness_schema_forbids_production_ready_and_requires_auditable_claims() -> None:
    schema = json.loads(
        (ROOT / "docs/codex-kit/assets/validation/readiness_evidence.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["decision"]["enum"] == [
        "BLOCKED",
        "INTERNAL_PILOT_READY",
        "READY_FOR_INDEPENDENT_ACCEPTANCE",
    ]
    claim = schema["properties"]["claims"]["items"]
    assert set(claim["required"]) >= {
        "code",
        "status",
        "executed_at",
        "executed_by",
        "policy",
        "gold_set",
        "evidence_refs",
    }
    assert claim["properties"]["executed_by"]["properties"]["kind"]["enum"] == [
        "AGENT",
        "CI",
        "HUMAN",
    ]


def test_gold_manifest_uses_real_counts_and_blocks_incomplete_sets() -> None:
    result = evaluate_gold_manifest(ROOT / "tests/gold/v1/manifest.json")
    assert result["passed"] is False
    assert result["counts"] == {
        "documents": 0,
        "duplicate_pairs": 0,
        "event_clusters": 0,
        "claim_evidence_annotations": 0,
        "search_questions": 0,
    }
    assert result["decision"] == "BLOCKED"


def test_manifest_hash_omits_self_hash() -> None:
    first = {"decision": "BLOCKED", "manifest_sha256": "0" * 64}
    second = {"decision": "BLOCKED", "manifest_sha256": "f" * 64}
    assert manifest_sha256(first) == manifest_sha256(second)


def test_current_readiness_package_is_schema_valid_and_honestly_blocked() -> None:
    path = ROOT / "docs/acceptance/round-11-readiness-evidence.json"
    validate_readiness(path)
    package = json.loads(path.read_text(encoding="utf-8"))
    assert package["decision"] == "BLOCKED"
    assert package["generated_by_ci"] is False
    assert any(claim["status"] == "INSUFFICIENT_EVIDENCE" for claim in package["claims"])
    assert {claim["executed_by"]["kind"] for claim in package["claims"]} == {"AGENT"}
    assert all(claim["executed_by"]["id"] != "HUMAN" for claim in package["claims"])


def test_ready_decision_is_rejected_when_any_claim_is_not_passed(tmp_path: Path) -> None:
    source = ROOT / "docs/acceptance/round-11-readiness-evidence.json"
    package = json.loads(source.read_text(encoding="utf-8"))
    package["decision"] = "INTERNAL_PILOT_READY"
    package["manifest_sha256"] = manifest_sha256(package)
    candidate = tmp_path / "readiness.json"
    candidate.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(ValueError, match="READY decision requires every claim to pass"):
        validate_readiness(candidate)


def test_readiness_rejects_missing_or_mismatched_evidence(tmp_path: Path) -> None:
    source = ROOT / "docs/acceptance/round-11-readiness-evidence.json"
    package = json.loads(source.read_text(encoding="utf-8"))
    package["claims"][0]["evidence_refs"][0]["sha256"] = "0" * 64
    package["manifest_sha256"] = manifest_sha256(package)
    candidate = tmp_path / "readiness.json"
    candidate.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence SHA-256 mismatch"):
        validate_readiness(candidate)


def test_round11_required_checks_and_make_targets_are_declared() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    risk_matrix = (ROOT / "scripts/ci/risk_matrix.py").read_text(encoding="utf-8")
    assert "make check-pr" in workflow
    publication_gates = risk_matrix.split('"publication": (', 1)[1].split("),", 1)[0]
    assert '"publication-adversarial"' in publication_gates
    assert '"phase3-trustworthy-event-test"' in publication_gates
    assert '"dependency": ("security-check",)' in risk_matrix
    for target in (
        "round11-test",
        "observability-test",
        "golden-replay",
        "load-test",
        "recovery-drill",
        "runbook-test",
        "round11-evidence-test",
        "readiness-evidence",
    ):
        assert f"{target}:" in makefile
    round11_recipe = makefile.split("round11-test:", 1)[1].split("\n\n", 1)[0]
    assert "apps/api/tests/test_round11_oidc_auth.py" in round11_recipe
    assert "apps/api/tests/test_round09_publication_paths.py" in round11_recipe
    assert "apps/api/tests/test_publication_rbac_integration.py" in round11_recipe
    assert "scripts/audit_publication_paths.py" in round11_recipe


def test_production_configuration_fails_closed_without_operations_dependencies() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", cursor_signing_key="x" * 64)


def test_round11_migration_declares_authoritative_replay_and_pilot_facts() -> None:
    migration = (ROOT / "apps/api/migrations/versions/0012_operations_readiness.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision = "0011_feed_search_daily"' in migration
    for table in (
        "failed_task",
        "replay_request",
        "usage_metric_bucket",
        "item_feedback",
        "recovery_exercise",
    ):
        assert f'"{table}"' in migration
