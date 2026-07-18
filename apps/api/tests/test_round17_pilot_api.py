from fastapi.testclient import TestClient
from srbg_api.main import create_app


def test_enterprise_pilot_and_gold_workflow_api_is_retired() -> None:
    client = TestClient(create_app(checkers={}))
    for path in (
        "/api/v1/admin/pilot-windows",
        "/api/v1/admin/gold/tasks",
        "/api/v1/admin/operator-tasks",
    ):
        assert client.post(path).status_code == 404
