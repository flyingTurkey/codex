from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import ValidationError
from srbg_api.config import Settings, get_settings
from srbg_api.main import create_app


def test_staging_ignores_local_identity_headers_for_all_internal_reader_channels(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SRBG_ENVIRONMENT", "staging")
    monkeypatch.setenv("SRBG_OIDC_ISSUER", "https://id.example.test")
    monkeypatch.setenv("SRBG_OIDC_AUDIENCE", "srbg-platform")
    monkeypatch.setenv("SRBG_OIDC_JWKS_URL", "https://id.example.test/jwks")
    get_settings.cache_clear()
    client = TestClient(create_app(checkers={}))
    local_headers = {
        "X-SRBG-Local-Roles": "platform_admin",
        "X-SRBG-Local-User-ID": str(UUID("019b0000-0000-7000-8000-000000001399")),
        "X-SRBG-Local-Step-Up": "true",
    }
    paths = (
        "/api/v1/feed",
        "/api/v1/events/019b0000-0000-7000-8000-000000001301",
        "/api/v1/search?q=bridge",
        "/api/v1/daily",
    )
    try:
        for path in paths:
            response = client.get(path, headers=local_headers)
            assert response.status_code == 401, path
    finally:
        get_settings.cache_clear()


def test_cors_rejects_wildcard_configuration() -> None:
    try:
        Settings(cors_allowed_origins=["https://*.example.test"])
    except ValidationError:
        return
    raise AssertionError("wildcard CORS configuration must be rejected")
