from fastapi.testclient import TestClient
from srbg_api.main import create_app


def test_legacy_event_candidate_api_is_unavailable_for_every_identity_header() -> None:
    client = TestClient(create_app(checkers={}))
    endpoint = (
        "/api/v1/admin/events/019b0000-0000-7000-8000-000000043001/"
        "candidate-items/019b0000-0000-7000-8000-000000043002"
    )
    for headers in (
        {},
        {"X-SRBG-Local-Roles": "owner"},
        {"X-SRBG-Local-Roles": "platform_admin", "Authorization": "Bearer forged"},
    ):
        assert client.post(endpoint, headers=headers).status_code == 404
