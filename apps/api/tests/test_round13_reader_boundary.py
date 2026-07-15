from pathlib import Path


def test_shadow_reader_mentions_only_versioned_projection_schema() -> None:
    source = Path("apps/api/src/srbg_api/internal_projection/reader.py").read_text(encoding="utf-8")
    assert "published_v1.current_event_summary" in source
    assert "published_v1.current_event_detail" in source
    assert "published_v1.title_search" in source
    for forbidden in (
        "intelligence_item",
        "raw_object",
        "review_task",
        "audit_log",
        "publication_revision",
        "include_draft",
    ):
        assert forbidden not in source
