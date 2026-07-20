# ruff: noqa: RUF001
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import ReviewCaseV2


def test_owner_review_projection_separates_fact_and_ai_decisions() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    claim_id = UUID("019f8100-0000-7000-8000-000000000002")
    fact_text = "发生了什么：" + "工" * 90
    impact_text = "工程影响与意义：" + "程" * 90
    limits_text = "限制与待跟踪：" + "证" * 104
    visible_count = len(fact_text) + len(impact_text) + len(limits_text)
    review = ReviewCaseV2.model_validate(
        {
            "case_id": "019f8100-0000-7000-8000-000000000101",
            "event_id": "019f8100-0000-7000-8000-000000000102",
            "document_version_id": "019f8100-0000-7000-8000-000000000001",
            "reason": "CONTENT_PREPARATION_REVIEW",
            "risk_tier": "R2",
            "safe_metadata": {"title": "铁路隧道瓦斯监测"},
            "state": "OPEN",
            "version": 3,
            "created_at": now,
            "updated_at": now,
            "content_preparation": {
                "status": "CURRENT",
                "source_excerpt": {
                    "text": "该铁路隧道已部署连续瓦斯监测。",
                    "claim_ids": [claim_id],
                    "evidence_locators": ["pdf:page=8&block=3"],
                },
                "summary": {
                    "visible_character_count": visible_count,
                    "paragraphs": [
                        {
                            "kind": "FACT",
                            "section": "WHAT_HAPPENED",
                            "text": fact_text,
                            "claim_ids": [claim_id],
                        },
                        {
                            "kind": "JUDGMENT",
                            "section": "ENGINEERING_IMPACT",
                            "text": impact_text,
                            "judgment_type": "ENGINEERING_SIGNIFICANCE",
                        },
                        {
                            "kind": "JUDGMENT",
                            "section": "LIMITATIONS_AND_FOLLOW_UP",
                            "text": limits_text,
                            "judgment_type": "LIMITATION_AND_FOLLOW_UP",
                        },
                    ],
                },
                "claims": [
                    {
                        "claim_id": claim_id,
                        "basis": "PROJECT_FIRST_PARTY_RECORD",
                        "evidence_locators": ["pdf:page=8&block=3"],
                    }
                ],
                "fact_decisions": [
                    {
                        "decision_id": "019f8100-0000-7000-8000-000000000201",
                        "command": "ACCEPT_CLAIM",
                        "created_at": now,
                    }
                ],
                "ai_summary_decisions": [
                    {
                        "decision_id": "019f8100-0000-7000-8000-000000000202",
                        "command": "REJECT_AI_SUMMARY",
                        "created_at": now,
                    }
                ],
            },
        }
    )

    assert review.content_preparation is not None
    assert review.content_preparation.fact_decisions[0].command == "ACCEPT_CLAIM"
    assert review.content_preparation.ai_summary_decisions[0].command == "REJECT_AI_SUMMARY"


def test_owner_review_rejects_forged_visible_character_count() -> None:
    from srbg_contracts import ContentSummaryCandidateV2

    with pytest.raises(ValidationError, match="visible character count"):
        ContentSummaryCandidateV2.model_validate(
            {
                "visible_character_count": 300,
                "paragraphs": [
                    {
                        "kind": "FACT",
                        "section": "WHAT_HAPPENED",
                        "text": "短事实",
                        "claim_ids": ["019f8100-0000-7000-8000-000000000002"],
                    },
                    {
                        "kind": "JUDGMENT",
                        "section": "ENGINEERING_IMPACT",
                        "text": "短判断",
                        "judgment_type": "ENGINEERING_SIGNIFICANCE",
                    },
                    {
                        "kind": "JUDGMENT",
                        "section": "LIMITATIONS_AND_FOLLOW_UP",
                        "text": "短限制",
                        "judgment_type": "LIMITATION_AND_FOLLOW_UP",
                    },
                ],
            }
        )
