from fastapi.testclient import TestClient
from srbg_api.main import create_app


def test_legacy_source_candidate_qualification_api_is_retired() -> None:
    client = TestClient(create_app(checkers={}))
    for method, path in (
        ("get", "/api/v1/admin/source-candidates"),
        ("post", "/api/v1/admin/source-candidates"),
        (
            "post",
            "/api/v1/admin/source-candidates/019b1800-0000-7000-8000-000000000001/decision",
        ),
    ):
        assert getattr(client, method)(path).status_code == 404
