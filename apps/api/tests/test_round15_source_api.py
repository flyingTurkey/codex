from fastapi.testclient import TestClient
from srbg_api.main import create_app


def test_enterprise_source_governance_api_is_retired() -> None:
    client = TestClient(create_app(checkers={}))
    source_id = "019b1500-0000-7000-8000-000000000001"
    for method, suffix in (
        ("get", ""),
        ("post", "/transitions"),
        ("post", "/pause"),
        ("post", "/approve"),
        ("put", "/governance-metadata"),
        ("post", "/assessments"),
        ("post", "/connector-config-versions/preview"),
    ):
        path = f"/api/v1/admin/sources/{source_id}{suffix}"
        assert getattr(client, method)(path).status_code == 404
