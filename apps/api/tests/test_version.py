from collections.abc import Awaitable, Callable
from typing import Any

import srbg_api.main as main
from fastapi.testclient import TestClient

HealthCheck = Callable[[], Awaitable[Any]]


def test_version_endpoint_returns_contract_and_schema_versions() -> None:
    assert hasattr(main, "create_app")
    client = TestClient(main.create_app(checkers={}))

    response = client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.json() == {
        "api_version": "v1",
        "content_schema_version": "1.1.0",
        "search_schema_version": "1.0.0",
        "semantic_search_enabled": False,
    }
