import inspect

from srbg_worker.ai_content_preparation import PostgresAiPreparationRepository


def test_repository_routes_controlled_pipeline_cost_through_atomic_bridge() -> None:
    reserve = inspect.getsource(PostgresAiPreparationRepository.reserve)
    settle = inspect.getsource(PostgresAiPreparationRepository.settle)
    release = inspect.getsource(PostgresAiPreparationRepository.release)

    assert "controlled_run_id" in reserve
    assert "reserve_controlled_ai_budget" in reserve
    assert "controlled_cost_reservation_microusd" in reserve
    assert "settle_controlled_ai_budget" in settle
    assert "release_controlled_ai_budget" in release
