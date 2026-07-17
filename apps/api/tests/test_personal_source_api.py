from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import (
    PersonalSourceCreateRequest,
    PersonalSourcePatchRequest,
    PersonalSourceReprobeRequest,
    PersonalSourceRuntimeState,
    PersonalSourceView,
    SourceProfileOverrideRequest,
    SourceProfileView,
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
        self.create_calls: list[PersonalSourceCreateRequest] = []
        self.reprobe_calls: list[PersonalSourceReprobeRequest] = []
        self.profile_override_calls: list[SourceProfileOverrideRequest] = []

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

    async def create_personal_source(
        self,
        payload: PersonalSourceCreateRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> PersonalSourceView:
        del actor_id, request_id
        self.create_calls.append(payload)
        return _view(desired_enabled=True)

    async def reprobe_personal_source(
        self,
        source_id: UUID,
        payload: PersonalSourceReprobeRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> PersonalSourceView:
        del actor_id, request_id
        assert source_id == SOURCE_ID
        self.reprobe_calls.append(payload)
        return _view(desired_enabled=True)

    async def get_source_profile(self, source_id: UUID) -> SourceProfileView:
        assert source_id == SOURCE_ID
        return _profile()

    async def patch_source_profile_override(
        self,
        source_id: UUID,
        payload: SourceProfileOverrideRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceProfileView:
        del actor_id, request_id
        assert source_id == SOURCE_ID
        self.profile_override_calls.append(payload)
        return _profile(overridden_fields=["industries"])

    async def revoke_source_profile_override(
        self,
        source_id: UUID,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceProfileView:
        del actor_id, request_id
        assert source_id == SOURCE_ID
        return _profile()


def _profile(*, overridden_fields: list[str] | None = None) -> SourceProfileView:
    values = {
        "industries": ["HIGHWAY"],
        "content_domains": ["SAFETY_REGULATION"],
        "language_tags": ["zh-CN"],
        "country_codes": ["CN"],
        "region_codes": ["CN-SC"],
        "declared_roles": ["OFFICIAL_PRIMARY"],
        "authority_level": "A0",
        "independence_level": "NOT_INDEPENDENT",
    }
    explanation = {
        "confidence": 85,
        "reason_codes": ["DETERMINISTIC_SOURCE_EVIDENCE"],
        "evidence_ids": ["homepage-1"],
        "basis": "AUTO_INFERRED",
    }
    return SourceProfileView.model_validate(
        {
            "snapshot_id": "019b0000-0000-7000-8000-000000000201",
            "version": 1,
            "status": "COMPLETE",
            "automatic": values,
            "effective": values,
            "field_explanations": {field: explanation for field in values},
            "overall_confidence": 85,
            "overridden_fields": overridden_fields or [],
            "evidence": [{
                "evidence_id": "homepage-1", "kind": "HOMEPAGE",
                "url": "https://www.mot.gov.cn/", "sha256": "a" * 64,
                "excerpt": "交通运输部",
            }],
            "technical_facts": ["RSS_ATOM"],
            "reason_codes": [],
            "rule_version": "source-profile-rules-v1",
            "prompt_version": "source-profile-prompt-v1",
            "schema_version": "source-profile-output-v1",
            "model_version": "deepseek-v4-flash",
            "input_sha256": "b" * 64,
            "generated_at": "2026-07-17T00:00:00Z",
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


def test_owner_can_add_url_and_reprobe_without_governance_form() -> None:
    service = StubPersonalSourceService()
    client = _client(service)
    headers = {"X-SRBG-Local-Roles": "owner"}

    created = client.post(
        "/api/v1/sources",
        json={"url": "https://www.mot.gov.cn/"},
        headers=headers,
    )
    reprobed = client.post(
        f"/api/v1/sources/{SOURCE_ID}/reprobe",
        json={},
        headers=headers,
    )

    assert created.status_code == 202
    assert reprobed.status_code == 202
    assert service.create_calls[0].url == "https://www.mot.gov.cn/"
    assert service.reprobe_calls[0].stream_id is None


def test_owner_can_view_override_and_revoke_profile_without_review_semantics() -> None:
    service = StubPersonalSourceService()
    client = _client(service)
    headers = {"X-SRBG-Local-Roles": "owner"}

    viewed = client.get(f"/api/v1/sources/{SOURCE_ID}/profile", headers=headers)
    overridden = client.patch(
        f"/api/v1/sources/{SOURCE_ID}/profile-override",
        json={"industries": ["HIGHWAY"]},
        headers=headers,
    )
    revoked = client.delete(
        f"/api/v1/sources/{SOURCE_ID}/profile-override", headers=headers
    )

    assert viewed.status_code == 200
    assert viewed.json()["field_explanations"]["authority_level"]["basis"] == "AUTO_INFERRED"
    assert overridden.json()["overridden_fields"] == ["industries"]
    assert revoked.json()["overridden_fields"] == []
    assert "human_review" not in viewed.text.casefold()
