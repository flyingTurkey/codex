from pathlib import Path

REPOSITORY = Path("apps/api/src/srbg_api/publication/repository.py")


def _source() -> str:
    return REPOSITORY.read_text(encoding="utf-8")


def test_owner_corrections_are_idempotent_and_transactional() -> None:
    source = _source()
    method = source[source.index("async def correct_automatic_relationship") :]
    assert "async with self._engine.begin() as connection" in method
    assert "WHERE command_id=:command_id" in method
    assert "owner_relationship_withdrawal" in method
    assert "owner_relationship_correction" in method


def test_split_and_model_corrections_invalidate_only_affected_relationships() -> None:
    source = _source()
    assert "PERS08_SPLIT_REQUIRES_DISTINCT_CHILDREN" in source
    assert "source_item_id=ANY(CAST(:member_ids AS uuid[]))" in source
    assert "resulting_decision_id" in source
    assert "owner-correction-v1" in source
    assert 'previous["algorithm_version"].startswith("owner-correction")' in source


def test_relation_changes_refresh_all_publication_surfaces_before_commit() -> None:
    source = _source()
    refresh = source[source.index("async def _refresh_relationship_projections") :]
    for projection in (
        "personal_content_projection",
        "personal_signal_projection",
        "personal_primary_search_projection",
        "unverified_ai_search_projection",
        "personal_daily_report_projection",
        "publication_projection_invalidation",
        "CACHE",
        "SEARCH",
        "DAILY_DIGEST",
    ):
        assert projection in refresh
    assert "'UPSERT'" in refresh


def test_automatic_relationships_never_delete_preserved_records() -> None:
    source = _source()
    relation_slice = source[source.index("async def _recalculate_automatic_relationships") :]
    for table in ("intelligence_item", "document", "document_version", "claim", "claim_evidence"):
        assert f"DELETE FROM {table}" not in relation_slice  # noqa: S608
