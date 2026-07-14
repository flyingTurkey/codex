from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from srbg_api.publication.gate import PublicationGate

POLICY = Path("docs/codex-kit/assets/validation/publication_gate_v3.json")
SCHEMA = Path("docs/codex-kit/assets/validation/publication_evaluation_v3.schema.json")


def _context() -> dict[str, object]:
    return {
        "evaluation_id": "019b0000-0000-7000-8000-000000008001",
        "policy_version": "3.0.0",
        "policy_sha256": sha256(POLICY.read_bytes()).hexdigest(),
        "evaluated_at": "2026-07-14T02:00:00Z",
        "item": {
            "item_id": "019b0000-0000-7000-8000-000000008002",
            "item_type": "SAFETY_REGULATION",
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
                "minimum_critical_ocr_confidence_bps": 9600,
            },
            "security": {
                "prompt_injection_detected": False,
                "resolution_status": "NONE",
                "resolution_id": None,
            },
            "privacy": {"status": "CLEAR"},
            "review": {
                "risk_level": "R3",
                "decision_status": "APPROVED",
                "decision_id": "019b0000-0000-7000-8000-000000008003",
                "submitted_by": "019b0000-0000-7000-8000-000000008004",
                "decided_by": "019b0000-0000-7000-8000-000000008005",
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
        },
    }


def test_v3_allows_ready_clean_high_confidence_reviewed_pdf() -> None:
    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        _context(), action="PUBLISH"
    )

    assert result.allowed is True


def test_v3_denies_non_ready_quarantined_or_low_confidence_critical_ocr() -> None:
    context = deepcopy(_context())
    context["server"]["document"]["processing_state"] = "PARSING"  # type: ignore[index]
    context["server"]["document"]["raw_security_status"] = "QUARANTINED"  # type: ignore[index]
    context["server"]["evidence_integrity"][  # type: ignore[index]
        "minimum_critical_ocr_confidence_bps"
    ] = 9400

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert {
        "DOCUMENT_NOT_READY",
        "RAW_OBJECT_NOT_CLEAN",
        "OCR_CRITICAL_CONFIDENCE_TOO_LOW",
    }.issubset(result.reasons)


def test_v3_denies_a_current_version_with_quarantined_attachments() -> None:
    context = deepcopy(_context())
    context["server"]["round03"]["unsafe_attachment_count"] = 1  # type: ignore[index]

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert result.allowed is False
    assert "ATTACHMENT_NOT_CLEAN" in result.reasons


def test_v3_non_unknown_status_requires_official_evidence_and_reviewer_decision() -> None:
    context = deepcopy(_context())
    context["item"]["regulation_status"] = "REPEALED"  # type: ignore[index]

    denied = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )
    context["server"]["round03"]["official_status_evidence"] = True  # type: ignore[index]
    context["server"]["round03"]["status_reviewer_decision"] = True  # type: ignore[index]
    allowed = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert "LEGAL_EFFECT_NOT_AUTHORIZED" in denied.reasons
    assert allowed.allowed is True
