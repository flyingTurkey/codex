from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_api.safety_regulations.query import InvalidFeedCursor, _decode_cursor, _encode_cursor
from srbg_contracts import (
    EventSummary,
    FeedNotice,
    FeedPage,
    HotTopicPage,
    ItemDetail,
    SourceComparison,
)

ITEM_ID = UUID("019b0000-0000-7000-8000-000000006001")
TASK_ID = UUID("019b0000-0000-7000-8000-000000006002")
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000006003")
NOW = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)
ClusterCandidateView = dict
ReviewTaskSummary = dict
ReviewDecisionResponse = dict


def test_malformed_base64_cursor_is_rejected_as_an_invalid_feed_cursor() -> None:
    with pytest.raises(InvalidFeedCursor):
        _decode_cursor("a")


def test_feed_cursor_decodes_to_database_driver_native_types() -> None:
    decoded = _decode_cursor(_encode_cursor(NOW, ITEM_ID))

    assert decoded == (NOW, ITEM_ID)
    assert isinstance(decoded[0], datetime)
    assert isinstance(decoded[1], UUID)


def _pending_item() -> EventSummary:
    return EventSummary(
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
        event_type="REGULATION_CHANGE",
        event_status="ACTIVE",
        canonical_event_id=ITEM_ID,
        event_version=1,
    )


class StubQueryService:
    feed_arguments: dict[str, object] | None = None

    async def get_feed(self, **arguments: object) -> FeedPage:
        self.feed_arguments = arguments
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

    async def list_product_normalization_candidates(self, *, status: str) -> list[object]:
        assert status == "PENDING_REVIEW"
        return []

    async def get_citation(self, item_id: UUID, citation_format: str) -> tuple[str, str]:
        assert item_id == ITEM_ID
        assert citation_format == "gb-t-7714"
        return "张三. 桥梁数字孪生研究[J]. 中国公路学报, 2025.", "text/plain; charset=utf-8"

    async def list_hot_topics(self, **arguments: object) -> HotTopicPage:
        assert arguments["window_days"] in {7, 14, 30}
        return HotTopicPage(
            items=[],
            generated_at=NOW,
            evaluation_tier="INTERNAL_TEST_FIXTURE",
            auto_merge_enabled=False,
        )

    async def get_source_comparison(self, event_id: UUID) -> SourceComparison:
        return SourceComparison(event_id=event_id, independent_source_count=0, sources=[])

    async def list_cluster_candidates(
        self, *, kind: str, status: str
    ) -> list[object]:
        assert kind == "DUPLICATE"
        assert status == "PENDING_REVIEW"
        return [
            ClusterCandidateView(
                id=TASK_ID,
                kind="DUPLICATE",
                status="PENDING_REVIEW",
                member_ids=[ITEM_ID, UUID("019b0000-0000-7000-8000-000000006009")],
                score_bps=9800,
                feature_explanations=["标题相似"],
                hard_conflicts=[],
                created_at=NOW,
            )
        ]

    async def list_review_tasks(self) -> list[object]:
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

    async def get_review_task(self, task_id: UUID) -> object:
        assert task_id == TASK_ID
        raise NotImplementedError


class StubPublicationService:
    reviewer_id: UUID | None = None
    digital_case_patch: object | None = None
    product_normalization_action: str | None = None
    cluster_action: str | None = None
    score_override: tuple[str, int] | None = None

    async def decide_review(
        self,
        review_task_id: UUID,
        *,
        action: str,
        reason: str,
        reviewer_id: UUID,
        digital_case_patch: object | None = None,
    ) -> object:
        assert review_task_id == TASK_ID
        assert action == "APPROVE"
        assert reason
        self.reviewer_id = reviewer_id
        self.digital_case_patch = digital_case_patch
        return ReviewDecisionResponse(
            review_task_id=TASK_ID,
            status="APPROVED",
            publication_revision_id=UUID("019b0000-0000-7000-8000-000000006005"),
        )

    async def decide_product_normalization(
        self,
        candidate_id: UUID,
        *,
        action: str,
        reason: str,
        reviewer_id: UUID,
    ) -> None:
        assert candidate_id == TASK_ID
        assert reason
        assert reviewer_id == REVIEWER_ID
        self.product_normalization_action = action

    async def decide_cluster(self, candidate_id: UUID, **values: object) -> None:
        assert candidate_id == TASK_ID
        assert values["reason"]
        assert values["reviewer_id"] == REVIEWER_ID
        self.cluster_action = str(values["action"])

    async def override_score(self, item_id: UUID, **values: object) -> None:
        assert item_id == ITEM_ID
        assert values["reviewer_id"] == REVIEWER_ID
        self.score_override = (str(values["dimension"]), int(values["score"]))


