from pathlib import Path

import httpx2 as httpx
from fastapi.testclient import TestClient
from srbg_api.config import get_settings
from srbg_api.main import create_app

from scripts.slo_weekly_report import _query, error_budget

ROOT = Path(__file__).parents[2]


def test_metrics_endpoint_uses_service_bearer_not_browser_role(monkeypatch) -> None:
    monkeypatch.setenv("SRBG_METRICS_BEARER_TOKEN", "m" * 32)
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(checkers={}))
        assert client.get("/metrics").status_code == 401
        response = client.get("/metrics", headers={"Authorization": f"Bearer {'m' * 32}"})
        assert response.status_code == 200
        assert "srbg_api_requests_total" in response.text
    finally:
        get_settings.cache_clear()


def test_compose_provisions_observability_without_floating_images() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")
    for service in ("prometheus", "alertmanager", "grafana", "otel-collector"):
        assert f"  {service}:\n" in compose
    assert "prom/prometheus:" in compose
    assert "grafana/grafana:" in compose
    assert ":latest" not in compose


def test_prometheus_local_storage_has_time_and_size_retention_limits() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    prometheus_section = compose.split("  prometheus:\n", 1)[1].split(
        "  alertmanager:\n", 1
    )[0]

    assert (
        "--storage.tsdb.retention.time="
        "${SRBG_PROMETHEUS_RETENTION_TIME:-15d}"
    ) in prometheus_section
    assert (
        "--storage.tsdb.retention.size="
        "${SRBG_PROMETHEUS_RETENTION_SIZE:-2GB}"
    ) in prometheus_section
    assert "SRBG_PROMETHEUS_RETENTION_TIME=15d" in example
    assert "SRBG_PROMETHEUS_RETENTION_SIZE=2GB" in example


def test_alertmanager_runtime_state_does_not_allocate_anonymous_volumes() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")
    alertmanager_section = compose.split("  alertmanager:\n", 1)[1].split(
        "  grafana:\n", 1
    )[0]

    assert (
        "    tmpfs:\n"
        "      - /alertmanager:uid=65534,gid=65534,mode=0750"
    ) in alertmanager_section


def test_slo_rules_cover_source_queue_api_search_and_backup() -> None:
    rules = (ROOT / "infra/observability/prometheus/rules.yml").read_text(encoding="utf-8")
    for alert in (
        "SourceCircuitOpen",
        "QueueOldestTaskTooOld",
        "ApiAvailabilityBudgetBurn",
        "SearchLatencySloBreach",
        "BackupVerificationFailed",
    ):
        assert f"alert: {alert}" in rules


def test_grafana_provisions_required_dashboards() -> None:
    dashboard_dir = ROOT / "infra/observability/grafana/dashboards"
    names = {path.name for path in dashboard_dir.glob("*.json")}
    assert names >= {"source-health.json", "operations.json", "quality-slo.json"}


def test_error_budget_never_reports_negative_remaining_budget() -> None:
    healthy = error_budget(target_percent=99.5, observed_percent=99.8)
    exhausted = error_budget(target_percent=99.5, observed_percent=98.0)
    assert healthy["remaining_percent_of_budget"] == 60.0
    assert exhausted["remaining_percent_of_budget"] == 0.0


def test_prometheus_nan_is_not_emitted_as_invalid_json_number() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"result": [{"value": [0, "NaN"]}]}},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert _query(client, "http://prometheus", "example") is None
