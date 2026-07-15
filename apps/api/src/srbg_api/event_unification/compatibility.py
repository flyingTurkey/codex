"""HTTP compatibility metadata for the read-only Item facade."""

from __future__ import annotations

from datetime import datetime
from email.utils import format_datetime
from uuid import UUID


def item_deprecation_headers(
    event_id: UUID, *, deprecation_at: datetime, sunset_at: datetime | None
) -> dict[str, str]:
    if deprecation_at.tzinfo is None:
        raise ValueError("deprecation_at must be timezone-aware")
    headers = {
        "Deprecation": f"@{int(deprecation_at.timestamp())}",
        "Link": (
            f'</api/v1/events/{event_id}>; rel="successor-version", '
            '</docs/compatibility/item-event>; rel="deprecation"; type="text/html"'
        ),
    }
    if sunset_at is not None:
        if sunset_at.tzinfo is None:
            raise ValueError("sunset_at must be timezone-aware")
        headers["Sunset"] = format_datetime(sunset_at, usegmt=True)
    return headers
