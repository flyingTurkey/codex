from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from srbg_api.publication.gate import PublicationGate

POLICY = Path("docs/codex-kit/assets/validation/publication_gate_v4.json")
SCHEMA = Path("docs/codex-kit/assets/validation/publication_evaluation_v4.schema.json")


def _context() -> dict[str, object]:
    return {
        "evaluation_id": "019b0000-0000-7000-8000-000000040001",
        "policy_version": "4.0.0",
        "policy_sha256": sha256(POLICY.read_bytes()).hexdigest(),
        "evaluated_at": "2026-07-14T12:00:00Z",
        "item": {
            "item_id": "019b0000-0000-7000-8000-000000040002",
            "item_type": "SAFETY_CASE",
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
                "claim_count": 4,
                "evidence_count": 4,
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
                "risk_level": "R3",
                "decision_status": "APPROVED",
                "decision_id": "019b0000-0000-7000-8000-000000040003",
                "submitted_by": "019b0000-0000-7000-8000-000000040004",
                "decided_by": "019b0000-0000-7000-8000-000000040005",
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
            "round04": {
                "event_assignment_confirmed": True,
                "profile_metadata_claims_authorized": True,
                "unreviewed_critical_claim_count": 0,
                "unresolved_casualty_loss_conflict_count": 0,
                "casualty_loss_claims_authorized": True,
                "cause_basis_state": "FORMAL_REVIEWED_FINDINGS",
                "responsibility_basis_state": "NO_FORMAL_BASIS",
                "formal_cause_evidence_authorized": True,
                "formal_responsibility_evidence_authorized": False,
                "controlled_prevention_tags_only": True,
                "operational_instruction_count": 0,
            },
        },
    }


def test_v4_allows_a_reviewed_r3_safety_case_with_formal_causes() -> None:
    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        _context(), action="PUBLISH"
    )

    assert result.allowed is True


def test_v4_denies_r4_and_unreviewed_or_conflicting_critical_fields() -> None:
    context = deepcopy(_context())
    context["server"]["review"]["risk_level"] = "R4"  # type: ignore[index]
    context["server"]["round04"]["unreviewed_critical_claim_count"] = 2  # type: ignore[index]
    context["server"]["round04"][  # type: ignore[index]
        "unresolved_casualty_loss_conflict_count"
    ] = 1

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert {
        "R4_NOT_PUBLISHABLE",
        "SAFETY_CASE_CRITICAL_CLAIM_UNREVIEWED",
        "SAFETY_CASE_CASUALTY_LOSS_CONFLICT",
    }.issubset(result.reasons)


def test_v4_denies_causes_or_responsibility_without_formal_authorized_evidence() -> None:
    context = deepcopy(_context())
    context["server"]["round04"]["formal_cause_evidence_authorized"] = False  # type: ignore[index]
    context["server"]["round04"][  # type: ignore[index]
        "responsibility_basis_state"
    ] = "FORMAL_REVIEWED_FINDINGS"

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert "SAFETY_CASE_CAUSE_NOT_FORMALLY_AUTHORIZED" in result.reasons
    assert "SAFETY_CASE_RESPONSIBILITY_NOT_FORMALLY_AUTHORIZED" in result.reasons


def test_v4_distinguishes_no_formal_basis_from_reviewed_empty_findings() -> None:
    no_basis = deepcopy(_context())
    reviewed_empty = deepcopy(_context())
    reviewed_empty["server"]["round04"][  # type: ignore[index]
        "responsibility_basis_state"
    ] = "FORMAL_REVIEWED_NO_FINDING"
    reviewed_empty["server"]["round04"][  # type: ignore[index]
        "formal_responsibility_evidence_authorized"
    ] = True

    assert PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        no_basis, action="PUBLISH"
    ).allowed
    assert PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        reviewed_empty, action="PUBLISH"
    ).allowed


def test_v4_denies_unconfirmed_event_or_operational_instructions() -> None:
    context = deepcopy(_context())
    context["server"]["round04"]["event_assignment_confirmed"] = False  # type: ignore[index]
    context["server"]["round04"]["controlled_prevention_tags_only"] = False  # type: ignore[index]
    context["server"]["round04"]["operational_instruction_count"] = 1  # type: ignore[index]

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert {
        "SAFETY_CASE_EVENT_UNCONFIRMED",
        "SAFETY_CASE_UNCONTROLLED_PREVENTION_CONTENT",
        "SAFETY_CASE_OPERATIONAL_INSTRUCTION_FORBIDDEN",
    }.issubset(result.reasons)


@pytest.mark.parametrize("unauthorized_value", [False, None])
def test_v4_denies_safety_profile_metadata_without_accepted_evidence_authorization(
    unauthorized_value: bool | None,
) -> None:
    context = deepcopy(_context())
    round04 = context["server"]["round04"]  # type: ignore[index]
    if unauthorized_value is None:
        del round04["profile_metadata_claims_authorized"]  # type: ignore[index]
    else:
        round04["profile_metadata_claims_authorized"] = unauthorized_value  # type: ignore[index]

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert result.allowed is False
    assert "SAFETY_CASE_PROFILE_METADATA_UNAUTHORIZED" in result.reasons


@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_reason"),
    [
        (
            "unreviewed_critical_claim_count",
            None,
            "SAFETY_CASE_CRITICAL_CLAIM_UNREVIEWED",
        ),
        (
            "unresolved_casualty_loss_conflict_count",
            "0",
            "SAFETY_CASE_CASUALTY_LOSS_CONFLICT",
        ),
        (
            "operational_instruction_count",
            -1,
            "SAFETY_CASE_OPERATIONAL_INSTRUCTION_FORBIDDEN",
        ),
    ],
)
def test_v4_fails_closed_when_required_safety_counts_are_missing_or_invalid(
    field: str,
    invalid_value: object,
    expected_reason: str,
) -> None:
    context = deepcopy(_context())
    round04 = context["server"]["round04"]  # type: ignore[index]
    if invalid_value is None:
        del round04[field]  # type: ignore[index]
    else:
        round04[field] = invalid_value  # type: ignore[index]

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert result.allowed is False
    assert expected_reason in result.reasons


@pytest.mark.parametrize(
    ("section", "field", "invalid_value", "expected_reason"),
    [
        (
            "evidence_integrity",
            "unresolved_conflict_count",
            None,
            "UNRESOLVED_CLAIM_CONFLICT",
        ),
        (
            "round03",
            "unresolved_relation_candidate_count",
            -1,
            "RELATION_CANDIDATE_UNREVIEWED",
        ),
        (
            "round03",
            "unreviewed_regulation_status_candidate_count",
            "0",
            "REGULATION_STATUS_CANDIDATE_UNREVIEWED",
        ),
        (
            "round03",
            "unsafe_attachment_count",
            None,
            "ATTACHMENT_NOT_CLEAN",
        ),
    ],
)
def test_v4_inherited_integrity_counts_also_fail_closed(
    section: str,
    field: str,
    invalid_value: object,
    expected_reason: str,
) -> None:
    context = deepcopy(_context())
    facts = context["server"][section]  # type: ignore[index]
    if invalid_value is None:
        del facts[field]  # type: ignore[index]
    else:
        facts[field] = invalid_value  # type: ignore[index]

    result = PublicationGate.from_files(POLICY, SCHEMA).evaluate(
        context, action="PUBLISH"
    )

    assert result.allowed is False
    assert expected_reason in result.reasons
