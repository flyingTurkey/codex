from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.ai_pipeline.evidence_gate import (
    AUTOMATIC_EVIDENCE_RULE_VERSION,
    AutomaticEvidenceCandidate,
    AutomaticEvidenceContext,
    AutomaticEvidenceGate,
    EvidenceFact,
)

VERSION = UUID("019d0000-0000-7000-8000-000000002601")
OTHER_VERSION = UUID("019d0000-0000-7000-8000-000000002602")
EVIDENCE = UUID("019d0000-0000-7000-8000-000000002603")


def _context(**changes: object) -> AutomaticEvidenceContext:
    values: dict[str, object] = {
        "document_version_id": VERSION,
        "evidence": {
            EVIDENCE: {
                "document_version_id": VERSION,
                "excerpt": "四川路桥于2026年7月18日发布,投入金额100万元。",
                "active": True,
            }
        },
        "official_first_party": False,
        "unresolved_conflict_fields": frozenset(),
        "prompt_injection_risk": False,
        "evaluated_at": datetime(2026, 7, 18, tzinfo=UTC),
    }
    values.update(changes)
    return AutomaticEvidenceContext.model_validate(values)


def _candidate(**changes: object) -> AutomaticEvidenceCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate-1",
        "field": "published_at",
        "value": "2026-07-18",
        "confidence_bps": 9900,
        "evidence_ids": [EVIDENCE],
        "attribution": None,
        "origin": "MODEL",
    }
    values.update(changes)
    return AutomaticEvidenceCandidate.model_validate(values)


def test_accepts_exact_current_evidence_as_evidence_fact() -> None:
    result = AutomaticEvidenceGate().evaluate(_candidate(), _context())
    assert isinstance(result, EvidenceFact)
    assert result.acceptance_method == "AUTOMATED_EVIDENCE_GATE"
    assert result.rule_version == AUTOMATIC_EVIDENCE_RULE_VERSION
    assert len(result.evidence_set_sha256) == 64


@pytest.mark.parametrize(
    ("candidate", "context", "reason"),
    [
        (
            _candidate(evidence_ids=[UUID("019d0000-0000-7000-8000-000000002699")]),
            _context(),
            "EVIDENCE_ID_NOT_FOUND",
        ),
        (
            _candidate(),
            _context(
                evidence={
                    EVIDENCE: {
                        "document_version_id": OTHER_VERSION,
                        "excerpt": "2026年7月18日",
                        "active": True,
                    }
                }
            ),
            "EVIDENCE_DOCUMENT_VERSION_MISMATCH",
        ),
        (
            _candidate(),
            _context(
                evidence={
                    EVIDENCE: {
                        "document_version_id": VERSION,
                        "excerpt": "2026年7月17日",
                        "active": True,
                    }
                }
            ),
            "SCALAR_EVIDENCE_MISMATCH",
        ),
        (
            _candidate(field="claimed_outcome", value="节约100万元"),
            _context(),
            "ENTERPRISE_ATTRIBUTION_REQUIRED",
        ),
        (
            _candidate(field="incident_cause", value="管理不善"),
            _context(official_first_party=False),
            "OFFICIAL_DIRECT_SUPPORT_REQUIRED",
        ),
        (
            _candidate(),
            _context(
                evidence={
                    EVIDENCE: {
                        "document_version_id": VERSION,
                        "excerpt": "2026年7月18日",
                        "active": False,
                    }
                }
            ),
            "EVIDENCE_INACTIVE",
        ),
        (
            _candidate(),
            _context(unresolved_conflict_fields=frozenset({"published_at"})),
            "UNRESOLVED_CONFLICT",
        ),
        (_candidate(), _context(prompt_injection_risk=True), "PROMPT_INJECTION_RISK"),
    ],
)
def test_rejects_unsafe_candidates_to_ai_judgment(
    candidate: AutomaticEvidenceCandidate,
    context: AutomaticEvidenceContext,
    reason: str,
) -> None:
    result = AutomaticEvidenceGate().evaluate(candidate, context)
    assert result.kind == "AI_JUDGMENT"
    assert reason in result.reason_codes


def test_explicit_enterprise_attribution_and_official_direct_text_are_required() -> None:
    attributed = _candidate(
        field="claimed_outcome",
        value="投入金额100万元",
        attribution="四川路桥",
    )
    assert isinstance(AutomaticEvidenceGate().evaluate(attributed, _context()), EvidenceFact)
    official = _candidate(field="incident_cause", value="投入金额100万元")
    assert isinstance(
        AutomaticEvidenceGate().evaluate(official, _context(official_first_party=True)),
        EvidenceFact,
    )


def test_rejects_numeric_conflict_even_when_model_confidence_is_high() -> None:
    candidate = _candidate(field="injury_count", value=2, confidence_bps=9999)
    result = AutomaticEvidenceGate().evaluate(candidate, _context())
    assert result.kind == "AI_JUDGMENT"
    assert "SCALAR_EVIDENCE_MISMATCH" in result.reason_codes


@pytest.mark.parametrize("field", ["legal_effect", "responsibility", "incident_cause"])
def test_rejects_legal_responsibility_and_causal_overreach(field: str) -> None:
    result = AutomaticEvidenceGate().evaluate(
        _candidate(field=field, value="投入金额100万元"),
        _context(official_first_party=False),
    )
    assert result.kind == "AI_JUDGMENT"
    assert "OFFICIAL_DIRECT_SUPPORT_REQUIRED" in result.reason_codes
