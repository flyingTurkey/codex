from datetime import UTC, date, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import (
    CollectionSummary,
    DailyReport,
    FeedPage,
    FingerprintResponse,
)

USER_ID = UUID("019b0000-0000-7000-8000-000000009001")
COLLECTION_ID = UUID("019b0000-0000-7000-8000-000000009101")
REPORT_ID = UUID("019b0000-0000-7000-8000-000000009201")
NOW = datetime(2026, 7, 15, tzinfo=UTC)


class FakePortalService:
    def __init__(self) -> None:
        self.saved: list[tuple[UUID, UUID, UUID | None, str]] = []

    async def close(self) -> None:
        pass

    async def search(self, **_: object) -> FeedPage:
        return FeedPage(
            items=[],
            next_cursor=None,
            fingerprint="search-v1",
            generated_at=NOW,
            freshness="fresh",
            notices=[],
        )

    async def list_saved(self, **_: object) -> FeedPage:
        return FeedPage(
            items=[],
            next_cursor=None,
            fingerprint="saved-v1",
            generated_at=NOW,
            freshness="fresh",
            notices=[],
        )

    async def save_item(
        self,
        *,
        owner_id: UUID,
        item_id: UUID,
        collection_id: UUID | None,
        idempotency_key: str,
    ) -> None:
        self.saved.append((owner_id, item_id, collection_id, idempotency_key))

    async def remove_saved_item(self, **_: object) -> None:
        pass

    async def list_collections(self, **_: object) -> list[CollectionSummary]:
        return [self._collection()]

    async def create_collection(self, **_: object) -> CollectionSummary:
        return self._collection()

    async def patch_collection(self, **_: object) -> CollectionSummary:
        return self._collection(version=2)

    async def get_daily(self, **_: object) -> DailyReport:
        return self._report(status="PUBLISHED")

    async def get_report(self, **_: object) -> DailyReport:
        return self._report(status="PUBLISHED")

    async def export_markdown(self, **_: object) -> str:
        return "# 四川路桥行业日报\n\n'=2+2"

    async def fingerprint(self, **_: object) -> FingerprintResponse:
        return FingerprintResponse(
            generated_at=NOW,
            feed_generation=1,
            search_generation=1,
            hot_topics_generation=1,
            latest_daily_report_id=REPORT_ID,
            fingerprint="sha256:" + "a" * 64,
        )

    @staticmethod
    def _collection(version: int = 1) -> CollectionSummary:
        return CollectionSummary(
            id=COLLECTION_ID,
            name="隧道专题",
            item_count=0,
            archived=False,
            version=version,
            created_at=NOW,
            updated_at=NOW,
        )

    @staticmethod
    def _report(status: str = "DRAFT") -> DailyReport:
        return DailyReport(
            id=REPORT_ID,
            report_date=date(2026, 7, 15),
            status=status,
            snapshot_at=NOW,
            published_at=NOW if status == "PUBLISHED" else None,
            requires_regeneration=False,
            sections=[],
        )


class FakePublicationService:
    def __init__(self) -> None:
        self.draft_calls: list[tuple[date, UUID, str]] = []
        self.publish_calls: list[tuple[UUID, UUID, str]] = []

    async def close(self) -> None:
        pass

    async def create_daily_draft(
        self,
        *,
        report_date: date,
        actor_id: UUID,
        idempotency_key: str,
    ) -> DailyReport:
        self.draft_calls.append((report_date, actor_id, idempotency_key))
        return FakePortalService._report()

    async def publish_daily_report(
        self,
        report_id: UUID,
        *,
        reviewer_id: UUID,
        idempotency_key: str,
    ) -> DailyReport:
        self.publish_calls.append((report_id, reviewer_id, idempotency_key))
        return FakePortalService._report(status="PUBLISHED")


def _client() -> tuple[TestClient, FakePortalService, FakePublicationService]:
    portal = FakePortalService()
    publication = FakePublicationService()
    return (
        TestClient(create_app(portal_service=portal, publication_service=publication)),
        portal,
        publication,
    )


def test_search_supports_etag_and_conditional_get() -> None:
    client, _, _ = _client()
    response = client.get("/api/v1/search", params={"q": "隧道+监测预警+四川"})
    assert response.status_code == 200
    assert response.headers["etag"].startswith('"sha256:')

    cached = client.get(
        "/api/v1/search",
        params={"q": "隧道+监测预警+四川"},
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert cached.status_code == 304
    assert cached.content == b""


def test_saved_item_requires_idempotency_key_and_uses_current_principal() -> None:
    client, portal, _ = _client()
    item_id = "019b0000-0000-7000-8000-000000009301"
    deprecated = client.post("/api/v1/saved-items", json={"item_id": item_id})
    assert deprecated.status_code == 410
    assert deprecated.headers["deprecation"].startswith("@")
    assert f"/api/v1/events/{item_id}" in deprecated.headers["link"]

    response = client.post(
        "/api/v1/saved-items",
        json={"item_id": item_id},
        headers={"Idempotency-Key": "save-item-0001"},
    )
    assert response.status_code == 410
    assert portal.saved == []


def test_collection_patch_requires_if_match() -> None:
    client, _, _ = _client()
    missing = client.patch(f"/api/v1/collections/{COLLECTION_ID}", json={"name": "桥梁专题"})
    assert missing.status_code == 428
    updated = client.patch(
        f"/api/v1/collections/{COLLECTION_ID}",
        json={"name": "桥梁专题"},
        headers={"If-Match": '"1"'},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2


def test_daily_draft_and_publish_are_reviewer_only_and_delegate_to_publication_service() -> None:
    client, _, publication = _client()
    payload = {"report_date": "2026-07-15"}
    headers = {"Idempotency-Key": "daily-draft-0001"}
    forbidden = client.post("/api/v1/admin/daily/drafts", json=payload, headers=headers)
    assert forbidden.status_code == 403

    reviewer_headers = {**headers, "X-SRBG-Local-Roles": "reviewer"}
    draft = client.post("/api/v1/admin/daily/drafts", json=payload, headers=reviewer_headers)
    assert draft.status_code == 201
    published = client.post(
        f"/api/v1/admin/daily/{REPORT_ID}/publish",
        headers={"Idempotency-Key": "daily-publish-0001", "X-SRBG-Local-Roles": "reviewer"},
    )
    assert published.status_code == 200
    assert publication.draft_calls == [(date(2026, 7, 15), USER_ID, "daily-draft-0001")]
    assert publication.publish_calls == [(REPORT_ID, USER_ID, "daily-publish-0001")]


def test_markdown_export_is_private_and_attachment_safe() -> None:
    client, _, _ = _client()
    response = client.get("/api/v1/export/markdown", params={"report_id": str(REPORT_ID)})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["cache-control"] == "private, no-store"
    assert response.text.startswith("# 四川路桥行业日报")
