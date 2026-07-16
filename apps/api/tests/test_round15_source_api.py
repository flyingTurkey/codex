from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import (
    AuthorityLevel,
    ConnectorConfigPreview,
    ConnectorConfigVersionView,
    ConnectorDefinitionView,
    ConnectorType,
    RuntimeAuthorization,
    SourceAssessmentSubmission,
    SourceChannel,
    SourceDetail,
    SourceEligibility,
    SourceLifecycleState,
    SourceState,
    SourceSummary,
    SourceType,
)

SOURCE_ID = UUID("019b1500-0000-7000-8000-000000000001")


def _summary() -> SourceSummary:
    return SourceSummary(
        id=SOURCE_ID,
        registry_code="TEST-1501",
        name="Round 15 source",
        base_url="https://example.test/",
        channel=SourceChannel.BOTH,
        source_type=SourceType.GOVERNMENT,
        authority_level=AuthorityLevel.A1,
        priority="P0",
        state=SourceState.CANDIDATE,
        enabled=False,
        effective_active=False,
        fixture_count=0,
        created_at=datetime.now(UTC),
        lifecycle_state=SourceLifecycleState.CANDIDATE,
        runtime_authorization=RuntimeAuthorization.DENIED,
        available_actions=["SUBMIT_COMPLIANCE", "RETIRE"],
    )


