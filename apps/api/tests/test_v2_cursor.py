from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.intelligence_v2.cursor import InvalidV2Cursor, V2CursorCodec

KEY = b"v2-closeout-test-cursor-signing-key-000000000000"
NOW = datetime(2026, 7, 19, tzinfo=UTC)
EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000011")


def test_v2_cursor_round_trips_and_is_bound_to_surface_and_filters() -> None:
    codec = V2CursorCodec(KEY)
    cursor = codec.encode(
        surface="feed",
        sort_values=(NOW.isoformat(), str(EVENT_ID)),
        filters={"primary_type": "SAFETY_INTELLIGENCE"},
    )
    assert codec.decode(
        cursor,
        surface="feed",
        filters={"primary_type": "SAFETY_INTELLIGENCE"},
        expected_values=2,
    ) == (NOW.isoformat(), str(EVENT_ID))
    with pytest.raises(InvalidV2Cursor):
        codec.decode(cursor, surface="hotspots", filters={}, expected_values=2)


def test_v2_cursor_rejects_tampering_and_wrong_shape() -> None:
    codec = V2CursorCodec(KEY)
    cursor = codec.encode(
        surface="search",
        sort_values=("100", NOW.isoformat(), str(EVENT_ID)),
        filters={"q": "隧道"},
    )
    with pytest.raises(InvalidV2Cursor):
        codec.decode(cursor + "x", surface="search", filters={"q": "隧道"}, expected_values=3)
    with pytest.raises(InvalidV2Cursor):
        codec.decode(cursor, surface="search", filters={"q": "隧道"}, expected_values=2)
