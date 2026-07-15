from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import (
    ClaimConflict,
    ClaimConflictDecisionResponse,
    EventDetail,
    EventTimeline,
    UnverifiedFact,
)

EVENT_ID = UUID("019b0000-0000-7000-8000-000000041001")
ITEM_ID = UUID("019b0000-0000-7000-8000-000000041002")
CLAIM_ID = UUID("019b0000-0000-7000-8000-000000041003")
CONFLICT_ID = UUID("019b0000-0000-7000-8000-000000041004")
CANDIDATE_CLAIM_ID = UUID("019b0000-0000-7000-8000-000000041005")
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000041006")
NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


class StubSafetyCaseQuery:
    async def get_event(self, event_id: UUID) -> EventDetail:
        assert event_id == EVENT_ID
        return EventDetail(
            id=EVENT_ID,
            event_type="SAFETY_INCIDENT",
            title="梅大高速茶阳路段“5·1”塌方灾害",
            project_name="梅大高速东延线",
            occurred_at=datetime(2024, 4, 30, 17, 57, tzinfo=UTC),
            region="广东省梅州市大埔县",
            hazard_type="GEOLOGICAL_DISASTER",
            engineering_type="HIGHWAY",
            incident_status="UNDER_INVESTIGATION",
            confirmed_facts=[],
            unverified_facts=[
                UnverifiedFact(
                    source_item_id=ITEM_ID,
                    claim_id=None,
                    conflict_id=CONFLICT_ID,
                    field="DEATH_COUNT",
                    label="死亡人数",
                    status="CONFLICTING",
                    reason="正式来源数字存在冲突。等待人工决定。",
                    evidence_ids=[],
                )
            ],
            timeline=EventTimeline(event_id=EVENT_ID, items=[]),
            relations=[],
            similar_scenario_tags=["HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
            prevention_measure_tags=["MONITORING_AND_EARLY_WARNING"],
        )


class StubSafetyCasePublication:
    reviewer_id: UUID | None = None

    async def list_claim_conflicts(self) -> list[ClaimConflict]:
        return [
            ClaimConflict(
                id=CONFLICT_ID,
                event_id=EVENT_ID,
                field="DEATH_COUNT",
                current_claim_id=CLAIM_ID,
                current_value=48,
                candidate_claim_id=CANDIDATE_CLAIM_ID,
                candidate_value=52,
                status="PENDING_REVIEW",
                detected_at=NOW,
            )
        ]

    async def resolve_claim_conflict(
        self,
        conflict_id: UUID,
        *,
        action: str,
        reason: str,
        reviewer_id: UUID,
    ) -> ClaimConflictDecisionResponse:
        assert conflict_id == CONFLICT_ID
        assert action == "ACCEPT_CANDIDATE"
        assert reason
        self.reviewer_id = reviewer_id
        return ClaimConflictDecisionResponse(
            conflict_id=conflict_id,
            status="RESOLVED",
            action="ACCEPT_CANDIDATE",
            resolved_claim_id=CANDIDATE_CLAIM_ID,
            resolved_at=NOW,
        )


def _client() -> tuple[TestClient, StubSafetyCasePublication]:
    publication = StubSafetyCasePublication()
    return (
        TestClient(
            create_app(
                checkers={},
                source_service=None,
                intelligence_service=StubSafetyCaseQuery(),  # type: ignore[arg-type]
                publication_service=publication,  # type: ignore[arg-type]
            ),
            headers={"X-SRBG-Local-Step-Up": "true"},
        ),
        publication,
    )


def test_viewer_event_projection_hides_both_conflicting_values() -> None:
    client, _ = _client()

    response = client.get(
        f"/api/v1/events/{EVENT_ID}", headers={"X-SRBG-Local-Roles": "viewer"}
    )

    assert response.status_code == 200
    fact = response.json()["unverified_facts"][0]
    assert fact["display_value"] == "待核实"
    assert fact["value"] is None
    assert fact["claim_id"] is None
    assert fact["evidence_ids"] == []
    assert "current_value" not in response.text
    assert "candidate_value" not in response.text


def test_conflict_workbench_is_reviewer_only() -> None:
    client, _ = _client()

    denied = client.get(
        "/api/v1/admin/claim-conflicts", headers={"X-SRBG-Local-Roles": "viewer"}
    )
    allowed = client.get(
        "/api/v1/admin/claim-conflicts", headers={"X-SRBG-Local-Roles": "reviewer"}
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()[0]["current_value"] == 48
    assert allowed.json()[0]["candidate_value"] == 52


def test_conflict_decision_uses_server_identity_and_single_publication_service() -> None:
    client, publication = _client()

    response = client.post(
        f"/api/v1/admin/claim-conflicts/{CONFLICT_ID}/decisions",
        headers={
            "X-SRBG-Local-Roles": "reviewer",
            "X-SRBG-Local-User-ID": str(REVIEWER_ID),
        },
        json={
            "action": "ACCEPT_CANDIDATE",
            "reason": "正式调查报告是更新且经逐字段审核的官方证据",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "RESOLVED"
    assert publication.reviewer_id == REVIEWER_ID
