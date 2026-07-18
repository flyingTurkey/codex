from fastapi.testclient import TestClient
from srbg_api.main import create_app


def test_enterprise_schedule_health_and_replay_api_is_retired() -> None:
    client = TestClient(create_app(checkers={}))
    for method, path in (
        ("get", "/api/v1/admin/source-health"),
        ("get", "/api/v1/admin/fetch-schedules"),
        ("post", "/api/v1/admin/operations/replays"),
    ):
        assert getattr(client, method)(path).status_code == 404
