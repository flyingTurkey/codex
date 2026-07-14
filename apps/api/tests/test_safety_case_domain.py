from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from srbg_api.safety_cases import (
    ClaimCandidate,
    ClaimField,
    ClaimReviewDecision,
    DedupDisposition,
    EventIdentity,
    EvidenceDescriptor,
    EvidenceRole,
    PublicFieldState,
    ReportStage,
    SourceAuthority,
    assert_reviewer_can_decide,
    assess_claim_candidate,
    detect_claim_conflict,
    findings_projection,
    project_public_field,
    safety_document_disposition,
    score_event_match,
)

SUBMITTER_ID = UUID("019b0000-0000-7000-8000-000000000401")
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000000402")


def _evidence(
    *,
    stage: ReportStage,
    authority: SourceAuthority = SourceAuthority.A0,
    role: EvidenceRole = EvidenceRole.PRIMARY_OFFICIAL,
) -> EvidenceDescriptor:
    return EvidenceDescriptor(
        evidence_id=UUID("019b0000-0000-7000-8000-000000000410"),
        report_stage=stage,
        authority=authority,
        role=role,
    )


def _accepted_decision() -> ClaimReviewDecision:
    return ClaimReviewDecision(
        accepted=True,
        reviewer_id=REVIEWER_ID,
        submitted_by=SUBMITTER_ID,
    )


def test_event_matching_uses_explainable_weighted_dimensions_and_threshold() -> None:
    existing = EventIdentity(
        occurred_on=date(2024, 5, 1),
        region="广东省梅州市大埔县",
        project="梅大高速茶阳路段",
        subjects=("广东梅大高速公路有限公司",),
        accident_type="ROADBED_COLLAPSE",
    )
    incoming = EventIdentity(
        occurred_on=date(2024, 5, 1),
        region="广东省 梅州市 大埔县",
        project="梅大高速茶阳路段",
        subjects=("广东梅大高速公路有限公司",),
        accident_type="GEOLOGICAL_DISASTER",
    )

    result = score_event_match(existing, incoming)

    assert result.total == 90
    assert result.dimension_scores == {
        "date": 25,
        "region": 20,
        "project": 30,
        "subject": 15,
        "accident_type": 0,
    }
    assert result.requires_human_review is True
    assert result.forms_candidate is True
    assert result.algorithm_version == "safety-event-match-v1"


@pytest.mark.parametrize(
    ("incoming", "expected_total"),
    [
        (
            EventIdentity(
                occurred_on=date(2024, 5, 1),
                region="广东省梅州市大埔县",
                project="另一项目",
                subjects=("另一主体",),
                accident_type="ROADBED_COLLAPSE",
            ),
            55,
        ),
        (
            EventIdentity(
                occurred_on=date(2024, 5, 1),
                region="另一地区",
                project="梅大高速茶阳路段",
                subjects=(),
                accident_type="ROADBED_COLLAPSE",
            ),
            65,
        ),
    ],
)
def test_event_candidate_requires_threshold_and_identity_guard(
    incoming: EventIdentity, expected_total: int
) -> None:
    existing = EventIdentity(
        occurred_on=date(2024, 5, 1),
        region="广东省梅州市大埔县",
        project="梅大高速茶阳路段",
        subjects=("广东梅大高速公路有限公司",),
        accident_type="ROADBED_COLLAPSE",
    )

    result = score_event_match(existing, incoming)

    assert result.total == expected_total
    assert result.forms_candidate is (expected_total >= 60)
    assert result.requires_human_review is result.forms_candidate


def test_same_accident_different_stages_are_preserved_for_link_review() -> None:
    disposition = safety_document_disposition(
        existing_stage=ReportStage.INITIAL_REPORT,
        incoming_stage=ReportStage.FOLLOW_UP_REPORT,
        existing_raw_sha256="a" * 64,
        incoming_raw_sha256="a" * 64,
        existing_url="https://example.test/case",
        incoming_url="https://example.test/case",
        title_similarity_bps=10_000,
    )

    assert disposition is DedupDisposition.PRESERVE_AND_LINK


def test_only_same_stage_same_raw_bytes_are_exact_duplicates() -> None:
    assert (
        safety_document_disposition(
            existing_stage=ReportStage.INITIAL_REPORT,
            incoming_stage=ReportStage.INITIAL_REPORT,
            existing_raw_sha256="b" * 64,
            incoming_raw_sha256="b" * 64,
            existing_url="https://example.test/initial",
            incoming_url="https://mirror.test/initial",
            title_similarity_bps=7_000,
        )
        is DedupDisposition.EXACT_RAW_DUPLICATE
    )
    assert (
        safety_document_disposition(
            existing_stage=ReportStage.INITIAL_REPORT,
            incoming_stage=ReportStage.INITIAL_REPORT,
            existing_raw_sha256="b" * 64,
            incoming_raw_sha256="c" * 64,
            existing_url="https://example.test/initial",
            incoming_url="https://mirror.test/initial",
            title_similarity_bps=9_999,
        )
        is DedupDisposition.PRESERVE_AS_DISTINCT
    )


