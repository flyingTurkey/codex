import pytest

from scripts.run_phase4_real_event_acceptance import require_source_display_projection


def test_source_display_accepts_one_visible_successful_fetch() -> None:
    require_source_display_projection(
        source_visible=True,
        stream_visible=True,
        normalized_url="https://zgglxb.chd.edu.cn/CN/current",
        expected_url="https://zgglxb.chd.edu.cn/CN/current",
        last_successful_fetch_at="2026-08-01T06:37:03Z",
        last_content_discovered_at="2026-08-01T06:37:03Z",
        discovered_count=1,
        fetched_count=1,
        failed_count=0,
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"source_visible": False}, "SOURCE_NOT_VISIBLE_ON_SOURCES"),
        ({"stream_visible": False}, "SOURCE_STREAM_NOT_VISIBLE_ON_SOURCES"),
        ({"fetched_count": 0}, "SOURCE_FETCH_NOT_VISIBLE_ON_SOURCES"),
        ({"failed_count": 1}, "SOURCE_FETCH_NOT_SUCCESSFUL_ON_SOURCES"),
    ],
)
def test_source_display_fails_closed_when_required_projection_is_missing(
    overrides: dict[str, object], reason: str
) -> None:
    facts: dict[str, object] = {
        "source_visible": True,
        "stream_visible": True,
        "normalized_url": "https://zgglxb.chd.edu.cn/CN/current",
        "expected_url": "https://zgglxb.chd.edu.cn/CN/current",
        "last_successful_fetch_at": "2026-08-01T06:37:03Z",
        "last_content_discovered_at": "2026-08-01T06:37:03Z",
        "discovered_count": 1,
        "fetched_count": 1,
        "failed_count": 0,
    }
    facts.update(overrides)

    with pytest.raises(RuntimeError, match=reason):
        require_source_display_projection(
            source_visible=bool(facts["source_visible"]),
            stream_visible=bool(facts["stream_visible"]),
            normalized_url=str(facts["normalized_url"]),
            expected_url=str(facts["expected_url"]),
            last_successful_fetch_at=facts["last_successful_fetch_at"],
            last_content_discovered_at=facts["last_content_discovered_at"],
            discovered_count=int(facts["discovered_count"]),
            fetched_count=int(facts["fetched_count"]),
            failed_count=int(facts["failed_count"]),
        )
