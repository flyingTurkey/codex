from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from srbg_api.publication.gate import PublicationGate

POLICY = Path("docs/codex-kit/assets/validation/publication_gate_v7.json")
SCHEMA = Path("docs/codex-kit/assets/validation/publication_evaluation_v7.schema.json")


def _context(item_type: str = "LOW_ALTITUDE_EQUIPMENT") -> dict[str, object]:
    return {
        "evaluation_id": "019b0000-0000-7000-8000-000000070001",
        "policy_version": "7.0.0",
        "policy_sha256": sha256(POLICY.read_bytes()).hexdigest(),
        "evaluated_at": "2026-07-15T12:00:00Z",
        "item": {
            "item_id": "019b0000-0000-7000-8000-000000070002",
            "item_type": item_type,
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
                "claim_count": 2,
                "evidence_count": 2,
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
                "risk_level": "R2",
                "decision_status": "PENDING",
                "decision_id": None,
                "submitted_by": "019b0000-0000-7000-8000-000000070003",
                "decided_by": None,
                "duties_separated": False,
            },
            "pipeline": {"candidate_schema_valid": True, "semantic_safety_scan_pass": True},
            "round03": {
                "unresolved_relation_candidate_count": 0,
                "unreviewed_regulation_status_candidate_count": 0,
                "unsafe_attachment_count": 0,
                "summary_claim_refs_valid": True,
                "official_status_evidence": False,
                "status_reviewer_decision": False,
            },
            "round07": {
                "identity_safe": True,
                "capability_groups_separated": True,
                "verified_capabilities_have_independent_evidence": True,
                "promotional_claims_vendor_attributed": True,
                "procurement_conclusion_count": 0,
                "vendor_image_download_count": 0,
                "permit_status": "UNKNOWN",
                "permit_evidence_authorized": False,
            },
        },
    }


def test_v7_allows_r2_product_in_full_feed_with_unknown_low_altitude_permit() -> None:
    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(_context(), action="PUBLISH")
    assert result.allowed is True


def test_v7_denies_vendor_claim_promoted_to_verified_and_procurement_conclusion() -> None:
    context = deepcopy(_context())
    round07 = context["server"]["round07"]  # type: ignore[index]
    round07["verified_capabilities_have_independent_evidence"] = False  # type: ignore[index]
    round07["procurement_conclusion_count"] = 1  # type: ignore[index]
    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(context, action="PUBLISH")
    assert "PRODUCT_VERIFIED_CAPABILITY_EVIDENCE_REQUIRED" in result.reasons
    assert "PRODUCT_PROCUREMENT_CONCLUSION_FORBIDDEN" in result.reasons


def test_v7_denies_claimed_permit_without_authorized_evidence_and_auto_selection() -> None:
    context = deepcopy(_context())
    round07 = context["server"]["round07"]  # type: ignore[index]
    round07["permit_status"] = "VERIFIED"  # type: ignore[index]
    publish = PublicationGate.from_files(POLICY, SCHEMA).evaluate(context, action="PUBLISH")
    selected = PublicationGate.from_files(POLICY, SCHEMA).evaluate(_context(), action="SELECTED")
    assert "PRODUCT_PERMIT_EVIDENCE_REQUIRED" in publish.reasons
    assert "PRODUCT_SELECTED_HUMAN_REVIEW_REQUIRED" in selected.reasons
