import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from srbg_api.intelligence_resolution.domain import DeduplicationDocument
from srbg_api.intelligence_resolution.service import ResolutionService

ITEM_A = UUID("019b0000-0000-7000-8000-000000008101")
ITEM_B = UUID("019b0000-0000-7000-8000-000000008102")
NOW = datetime(2026, 7, 15, tzinfo=UTC)


class FakeStore:
    candidates: list[dict[str, Any]]
    scores: list[dict[str, Any]]

    def __init__(self) -> None:
        self.candidates = []
        self.scores = []

    async def save_duplicate_candidate(self, **values: Any) -> UUID:
        self.candidates.append(values)
        return UUID("019b0000-0000-7000-8000-000000008103")

    async def save_score_set(self, **values: Any) -> UUID:
        self.scores.append(values)
        return UUID("019b0000-0000-7000-8000-000000008104")


def _document(external_id: str, title: str) -> DeduplicationDocument:
    return DeduplicationDocument(
        canonical_url=f"https://example.com/{external_id}",
        source_id="source-a",
        external_id=external_id,
        title=title,
        body="桥梁施工数字化进展",
        entities=("桥梁",),
        occurred_at=NOW,
        region="四川",
        project="测试项目",
    )


def test_resolution_service_persists_explainable_candidates_and_all_available_scores() -> None:
    store = FakeStore()
    service = ResolutionService(store=store, now=lambda: NOW)

    candidate_id = asyncio.run(
        service.evaluate_pair(
            left_item_id=ITEM_A,
            left=_document("a", "桥梁数字化施工进展"),
            right_item_id=ITEM_B,
            right=_document("b", "桥梁数字化施工进展"),
            recall_methods=("RULE",),
        )
    )
    score_set_id = asyncio.run(
        service.score_item(
            item_id=ITEM_A,
            scoring_input={
                "relevance_features": (70, 20, 10),
                "authority_level": "A1",
                "impact_features": (30, 20, 15, 10),
                "novelty_similarity_bps": 2_000,
                "published_at": NOW,
                "content_type": "DIGITAL_CASE",
                "accepted_claim_coverage_bps": 10_000,
                "locator_integrity": True,
                "primary_evidence": True,
                "extraction_confidence_bps": 9_000,
                "cross_source_agreement_bps": 8_000,
                "human_reviewed": True,
                "unresolved_conflicts": 0,
                "independent_source_count": 2,
                "event_activity_count": 3,
            },
        )
    )

    assert candidate_id is not None
    assert store.candidates[0]["requires_human_review"] is True
    assert store.candidates[0]["hard_conflicts"] == ()
    assert score_set_id is not None
    assert set(store.scores[0]["scores"]) == {
        "RELEVANCE",
        "AUTHORITY",
        "IMPACT",
        "NOVELTY",
        "TIMELINESS",
        "EVIDENCE",
        "CONFIDENCE",
        "HEAT",
    }
