from datetime import UTC, datetime
from uuid import UUID

from srbg_api.event_unification.compatibility import item_deprecation_headers


def test_item_api_headers_advertise_successor_without_inventing_sunset() -> None:
    event_id = UUID("019b0000-0000-7000-8000-000000001401")
    headers = item_deprecation_headers(
        event_id,
        deprecation_at=datetime(2026, 7, 15, tzinfo=UTC),
        sunset_at=None,
    )
    assert headers["Deprecation"].startswith("@")
    assert f'</api/v1/events/{event_id}>; rel="successor-version"' in headers["Link"]
    assert "Sunset" not in headers


def test_item_api_sunset_is_emitted_only_when_configured() -> None:
    headers = item_deprecation_headers(
        UUID("019b0000-0000-7000-8000-000000001401"),
        deprecation_at=datetime(2026, 7, 15, tzinfo=UTC),
        sunset_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert headers["Sunset"] == "Fri, 01 Jan 2027 00:00:00 GMT"
