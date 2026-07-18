from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.auth import LOCAL_USER_ID
from srbg_api.main import create_app
from srbg_contracts import (
    OwnerRelationshipCorrectionRequest,
    OwnerRelationshipCorrectionResponse,
)

EVENT_ID = UUID("019b0000-0000-7000-8000-000000008001")
DECISION_ID = UUID("019b0000-0000-7000-8000-000000008002")
COMMAND_ID = UUID("019b0000-0000-7000-8000-000000008003")


class StubPublicationService:
    call: tuple[UUID, OwnerRelationshipCorrectionRequest, UUID] | None = None

    async def correct_automatic_relationship(
        self,
        event_id: UUID,
        *,
        payload: OwnerRelationshipCorrectionRequest,
        owner_id: UUID,
    ) -> OwnerRelationshipCorrectionResponse:
        self.call = (event_id, payload, owner_id)
        return OwnerRelationshipCorrectionResponse(
            correction_id=COMMAND_ID,
            event_id=event_id,
            action=payload.action,
            event_version=2,
            projection_generation=4,
        )


def _client(service: StubPublicationService) -> TestClient:
    return TestClient(create_app(publication_service=service))


def test_fixed_local_owner_can_withdraw_an_automatic_relationship() -> None:
    service = StubPublicationService()
    response = _client(service).post(
        f"/api/v1/events/{EVENT_ID}/relationship-corrections",
        headers={"X-SRBG-Local-Roles": "owner"},
        json={
            "command_id": str(COMMAND_ID),
            "action": "WITHDRAW_RELATION",
            "decision_id": str(DECISION_ID),
            "reason": "different incidents",
        },
    )
    assert response.status_code == 200
    assert response.json()["projection_generation"] == 4
    assert service.call is not None and service.call[2] == LOCAL_USER_ID


def test_role_header_cannot_change_fixed_owner_authority() -> None:
    service = StubPublicationService()
    response = _client(service).post(
        f"/api/v1/events/{EVENT_ID}/relationship-corrections",
        headers={"X-SRBG-Local-Roles": "viewer"},
        json={
            "command_id": str(COMMAND_ID),
            "action": "WITHDRAW_RELATION",
            "decision_id": str(DECISION_ID),
            "reason": "different incidents",
        },
    )
    assert response.status_code == 200
    assert service.call is not None and service.call[2] == LOCAL_USER_ID


def test_owner_correction_rejects_unknown_fields() -> None:
    response = _client(StubPublicationService()).post(
        f"/api/v1/events/{EVENT_ID}/relationship-corrections",
        headers={"X-SRBG-Local-Roles": "owner"},
        json={
            "command_id": str(COMMAND_ID),
            "action": "WITHDRAW_RELATION",
            "decision_id": str(DECISION_ID),
            "reason": "different incidents",
            "publication_status": "PUBLISHED",
        },
    )
    assert response.status_code == 422
