from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import UUID

import srbg_api.main as main
from fastapi.testclient import TestClient

HealthCheck = Callable[[], Awaitable[Any]]


async def _up() -> dict[str, object]:
    return {"status": "up", "latency_ms": 1, "error_code": None}


async def _redis_down() -> dict[str, object]:
    return {"status": "down", "latency_ms": 1, "error_code": "unavailable"}


def _app(checkers: Mapping[str, HealthCheck] | None = None) -> Any:
    assert hasattr(main, "create_app")
    return main.create_app(checkers=checkers)


def test_liveness_does_not_depend_on_external_services() -> None:
    client = TestClient(_app({"redis": _redis_down}))

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "api"
    assert response.json()["timestamp"].endswith("Z")


def test_readiness_reports_all_healthy_dependencies() -> None:
    client = TestClient(_app({"postgresql": _up, "redis": _up, "object_storage": _up}))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert set(response.json()["checks"]) == {
        "postgresql",
        "redis",
        "object_storage",
    }


def test_readiness_is_unavailable_when_redis_is_down() -> None:
    client = TestClient(_app({"postgresql": _up, "redis": _redis_down, "object_storage": _up}))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["redis"] == {
        "status": "down",
        "latency_ms": 1,
        "error_code": "unavailable",
    }


def test_missing_route_uses_problem_details() -> None:
    client = TestClient(_app({"postgresql": _up, "redis": _up, "object_storage": _up}))

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 404
    assert response.json()["title"] == "Not Found"
    assert UUID(response.json()["request_id"]).version == 7


def test_metrics_rejects_anonymous_and_browser_identity(monkeypatch) -> None:
    monkeypatch.setenv("SRBG_METRICS_BEARER_TOKEN", "m" * 32)
    main.get_settings.cache_clear()
    try:
        client = TestClient(_app({"postgresql": _up, "redis": _up, "object_storage": _up}))
        assert client.get("/metrics").status_code == 401
        assert client.get(
            "/metrics", headers={"X-SRBG-Local-Roles": "platform_admin"}
        ).status_code == 401
    finally:
        main.get_settings.cache_clear()


def test_metrics_allows_service_token_while_health_probes_remain_anonymous(monkeypatch) -> None:
    monkeypatch.setenv("SRBG_METRICS_BEARER_TOKEN", "m" * 32)
    main.get_settings.cache_clear()
    try:
        client = TestClient(_app({"postgresql": _up, "redis": _up, "object_storage": _up}))
        response = client.get("/metrics", headers={"Authorization": f"Bearer {'m' * 32}"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
    finally:
        main.get_settings.cache_clear()
