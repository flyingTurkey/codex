from dataclasses import replace
from uuid import UUID

from srbg_api.intelligence_resolution.automatic_relationships import (
    AutomaticRelationshipInput,
    RelationshipKind,
    RelationshipSuppression,
    decide_automatic_relationship,
    input_fingerprint,
)

LEFT = UUID("019b0000-0000-7000-8000-000000008001")
RIGHT = UUID("019b0000-0000-7000-8000-000000008002")
LEFT_VERSION = UUID("019b0000-0000-7000-8000-000000008011")
RIGHT_VERSION = UUID("019b0000-0000-7000-8000-000000008012")


def _input(**changes: object) -> AutomaticRelationshipInput:
    value = AutomaticRelationshipInput(
        left_item_id=LEFT,
        right_item_id=RIGHT,
        left_document_version_id=LEFT_VERSION,
        right_document_version_id=RIGHT_VERSION,
        left_content_sha256="a" * 64,
        right_content_sha256="b" * 64,
        score_bps=9700,
        hard_conflicts=(),
        exact_identity=False,
        relation_hint=None,
        left_report_stage=None,
        right_report_stage=None,
        left_source_role="MEDIA_REPORT",
        right_source_role="MEDIA_REPORT",
        algorithm_version="pers08-relations-v1",
        model_version="pers08-model-v1",
    )
    return replace(value, **changes)


def test_high_confidence_pair_is_automatic_and_idempotently_fingerprinted() -> None:
    first = _input()
    reversed_pair = replace(
        first,
        left_item_id=RIGHT,
        right_item_id=LEFT,
        left_document_version_id=RIGHT_VERSION,
        right_document_version_id=LEFT_VERSION,
        left_content_sha256="b" * 64,
        right_content_sha256="a" * 64,
        left_source_role="MEDIA_REPORT",
        right_source_role="MEDIA_REPORT",
    )
    decision = decide_automatic_relationship(first)
    assert decision is not None
    assert decision.kind is RelationshipKind.DUPLICATE
    assert input_fingerprint(first, RelationshipKind.DUPLICATE) == input_fingerprint(
        reversed_pair, RelationshipKind.DUPLICATE
    )


def test_similar_titles_with_a_hard_event_conflict_stay_independent() -> None:
    assert decide_automatic_relationship(_input(hard_conflicts=("REGION",))) is None


def test_initial_follow_up_and_final_reports_are_never_duplicates() -> None:
    follow_up = decide_automatic_relationship(
        _input(left_report_stage="INITIAL", right_report_stage="FOLLOW_UP", score_bps=10_000)
    )
    final = decide_automatic_relationship(
        _input(left_report_stage="FOLLOW_UP", right_report_stage="FINAL", score_bps=10_000)
    )
    assert follow_up is not None and follow_up.kind is RelationshipKind.FOLLOW_UP_OF
    assert final is not None and final.kind is RelationshipKind.INVESTIGATES
    assert follow_up.source_item_id == RIGHT and follow_up.target_item_id == LEFT


def test_source_roles_remain_distinct_even_for_identical_content() -> None:
    decision = decide_automatic_relationship(
        _input(
            exact_identity=True,
            score_bps=10_000,
            left_source_role="VENDOR_STATEMENT",
            right_source_role="INDEPENDENT_VERIFICATION",
        )
    )
    assert decision is not None
    assert decision.kind is RelationshipKind.RELATED_CONTENT


def test_owner_withdrawal_suppresses_same_input_but_not_material_change() -> None:
    original = _input()
    fingerprint = input_fingerprint(original, RelationshipKind.DUPLICATE)
    suppression = RelationshipSuppression(
        kind=RelationshipKind.DUPLICATE,
        member_ids=frozenset({LEFT, RIGHT}),
        input_fingerprint_sha256=fingerprint,
    )
    assert decide_automatic_relationship(original, suppressions=(suppression,)) is None
    changed = replace(original, right_content_sha256="c" * 64)
    assert decide_automatic_relationship(changed, suppressions=(suppression,)) is not None


def test_product_model_and_version_inheritance_require_explicit_keys() -> None:
    model = decide_automatic_relationship(
        _input(relation_hint="MODEL_ALIAS", exact_identity=True, score_bps=10_000)
    )
    version = decide_automatic_relationship(
        _input(relation_hint="VERSION_SUCCESSOR", exact_identity=True, score_bps=10_000)
    )
    assert model is not None and model.kind is RelationshipKind.MODEL_ALIAS
    assert version is not None and version.kind is RelationshipKind.VERSION_SUCCESSOR


def test_same_event_and_topic_keys_create_explicit_relationships() -> None:
    same_event = decide_automatic_relationship(
        _input(relation_hint="SAME_EVENT", score_bps=9_700)
    )
    topic = decide_automatic_relationship(_input(relation_hint="TOPIC", score_bps=9_700))
    assert same_event is not None and same_event.kind is RelationshipKind.SAME_EVENT
    assert topic is not None and topic.kind is RelationshipKind.TOPIC
