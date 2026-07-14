from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_api.safety_regulations.query import InvalidFeedCursor, _decode_cursor, _encode_cursor
from srbg_contracts import (
    FeedNotice,
    FeedPage,
    ItemDetail,
    ItemSummary,
    ReviewDecisionResponse,
    ReviewTaskDetail,
    ReviewTaskSummary,
)

ITEM_ID = UUID("019b0000-0000-7000-8000-000000006001")
TASK_ID = UUID("019b0000-0000-7000-8000-000000006002")
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000006003")
NOW = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)


def test_malformed_base64_cursor_is_rejected_as_an_invalid_feed_cursor() -> None:
    with pytest.raises(InvalidFeedCursor):
        _decode_cursor("a")


def test_feed_cursor_decodes_to_database_driver_native_types() -> None:
    decoded = _decode_cursor(_encode_cursor(NOW, ITEM_ID))

    assert decoded == (NOW, ITEM_ID)
    assert isinstance(decoded[0], datetime)
    assert isinstance(decoded[1], UUID)


def _pending_item() -> ItemSummary:
    return ItemSummary(
        id=ITEM_ID,
        publication_revision_id=None,
        domain="SAFETY",
        content_type="SAFETY_REGULATION",
        title="生产安全事故应急预案管理办法",
        source_name="应急管理部",
        source_published_at=datetime(2016, 6, 3, 10, 28, tzinfo=UTC),
        first_discovered_at=NOW,
        activity_at=NOW,
        original_url="https://www.mem.gov.cn/example.shtml",
        review_status="PENDING",
    )


class StubQueryService:
    async def get_feed(self, **_: object) -> FeedPage:
        return FeedPage(
            items=[_pending_item()],
            next_cursor=None,
            fingerprint="sha256:pending",
            generated_at=NOW,
            freshness="fresh",
            notices=[
                FeedNotice(
                    code="R3_RESTRICTED",
                    level="info",
                    message="待人工审核; 暂不展示敏感字段。",
                )
            ],
        )

    async def get_item(self, item_id: UUID) -> ItemDetail:
        assert item_id == ITEM_ID
        return ItemDetail(
            item=_pending_item(),
            notice=FeedNotice(
                code="R3_RESTRICTED",
                level="info",
                message="待人工审核; 暂不展示敏感字段。",
            ),
        )

    async def list_review_tasks(self) -> list[ReviewTaskSummary]:
        return [
            ReviewTaskSummary(
                id=TASK_ID,
                item_id=ITEM_ID,
                status="PENDING",
                risk_level="R3",
                title="生产安全事故应急预案管理办法",
                source_name="应急管理部",
                submitted_by=UUID("019b0000-0000-7000-8000-000000006004"),
                submitted_at=NOW,
            )
        ]

    async def get_review_task(self, task_id: UUID) -> ReviewTaskDetail:
        assert task_id == TASK_ID
        raise NotImplementedError


class StubPublicationService:
    reviewer_id: UUID | None = None

    async def decide_review(
        self,
        review_task_id: UUID,
        *,
        action: str,
        reason: str,
        reviewer_id: UUID,
    ) -> ReviewDecisionResponse:
        assert review_task_id == TASK_ID
        assert action == "APPROVE"
        assert reason
        self.reviewer_id = reviewer_id
        return ReviewDecisionResponse(
            review_task_id=TASK_ID,
            status="APPROVED",
            publication_revision_id=UUID("019b0000-0000-7000-8000-000000006005"),
        )


def _client() -> tuple[TestClient, StubPublicationService]:
    publication = StubPublicationService()
    app = create_app(
        checkers={},
        source_service=None,
        intelligence_service=StubQueryService(),
        publication_service=publication,
    )
    return TestClient(app), publication


def test_viewer_feed_and_detail_receive_only_r3_whitelist() -> None:
    client, _ = _client()
    headers = {"X-SRBG-Local-Roles": "viewer"}

    feed = client.get("/api/v1/feed?mode=all&domain=safety", headers=headers)
    detail = client.get(f"/api/v1/items/{ITEM_ID}", headers=headers)

    assert feed.status_code == 200
    item = feed.json()["items"][0]
    assert item["publication_revision_id"] is None
    assert set(item) == {
        "id",
        "publication_revision_id",
        "domain",
        "content_type",
        "title",
        "source_name",
        "source_published_at",
        "first_discovered_at",
        "activity_at",
        "original_url",
        "review_status",
    }
    assert detail.status_code == 200
    assert "claims" not in detail.json()
    assert "evidence" not in detail.json()


def test_viewer_cannot_approve_and_request_cannot_smuggle_publication_state() -> None:
    client, _ = _client()
    payload = {"action": "APPROVE", "reason": "looks good"}

    denied = client.post(
        f"/api/v1/admin/review-tasks/{TASK_ID}/decisions",
        headers={"X-SRBG-Local-Roles": "viewer"},
        json=payload,
    )
    smuggled = client.post(
        f"/api/v1/admin/review-tasks/{TASK_ID}/decisions",
        headers={"X-SRBG-Local-Roles": "reviewer"},
        json=payload | {"publication_status": "PUBLISHED"},
    )

    assert denied.status_code == 403
    assert smuggled.status_code == 422


def test_reviewer_identity_is_server_parsed_and_passed_to_publication_service() -> None:
    client, publication = _client()

    response = client.post(
        f"/api/v1/admin/review-tasks/{TASK_ID}/decisions",
        headers={
            "X-SRBG-Local-Roles": "reviewer",
            "X-SRBG-Local-User-ID": str(REVIEWER_ID),
        },
        json={"action": "APPROVE", "reason": "evidence matches"},
    )

    assert response.status_code == 200
    assert publication.reviewer_id == REVIEWER_ID
