from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.ai_admin.api import AiAdminService
from srbg_api.ai_pipeline.catalog import ProviderCode, provider_catalog
from srbg_api.main import create_app

CONFIG_ID = UUID("019d0000-0000-7000-8000-000000002010")


class StubAiAdminService(AiAdminService):
    def __init__(self) -> None:
        self.captured_value: str | None = None

    async def providers(self) -> list[dict[str, object]]:
        return [
            {
                "code": capability.code.value,
                "base_url": capability.base_url,
                "request_path": capability.request_path,
                "models": list(capability.models),
                "real_call_enabled": capability.real_call_enabled,
                "key_configured": capability.code is ProviderCode.DEEPSEEK,
                "runtime_status": "READY"
                if capability.code is ProviderCode.DEEPSEEK
                else "MOCK_ONLY",
                "blocking_reasons": [],
            }
            for capability in provider_catalog()
        ]

    async def activate(self, *, provider: ProviderCode, model: str, actor_id: UUID) -> UUID:
        assert provider is ProviderCode.DEEPSEEK
        assert model == "deepseek-v4-flash"
        return CONFIG_ID

    async def put_secret(self, *, provider: ProviderCode, secret: str, actor_id: UUID) -> None:
        assert provider is ProviderCode.DEEPSEEK
        self.captured_value = secret


def _client(service: StubAiAdminService) -> TestClient:
    return TestClient(create_app(checkers={}, ai_admin_service=service))


def test_provider_catalog_is_owner_setting_and_has_no_arbitrary_url() -> None:
    client = _client(StubAiAdminService())
    assert client.get("/api/v1/admin/ai/providers").status_code == 404
    response = client.get("/api/v1/settings/ai/providers")
    assert response.status_code == 200
    deepseek = next(item for item in response.json() if item["code"] == "deepseek")
    assert deepseek["base_url"] == "https://api.deepseek.com"


def test_owner_activation_requires_fixed_catalog_model() -> None:
    client = _client(StubAiAdminService())
    response = client.post(
        "/api/v1/settings/ai/configurations",
        json={"provider": "deepseek", "model": "deepseek-v4-flash"},
    )
    assert response.status_code == 201
    assert response.json() == {"id": str(CONFIG_ID), "status": "ACTIVE"}
    assert (
        client.post(
            "/api/v1/settings/ai/configurations",
            json={"provider": "deepseek", "model": "unapproved", "base_url": "https://evil"},
        ).status_code
        == 422
    )


def test_secret_endpoint_never_echoes_secret() -> None:
    service = StubAiAdminService()
    response = _client(service).put(
        "/api/v1/settings/ai/providers/deepseek/secret",
        json={"api_key": "test-only-secret"},
    )
    assert response.status_code == 204
    assert response.content == b""
    assert service.captured_value == "test-only-secret"
    assert b"test-only-secret" not in response.content
