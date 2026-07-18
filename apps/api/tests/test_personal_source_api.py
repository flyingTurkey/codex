from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import (
    DiscoveryDailyUsageView,
    DiscoverySettingPatchRequest,
    DiscoverySettingView,
    DiscoveryTopicPatchRequest,
    DiscoveryTopicView,
    PersonalSourceActivityItemView,
    PersonalSourceActivityPage,
    PersonalSourceCreateRequest,
    PersonalSourcePatchRequest,
    PersonalSourceReprobeRequest,
    PersonalSourceRunSummaryView,
    PersonalSourceRuntimeState,
    PersonalSourceView,
    SourceAutoScoreDetailView,
    SourceProfileOverrideRequest,
    SourceProfileView,
)

SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000001")
TOPIC_ID = UUID("019b0000-0000-7000-8000-000000000002")


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
        self.setting_calls: list[DiscoverySettingPatchRequest] = []
        self.topic_calls: list[DiscoveryTopicPatchRequest] = []

    async def get_discovery_setting(self) -> DiscoverySettingView:
        return DiscoverySettingView(
            automation_enabled=True,
            discovery_interval_seconds=21_600,
            next_run_at=datetime(2026, 7, 17, 6, tzinfo=UTC),
            baidu_status="KEY_MISSING",
            updated_at=datetime(2026, 7, 17, tzinfo=UTC),
        )

    async def patch_discovery_setting(
        self,
        payload: DiscoverySettingPatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> DiscoverySettingView:
        del actor_id, request_id
        self.setting_calls.append(payload)
        return (await self.get_discovery_setting()).model_copy(
            update={"automation_enabled": payload.automation_enabled}
        )

    async def list_discovery_topics(self) -> list[DiscoveryTopicView]:
        return [
            DiscoveryTopicView(
                id=TOPIC_ID,
                code="HIGHWAY",
                name="公路",
                keywords=["公路"],
                excluded_terms=[],
                focus_regions=[],
                enabled=True,
                version=1,
                updated_at=datetime(2026, 7, 17, tzinfo=UTC),
            )
        ]

    async def patch_discovery_topic(
        self,
        topic_id: UUID,
        payload: DiscoveryTopicPatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> DiscoveryTopicView:
        del actor_id, request_id
        assert topic_id == TOPIC_ID
        self.topic_calls.append(payload)
        return (await self.list_discovery_topics())[0].model_copy(
            update={"keywords": payload.keywords or ["公路"]}
        )

    async def get_discovery_usage(self) -> DiscoveryDailyUsageView:
        return DiscoveryDailyUsageView(local_date="2026-07-17", probe_used=9, auto_enable_used=3)

    async def get_auto_score(self, source_id: UUID) -> SourceAutoScoreDetailView:
        assert source_id == SOURCE_ID
        return SourceAutoScoreDetailView(
            snapshot_id=UUID("019b0000-0000-7000-8000-000000000003"),
            source_id=SOURCE_ID,
            total_score=70,
            eligible=True,
            reason_codes=[],
            rule_version="personal-source-auto-score-v1",
            evaluated_at=datetime(2026, 7, 17, tzinfo=UTC),
            topic_relevance_score=30,
            connector_stability_score=20,
            sample_completeness_score=10,
            profile_evidence_score=5,
            content_validity_score=5,
            component_explanations={"topic_relevance": "3/4"},
            hard_gate_results={"ssrf_safe": True},
            evidence_refs=["probe:a"],
        )

    async def list_personal_sources(self) -> list[PersonalSourceView]:
        return [_view(desired_enabled=True)]

    async def get_personal_source(self, source_id: UUID) -> PersonalSourceView:
        assert source_id == SOURCE_ID
        return _view(desired_enabled=True)

    async def get_personal_source_activity(
        self, source_id: UUID, *, cursor: str | None, limit: int
    ) -> PersonalSourceActivityPage:
        assert source_id == SOURCE_ID
        assert cursor is None
        assert limit == 30
        return PersonalSourceActivityPage(
            items=[PersonalSourceActivityItemView(
                id=UUID("019b0000-0000-7000-8000-000000000004"),
                kind="COLLECTION_RUN", occurred_at=datetime(2026, 7, 17, tzinfo=UTC),
                status="SUCCEEDED", discovered_count=2, fetched_count=2, failed_count=0,
            )],
            run_summary=PersonalSourceRunSummaryView(
                last_run_at=datetime(2026, 7, 17, tzinfo=UTC), last_run_status="SUCCEEDED",
                discovered_count=2, fetched_count=2, failed_count=0,
            ),
        )

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
            "evidence": [
                {
                    "evidence_id": "homepage-1",
                    "kind": "HOMEPAGE",
                    "url": "https://www.mot.gov.cn/",
                    "sha256": "a" * 64,
                    "excerpt": "交通运输部",
                }
            ],
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


def test_role_header_cannot_remove_fixed_owner_source_activity_access() -> None:
    client = _client()
    owner = client.get(
        f"/api/v1/sources/{SOURCE_ID}/activity",
        headers={"X-SRBG-Local-Roles": "owner,viewer"},
    )
    viewer = client.get(
        f"/api/v1/sources/{SOURCE_ID}/activity",
        headers={"X-SRBG-Local-Roles": "viewer"},
    )

    assert owner.status_code == 200
    assert owner.json()["items"][0]["kind"] == "COLLECTION_RUN"
    assert owner.json()["run_summary"]["fetched_count"] == 2
    assert viewer.status_code == 200


def test_identity_headers_cannot_change_fixed_owner_source_authority() -> None:
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

    assert non_owner.status_code == 200
    assert second_owner.status_code == 200


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
    revoked = client.delete(f"/api/v1/sources/{SOURCE_ID}/profile-override", headers=headers)

    assert viewed.status_code == 200
    assert viewed.json()["field_explanations"]["authority_level"]["basis"] == "AUTO_INFERRED"
    assert overridden.json()["overridden_fields"] == ["industries"]
    assert revoked.json()["overridden_fields"] == []
    assert "human_review" not in viewed.text.casefold()


def test_owner_can_manage_discovery_topics_setting_usage_and_score() -> None:
    service = StubPersonalSourceService()
    client = _client(service)
    headers = {"X-SRBG-Local-Roles": "owner"}

    setting = client.get("/api/v1/source-discovery/settings", headers=headers)
    patched_setting = client.patch(
        "/api/v1/source-discovery/settings",
        json={"automation_enabled": False},
        headers=headers,
    )
    topics = client.get("/api/v1/source-discovery/topics", headers=headers)
    patched_topic = client.patch(
        f"/api/v1/source-discovery/topics/{TOPIC_ID}",
        json={"keywords": ["公路", "道路工程"]},
        headers=headers,
    )
    usage = client.get("/api/v1/source-discovery/usage", headers=headers)
    score = client.get(f"/api/v1/sources/{SOURCE_ID}/auto-score", headers=headers)

    assert setting.status_code == 200
    assert patched_setting.json()["automation_enabled"] is False
    assert topics.json()[0]["code"] == "HIGHWAY"
    assert patched_topic.json()["keywords"] == ["公路", "道路工程"]
    assert usage.json()["probe_remaining"] == 91
    assert score.json()["total_score"] == 70
    assert len(service.setting_calls) == 1
    assert len(service.topic_calls) == 1


def test_role_header_cannot_remove_fixed_owner_discovery_authority() -> None:
    client = _client()
    headers = {"X-SRBG-Local-Roles": "viewer"}

    read = client.get("/api/v1/source-discovery/topics", headers=headers)
    write = client.patch(
        "/api/v1/source-discovery/settings",
        json={"automation_enabled": False},
        headers=headers,
    )

    assert read.status_code == 200
    assert write.status_code == 200
