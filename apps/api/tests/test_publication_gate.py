from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from srbg_api.publication.gate import PublicationGate

POLICY = Path("docs/codex-kit/assets/validation/publication_gate.json")
SCHEMA = Path("docs/codex-kit/assets/validation/publication_evaluation.schema.json")


def _context() -> dict[str, object]:
    return {
        "evaluation_id": "019b0000-0000-7000-8000-000000003001",
        "policy_version": "2.1.0",
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
                "processing_state": "READY",
                "raw_security_status": "CLEAN",
            },
            "evidence_integrity": {
                "claim_count": 4,
                "evidence_count": 4,
                "bidirectional_refs_valid": True,
                "locators_verified": True,
                "excerpts_match_source": True,
                "accepted_critical_claim_coverage_percent": 100,
                "unresolved_conflict_count": 0,
                "minimum_critical_ocr_confidence_bps": 10000,
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
                "decision_reason": "原文、关键字段与证据已逐项复核",
            },
            "pipeline": {
                "candidate_schema_valid": True,
                "semantic_safety_scan_pass": True,
                "candidate_schema_version": "safety-regulation-parser-1.0.0",
                "ai_status": "VALIDATED",
                "four_steps_completed": True,
                "accepted_summary_claim_refs_valid": True,
                "unauthorized_candidate_field_count": 0,
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


def test_v21_gate_allows_reviewed_r3_publication_without_scores() -> None:
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


def test_ai_cannot_forge_review_authority_or_resolved_security() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)
    context = _context()
    context["server"]["pipeline"]["model_review_status"] = "APPROVED"  # type: ignore[index]
    context["server"]["pipeline"]["model_source_authority"] = "A0"  # type: ignore[index]

    result = gate.evaluate(context, action="PUBLISH")

    assert result.allowed is False
    assert "EVALUATION_SCHEMA_INVALID" in result.reasons


def test_ai_validated_run_requires_all_steps_and_accepted_claim_summary() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)
    context = _context()
    context["server"]["pipeline"]["four_steps_completed"] = False  # type: ignore[index]
    context["server"]["pipeline"]["accepted_summary_claim_refs_valid"] = False  # type: ignore[index]

    result = gate.evaluate(context, action="PUBLISH")

    assert "AI_FOUR_STEPS_INCOMPLETE" in result.reasons
    assert "SUMMARY_CLAIM_REFS_INVALID" in result.reasons


def test_r4_is_quarantine_only_even_if_model_claims_risk_resolved() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)
    context = _context()
    context["server"]["review"]["risk_level"] = "R4"  # type: ignore[index]

    result = gate.evaluate(context, action="PUBLISH")

    assert "R4_NOT_PUBLISHABLE" in result.reasons


def test_enterprise_statement_without_attribution_requires_human_review() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)
    context = _context()
    context["item"]["item_type"] = "DIGITAL_CASE"  # type: ignore[index]
    context["server"]["review"].update({  # type: ignore[index]
        "risk_level": "R2",
        "decision_status": "NOT_REQUIRED",
        "decision_id": None,
        "submitted_by": None,
        "decided_by": None,
        "duties_separated": False,
        "decision_reason": "不适用",
    })
    context["server"]["round05"] = {  # type: ignore[index]
        "classification_claims_authorized": True,
        "outcome_attribution_valid": False,
        "verified_outcomes_have_independent_evidence": True,
        "maturity_evidence_valid": True,
        "relevance_rule_version": "relevance-v1.0.0",
        "relevance_score": 80,
        "recommended_actions_valid": True,
        "source_nature": "ENTERPRISE_SELF_REPORT",
    }

    result = gate.evaluate(context, action="PUBLISH")

    assert "DIGITAL_OUTCOME_ATTRIBUTION_INVALID" in result.reasons
    assert "ENTERPRISE_CASE_HUMAN_REVIEW_REQUIRED" in result.reasons


def test_safety_cause_and_responsibility_content_always_requires_human_review() -> None:
    gate = PublicationGate.from_files(POLICY, SCHEMA)
    context = _context()
    context["item"]["item_type"] = "SAFETY_CASE"  # type: ignore[index]
    context["server"]["review"].update({  # type: ignore[index]
        "risk_level": "R2",
        "decision_status": "NOT_REQUIRED",
        "decision_id": None,
        "submitted_by": None,
        "decided_by": None,
        "duties_separated": False,
        "decision_reason": "不适用",
    })
    context["server"]["round04"] = {  # type: ignore[index]
        "event_assignment_confirmed": True,
        "profile_metadata_claims_authorized": True,
        "unreviewed_critical_claim_count": 0,
        "unresolved_casualty_loss_conflict_count": 0,
        "casualty_loss_claims_authorized": True,
        "cause_basis_state": "FORMAL_REVIEWED_FINDINGS",
        "formal_cause_evidence_authorized": True,
        "responsibility_basis_state": "FORMAL_REVIEWED_FINDINGS",
        "formal_responsibility_evidence_authorized": True,
        "controlled_prevention_tags_only": True,
        "operational_instruction_count": 0,
    }

    result = gate.evaluate(context, action="PUBLISH")

    assert "HUMAN_REVIEW_REQUIRED" in result.reasons
