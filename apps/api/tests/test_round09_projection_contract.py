from pathlib import Path


def test_publication_transaction_updates_all_projection_states_and_events() -> None:
    source = Path("apps/api/src/srbg_api/publication/repository.py").read_text(
        encoding="utf-8"
    )
    assert 'for projection in ("SEARCH", "CACHE", "DAILY_DIGEST")' in source
    assert "INSERT INTO publication_projection_state" in source
    assert "ON CONFLICT (publication_id, projection) DO UPDATE" in source
    assert "INSERT INTO publication_projection_invalidation" in source
    assert '"visible": action != "WITHDRAW"' in source


def test_projection_generation_is_transactionally_advanced_for_every_revision() -> None:
    migration = Path(
        "apps/api/migrations/versions/0010_ai_editorial_governance.py"
    ).read_text(encoding="utf-8")
    assert "publication_projection_state" in migration
    assert "generation >= 1" in migration
    assert "srbg_publication_writer" in migration