def _client() -> tuple[TestClient, StubPublicationService]:
    publication = StubPublicationService()
    app = create_app(
        checkers={},
        source_service=None,
        intelligence_service=StubQueryService(),
        publication_service=publication,
    )
    return TestClient(app, headers={"X-SRBG-Local-Step-Up": "true"}), publication


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
        "event_type",
        "event_status",
        "canonical_event_id",
        "event_version",
    }
    assert detail.status_code == 200
    assert detail.headers["deprecation"].startswith("@")
    assert f"</api/v1/events/{ITEM_ID}>; rel=\"successor-version\"" in detail.headers["link"]
    assert "sunset" not in detail.headers
    assert "claims" not in detail.json()
    assert "evidence" not in detail.json()


def test_legacy_review_decision_api_is_unavailable() -> None:
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

    assert denied.status_code == 404
    assert smuggled.status_code == 404


def test_hot_topics_remain_readable_but_legacy_governance_writes_are_unavailable() -> None:
    client, publication = _client()
    viewer = {"X-SRBG-Local-Roles": "viewer"}
    reviewer = {
        "X-SRBG-Local-Roles": "reviewer",
        "X-SRBG-Local-User-ID": str(REVIEWER_ID),
    }
    other_item = "019b0000-0000-7000-8000-000000006009"

    hot = client.get("/api/v1/hot-topics?window=14d", headers=viewer)
    denied = client.post(
        f"/api/v1/admin/clustering-workbench/DUPLICATE/{TASK_ID}/decisions",
        headers=viewer,
        json={
            "action": "MERGE",
            "member_ids": [str(ITEM_ID), other_item],
            "reason": "证据一致",
        },
    )
    queue = client.get(
        "/api/v1/admin/clustering-workbench?kind=DUPLICATE&status=PENDING_REVIEW",
        headers=reviewer,
    )
    decided = client.post(
        f"/api/v1/admin/clustering-workbench/DUPLICATE/{TASK_ID}/decisions",
        headers=reviewer,
        json={
            "action": "MERGE",
            "member_ids": [str(ITEM_ID), other_item],
            "reason": "同一项目、标段和阶段, 证据一致",
        },
    )
    overridden = client.post(
        f"/api/v1/admin/items/{ITEM_ID}/score-overrides",
        headers=reviewer,
        json={"dimension": "IMPACT", "score": 70, "reason": "正式文件确认影响范围"},
    )
    smuggled = client.post(
        f"/api/v1/admin/items/{ITEM_ID}/score-overrides",
        headers=reviewer,
        json={
            "dimension": "IMPACT",
            "score": 70,
            "reason": "正式文件确认影响范围",
            "publication_status": "PUBLISHED",
        },
    )

    assert hot.status_code == 200
    assert hot.json()["auto_merge_enabled"] is False
    assert denied.status_code == 404
    assert queue.status_code == 404
    assert decided.status_code == 404
    assert overridden.status_code == 404
    assert smuggled.status_code == 404
    assert publication.cluster_action is None
    assert publication.score_override is None


def test_legacy_reviewer_identity_endpoint_is_unavailable() -> None:
    client, publication = _client()

    response = client.post(
        f"/api/v1/admin/review-tasks/{TASK_ID}/decisions",
        headers={
            "X-SRBG-Local-Roles": "reviewer",
            "X-SRBG-Local-User-ID": str(REVIEWER_ID),
        },
        json={"action": "APPROVE", "reason": "evidence matches"},
    )

    assert response.status_code == 404
    assert publication.reviewer_id is None


def test_digital_feed_filters_are_forwarded_to_the_shared_query_service() -> None:
    client, _ = _client()
    query = client.app.state.intelligence_service

    response = client.get(
        "/api/v1/feed?domain=digital&content_type=DIGITAL_CASE"
        "&engineering_domain=BRIDGE&scenario=SMART_BEAM_FACTORY"
        "&maturity=SINGLE_PROJECT_PRODUCTION"
        "&source_nature=ENTERPRISE_SELF_REPORT&sort=relevance",
        headers={"X-SRBG-Local-Roles": "viewer"},
    )

    assert response.status_code == 200
    assert query.feed_arguments == {
        "mode": "all",
        "domain": "digital",
        "content_type": "DIGITAL_CASE",
        "engineering_domain": "BRIDGE",
        "scenario": "SMART_BEAM_FACTORY",
        "maturity": "SINGLE_PROJECT_PRODUCTION",
        "source_nature": "ENTERPRISE_SELF_REPORT",
        "paper_type": None,
        "technology_tag": None,
        "access_level": None,
        "year": None,
        "product_kind": None,
        "evidence_level": None,
            "deployment_mode": None,
            "region": None,
            "source_id": None,
            "source_authority": None,
            "published_from": None,
            "published_to": None,
            "review_status": None,
            "evidence_status": None,
            "sort": "relevance",
        "cursor": None,
        "limit": 20,
    }


