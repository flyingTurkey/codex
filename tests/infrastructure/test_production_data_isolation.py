from pathlib import Path


def test_source_center_excludes_explicit_fixture_state() -> None:
    source = Path("apps/api/src/srbg_api/source_registry/repository.py").read_text(
        encoding="utf-8"
    )

    assert "source.state <> 'FIXTURE_TEST'" in source
    assert "source.trial_kind IS DISTINCT FROM 'FIXTURE_REPLAY'" in source
    assert "NOT LIKE '%.test'" not in source


def test_publication_projection_excludes_explicit_fixture_state() -> None:
    source = Path("apps/api/src/srbg_api/internal_projection/backfill.py").read_text(
        encoding="utf-8"
    )

    assert "source.state <> 'FIXTURE_TEST'" in source
    assert "source.trial_kind IS DISTINCT FROM 'FIXTURE_REPLAY'" in source
    assert "NOT LIKE '%.test'" not in source
