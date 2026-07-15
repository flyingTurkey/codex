from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from srbg_api.publication.gate import PublicationGate

POLICY = Path("docs/codex-kit/assets/validation/publication_gate_v5.json")
SCHEMA = Path("docs/codex-kit/assets/validation/publication_evaluation_v5.schema.json")


def _context(*, source_nature: str = "GOVERNMENT_CASE_COLLECTION") -> dict[str, object]:
    return {
        "evaluation_id": "019b0000-0000-7000-8000-000000050001",
        "policy_version": "5.0.0",
        "policy_sha256": sha256(POLICY.read_bytes()).hexdigest(),
        "evaluated_at": "2026-07-14T12:00:00Z",
        "item": {
            "item_id": "019b0000-0000-7000-8000-000000050002",
            "item_type": "DIGITAL_CASE",
            "is_demo": False,
            "publishable": True,
            "regulation_status": "UNKNOWN",
        },
        "server": {
            "source": {
                "status": "ACTIVE",
                "policy_status": "VALID",
                "excerpt_policy_pass": True,
                "attribution_policy_pass": True,
            },
            "document": {
                "is_current": True,
                "lifecycle_status": "ACTIVE",
                "hash_verified": True,
                "url_policy_pass": True,
                "processing_state": "READY",
                "raw_security_status": "CLEAN",
            },
            "evidence_integrity": {
                "claim_count": 6,
                "evidence_count": 6,
                "bidirectional_refs_valid": True,
                "locators_verified": True,
                "excerpts_match_source": True,
                "accepted_critical_claim_coverage_percent": 100,
                "unresolved_conflict_count": 0,
                "minimum_critical_ocr_confidence_bps": 10000,
            },
            "security": {
                "prompt_injection_detected": False,
                "resolution_status": "NONE",
                "resolution_id": None,
            },
            "privacy": {"status": "CLEAR"},
            "review": {
                "risk_level": "R1",
                "decision_status": "APPROVED",
                "decision_id": "019b0000-0000-7000-8000-000000050003",
                "submitted_by": "019b0000-0000-7000-8000-000000050004",
                "decided_by": "019b0000-0000-7000-8000-000000050005",
                "duties_separated": True,
            },
            "pipeline": {
                "candidate_schema_valid": True,
                "semantic_safety_scan_pass": True,
            },
            "round03": {
                "unresolved_relation_candidate_count": 0,
                "unreviewed_regulation_status_candidate_count": 0,
                "unsafe_attachment_count": 0,
                "summary_claim_refs_valid": True,
                "official_status_evidence": False,
                "status_reviewer_decision": False,
            },
            "round05": {
                "source_nature": source_nature,
                "classification_claims_authorized": True,
                "outcome_attribution_valid": True,
                "verified_outcomes_have_independent_evidence": True,
                "maturity_evidence_valid": True,
                "relevance_rule_version": "relevance-v1.0.0",
                "relevance_score": 90,
                "recommended_actions_valid": True,
            },
        },
    }


def test_v5_allows_strict_government_case_into_selected() -> None:
    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(_context(), action="SELECTED")

    assert result.allowed is True


def test_v5_enterprise_case_requires_human_review_before_selected() -> None:
    context = _context(source_nature="ENTERPRISE_SELF_REPORT")
    context["server"]["review"]["decision_status"] = "PENDING"  # type: ignore[index]
    context["server"]["review"]["decision_id"] = None  # type: ignore[index]

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(context, action="SELECTED")

    assert result.allowed is False
    assert "ENTERPRISE_CASE_HUMAN_REVIEW_REQUIRED" in result.reasons


def test_v5_denies_unverified_outcomes_and_unsupported_scale_maturity() -> None:
    context = deepcopy(_context())
    round05 = context["server"]["round05"]  # type: ignore[index]
    round05["verified_outcomes_have_independent_evidence"] = False  # type: ignore[index]
    round05["maturity_evidence_valid"] = False  # type: ignore[index]

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(context, action="PUBLISH")

    assert "DIGITAL_VERIFIED_OUTCOME_EVIDENCE_REQUIRED" in result.reasons
    assert "DIGITAL_MATURITY_EVIDENCE_REQUIRED" in result.reasons


def test_v5_relevance_is_explainable_but_not_a_confidence_threshold() -> None:
    context = deepcopy(_context())
    context["server"]["round05"]["relevance_score"] = 10  # type: ignore[index]

    allowed = PublicationGate.from_files(POLICY, SCHEMA).evaluate(context, action="SELECTED")
    context["server"]["round05"]["relevance_rule_version"] = "confidence-v1"  # type: ignore[index]
    denied = PublicationGate.from_files(POLICY, SCHEMA).evaluate(context, action="SELECTED")

    assert allowed.allowed is True
    assert "DIGITAL_RELEVANCE_RULE_INVALID" in denied.reasons
