from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from srbg_api.intelligence_v2.domain import (
    HotspotCandidate,
    HotspotCandidateReason,
    HotspotComponentEvidence,
    HotspotComponents,
    HotspotSourceEvidence,
    RelevanceDecision,
    calculate_hotspot_award,
    decide_projection,
    evaluate_hotspot_candidate,
)
from srbg_contracts import PrimaryIntelligenceType

NOW = datetime(2026, 7, 20, 2, 0, tzinfo=UTC)
CLAIM_A = UUID("019f8400-0000-7000-8000-000000000101")
CLAIM_B = UUID("019f8400-0000-7000-8000-000000000102")
SOURCE_A = UUID("019f8400-0000-7000-8000-000000000201")
SOURCE_B = UUID("019f8400-0000-7000-8000-000000000202")


def test_uncertain_relevance_never_projects() -> None:
    assert decide_projection(RelevanceDecision.LOW_CONFIDENCE, "R1") == "REVIEW_ONLY"
    assert decide_projection(RelevanceDecision.RELEVANT, "R4") == "QUARANTINE_ONLY"
    assert decide_projection(RelevanceDecision.RELEVANT, "R3") == "R3_METADATA"
    assert decide_projection(RelevanceDecision.RELEVANT, "R2") == "FULL"


def test_hotspot_is_derived_by_server_rule() -> None:
    components = HotspotComponents(
        impact_scope=20,
        engineering_materiality=20,
        novelty=15,
        urgency=10,
        evidence_authority=10,
    )
    result = calculate_hotspot_award(
        components=components,
        independent_source_count=1,
        authoritative_first_party=True,
    )
    assert result.awarded is True
    assert result.score == 75
    assert result.rule_version == "hotspot-v2.0.0"


@pytest.mark.parametrize("field,value", [("impact_scope", 26), ("novelty", 21)])
def test_hotspot_component_caps_are_enforced(field: str, value: int) -> None:
    payload = {
        "impact_scope": 0,
        "engineering_materiality": 0,
        "novelty": 0,
        "urgency": 0,
        "evidence_authority": 0,
        field: value,
    }
    with pytest.raises(ValueError):
        HotspotComponents(**payload)


def _component_evidence(*claim_ids: UUID) -> tuple[HotspotComponentEvidence, ...]:
    return (
        HotspotComponentEvidence("impact_scope", 20, frozenset(claim_ids)),
        HotspotComponentEvidence("engineering_materiality", 20, frozenset(claim_ids)),
        HotspotComponentEvidence("novelty", 15, frozenset(claim_ids)),
        HotspotComponentEvidence("urgency", 10, frozenset(claim_ids)),
        HotspotComponentEvidence("evidence_authority", 10, frozenset(claim_ids)),
    )


@pytest.mark.parametrize("primary_type", list(PrimaryIntelligenceType))
def test_hotspot_uses_two_recent_independent_sources_without_changing_primary_type(
    primary_type: PrimaryIntelligenceType,
) -> None:
    candidate = HotspotCandidate(
        claim_ids=frozenset({CLAIM_A, CLAIM_B}),
        reasons=(
            HotspotCandidateReason(
                "两份独立工程事实均指向同一重大进展",
                frozenset({CLAIM_A, CLAIM_B}),
            ),
        ),
    )
    sources = (
        HotspotSourceEvidence(
            source_id=SOURCE_A,
            organization_key="org-a",
            lineage_root="original-a",
            role="ORIGINAL",
            published_at=NOW - timedelta(days=7),
            accepted_claim_ids=frozenset({CLAIM_A}),
            qualified=True,
            authoritative_first_party=False,
        ),
        HotspotSourceEvidence(
            source_id=SOURCE_B,
            organization_key="org-b",
            lineage_root="original-b",
            role="INDEPENDENT_REPORT",
            published_at=NOW - timedelta(hours=1),
            accepted_claim_ids=frozenset({CLAIM_B}),
            qualified=True,
            authoritative_first_party=False,
        ),
    )

    result = evaluate_hotspot_candidate(
        candidate=candidate,
        component_evidence=_component_evidence(CLAIM_A, CLAIM_B),
        sources=sources,
        primary_type=primary_type,
        evaluated_at=NOW,
    )

    assert result.awarded is True
    assert result.trigger == "MULTI_SOURCE_7D"
    assert result.independent_source_count == 2
    assert result.primary_type is primary_type
    assert result.reasons == ("两份独立工程事实均指向同一重大进展",)


