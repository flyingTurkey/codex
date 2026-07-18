from fastapi.testclient import TestClient
from srbg_api.auth import LOCAL_USER_ID
from srbg_api.main import create_app


def test_personal_identity_ignores_forged_remote_and_role_headers() -> None:
    client = TestClient(create_app(checkers={}))
    response = client.get(
        "/api/v1/me",
        headers={
            "Authorization": "Bearer attacker-controlled-token",
            "X-SRBG-Local-Roles": "platform_admin,reviewer",
            "X-SRBG-Local-User-ID": "019b0000-0000-7000-8000-000000000011",
        },
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == str(LOCAL_USER_ID)
    assert response.json()["roles"] == ["owner"]


def test_personal_openapi_has_no_enterprise_authentication_surface() -> None:
    document = create_app(checkers={}).openapi()
    assert document.get("components", {}).get("securitySchemes", {}) == {}
    assert not any(path.startswith("/api/v1/admin") for path in document["paths"])
