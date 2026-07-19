from collections import Counter

from srbg_api.intelligence_v2.structural_corpus import (
    CORPUS_VERSION,
    STRUCTURAL_REPLAY_CORPUS,
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
