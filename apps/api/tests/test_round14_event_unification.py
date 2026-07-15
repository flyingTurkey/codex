from uuid import UUID

import pytest
from srbg_api.event_unification.domain import (
    EVENT_TYPE_BY_ITEM_TYPE,
    AliasCycleError,
    EventAlias,
    MatchDecision,
    classify_match,
    resolve_canonical_event,
)


def test_every_item_type_has_an_explicit_non_incident_default_mapping() -> None:
    assert EVENT_TYPE_BY_ITEM_TYPE == {
        "DIGITAL_CASE": "DIGITAL_PROJECT",
        "JOURNAL_PAPER": "RESEARCH_RESULT",
        "SOFTWARE_PRODUCT": "PRODUCT_RELEASE",
        "IOT_PRODUCT": "PRODUCT_RELEASE",
        "LOW_ALTITUDE_EQUIPMENT": "PRODUCT_RELEASE",
        "AI_EQUIPMENT": "PRODUCT_RELEASE",
        "SAFETY_REGULATION": "REGULATION_CHANGE",
        "SAFETY_CASE": "SAFETY_INCIDENT",
    }


def test_only_exact_identity_can_auto_bind_and_fuzzy_match_stays_candidate() -> None:
    assert classify_match(exact_identity=True, hard_conflicts=()) is MatchDecision.AUTO_BIND
    assert classify_match(exact_identity=False, hard_conflicts=()) is MatchDecision.CANDIDATE
    assert (
        classify_match(exact_identity=True, hard_conflicts=("document_number",))
        is MatchDecision.CANDIDATE
    )


def test_alias_resolution_is_stable_and_rejects_cycles() -> None:
    first = UUID("018f0000-0000-7000-8000-000000000001")
    second = UUID("018f0000-0000-7000-8000-000000000002")
    third = UUID("018f0000-0000-7000-8000-000000000003")
    assert (
        resolve_canonical_event(first, {first: EventAlias(second), second: EventAlias(third)})
        == third
    )
    with pytest.raises(AliasCycleError):
        resolve_canonical_event(first, {first: EventAlias(second), second: EventAlias(first)})
