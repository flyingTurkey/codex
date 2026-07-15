from uuid import UUID

from srbg_api.digital_cases.domain import (
    MaturityEvidence,
    OutcomeEvidence,
    calculate_relevance,
    validate_maturity,
    validate_outcome_verification,
    validate_taxonomy,
)


def test_relevance_v1_uses_highest_domain_weight_and_evidence_backed_bonuses() -> None:
    result = calculate_relevance(
        ["BUILDING", "BRIDGE"],
        is_sichuan=True,
        has_direct_srbg_relation=True,
    )

    assert result.score == 100
    assert result.rule_version == "relevance-v1.0.0"
    assert [factor.points for factor in result.factors] == [70, 20, 10]


def test_relevance_v1_is_nationwide_and_sichuan_is_only_a_bonus() -> None:
    result = calculate_relevance(["ROAD"], is_sichuan=False, has_direct_srbg_relation=False)

    assert result.score == 67
    assert result.factors[0].points == 67


def test_scale_maturity_requires_project_and_operating_evidence() -> None:
    missing = validate_maturity(
        "ENTERPRISE_SCALE",
        MaturityEvidence(named_project_count=0, deployment_count=None, operating_months=None),
    )
    supported = validate_maturity(
        "SINGLE_PROJECT_PRODUCTION",
        MaturityEvidence(named_project_count=1, deployment_count=5913, operating_months=None),
    )

    assert "MATURITY_PRODUCTION_EVIDENCE_REQUIRED" in missing
    assert supported == ()


def test_claimed_outcome_cannot_be_promoted_by_the_attributed_publishers_own_evidence() -> None:
    publisher_id = UUID("019b0000-0000-7000-8000-000000005101")
    evidence = OutcomeEvidence(
        attributed_entity_id=publisher_id,
        evidence_source_entity_ids=(publisher_id,),
        evidence_roles=("PRIMARY_AUTHOR",),
    )

    assert validate_outcome_verification("VERIFIED", evidence) == ("INDEPENDENT_EVIDENCE_REQUIRED",)


def test_independent_confirmation_can_support_verified_outcome() -> None:
    evidence = OutcomeEvidence(
        attributed_entity_id=UUID("019b0000-0000-7000-8000-000000005102"),
        evidence_source_entity_ids=(UUID("019b0000-0000-7000-8000-000000005103"),),
        evidence_roles=("INDEPENDENT_CONFIRMATION",),
    )

    assert validate_outcome_verification("VERIFIED", evidence) == ()


def test_taxonomy_rejects_codes_outside_the_canonical_vocabulary() -> None:
    assert (
        validate_taxonomy(
            engineering_domains=["BRIDGE"],
            lifecycle_stages=["CONSTRUCTION"],
            technology_tags=["BIM"],
            application_scenarios=["QUALITY_CONTROL"],
        )
        == ()
    )
    assert validate_taxonomy(
        engineering_domains=["BRIDGE"],
        lifecycle_stages=["CONSTRUCTION"],
        technology_tags=["MAGIC_AI"],
        application_scenarios=["QUALITY_CONTROL"],
    ) == ("DIGITAL_TAXONOMY_CODE_INVALID",)