class SourceV2Stub:
    def __init__(self) -> None:
        self.actions: list[tuple[str, UUID]] = []
        self.assessment_payloads: list[SourceAssessmentSubmission] = []

    async def get_source(self, source_id: UUID) -> SourceDetail:
        assert source_id == SOURCE_ID
        return SourceDetail(
            **_summary().model_dump(),
            collection_method="manual",
            poll_interval_minutes=60,
            owner="legacy-owner",
            eligibility=SourceEligibility(
                effective_active=False,
                policy_valid=False,
                onboarding_valid=False,
                onboarding_policy_matches=False,
                required_checks_complete=False,
                fixture_count=0,
                missing_reasons=["V2_POLICY_REQUIRED"],
            ),
        )

    async def lifecycle_action(
        self,
        source_id: UUID,
        action: str,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        assert source_id == SOURCE_ID and reason
        assert request_id
        self.actions.append((action, actor_id))
        return await self.get_source(source_id)

    async def list_connector_definitions(self) -> list[ConnectorDefinitionView]:
        return [
            ConnectorDefinitionView(
                id=UUID("019b1500-0000-7000-8000-000000000010"),
                connector_type=ConnectorType.RSS_ATOM,
                definition_version="1.0.0",
                schema_version="2020-12",
                schema_document={"type": "object"},
                schema_sha256="a" * 64,
                executor_key="builtin:rss_atom:v1",
                capabilities=["DISCOVERY", "FETCH"],
            )
        ]

    async def preview_connector_config(
        self, source_id: UUID, payload: object
    ) -> ConnectorConfigPreview:
        assert source_id == SOURCE_ID
        return ConnectorConfigPreview(
            connector_type=ConnectorType.RSS_ATOM,
            definition_version="1.0.0",
            schema_version="2020-12",
            schema_sha256="a" * 64,
            config={"allowed_hosts": ["example.test"], "feed_url": "https://example.test/feed"},
            network_io_performed=False,
        )

    async def save_connector_config(
        self, source_id: UUID, payload: object, *, actor_id: UUID, request_id: str
    ) -> ConnectorConfigVersionView:
        assert source_id == SOURCE_ID and actor_id and request_id
        return ConnectorConfigVersionView(
            id=UUID("019b1500-0000-7000-8000-000000000011"),
            source_id=source_id,
            policy_version_id=UUID("019b1500-0000-7000-8000-000000000012"),
            connector_type=ConnectorType.RSS_ATOM,
            definition_version="1.0.0",
            version_number=1,
            config_sha256="b" * 64,
            config={"allowed_hosts": ["example.test"], "feed_url": "https://example.test/feed"},
            allowed_hosts=["example.test"],
            credential_configured=True,
            validation_status="VALID",
            created_by=actor_id,
            created_at=datetime.now(UTC),
        )

    async def list_connector_configs(self, source_id: UUID) -> list[ConnectorConfigVersionView]:
        return []

    async def update_governance_metadata(
        self, source_id: UUID, payload: object, *, actor_id: UUID, request_id: str
    ) -> SourceDetail:
        assert source_id == SOURCE_ID and actor_id and request_id
        self.actions.append(("UPDATE_GOVERNANCE_METADATA", actor_id))
        return await self.get_source(source_id)

    async def append_assessments(
        self,
        source_id: UUID,
        payload: SourceAssessmentSubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        assert source_id == SOURCE_ID and actor_id and request_id
        self.actions.append(("APPEND_ASSESSMENTS", actor_id))
        self.assessment_payloads.append(payload)
        return await self.get_source(source_id)


def test_legacy_state_write_endpoints_are_gone_and_commands_are_rbac_protected() -> None:
    stub = SourceV2Stub()
    client = TestClient(create_app(checkers={}, source_service=stub))
    headers = {
        "X-SRBG-Local-Roles": "source_admin",
        "X-SRBG-Local-Step-Up": "true",
    }

    legacy = client.post(
        f"/api/v1/admin/sources/{SOURCE_ID}/transitions",
        headers=headers,
        json={"target_state": "ACTIVE", "reason": "forged"},
    )
    pause = client.post(
        f"/api/v1/admin/sources/{SOURCE_ID}/pause",
        headers=headers,
        json={"reason": "planned maintenance"},
    )
    viewer_pause = client.post(
        f"/api/v1/admin/sources/{SOURCE_ID}/pause",
        headers={"X-SRBG-Local-Roles": "viewer"},
        json={"reason": "forged"},
    )

    assert legacy.status_code == 410
    assert legacy.headers["link"].endswith(
        f"/api/v1/admin/sources/{SOURCE_ID}/approve>; rel=\"successor-version\""
    )
    assert pause.status_code == 200
    assert stub.actions[0][0] == "PAUSE"
    assert viewer_pause.status_code == 403


def test_source_detail_exposes_authoritative_lifecycle_separately_from_legacy_flags() -> None:
    client = TestClient(create_app(checkers={}, source_service=SourceV2Stub()))
    response = client.get(
        f"/api/v1/admin/sources/{SOURCE_ID}",
        headers={"X-SRBG-Local-Roles": "auditor"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["lifecycle_state"] == "CANDIDATE"
    assert body["runtime_authorization"] == "DENIED"
    assert body["state"] == "CANDIDATE"
    assert body["enabled"] is False


def test_connector_preview_is_rbac_protected_and_declares_no_network_io() -> None:
    client = TestClient(create_app(checkers={}, source_service=SourceV2Stub()))
    payload = {
        "connector_type": "RSS_ATOM",
        "definition_version": "1.0.0",
        "config": {
            "allowed_hosts": ["example.test"],
            "feed_url": "https://example.test/feed",
            "credential_ref": "vault://source-connectors/example/rss",
        },
    }
    admin = {
        "X-SRBG-Local-Roles": "source_admin",
        "X-SRBG-Local-Step-Up": "true",
    }

    response = client.post(
        f"/api/v1/admin/sources/{SOURCE_ID}/connector-config-versions/preview",
        headers=admin,
        json=payload,
    )
    viewer = client.post(
        f"/api/v1/admin/sources/{SOURCE_ID}/connector-config-versions/preview",
        headers={"X-SRBG-Local-Roles": "viewer"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["network_io_performed"] is False
    assert viewer.status_code == 403


def test_governance_metadata_and_assessments_have_bounded_step_up_commands() -> None:
    stub = SourceV2Stub()
    client = TestClient(create_app(checkers={}, source_service=stub))
    admin = {
        "X-SRBG-Local-Roles": "source_admin",
        "X-SRBG-Local-Step-Up": "true",
    }
    metadata = {
        "governance_owner_id": "019b1500-0000-7000-8000-000000000099",
        "country_codes": ["CN"],
        "region_codes": ["CN-SC"],
        "language_tags": ["zh-CN"],
        "industries": ["HIGHWAY"],
        "content_domains": ["SAFETY_REGULATION"],
        "declared_roles": ["OFFICIAL_PRIMARY"],
        "reason": "assign accountable governance metadata",
    }
    assessment = {
        "authority": {
            "level": "A1",
            "rule_version": "authority-v1",
            "reason_codes": ["GOVERNMENT_PUBLISHER"],
            "evidence_refs": ["policy:official-domain"],
            "assessed_at": datetime.now(UTC).isoformat(),
        },
        "independence": {
            "level": "EDITORIALLY_INDEPENDENT",
            "rule_version": "independence-v1",
            "reason_codes": ["EDITORIAL_CONTROL"],
            "evidence_refs": ["review:editorial-policy"],
            "assessed_at": datetime.now(UTC).isoformat(),
        },
        "reason": "record explainable assessments",
    }

    first = client.put(
        f"/api/v1/admin/sources/{SOURCE_ID}/governance-metadata",
        headers=admin,
        json=metadata,
    )
    second = client.post(
        f"/api/v1/admin/sources/{SOURCE_ID}/assessments",
        headers=admin,
        json=assessment,
    )
    forged = client.put(
        f"/api/v1/admin/sources/{SOURCE_ID}/governance-metadata",
        headers=admin,
        json=metadata | {"lifecycle_state": "ACTIVE"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert forged.status_code == 422
    assert [action for action, _ in stub.actions] == [
        "UPDATE_GOVERNANCE_METADATA",
        "APPEND_ASSESSMENTS",
    ]


def test_assessment_api_rejects_naive_time_and_normalizes_offsets_to_utc() -> None:
    stub = SourceV2Stub()
    client = TestClient(create_app(checkers={}, source_service=stub))
    admin = {
        "X-SRBG-Local-Roles": "source_admin",
        "X-SRBG-Local-Step-Up": "true",
    }
    endpoint = f"/api/v1/admin/sources/{SOURCE_ID}/assessments"
    payload = {
        "authority": {
            "level": "A1",
            "rule_version": "authority-v1",
            "reason_codes": ["GOVERNMENT_PUBLISHER"],
            "evidence_refs": ["policy:official-domain"],
            "assessed_at": "2026-07-16T08:00:00+08:00",
        },
        "independence": {
            "level": "EDITORIALLY_INDEPENDENT",
            "rule_version": "independence-v1",
            "reason_codes": ["EDITORIAL_CONTROL"],
            "evidence_refs": ["review:editorial-policy"],
            "assessed_at": "2026-07-16T08:00:00+08:00",
        },
        "reason": "normalize assessment timestamps",
    }

    naive = client.post(
        endpoint,
        headers=admin,
        json={
            **payload,
            "authority": {
                **payload["authority"],
                "assessed_at": "2026-07-16T08:00:00",
            },
        },
    )
    normalized = client.post(endpoint, headers=admin, json=payload)

    assert naive.status_code == 422
    assert normalized.status_code == 200
    assert len(stub.assessment_payloads) == 1
    accepted = stub.assessment_payloads[0]
    assert accepted.authority.assessed_at == datetime(2026, 7, 16, tzinfo=UTC)
    assert accepted.authority.assessed_at.tzinfo is UTC
    assert accepted.independence.assessed_at == datetime(2026, 7, 16, tzinfo=UTC)
    assert accepted.independence.assessed_at.tzinfo is UTC


def test_round15_admin_rbac_matrix_and_saved_config_redaction() -> None:
    stub = SourceV2Stub()
    client = TestClient(create_app(checkers={}, source_service=stub))
    metadata = {
        "governance_owner_id": "019b1500-0000-7000-8000-000000000099",
        "country_codes": ["CN"],
        "region_codes": ["CN-SC"],
        "language_tags": ["zh-CN"],
        "industries": ["HIGHWAY"],
        "content_domains": ["SAFETY_REGULATION"],
        "declared_roles": ["OFFICIAL_PRIMARY"],
        "reason": "exercise the source administration RBAC matrix",
    }
    endpoint = f"/api/v1/admin/sources/{SOURCE_ID}/governance-metadata"

    for role in ("viewer", "editor", "reviewer", "auditor"):
        response = client.put(
            endpoint,
            headers={"X-SRBG-Local-Roles": role, "X-SRBG-Local-Step-Up": "true"},
            json=metadata,
        )
        assert response.status_code == 403

    for role in ("source_admin", "platform_admin"):
        response = client.put(
            endpoint,
            headers={"X-SRBG-Local-Roles": role},
            json=metadata,
        )
        assert response.status_code == 403

    auditor_read = client.get(
        "/api/v1/admin/connector-definitions",
        headers={"X-SRBG-Local-Roles": "auditor"},
    )
    platform_write = client.put(
        endpoint,
        headers={
            "X-SRBG-Local-Roles": "platform_admin",
            "X-SRBG-Local-Step-Up": "true",
        },
        json=metadata,
    )
    saved = client.post(
        f"/api/v1/admin/sources/{SOURCE_ID}/connector-config-versions",
        headers={
            "X-SRBG-Local-Roles": "source_admin",
            "X-SRBG-Local-Step-Up": "true",
        },
        json={
            "connector_type": "RSS_ATOM",
            "definition_version": "1.0.0",
            "config": {
                "allowed_hosts": ["example.test"],
                "feed_url": "https://example.test/feed",
                "credential_ref": "vault://source-connectors/example/rss",
            },
            "reason": "save the reviewed connector version",
        },
    )

    assert auditor_read.status_code == 200
    assert platform_write.status_code == 200
    assert saved.status_code == 201
    assert saved.json()["credential_configured"] is True
    assert "credential_ref" not in saved.text
