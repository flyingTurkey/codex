import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_api.source_registry.api import _read_fixture_body
from srbg_contracts import (
    AuthorityLevel,
    CreateSourceRequest,
    SourceChannel,
    SourceDetail,
    SourceEligibility,
    SourceState,
    SourceSummary,
    SourceType,
)

SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000001")


def _summary() -> SourceSummary:
    return SourceSummary(
        id=SOURCE_ID,
        registry_code="GOV-001",
        name="国家法律法规数据库",
        base_url="https://flk.npc.gov.cn/",
        channel=SourceChannel.SAFETY,
        source_type=SourceType.GOVERNMENT,
        authority_level=AuthorityLevel.A0,
        priority="P0",
        state=SourceState.CANDIDATE,
        enabled=False,
        effective_active=False,
        fixture_count=0,
        created_at=datetime.now(UTC),
    )


class StubSourceService:
    async def list_sources(self) -> list[SourceSummary]:
        return [_summary()]

    async def create_source(
        self,
        payload: CreateSourceRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        summary = _summary().model_copy(update={"name": payload.name, "registry_code": None})
        return SourceDetail(
            **summary.model_dump(),
            collection_method=payload.collection_method,
            poll_interval_minutes=payload.poll_interval_minutes,
            owner=payload.owner,
            eligibility=SourceEligibility(
                effective_active=False,
                policy_valid=False,
                onboarding_valid=False,
                onboarding_policy_matches=False,
                required_checks_complete=False,
                fixture_count=0,
                missing_reasons=["VALID_POLICY_REQUIRED"],
            ),
        )


def _client() -> TestClient:
    return TestClient(
        create_app(checkers={}, source_service=StubSourceService()),
        headers={"X-SRBG-Local-Step-Up": "true"},
    )


def _source_payload() -> dict[str, object]:
    return {
        "name": "四川交通试点来源",
        "base_url": "https://example.test/source/",
        "channel": "BOTH",
        "source_type": "government",
        "authority_level": "A1",
        "priority": "P0",
        "collection_method": "manual_fixture",
        "poll_interval_minutes": 60,
        "owner": "source_ops",
    }


def test_viewer_can_neither_register_nor_enable_source() -> None:
    client = _client()
    viewer_headers = {"X-SRBG-Local-Roles": "viewer"}

    create_response = client.post(
        "/api/v1/admin/sources",
        json=_source_payload(),
        headers=viewer_headers,
    )
    enable_response = client.post(
        f"/api/v1/admin/sources/{SOURCE_ID}/enable",
        json={"reason": "should fail"},
        headers=viewer_headers,
    )

    assert create_response.status_code == 403
    assert create_response.headers["content-type"].startswith("application/problem+json")
    assert enable_response.status_code == 403


def test_source_admin_can_list_and_register_default_denied_source() -> None:
    client = _client()
    headers = {"X-SRBG-Local-Roles": "source_admin"}

    list_response = client.get("/api/v1/admin/sources", headers=headers)
    create_response = client.post(
        "/api/v1/admin/sources",
        json=_source_payload(),
        headers=headers,
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["state"] == "CANDIDATE"
    assert create_response.status_code == 201
    assert create_response.json()["enabled"] is False
    assert create_response.json()["effective_active"] is False


def test_request_cannot_smuggle_enabled_or_state_into_source_creation() -> None:
    client = _client()
    payload = _source_payload() | {"state": "ACTIVE", "enabled": True}

    response = client.post(
        "/api/v1/admin/sources",
        json=payload,
        headers={"X-SRBG-Local-Roles": "source_admin"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_fixture_stream_is_bounded_without_relying_on_content_length() -> None:
    async def read_body(chunks: list[bytes], max_bytes: int) -> bytes:
        messages: list[dict[str, Any]] = [
            {
                "type": "http.request",
                "body": chunk,
                "more_body": index < len(chunks) - 1,
            }
            for index, chunk in enumerate(chunks)
        ]

        async def receive() -> dict[str, Any]:
            return messages.pop(0)

        request = Request({"type": "http", "method": "POST", "headers": []}, receive)
        return await _read_fixture_body(request, max_bytes)

    assert asyncio.run(read_body([b"abc", b"de"], 5)) == b"abcde"
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(read_body([b"abc", b"def"], 5))
    assert rejected.value.status_code == 413


def test_unexpected_source_failure_returns_safe_problem_details() -> None:
    class FailingSourceService:
        async def list_sources(self) -> list[SourceSummary]:
            raise OSError("secret backend detail")

    client = TestClient(
        create_app(checkers={}, source_service=FailingSourceService()),
        raise_server_exceptions=False,
    )
    response = client.get(
        "/api/v1/admin/sources",
        headers={"X-SRBG-Local-Roles": "source_admin"},
    )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Internal server error"
    assert "secret backend detail" not in response.text
