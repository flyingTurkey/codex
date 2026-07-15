from datetime import UTC, datetime

import srbg_contracts.models as models


def test_liveness_response_serializes_utc_timestamp() -> None:
    assert hasattr(models, "LivenessResponse")

    response = models.LivenessResponse(
        status="ok",
        service="api",
        timestamp=datetime(2026, 7, 13, 6, 0, tzinfo=UTC),
    )

    assert response.model_dump(mode="json") == {
        "status": "ok",
        "service": "api",
        "timestamp": "2026-07-13T06:00:00Z",
    }


def test_version_response_contains_only_public_versions() -> None:
    assert hasattr(models, "VersionResponse")

    response = models.VersionResponse(api_version="v1", content_schema_version="1.1.0")

    assert response.model_dump(mode="json") == {
        "api_version": "v1",
        "content_schema_version": "1.1.0",
        "search_schema_version": "1.0.0",
        "semantic_search_enabled": False,
    }


def test_user_roles_include_auditor_and_required_operational_roles() -> None:
    assert hasattr(models, "UserRole")

    assert {role.value for role in models.UserRole} == {
        "viewer",
        "editor",
        "reviewer",
        "source_admin",
        "platform_admin",
        "auditor",
    }


def test_cursor_page_exposes_cursor_without_total_count() -> None:
    assert hasattr(models, "CursorPage")

    page = models.CursorPage[str](items=["item-1"], next_cursor="next", has_more=True)

    assert page.model_dump() == {
        "items": ["item-1"],
        "next_cursor": "next",
        "has_more": True,
    }
