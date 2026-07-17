from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import (
    PersonalSourcePatchRequest,
    PersonalSourceRuntimeState,
    PersonalSourceView,
)

SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000001")


def _view(
    *,
    desired_enabled: bool = False,
    runtime_state: PersonalSourceRuntimeState = PersonalSourceRuntimeState.PENDING_CONFIGURATION,
) -> PersonalSourceView:
    return PersonalSourceView(
        id=SOURCE_ID,
        display_name="交通运输部",
        url="https://www.mot.gov.cn/",
        desired_enabled=desired_enabled,
        runtime_state=runtime_state,
        manual_disabled_at=None,
    )


class StubPersonalSourceService:
    def __init__(self) -> None:
        self.patch_calls: list[tuple[PersonalSourcePatchRequest, UUID]] = []

    async def list_personal_sources(self) -> list[PersonalSourceView]:
        return [_view(desired_enabled=True)]

    async def get_personal_source(self, source_id: UUID) -> PersonalSourceView:
        assert source_id == SOURCE_ID
        return _view(desired_enabled=True)

    async def patch_personal_source(
        self,
        source_id: UUID,
        payload: PersonalSourcePatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> PersonalSourceView:
        assert source_id == SOURCE_ID
        assert request_id
        self.patch_calls.append((payload, actor_id))
        return _view(
            desired_enabled=payload.desired_enabled
            if payload.desired_enabled is not None
            else True,
            runtime_state=PersonalSourceRuntimeState.PENDING_CONFIGURATION,
        ).model_copy(
            update={
                "display_name": payload.display_name or "交通运输部",
                "manual_disabled_at": datetime.now(UTC)
                if payload.desired_enabled is False
                else None,
            }
        )


def _client(service: StubPersonalSourceService | None = None) -> TestClient:
    return TestClient(
        create_app(checkers={}, source_service=service or StubPersonalSourceService())
    )


def test_fixed_local_owner_can_list_get_and_patch_personal_sources() -> None:
    service = StubPersonalSourceService()
    client = _client(service)
    owner_headers = {"X-SRBG-Local-Roles": "owner,viewer"}

    listed = client.get("/api/v1/sources", headers=owner_headers)
    detail = client.get(f"/api/v1/sources/{SOURCE_ID}", headers=owner_headers)
    patched = client.patch(
        f"/api/v1/sources/{SOURCE_ID}",
        json={"desired_enabled": False},
        headers=owner_headers,
    )

    assert listed.status_code == 200
    assert detail.status_code == 200
    assert patched.status_code == 200
    assert patched.json()["desired_enabled"] is False
    assert patched.json()["runtime_state"] == "PENDING_CONFIGURATION"
    assert len(service.patch_calls) == 1


def test_non_owner_and_second_local_identity_cannot_write_personal_source() -> None:
    client = _client()
    non_owner = client.patch(
        f"/api/v1/sources/{SOURCE_ID}",
        json={"desired_enabled": False},
        headers={"X-SRBG-Local-Roles": "viewer"},
    )
    second_owner = client.patch(
        f"/api/v1/sources/{SOURCE_ID}",
        json={"desired_enabled": False},
        headers={
            "X-SRBG-Local-Roles": "owner",
            "X-SRBG-Local-User-ID": "019b0000-0000-7000-8000-000000009999",
        },
    )

    assert non_owner.status_code == 403
    assert second_owner.status_code == 403
    assert non_owner.headers["content-type"].startswith("application/problem+json")


def test_personal_patch_rejects_non_whitelisted_fields() -> None:
    response = _client().patch(
        f"/api/v1/sources/{SOURCE_ID}",
        json={"desired_enabled": True, "runtime_state": "RUNNING"},
        headers={"X-SRBG-Local-Roles": "owner"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
