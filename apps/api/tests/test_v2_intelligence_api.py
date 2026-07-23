from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.intelligence_v2.service import MediaDeliveryUnavailable, ProjectionNotFound
from srbg_api.intelligence_v2.technical_exceptions import SafetyExceptionHardBlock
from srbg_api.main import create_app
from srbg_contracts import FeedPageV2, OwnerExceptionCommand

NOW = datetime(2026, 7, 19, tzinfo=UTC)
EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000011")
EXCEPTION_ID = UUID("019f7c00-0000-7000-8000-000000000012")
SAFETY_EXCEPTION_ID = UUID("019f7c00-0000-7000-8000-000000000112")


class FakeV2Service:
    async def close(self) -> None:
        pass

    async def feed(self, **filters: object) -> FeedPageV2:
        if filters.get("cursor") == "invalid":
            from srbg_api.intelligence_v2.cursor import InvalidV2Cursor

            raise InvalidV2Cursor("invalid")
        return FeedPageV2(items=[], generated_at=NOW)

    async def search(self, **_: object) -> FeedPageV2:
        return FeedPageV2(items=[], generated_at=NOW)

    async def hotspots(self, **_: object) -> FeedPageV2:
        return FeedPageV2(items=[], generated_at=NOW)

    async def event(self, event_id: UUID):
        raise ProjectionNotFound(str(event_id))

    async def appendix(self, event_id: UUID):
        from srbg_api.intelligence_v2.service import ProjectionNotFound

        raise ProjectionNotFound(str(event_id))

    async def review_cases(self, **_: object):
        return []

    async def review_case(self, case_id: UUID):
        return {
            "case_id": case_id,
            "event_id": None,
            "document_version_id": "019f7c00-0000-7000-8000-000000000095",
            "reason": "LOW_CONFIDENCE",
            "risk_tier": "R3",
            "safe_metadata": {"title": "待复核"},
            "state": "OPEN",
            "processing_state": "IDLE",
            "version": 1,
            "created_at": NOW,
            "updated_at": NOW,
        }

    async def quarantine(self, case_id: UUID):
        return {
            "projection_kind": "QUARANTINE",
            "case_id": case_id,
            "event_id": EVENT_ID,
            "title": "隔离内容",
            "primary_type": "SAFETY_INTELLIGENCE",
            "official_source": False,
            "source_published_at": None,
            "first_discovered_at": None,
            "original_url": "https://example.com/source/1",
            "isolation_reason": "UNRESOLVED_PROMPT_INJECTION",
        }

    async def decide(self, **_: object):
        return {
            "decision_id": "019f7c00-0000-7000-8000-000000000099",
            "case_id": "019f7c00-0000-7000-8000-000000000098",
            "version": 2,
            "recorded_at": NOW,
            "reprocessing_outbox_id": "019f7c00-0000-7000-8000-000000000096",
            "reprocessing_state": "QUEUED",
        }

    async def media_preview(self, media_id: UUID):
        return b"safe-image", "image/webp"

    async def media_download(self, media_id: UUID, *, max_age_seconds: int):
        assert max_age_seconds == 300
        return "https://objects.example/private?expires=300"


class FakeTechnicalExceptionService:
    async def close(self) -> None:
        pass

    async def list_exceptions(self, **_: object):
        return [self._view()]

    async def get_exception(self, exception_id: UUID):
        assert exception_id == EXCEPTION_ID
        return self._view()

    async def command(
        self,
        *,
        exception_id: UUID,
        command: OwnerExceptionCommand,
        owner_id: UUID,
        idempotency_key: UUID,
    ):
        del owner_id
        assert exception_id == EXCEPTION_ID
        assert command.event_type.value == "RETRY_REQUESTED"
        return {
            "id": "019f7c00-0000-7000-8000-000000000014",
            "exception_id": exception_id,
            "event_type": "RETRY_REQUESTED",
            "expected_version": 1,
            "idempotency_key": idempotency_key,
            "created_at": NOW,
        }

    @staticmethod
    def _view():
        return {
            "id": EXCEPTION_ID,
            "kind": "TECHNICAL",
            "status": "OPEN",
            "overrideability": None,
            "source_id": "019f7c00-0000-7000-8000-000000000015",
            "source_stream_id": "019f7c00-0000-7000-8000-000000000016",
            "document_version_id": "019f7c00-0000-7000-8000-000000000017",
            "decision_id": "019f7c00-0000-7000-8000-000000000018",
            "reason_codes": ["TECHNICAL_EXHAUSTED"],
            "attempt_count": 4,
            "version": 1,
            "opened_at": NOW,
            "updated_at": NOW,
            "resolved_at": None,
        }


