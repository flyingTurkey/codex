from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from srbg_api.publication.gate import PublicationGate

POLICY = Path("docs/codex-kit/assets/validation/publication_gate.json")
SCHEMA = Path("docs/codex-kit/assets/validation/publication_evaluation.schema.json")


def _context() -> dict[str, object]:
    return {
        "evaluation_id": "019b0000-0000-7000-8000-000000003001",
        "policy_version": "2.0.0",
        "policy_sha256": sha256(POLICY.read_bytes()).hexdigest(),
        "evaluated_at": "2026-07-14T02:00:00Z",
        "item": {
            "item_id": "019b0000-0000-7000-8000-000000003002",
            "item_type": "SAFETY_REGULATION",
            "is_demo": False,
            "publishable": True,
        },
        "server": {
            "source": {
                "source_id": "019b0000-0000-7000-8000-000000003003",
                "status": "ACTIVE",
                "authority_level": "A1",
                "policy_version": "fixture-v1",
                "policy_status": "VALID",
                "excerpt_policy_pass": True,
                "attribution_policy_pass": True,
            },
            "document": {
                "document_id": "019b0000-0000-7000-8000-000000003004",
                "document_version_id": "019b0000-0000-7000-8000-000000003005",
                "content_sha256": "b" * 64,
                "is_current": True,
                "lifecycle_status": "ACTIVE",
                "hash_verified": True,
                "url_policy_pass": True,
            },
            "evidence_integrity": {
                "claim_count": 4,
                "evidence_count": 4,
                "bidirectional_refs_valid": True,
                "locators_verified": True,
                "excerpts_match_source": True,
                "accepted_critical_claim_coverage_percent": 100,
                "unresolved_conflict_count": 0,
                "validator_version": "1.0.0",
            },
            "security": {
                "prompt_injection_detected": False,
                "resolution_status": "NONE",
                "resolution_id": None,
                "scanner_version": "rules-1.0.0",
                "input_sha256": "b" * 64,
            },
            "privacy": {
                "status": "CLEAR",
                "scanner_version": "rules-1.0.0",
                "reputational_risk_reviewed": True,
            },
            "review": {
                "risk_level": "R3",
                "required": True,
                "decision_status": "APPROVED",
                "decision_id": "019b0000-0000-7000-8000-000000003006",
                "submitted_by": "019b0000-0000-7000-8000-000000003007",
                "decided_by": "019b0000-0000-7000-8000-000000003008",
                "duties_separated": True,
            },
            "pipeline": {
                "candidate_schema_valid": True,
                "semantic_safety_scan_pass": True,
                "candidate_schema_version": "safety-regulation-parser-1.0.0",
            },
        },
    }


def test_v2_gate_allows_reviewed_r3_publication_without_scores() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)

    result = gate.evaluate(_context(), action="PUBLISH")

    assert result.allowed is True
    assert result.decision == "PUBLISH"
    assert result.reasons == ()


def test_missing_scores_default_deny_selected_feed() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)

    result = gate.evaluate(_context(), action="SELECTED")

    assert result.allowed is False
    assert result.decision == "DENY"
    assert "SELECTED_SCORES_REQUIRED" in result.reasons


def test_authoritative_source_and_duties_failures_override_candidate_claims() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)
    context = deepcopy(_context())
    context["server"]["source"]["status"] = "CANDIDATE"  # type: ignore[index]
    context["server"]["review"]["duties_separated"] = False  # type: ignore[index]

    result = gate.evaluate(context, action="PUBLISH")

    assert result.allowed is False
    assert "SOURCE_NOT_ACTIVE" in result.reasons
    assert "DUTIES_NOT_SEPARATED" in result.reasons


def test_round02_refuses_non_unknown_regulation_status() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)
    context = _context()
    context["item"]["regulation_status"] = "EFFECTIVE"  # type: ignore[index]

    result = gate.evaluate(context, action="PUBLISH")

    assert result.allowed is False
    assert "LEGAL_EFFECT_NOT_AUTHORIZED" in result.reasons
