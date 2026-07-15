from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from srbg_api.publication.gate import PublicationGate

POLICY = Path("docs/codex-kit/assets/validation/publication_gate_v6.json")
SCHEMA = Path("docs/codex-kit/assets/validation/publication_evaluation_v6.schema.json")


def _context() -> dict[str, object]:
    return {
        "evaluation_id": "019b0000-0000-7000-8000-000000060001",
        "policy_version": "6.0.0",
        "policy_sha256": sha256(POLICY.read_bytes()).hexdigest(),
        "evaluated_at": "2026-07-15T12:00:00Z",
        "item": {
            "item_id": "019b0000-0000-7000-8000-000000060002",
            "item_type": "JOURNAL_PAPER",
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
                "claim_count": 5,
                "evidence_count": 5,
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
                "decision_id": "019b0000-0000-7000-8000-000000060003",
                "submitted_by": "019b0000-0000-7000-8000-000000060004",
                "decided_by": "019b0000-0000-7000-8000-000000060005",
                "duties_separated": True,
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
            "round06": {
                "identity_resolved": True,
                "access_level": "METADATA_ONLY",
                "access_policy_valid": True,
                "abstract_permitted": False,
                "abstract_present": False,
                "fulltext_storage_count": 0,
                "fulltext_link_licensed": False,
                "research_claim_refs_valid": True,
                "maturity_evidence_valid": True,
                "unreviewed_update_relation_count": 0,
                "relation_status": "CURRENT",
            },
        },
    }


def test_v6_allows_metadata_only_paper_without_abstract_or_fulltext() -> None:
    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(_context(), action="PUBLISH")
    assert result.allowed is True


def test_v6_denies_unlicensed_abstract_and_any_fulltext_storage() -> None:
    context = deepcopy(_context())
    round06 = context["server"]["round06"]  # type: ignore[index]
    round06["abstract_present"] = True  # type: ignore[index]
    round06["fulltext_storage_count"] = 1  # type: ignore[index]
    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(context, action="PUBLISH")
    assert "PAPER_ABSTRACT_LICENCE_REQUIRED" in result.reasons
    assert "PAPER_FULLTEXT_STORAGE_FORBIDDEN" in result.reasons


def test_v6_denies_unreviewed_retraction_and_unsupported_maturity() -> None:
    context = deepcopy(_context())
    round06 = context["server"]["round06"]  # type: ignore[index]
    round06["unreviewed_update_relation_count"] = 1  # type: ignore[index]
    round06["maturity_evidence_valid"] = False  # type: ignore[index]
    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(context, action="PUBLISH")
    assert "PAPER_UPDATE_RELATION_UNREVIEWED" in result.reasons
    assert "PAPER_MATURITY_EVIDENCE_REQUIRED" in result.reasons