class FakeSafetyExceptionService:
    async def close(self) -> None:
        pass

    async def list_exceptions(self, **filters: object):
        assert filters["kind"] == "SAFETY"
        return [self._view()]

    async def get_exception(self, exception_id: UUID):
        assert exception_id == SAFETY_EXCEPTION_ID
        return self._view()

    async def command(
        self,
        *,
        exception_id: UUID,
        command: OwnerExceptionCommand,
        owner_id: UUID,
        idempotency_key: UUID,
    ):
        del owner_id
        assert exception_id == SAFETY_EXCEPTION_ID
        if command.expected_version == 2:
            raise SafetyExceptionHardBlock("MALICIOUS_PAYLOAD")
        return {
            "id": "019f7c00-0000-7000-8000-000000000114",
            "exception_id": exception_id,
            "event_type": command.event_type.value,
            "expected_version": command.expected_version,
            "idempotency_key": idempotency_key,
            "created_at": NOW,
        }

    @staticmethod
    def _view():
        return {
            "id": SAFETY_EXCEPTION_ID,
            "kind": "SAFETY",
            "status": "OPEN",
            "overrideability": "OWNER_DECIDABLE",
            "source_id": "019f7c00-0000-7000-8000-000000000115",
            "source_stream_id": None,
            "document_version_id": "019f7c00-0000-7000-8000-000000000117",
            "decision_id": "019f7c00-0000-7000-8000-000000000118",
            "reason_codes": ["SAFETY_SIGNAL"],
            "safety_reason_code": "PROMPT_INJECTION_DETECTED",
            "safe_title": "疑似提示词注入内容",
            "source_name": "交通运输部",
            "discovered_at": NOW,
            "safe_evidence_ids": ["019f7c00-0000-7000-8000-000000000119"],
            "attempt_count": 0,
            "version": 1,
            "opened_at": NOW,
            "updated_at": NOW,
            "resolved_at": None,
        }


def test_v2_feed_starts_empty_and_uses_v2_generation() -> None:
    with TestClient(create_app(v2_intelligence_service=FakeV2Service())) as client:
        response = client.get("/api/v2/feed")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["projection_generation"] == "v2"


def test_unprojected_event_is_404_not_review_content() -> None:
    with TestClient(create_app(v2_intelligence_service=FakeV2Service())) as client:
        response = client.get(f"/api/v2/events/{EVENT_ID}")
    assert response.status_code == 404


def test_owner_quarantine_surface_returns_only_safe_metadata() -> None:
    case_id = UUID("019f7c00-0000-7000-8000-000000000098")
    with TestClient(create_app(v2_intelligence_service=FakeV2Service())) as client:
        response = client.get(f"/api/v2/review/quarantine/{case_id}")

    assert response.status_code == 200
    assert set(response.json()) == {
        "projection_kind",
        "case_id",
        "event_id",
        "title",
        "primary_type",
        "official_source",
        "source_published_at",
        "first_discovered_at",
        "original_url",
        "isolation_reason",
    }


def test_review_decision_requires_concurrency_and_idempotency_headers() -> None:
    case_id = UUID("019f7c00-0000-7000-8000-000000000098")
    body = {"command": "CONFIRM_RELEVANCE", "reason": "有直接工程影响证据", "expected_version": 1}
    with TestClient(create_app(v2_intelligence_service=FakeV2Service())) as client:
        missing = client.post(f"/api/v2/review/cases/{case_id}/decisions", json=body)
        accepted = client.post(
            f"/api/v2/review/cases/{case_id}/decisions",
            json=body,
            headers={"If-Match": '"1"', "Idempotency-Key": "019f7c00-0000-7000-8000-000000000097"},
        )
    assert missing.status_code == 422
    assert accepted.status_code == 202
    assert accepted.json()["reprocessing_state"] == "QUEUED"


def test_replaced_v1_reader_routes_are_gone() -> None:
    with TestClient(create_app(v2_intelligence_service=FakeV2Service())) as client:
        for path in (
            "/api/v1/feed",
            "/api/v1/search",
            "/api/v1/hot-topics",
            f"/api/v1/items/{EVENT_ID}",
            f"/api/v1/events/{EVENT_ID}",
            f"/api/v1/events/{EVENT_ID}/content",
        ):
            assert client.get(path).status_code == 404, path


def test_v2_media_preview_is_private_and_download_is_short_redirect() -> None:
    media_id = UUID("019f7c00-0000-7000-8000-000000000096")
    with TestClient(create_app(v2_intelligence_service=FakeV2Service())) as client:
        preview = client.get(f"/api/v2/media/{media_id}/preview")
        download = client.get(f"/api/v2/media/{media_id}/download", follow_redirects=False)
    assert preview.status_code == 200
    assert preview.headers["cache-control"] == "private, max-age=300"
    assert download.status_code == 302
    assert download.headers["cache-control"] == "no-store"
    assert download.headers["location"].endswith("expires=300")


