# ruff: noqa: RUF001
from datetime import UTC, datetime
from uuid import UUID

from srbg_contracts import EventAppendixV2

EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000111")
CLAIM_ID = UUID("019f7c00-0000-7000-8000-000000000112")
EVIDENCE_ID = UUID("019f7c00-0000-7000-8000-000000000113")
NOW = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)


def test_reader_appendix_keeps_governance_facts_in_distinct_typed_groups() -> None:
    appendix = EventAppendixV2.model_validate(
        {
            "event_id": EVENT_ID,
            "claims": [
                {
                    "id": CLAIM_ID,
                    "claim_type": "SAFETY_FACT",
                    "label": "通报阶段",
                    "value": "最终调查",
                    "evidence_ids": [EVIDENCE_ID],
                    "decision_status": "ACCEPTED",
                }
            ],
            "evidence": [
                {
                    "id": EVIDENCE_ID,
                    "claim_ids": [CLAIM_ID],
                    "excerpt": "调查报告认定该材料为最终调查结论。",
                    "excerpt_sha256": "a" * 64,
                    "original_url": "https://example.gov.cn/investigation/1",
                    "paragraph_id": "html-p-0001",
                    "char_start": 0,
                    "char_end": 18,
                }
            ],
            "automatic_results": [
                {
                    "signal_id": "019f7c00-0000-7000-8000-000000000114",
                    "result_type": "UNVERIFIED_AI",
                    "title": "模型候选，不是证据事实",
                    "original_url": "https://example.gov.cn/investigation/1",
                }
            ],
            "relationships": [
                {
                    "id": "019f7c00-0000-7000-8000-000000000115",
                    "event_id": EVENT_ID,
                    "from_item_id": "019f7c00-0000-7000-8000-000000000116",
                    "to_item_id": "019f7c00-0000-7000-8000-000000000117",
                    "relation_type": "INVESTIGATES",
                    "from_stage": "FINAL_INVESTIGATION",
                    "to_stage": "INITIAL_REPORT",
                    "reviewed_at": NOW,
                }
            ],
            "automatic_relationships": [
                {
                    "id": "019f7c00-0000-7000-8000-000000000118",
                    "relationship_key": "follow-up:final:initial",
                    "kind": "FOLLOW_UP_OF",
                    "source_item_id": "019f7c00-0000-7000-8000-000000000116",
                    "target_item_id": "019f7c00-0000-7000-8000-000000000117",
                    "status": "ACTIVE",
                    "score_bps": 9200,
                    "reason_codes": ["REPORT_STAGE_SEQUENCE"],
                    "algorithm_version": "relationship-v1",
                    "input_fingerprint_sha256": "b" * 64,
                    "created_at": NOW,
                }
            ],
            "corrections": [
                {
                    "id": "019f7c00-0000-7000-8000-000000000119",
                    "kind": "SOURCE_CORRECTED",
                    "description": "来源更正导致当前摘录与总结失效。",
                    "occurred_at": NOW,
                    "affects": ["SOURCE_EXCERPT", "AI_SUMMARY"],
                    "document_version_id": "019f7c00-0000-7000-8000-000000000120",
                }
            ],
            "review_context": {
                "case_id": "019f7c00-0000-7000-8000-000000000121",
                "href": "/review?case_id=019f7c00-0000-7000-8000-000000000121",
            },
            "content_summary": {
                "total_items": 6,
                "heavy_content": True,
                "truncated_sections": ["EVIDENCE"],
            },
        }
    )

    assert appendix.relationships[0].from_stage == "FINAL_INVESTIGATION"
    assert appendix.automatic_relationships[0].kind == "FOLLOW_UP_OF"
    assert appendix.corrections[0].affects == ["SOURCE_EXCERPT", "AI_SUMMARY"]
    assert appendix.review_context is not None
    assert appendix.review_context.href.endswith(str(appendix.review_context.case_id))
    assert appendix.content_summary.heavy_content is True


def test_reader_appendix_has_a_safe_review_list_fallback_and_empty_summary() -> None:
    appendix = EventAppendixV2(event_id=EVENT_ID)

    assert appendix.review_context is None
    assert appendix.review_href == "/review"
    assert appendix.content_summary.total_items == 0
    assert appendix.content_summary.heavy_content is False
