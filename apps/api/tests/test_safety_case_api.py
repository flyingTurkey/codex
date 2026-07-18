from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import EventDetail, EventTimeline, UnverifiedFact

EVENT_ID = UUID("019b0000-0000-7000-8000-000000041001")
ITEM_ID = UUID("019b0000-0000-7000-8000-000000041002")
CONFLICT_ID = UUID("019b0000-0000-7000-8000-000000041004")


class StubSafetyCaseQuery:
    async def get_event(self, event_id: UUID) -> EventDetail:
        assert event_id == EVENT_ID
        return EventDetail(
            id=EVENT_ID,
            event_type="SAFETY_INCIDENT",
            title="梅大高速茶阳路段塌方灾害",
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
                    reason="正式来源数字冲突, 未形成证据事实。",
                    evidence_ids=[],
                )
            ],
            timeline=EventTimeline(event_id=EVENT_ID, items=[]),
            relations=[],
            similar_scenario_tags=["HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
            prevention_measure_tags=["MONITORING_AND_EARLY_WARNING"],
        )


def _client() -> TestClient:
    return TestClient(
        create_app(
            checkers={},
            source_service=None,
            intelligence_service=StubSafetyCaseQuery(),  # type: ignore[arg-type]
            publication_service=None,
        )
    )


def test_owner_event_projection_hides_conflicting_values() -> None:
    response = _client().get(f"/api/v1/events/{EVENT_ID}")

    assert response.status_code == 200
    fact = response.json()["unverified_facts"][0]
    assert fact["value"] is None
    assert fact["claim_id"] is None
    assert fact["evidence_ids"] == []
    assert "current_value" not in response.text
    assert "candidate_value" not in response.text


def test_claim_conflict_review_apis_are_retired_for_every_legacy_role() -> None:
    client = _client()
    for role in ("owner", "reviewer", "source_admin", "platform_admin"):
        headers = {"X-SRBG-Local-Roles": role}
        assert client.get("/api/v1/admin/claim-conflicts", headers=headers).status_code == 404
        assert (
            client.post(
                f"/api/v1/admin/claim-conflicts/{CONFLICT_ID}/decisions",
                headers=headers,
                json={"action": "ACCEPT_CANDIDATE", "reason": "legacy"},
            ).status_code
            == 404
        )
