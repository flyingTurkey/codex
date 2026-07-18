from fastapi.testclient import TestClient
from srbg_api.main import create_app


def test_enterprise_operations_api_is_retired() -> None:
    client = TestClient(create_app(checkers={}))
    for method, path in (
        ("get", "/api/v1/admin/operations"),
        ("post", "/api/v1/admin/operations/replays"),
        ("post", "/api/v1/feedback"),
    ):
        assert getattr(client, method)(path).status_code == 404