def test_hotspot_deduplicates_reprints_and_same_organization() -> None:
    candidate = HotspotCandidate(
        claim_ids=frozenset({CLAIM_A, CLAIM_B}),
        reasons=(HotspotCandidateReason("候选理由", frozenset({CLAIM_A})),),
    )
    sources = (
        HotspotSourceEvidence(
            SOURCE_A,
            "same-org",
            "same-lineage",
            "ORIGINAL",
            NOW,
            frozenset({CLAIM_A}),
            True,
            False,
        ),
        HotspotSourceEvidence(
            SOURCE_B,
            "other-org",
            "same-lineage",
            "REPRINT",
            NOW,
            frozenset({CLAIM_B}),
            True,
            False,
        ),
        HotspotSourceEvidence(
            UUID("019f8400-0000-7000-8000-000000000203"),
            "same-org",
            "other-lineage",
            "INDEPENDENT_REPORT",
            NOW,
            frozenset({CLAIM_B}),
            True,
            False,
        ),
    )

    result = evaluate_hotspot_candidate(
        candidate=candidate,
        component_evidence=_component_evidence(CLAIM_A, CLAIM_B),
        sources=sources,
        primary_type=PrimaryIntelligenceType.INDUSTRY_UPDATE,
        evaluated_at=NOW,
    )

    assert result.awarded is False
    assert result.independent_source_count == 1


def test_hotspot_authority_path_requires_current_claim_evidence_and_score_70() -> None:
    candidate = HotspotCandidate(
        claim_ids=frozenset({CLAIM_A}),
        reasons=(HotspotCandidateReason("权威一手材料显示重大运营后果", frozenset({CLAIM_A})),),
    )
    authority = HotspotSourceEvidence(
        SOURCE_A,
        "authority-org",
        "authority-original",
        "ORIGINAL",
        NOW,
        frozenset({CLAIM_A}),
        True,
        True,
    )

    awarded = evaluate_hotspot_candidate(
        candidate=candidate,
        component_evidence=_component_evidence(CLAIM_A),
        sources=(authority,),
        primary_type=PrimaryIntelligenceType.SAFETY_INTELLIGENCE,
        evaluated_at=NOW,
    )
    rejected = evaluate_hotspot_candidate(
        candidate=candidate,
        component_evidence=(
            HotspotComponentEvidence("impact_scope", 19, frozenset({CLAIM_A})),
            HotspotComponentEvidence("engineering_materiality", 20, frozenset({CLAIM_A})),
            HotspotComponentEvidence("novelty", 10, frozenset({CLAIM_A})),
            HotspotComponentEvidence("urgency", 10, frozenset({CLAIM_A})),
            HotspotComponentEvidence("evidence_authority", 10, frozenset({CLAIM_A})),
        ),
        sources=(authority,),
        primary_type=PrimaryIntelligenceType.SAFETY_INTELLIGENCE,
        evaluated_at=NOW,
    )

    assert awarded.awarded is True
    assert awarded.trigger == "AUTHORITY_SCORE"
    assert awarded.score == 75
    assert rejected.awarded is False
    assert rejected.score == 69


def test_hotspot_fails_closed_for_old_or_unaccepted_claim_evidence() -> None:
    candidate = HotspotCandidate(
        claim_ids=frozenset({CLAIM_A, CLAIM_B}),
        reasons=(HotspotCandidateReason("无充分证据的理由", frozenset({CLAIM_A, CLAIM_B})),),
    )
    sources = (
        HotspotSourceEvidence(
            SOURCE_A,
            "org-a",
            "root-a",
            "ORIGINAL",
            NOW - timedelta(days=7, seconds=1),
            frozenset({CLAIM_A}),
            True,
            False,
        ),
        HotspotSourceEvidence(
            SOURCE_B,
            "org-b",
            "root-b",
            "INDEPENDENT_REPORT",
            NOW,
            frozenset(),
            True,
            False,
        ),
    )

    result = evaluate_hotspot_candidate(
        candidate=candidate,
        component_evidence=_component_evidence(CLAIM_A, CLAIM_B),
        sources=sources,
        primary_type=PrimaryIntelligenceType.DIGITAL_TRANSFORMATION,
        evaluated_at=NOW,
    )

    assert result.awarded is False
    assert result.reason_codes == ("CANDIDATE_CLAIMS_NOT_CURRENT_ACCEPTED",)