@pytest.mark.parametrize(
    "field",
    [ClaimField.OFFICIAL_DIRECT_CAUSES, ClaimField.RESPONSIBILITY_FINDINGS],
)
def test_causes_and_responsibility_require_formal_official_evidence(
    field: ClaimField,
) -> None:
    informal_candidate = ClaimCandidate(
        claim_id=UUID("019b0000-0000-7000-8000-000000000420"),
        field=field,
        value=["媒体推测原因"],
        evidence=_evidence(
            stage=ReportStage.FOLLOW_UP_REPORT,
            authority=SourceAuthority.B1,
            role=EvidenceRole.SECONDARY_REPORT,
        ),
    )

    assessment = assess_claim_candidate(informal_candidate, _accepted_decision())

    assert assessment.accepted is False
    assert assessment.reason == "FORMAL_OFFICIAL_EVIDENCE_REQUIRED"


@pytest.mark.parametrize(
    "stage",
    [ReportStage.FINAL_INVESTIGATION, ReportStage.ENFORCEMENT],
)
def test_formal_a0_or_a1_claim_still_requires_separated_human_acceptance(
    stage: ReportStage,
) -> None:
    candidate = ClaimCandidate(
        claim_id=UUID("019b0000-0000-7000-8000-000000000421"),
        field=ClaimField.OFFICIAL_DIRECT_CAUSES,
        value=["正式报告认定的直接原因"],
        evidence=_evidence(stage=stage, authority=SourceAuthority.A1),
    )

    assert assess_claim_candidate(candidate, None).reason == "HUMAN_DECISION_REQUIRED"
    assert assess_claim_candidate(candidate, _accepted_decision()).accepted is True


@pytest.mark.parametrize(
    "field",
    [ClaimField.DEATHS, ClaimField.INJURIES, ClaimField.LOSS_AMOUNT_MINOR],
)
def test_consequence_fields_allow_any_official_stage_but_require_field_decision(
    field: ClaimField,
) -> None:
    candidate = ClaimCandidate(
        claim_id=UUID("019b0000-0000-7000-8000-000000000422"),
        field=field,
        value=30,
        evidence=_evidence(stage=ReportStage.INITIAL_REPORT, authority=SourceAuthority.A1),
    )

    assert assess_claim_candidate(candidate, None).accepted is False
    assert assess_claim_candidate(candidate, _accepted_decision()).accepted is True


def test_no_formal_basis_is_null_and_reviewed_no_findings_is_empty() -> None:
    assert findings_projection(formal_evidence_reviewed=False, findings=()) is None
    assert findings_projection(formal_evidence_reviewed=True, findings=()) == ()
    assert findings_projection(
        formal_evidence_reviewed=True,
        findings=("正式认定",),
    ) == ("正式认定",)


def test_conflicting_casualty_claim_opens_manual_queue_and_hides_public_value() -> None:
    current = ClaimCandidate(
        claim_id=UUID("019b0000-0000-7000-8000-000000000431"),
        field=ClaimField.DEATHS,
        value=48,
        evidence=_evidence(stage=ReportStage.FOLLOW_UP_REPORT),
    )
    candidate = ClaimCandidate(
        claim_id=UUID("019b0000-0000-7000-8000-000000000432"),
        field=ClaimField.DEATHS,
        value=52,
        evidence=_evidence(stage=ReportStage.FINAL_INVESTIGATION),
    )

    conflict = detect_claim_conflict(current, candidate)
    public = project_public_field(current_value=48, unresolved_conflict=conflict)

    assert conflict is not None
    assert conflict.requires_human_review is True
    assert conflict.current_value_snapshot == 48
    assert conflict.candidate_value_snapshot == 52
    assert public.value is None
    assert public.state is PublicFieldState.UNAVAILABLE_PENDING_VERIFICATION


def test_submitter_cannot_approve_own_safety_case() -> None:
    with pytest.raises(PermissionError, match="submitter cannot review their own safety case"):
        assert_reviewer_can_decide(SUBMITTER_ID, SUBMITTER_ID)

    assert_reviewer_can_decide(SUBMITTER_ID, REVIEWER_ID)
