from pathlib import Path


def test_projection_worker_supplies_search_and_daily_side_effects() -> None:
    worker = Path("apps/worker/src/srbg_worker/app.py").read_text(encoding="utf-8")
    repository = Path("apps/api/src/srbg_api/publication/repository.py").read_text(encoding="utf-8")
    assert "search_projection=projection_writer.apply_search" in worker
    assert "daily_digest=projection_writer.invalidate_daily" in worker
    assert 'event["projection"] == "SEARCH"' in repository
    assert 'event["projection"] == "DAILY_DIGEST"' in repository
    assert "projection callback is required" in repository
