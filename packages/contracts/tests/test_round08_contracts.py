from datetime import UTC, datetime
from uuid import UUID

import pytest
import srbg_contracts.models as models
from pydantic import ValidationError

NOW = datetime(2026, 7, 15, 3, 0, tzinfo=UTC)
ITEM_ID = UUID("019b0000-0000-7000-8000-000000008001")


def _dimension(name: str, score: int) -> models.ScoreDimensionSummary:
    return models.ScoreDimensionSummary(
        dimension=name,
        raw_score=score,
        score=score,
        features=[
            models.ScoreFeature(
                code="ACCEPTED_CLAIM_COVERAGE",
                label="已接受事实覆盖",
                points=score,
                explanation="仅使用 accepted claims 与证据计算",
            )
        ],
        rule_version="scoring-v1.0.0",
        calculated_at=NOW,
    )


def test_item_summary_exposes_named_scores_without_a_generic_credibility_score() -> None:
    scores = models.ScoreSummary(
        relevance=_dimension("RELEVANCE", 88),
        authority=_dimension("AUTHORITY", 95),
        impact=None,
        novelty=None,
        timeliness=None,
        evidence=None,
        confidence=None,
        heat=_dimension("HEAT", 61),
    )
    item = models.ItemSummary(
        id=ITEM_ID,
        publication_revision_id=UUID("019b0000-0000-7000-8000-000000008002"),
        domain="DIGITAL",
        content_type="DIGITAL_CASE",
        title="桥梁数字化施工案例",
        source_name="四川路桥",
        source_published_at=NOW,
        first_discovered_at=NOW,
        activity_at=NOW,
        original_url="https://example.com/case",
        review_status="APPROVED",
        scores=scores,
    )

    payload = item.model_dump(mode="json", exclude_none=True)
    assert payload["scores"]["relevance"]["score"] == 88
    assert payload["scores"]["heat"]["dimension"] == "HEAT"
    assert "credibility" not in payload["scores"]


def test_score_override_requires_a_reason_and_preserves_raw_score() -> None:
    overridden = models.ScoreDimensionSummary(
        dimension="IMPACT",
        raw_score=50,
        score=70,
        features=[],
        rule_version="scoring-v1.0.0",
        calculated_at=NOW,
        overridden=True,
        override_reason="正式文件确认影响范围扩大",
    )
    assert overridden.raw_score == 50
    assert overridden.score == 70

    with pytest.raises(ValidationError, match="override reason"):
        models.ScoreDimensionSummary(
            dimension="IMPACT",
            raw_score=50,
            score=70,
            features=[],
            rule_version="scoring-v1.0.0",
            calculated_at=NOW,
            overridden=True,
        )


def test_event_detail_supports_all_domain_event_types_with_explicit_type() -> None:
    fields = models.EventDetail.model_fields
    assert set(models.EventType) == {
        models.EventType.SAFETY_INCIDENT,
        models.EventType.REGULATION_CHANGE,
        models.EventType.DIGITAL_PROJECT,
        models.EventType.RESEARCH_RESULT,
        models.EventType.PRODUCT_RELEASE,
    }
    assert fields["event_type"].is_required()
    assert fields["independent_source_count"].default == 0
