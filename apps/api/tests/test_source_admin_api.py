from fastapi.testclient import TestClient
from srbg_api.main import create_app


def test_legacy_source_admin_api_and_fixture_upload_are_retired() -> None:
    client = TestClient(create_app(checkers={}))
    source_id = "019b0000-0000-7000-8000-000000000001"
    for method, path in (
        ("get", "/api/v1/admin/sources"),
        ("post", "/api/v1/admin/sources"),
        ("post", f"/api/v1/admin/sources/{source_id}/enable"),
        ("post", f"/api/v1/admin/sources/{source_id}/fixture"),
    ):
        assert getattr(client, method)(path).status_code == 404