def test_paper_filters_and_citation_use_existing_item_resource() -> None:
    client, _ = _client()
    query = client.app.state.intelligence_service
    headers = {"X-SRBG-Local-Roles": "viewer"}

    feed = client.get(
        "/api/v1/feed?domain=digital&content_type=JOURNAL_PAPER"
        "&engineering_domain=BRIDGE&technology_tag=DIGITAL_TWIN"
        "&paper_type=ARTICLE&access_level=METADATA_ONLY&year=2025",
        headers=headers,
    )
    citation = client.get(f"/api/v1/items/{ITEM_ID}/citation?format=gb-t-7714", headers=headers)

    assert feed.status_code == 200
    assert query.feed_arguments is not None
    assert query.feed_arguments["content_type"] == "JOURNAL_PAPER"
    assert query.feed_arguments["technology_tag"] == "DIGITAL_TWIN"
    assert query.feed_arguments["paper_type"] == "ARTICLE"
    assert query.feed_arguments["access_level"] == "METADATA_ONLY"
    assert query.feed_arguments["year"] == 2025
    assert citation.status_code == 200
    assert "桥梁数字孪生研究" in citation.text


def test_product_filters_are_forwarded_to_the_unified_feed_service() -> None:
    client, _ = _client()
    query = client.app.state.intelligence_service
    response = client.get(
        "/api/v1/feed?domain=digital&content_type=LOW_ALTITUDE_EQUIPMENT"
        "&product_kind=UAV_DOCK&evidence_level=VENDOR_CLAIM_ONLY"
        "&deployment_mode=EDGE&scenario=INSPECTION&maturity=ENGINEERING_PROTOTYPE",
        headers={"X-SRBG-Local-Roles": "viewer"},
    )

    assert response.status_code == 200
    assert query.feed_arguments is not None
    assert query.feed_arguments["content_type"] == "LOW_ALTITUDE_EQUIPMENT"
    assert query.feed_arguments["product_kind"] == "UAV_DOCK"
    assert query.feed_arguments["evidence_level"] == "VENDOR_CLAIM_ONLY"
    assert query.feed_arguments["deployment_mode"] == "EDGE"


def test_legacy_digital_case_review_patch_is_unavailable() -> None:
    client, publication = _client()
    patch = {
        "engineering_domains": ["BRIDGE"],
        "lifecycle_stages": ["CONSTRUCTION"],
        "technology_tags": ["BIM"],
        "application_scenarios": ["SMART_BEAM_FACTORY"],
        "maturity_level": "SINGLE_PROJECT_PRODUCTION",
        "maturity_evidence_ids": ["019b0000-0000-7000-8000-000000050010"],
        "outcome_attributions": [],
    }

    response = client.post(
        f"/api/v1/admin/review-tasks/{TASK_ID}/decisions",
        headers={"X-SRBG-Local-Roles": "reviewer"},
        json={"action": "APPROVE", "reason": "evidence matches", "digital_case_patch": patch},
    )

    assert response.status_code == 404
    assert publication.digital_case_patch is None


def test_product_normalization_review_api_is_retired() -> None:
    client, publication = _client()
    payload = {"action": "KEEP_DISTINCT", "reason": "型号不同，保持独立产品记录"}  # noqa: RUF001
    denied = client.post(
        f"/api/v1/admin/product-normalization-candidates/{TASK_ID}/decision",
        headers={"X-SRBG-Local-Roles": "viewer"},
        json=payload,
    )
    accepted = client.post(
        f"/api/v1/admin/product-normalization-candidates/{TASK_ID}/decision",
        headers={
            "X-SRBG-Local-Roles": "reviewer",
            "X-SRBG-Local-User-ID": str(REVIEWER_ID),
        },
        json=payload,
    )

    assert denied.status_code == 404
    assert accepted.status_code == 404
    assert publication.product_normalization_action is None
