from collections import Counter

from srbg_api.intelligence_v2.structural_corpus import (
    CORPUS_VERSION,
    STRUCTURAL_REPLAY_CORPUS,
    StructuralPrediction,
    evaluate_structural_replay,
)
from srbg_contracts import EngineeringObject, PrimaryIntelligenceType


def test_structural_replay_has_frozen_360_case_distribution() -> None:
    assert CORPUS_VERSION == "civil-intelligence-structural-replay-v2.0.0"
    assert len(STRUCTURAL_REPLAY_CORPUS) == 360
    assert len({case.case_id for case in STRUCTURAL_REPLAY_CORPUS}) == 360
    assert Counter(case.bucket for case in STRUCTURAL_REPLAY_CORPUS) == {
        "POSITIVE": 180,
        "BOUNDARY": 90,
        "NEGATIVE": 90,
    }


def test_structural_replay_is_explicitly_not_human_gold() -> None:
    positive = [case for case in STRUCTURAL_REPLAY_CORPUS if case.bucket == "POSITIVE"]
    assert Counter(case.primary_type for case in positive) == {
        primary_type: 60 for primary_type in PrimaryIntelligenceType
    }
    assert {case.engineering_object for case in positive} == set(EngineeringObject)
    assert all(
        case.locked_negative
        for case in STRUCTURAL_REPLAY_CORPUS
        if case.bucket == "NEGATIVE"
    )


def test_structural_replay_covers_both_cross_cutting_facets_without_claiming_owner_gold() -> None:
    specialty_cases = [
        case
        for case in STRUCTURAL_REPLAY_CORPUS
        if case.specialty_facet == "TUNNEL_GAS_MONITORING"
    ]
    assert specialty_cases
    assert all(case.engineering_object == EngineeringObject.TUNNEL for case in specialty_cases)
    assert {
        case.supporting_engineering_object for case in specialty_cases
    } == {EngineeringObject.HIGHWAY, EngineeringObject.RAILWAY}
    assert any(
        case.equipment_domain == "CONSTRUCTION_MACHINERY"
        for case in STRUCTURAL_REPLAY_CORPUS
    )

    predictions = {
        case.case_id: StructuralPrediction(
            directly_relevant=case.directly_relevant is True,
            primary_type=case.primary_type,
        )
        for case in STRUCTURAL_REPLAY_CORPUS
    }
    report = evaluate_structural_replay(predictions)

    assert report.corpus_version == CORPUS_VERSION
    assert report.label_authority == "STRUCTURAL_REPLAY"
    assert report.authorizes_auto_pass is False
    assert report.precision_bps == 10_000
    assert report.recall_bps == 10_000
    assert report.locked_negative_leaks == 0


def test_structural_replay_report_explains_locked_negative_leaks() -> None:
    predictions = {
        case.case_id: StructuralPrediction(
            directly_relevant=case.directly_relevant is True,
            primary_type=case.primary_type,
        )
        for case in STRUCTURAL_REPLAY_CORPUS
    }
    leaked = next(case for case in STRUCTURAL_REPLAY_CORPUS if case.locked_negative)
    predictions[leaked.case_id] = StructuralPrediction(
        directly_relevant=True,
        primary_type=PrimaryIntelligenceType.INDUSTRY_UPDATE,
    )

    report = evaluate_structural_replay(predictions)

    assert report.locked_negative_leaks == 1
    assert report.failed_case_ids == (leaked.case_id,)
