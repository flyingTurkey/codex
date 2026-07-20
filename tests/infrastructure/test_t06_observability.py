from pathlib import Path


def test_t06_runtime_summary_and_projection_refresh_are_observable() -> None:
    observability = Path("apps/api/src/srbg_api/observability.py").read_text(encoding="utf-8")
    worker = Path("apps/worker/src/srbg_worker/ai_content_preparation.py").read_text(
        encoding="utf-8"
    )
    publisher = Path("apps/api/src/srbg_api/publication/repository.py").read_text(
        encoding="utf-8"
    )
    admin = Path("apps/api/src/srbg_api/ai_admin/service.py").read_text(encoding="utf-8")
    alerts = Path("infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")

    assert "srbg_t06_ai_runtime_state" in observability
    assert "srbg_t06_ai_summary_state_transitions_total" in observability
    assert "srbg_t06_ai_projection_refresh_total" in observability
    assert "T06_AI_SUMMARY_STATE_TRANSITIONS.labels" in worker
    assert "T06_AI_PROJECTION_REFRESH.labels" in publisher
    assert "T06_AI_RUNTIME_STATE.labels" in admin
    assert "T06AiApprovedContentSuccessStale" in alerts
    assert "T06AiProjectionRefreshDeadLetter" in alerts
