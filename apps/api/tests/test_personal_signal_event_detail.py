from __future__ import annotations

from uuid import UUID

import pytest
from srbg_api.internal_projection.reader import PublishedEventNotFound
from srbg_api.internal_projection.service import PublishedIntelligenceQueryService
from srbg_contracts import PublishedEventDetailV1

EVENT_ID = UUID("019f75c0-e4dd-7c55-882c-86dfbed2d9f4")
SIGNAL_ID = UUID("019f75c0-e4dd-7c55-882c-86dfbed2d9f5")
CLAIM_ID = UUID("019f75c0-e4dd-7c55-882c-86dfbed2d9f6")
EVIDENCE_ID = UUID("019f75c0-e4dd-7c55-882c-86dfbed2d9f7")


class _PersonalOnlyReader:
    async def get_event(self, event_id: UUID):
        raise PublishedEventNotFound(str(event_id))

    async def list_personal_signals_for_event(self, event_id: UUID):
        assert event_id == EVENT_ID
        return [
            {
                "signal_id": SIGNAL_ID,
                "event_id": EVENT_ID,
                "result_type": "EVIDENCE_FACT",
                "generation": 2,
                "payload": {
                    "title": "国务院公开政策",
                    "original_url": "https://www.gov.cn/zhengce/example.htm",
                    "source_name": "中国政府网政策",
                    "domain": "DIGITAL",
                    "content_type": "DIGITAL_CASE",
                    "source_published_at": None,
                    "first_discovered_at": "2026-07-18T12:00:00Z",
                    "activity_at": "2026-07-18T12:00:00Z",
                    "review_status": "PENDING",
                    "event_type": "DIGITAL_PROJECT",
                    "evidence_facts": [
                        {
                            "claim_id": str(CLAIM_ID),
                            "fact_kind": "EVIDENCE_FACT",
                            "field_name": "title",
                            "value": "国务院公开政策",
                            "evidence": [
                                {
                                    "evidence_id": str(EVIDENCE_ID),
                                    "excerpt_sha256": "a" * 64,
                                    "locator": "HTML_PARAGRAPH",
                                }
                            ],
                        }
                    ],
                },
            }
        ]


class _MetadataAndPersonalReader(_PersonalOnlyReader):
    async def get_event(self, event_id: UUID):
        return PublishedEventDetailV1.model_validate(
            {
                "summary": {
                    "id": str(EVENT_ID),
                    "publication_revision_id": None,
                    "projection_version": "1.1.0",
                    "generation": 5,
                    "domain": "DIGITAL",
                    "content_type": "DIGITAL_CASE",
                    "title": "国务院公开政策",
                    "source_name": "中国政府网政策",
                    "source_published_at": None,
                    "first_discovered_at": "2026-07-18T12:00:00Z",
                    "original_url": "https://www.gov.cn/zhengce/example.htm",
                    "review_status": "PENDING",
                    "discovery_status": "MACHINE_DISCOVERED",
                    "fact_review_status": "PENDING_HUMAN_REVIEW",
                    "publication_risk_tier": "R3",
                    "content_severity": "UNASSESSED",
                    "projection_level": "METADATA_ONLY",
                },
                "claims": [],
                "evidence": [],
            }
        )


class _DuplicateFeedReader(_MetadataAndPersonalReader):
    async def list_events(self, *, limit: int):
        assert limit == 20
        return [(await self.get_event(EVENT_ID)).summary]

    async def list_personal_signals(self, *, limit: int):
        assert limit == 20
        return await self.list_personal_signals_for_event(EVENT_ID)


@pytest.mark.asyncio
async def test_personal_signal_event_has_detail_and_evidence_when_legacy_projection_is_absent():
    service = PublishedIntelligenceQueryService(_PersonalOnlyReader())  # type: ignore[arg-type]

    detail = await service.get_event(EVENT_ID)

    assert detail.id == EVENT_ID
    assert detail.title == "国务院公开政策"
    assert [claim.claim_id for claim in detail.claims] == [CLAIM_ID]
    assert [evidence.evidence_id for evidence in detail.evidence] == [EVIDENCE_ID]
    assert detail.evidence[0].content_sha256 == "a" * 64
    assert detail.automatic_results[0].result_type == "EVIDENCE_FACT"


@pytest.mark.asyncio
async def test_personal_evidence_enriches_metadata_only_projection() -> None:
    service = PublishedIntelligenceQueryService(_MetadataAndPersonalReader())  # type: ignore[arg-type]

    detail = await service.get_event(EVENT_ID)

    assert [claim.claim_id for claim in detail.claims] == [CLAIM_ID]
    assert [evidence.evidence_id for evidence in detail.evidence] == [EVIDENCE_ID]


@pytest.mark.asyncio
async def test_feed_collapses_metadata_and_evidence_projection_for_same_event() -> None:
    service = PublishedIntelligenceQueryService(_DuplicateFeedReader())  # type: ignore[arg-type]

    feed = await service.get_feed()

    assert [item.id for item in feed.items] == [EVENT_ID]
    assert feed.items[0].automatic_result_type == "EVIDENCE_FACT"
