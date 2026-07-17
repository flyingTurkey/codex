from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from srbg_api.auth import Principal
from srbg_api.config import Settings
from srbg_api.main import create_app
from srbg_api.source_automation.api import _recent_platform_step_up
from srbg_contracts import (
    CursorPage,
    DiscoveryChannel,
    QualificationBundleView,
    QualificationVerdict,
    SourceCandidateDecisionResult,
    SourceCandidateStatus,
    SourceCandidateSummary,
    StoragePolicy,
    UserRole,
)

CANDIDATE_ID = UUID("019b1800-0000-7000-8000-000000000001")
SOURCE_ID = UUID("019b1800-0000-7000-8000-000000000002")
NOW = datetime.now(UTC)


def _bundle() -> QualificationBundleView:
    return QualificationBundleView(
        id=UUID("019b1800-0000-7000-8000-000000000003"),
        candidate_id=CANDIDATE_ID,
        run_id=UUID("019b1800-0000-7000-8000-000000000004"),
        rule_version="source-qualification-v1",
        material_fingerprint="a" * 64,
        verdict=QualificationVerdict.QUALIFIED,
        storage_policy=StoragePolicy.RAW_EVIDENCE_ALLOWED,
        checks=[],
        sampled_item_count=4,
        relevant_item_count=4,
        reason_codes=[],
        bundle_sha256="b" * 64,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def _candidate() -> SourceCandidateSummary:
    return SourceCandidateSummary(
        id=CANDIDATE_ID,
        institution_name="四川省交通运输厅",
        canonical_url="https://jtt.sc.gov.cn/",
        authorization_boundary="jtt.sc.gov.cn",
        discovery_channels=[DiscoveryChannel.BAIDU_SEARCH],
        status=SourceCandidateStatus.READY_FOR_DECISION,
        industries=[],
        content_domains=[],
        language_tags=["zh-CN"],
        occurrence_count=2,
        first_discovered_at=NOW,
        last_discovered_at=NOW,
        latest_qualification=_bundle(),
        available_actions=["REQUEST_QUALIFICATION", "ENABLE", "DISMISS"],
        batch_enable_eligible=True,
    )


class AutomationStub:
    def __init__(self) -> None:
        self.decision_calls: list[tuple[UUID, str, UUID]] = []

    async def list_candidates(self, **_: object) -> CursorPage[SourceCandidateSummary]:
        return CursorPage(items=[_candidate()], next_cursor=None, has_more=False)

    async def decide_candidate(
        self,
        candidate_id: UUID,
        payload: object,
        *,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
    ) -> SourceCandidateDecisionResult:
        assert request_id and idempotency_key
        self.decision_calls.append((candidate_id, idempotency_key, actor_id))
        return SourceCandidateDecisionResult(
            candidate_id=candidate_id,
            status=SourceCandidateStatus.ENABLED,
            source_id=SOURCE_ID,
            production_refetch_enqueued=True,
            idempotent_replay=False,
            decided_at=NOW,
        )


def test_candidate_listing_is_readable_but_enable_is_platform_admin_only() -> None:
    service = AutomationStub()
    client = TestClient(create_app(checkers={}, source_automation_service=service))

    listing = client.get(
        "/api/v1/admin/source-candidates?limit=20&status=READY_FOR_DECISION",
        headers={"X-SRBG-Local-Roles": "source_admin"},
    )
    source_admin_decision = client.post(
        f"/api/v1/admin/source-candidates/{CANDIDATE_ID}/decisions",
        headers={
            "X-SRBG-Local-Roles": "source_admin",
            "X-SRBG-Local-Step-Up": "true",
            "Idempotency-Key": "019b1800-0000-7000-8000-000000000099",
        },
        json={
            "decision": "ENABLE",
            "expected_bundle_sha256": "b" * 64,
            "reason": "source admin cannot make the final decision",
        },
    )
    platform_decision = client.post(
        f"/api/v1/admin/source-candidates/{CANDIDATE_ID}/decisions",
        headers={
            "X-SRBG-Local-Roles": "platform_admin",
            "X-SRBG-Local-Step-Up": "true",
            "Idempotency-Key": "019b1800-0000-7000-8000-000000000098",
        },
        json={
            "decision": "ENABLE",
            "expected_bundle_sha256": "b" * 64,
            "reason": "enable a current all-green qualification bundle",
        },
    )

    assert listing.status_code == 200
    assert listing.json()["items"][0]["latest_qualification"]["bundle_sha256"] == "b" * 64
    assert source_admin_decision.status_code == 403
    assert platform_decision.status_code == 200
    assert platform_decision.json()["production_refetch_enqueued"] is True
    assert len(service.decision_calls) == 1


def test_candidate_decision_requires_step_up_and_idempotency_key() -> None:
    client = TestClient(create_app(checkers={}, source_automation_service=AutomationStub()))
    payload = {
        "decision": "ENABLE",
        "expected_bundle_sha256": "b" * 64,
        "reason": "enable current candidate",
    }

    no_step_up = client.post(
        f"/api/v1/admin/source-candidates/{CANDIDATE_ID}/decisions",
        headers={"X-SRBG-Local-Roles": "platform_admin", "Idempotency-Key": "valid-key-123"},
        json=payload,
    )
    no_key = client.post(
        f"/api/v1/admin/source-candidates/{CANDIDATE_ID}/decisions",
        headers={
            "X-SRBG-Local-Roles": "platform_admin",
            "X-SRBG-Local-Step-Up": "true",
        },
        json=payload,
    )

    assert no_step_up.status_code == 403
    assert no_key.status_code == 422


@pytest.mark.asyncio
async def test_production_candidate_decision_rejects_mfa_older_than_five_minutes() -> None:
    principal = Principal(
        user_id=UUID("019b1800-0000-7000-8000-000000000090"),
        display_name="platform administrator",
        roles=frozenset({UserRole.PLATFORM_ADMIN}),
        local_identity=False,
        acr="urn:srbg:mfa",
        amr=frozenset({"mfa"}),
        authenticated_at=datetime.now(UTC) - timedelta(minutes=6),
    )

    with pytest.raises(HTTPException) as error:
        await _recent_platform_step_up(principal, Settings())

    assert error.value.status_code == 403
    assert "five minutes" in str(error.value.detail)