def test_v2_media_storage_failure_is_problem_details_without_exposing_storage_error() -> None:
    class UnavailableMediaService(FakeV2Service):
        async def media_preview(self, media_id: UUID):
            del media_id
            raise MediaDeliveryUnavailable("s3 access key must never leak")

    media_id = UUID("019f7c00-0000-7000-8000-000000000096")
    with TestClient(create_app(v2_intelligence_service=UnavailableMediaService())) as client:
        response = client.get(f"/api/v2/media/{media_id}/preview")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "MEDIA_TEMPORARILY_UNAVAILABLE"
    assert "access key" not in response.text


def test_invalid_v2_cursor_returns_problem_details_with_stable_code() -> None:
    with TestClient(create_app(v2_intelligence_service=FakeV2Service())) as client:
        response = client.get("/api/v2/feed?cursor=invalid")
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "INVALID_CURSOR"


def test_review_case_uses_the_typed_safe_contract() -> None:
    case_id = UUID("019f7c00-0000-7000-8000-000000000098")
    with TestClient(create_app(v2_intelligence_service=FakeV2Service())) as client:
        response = client.get(f"/api/v2/review/cases/{case_id}")
    assert response.status_code == 200
    assert response.json()["processing_state"] == "IDLE"
    assert "document_version_id" in response.json()


def test_owner_technical_exception_api_is_filtered_safe_and_idempotency_guarded() -> None:
    service = FakeTechnicalExceptionService()
    app = create_app(technical_exception_service=service)
    with TestClient(app) as client:
        listed = client.get("/api/v2/owner/exceptions?kind=TECHNICAL&status=OPEN&limit=20")
        detail = client.get(f"/api/v2/owner/exceptions/{EXCEPTION_ID}")
        missing_headers = client.post(
            f"/api/v2/owner/exceptions/{EXCEPTION_ID}/commands",
            json={
                "exception_id": str(EXCEPTION_ID),
                "event_type": "RETRY_REQUESTED",
                "expected_version": 1,
            },
        )
        retried = client.post(
            f"/api/v2/owner/exceptions/{EXCEPTION_ID}/commands",
            json={
                "exception_id": str(EXCEPTION_ID),
                "event_type": "RETRY_REQUESTED",
                "expected_version": 1,
            },
            headers={
                "If-Match": '"1"',
                "Idempotency-Key": "019f7c00-0000-7000-8000-000000000019",
            },
        )
        forbidden_safety_action = client.post(
            f"/api/v2/owner/exceptions/{EXCEPTION_ID}/commands",
            json={
                "exception_id": str(EXCEPTION_ID),
                "event_type": "OWNER_ALLOWED",
                "expected_version": 1,
            },
            headers={
                "If-Match": '"1"',
                "Idempotency-Key": "019f7c00-0000-7000-8000-000000000020",
            },
        )

    assert listed.status_code == 200
    assert listed.json() == [detail.json()]
    assert "safe_metadata" not in detail.json()
    assert "url" not in detail.text.casefold()
    assert missing_headers.status_code == 422
    assert retried.status_code == 202
    assert retried.json()["event_type"] == "RETRY_REQUESTED"
    assert forbidden_safety_action.status_code == 422


def test_owner_safety_exception_uses_same_route_and_hard_block_is_problem_details() -> None:
    service = FakeSafetyExceptionService()
    with TestClient(create_app(technical_exception_service=service)) as client:
        listed = client.get("/api/v2/owner/exceptions?kind=SAFETY&status=OPEN&limit=20")
        allowed = client.post(
            f"/api/v2/owner/exceptions/{SAFETY_EXCEPTION_ID}/commands",
            json={
                "exception_id": str(SAFETY_EXCEPTION_ID),
                "event_type": "OWNER_ALLOWED",
                "expected_version": 1,
            },
            headers={
                "If-Match": '"1"',
                "Idempotency-Key": "019f7c00-0000-7000-8000-000000000120",
            },
        )
        hard_blocked = client.post(
            f"/api/v2/owner/exceptions/{SAFETY_EXCEPTION_ID}/commands",
            json={
                "exception_id": str(SAFETY_EXCEPTION_ID),
                "event_type": "OWNER_ALLOWED",
                "expected_version": 2,
            },
            headers={
                "If-Match": '"2"',
                "Idempotency-Key": "019f7c00-0000-7000-8000-000000000121",
            },
        )

    assert listed.status_code == 200
    assert listed.json()[0]["safety_reason_code"] == "PROMPT_INJECTION_DETECTED"
    assert "raw_content" not in listed.text
    assert allowed.status_code == 202
    assert allowed.json()["event_type"] == "OWNER_ALLOWED"
    assert hard_blocked.status_code == 409
    assert hard_blocked.headers["content-type"].startswith("application/problem+json")
    assert hard_blocked.json()["code"] == "SAFETY_HARD_BLOCK_NON_OVERRIDABLE"
