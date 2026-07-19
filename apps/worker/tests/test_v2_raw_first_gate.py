from pathlib import Path


def test_worker_does_not_materialize_event_before_relevance_gate() -> None:
    source = Path("apps/worker/src/srbg_worker/app.py").read_text(encoding="utf-8")
    start = source.index("async def _start_ai_content_preparation")
    end = source.index("async def _handle_ai_content_result")
    assert "materialize_local" not in source[start:end]


def test_local_materialization_no_longer_precreates_digital_item_or_event() -> None:
    source = Path("apps/worker/src/srbg_worker/ai_content_preparation.py").read_text(
        encoding="utf-8"
    )
    start = source.index("async def materialize_local")
    end = source.index("async def successful_output", start)
    body = source[start:end]
    assert "_INSERT_ITEM_SQL" not in body
    assert "_ensure_personal_event" not in body
