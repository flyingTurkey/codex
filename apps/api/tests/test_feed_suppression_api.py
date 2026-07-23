from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import FeedSuppressionCommand

NOW = datetime(2026, 7, 23, tzinfo=UTC)
RULE_ID = UUID("019f9000-0000-7000-8000-000000000044")
IDEMPOTENCY_KEY = "019f9000-0000-7000-8000-000000000045"


class FakeSuppressionService:
    def __init__(self) -> None:
        self.commands: list[tuple[FeedSuppressionCommand, UUID, UUID, UUID | None]] = []

    async def close(self) -> None:
        pass

    async def list_feed_suppressions(self, *, active_only: bool):
        assert active_only is True
        return [self._view()]

    async def command_feed_suppression(
        self,
        *,
        command: FeedSuppressionCommand,
        owner_id: UUID,
        idempotency_key: UUID,
        expected_rule_id: UUID | None,
    ):
        self.commands.append((command, owner_id, idempotency_key, expected_rule_id))
        return self._view(action=command.action.value, supersedes=command.supersedes_rule_id)

    @staticmethod
    def _view(*, action: str = "ACTIVATE", supersedes: UUID | None = None):
        return {
            "id": RULE_ID,
            "action": action,
            "scope": "PRIMARY_TYPE",
            "target_key": "INDUSTRY_UPDATE",
            "feedback_reason": "OWNER_PREFERENCE",
            "supersedes_rule_id": supersedes,
            "effective_at": NOW,
            "created_at": NOW,
        }


def test_owner_can_list_and_activate_feed_suppression_idempotently() -> None:
    service = FakeSuppressionService()
    with TestClient(create_app(publication_service=service)) as client:
        listed = client.get("/api/v2/owner/suppressions?active_only=true")
        missing_key = client.post(
            "/api/v2/owner/suppressions",
            json={
                "action": "ACTIVATE",
                "scope": "PRIMARY_TYPE",
                "target_key": "INDUSTRY_UPDATE",
                "feedback_reason": "OWNER_PREFERENCE",
            },
        )
        activated = client.post(
            "/api/v2/owner/suppressions",
            json={
                "action": "ACTIVATE",
                "scope": "PRIMARY_TYPE",
                "target_key": "INDUSTRY_UPDATE",
                "feedback_reason": "OWNER_PREFERENCE",
            },
            headers={"Idempotency-Key": IDEMPOTENCY_KEY},
        )

    assert listed.status_code == 200
    assert listed.json()[0]["id"] == str(RULE_ID)
    assert missing_key.status_code == 422
    assert activated.status_code == 201
    assert service.commands[0][3] is None


def test_revocation_requires_matching_if_match_and_rejects_safety_semantics() -> None:
    service = FakeSuppressionService()
    body = {
        "action": "REVOKE",
        "scope": "PRIMARY_TYPE",
        "target_key": "INDUSTRY_UPDATE",
        "feedback_reason": "OWNER_PREFERENCE",
        "supersedes_rule_id": str(RULE_ID),
    }
    with TestClient(create_app(publication_service=service)) as client:
        missing_precondition = client.post(
            "/api/v2/owner/suppressions", json=body, headers={"Idempotency-Key": IDEMPOTENCY_KEY}
        )
        mismatch = client.post(
            "/api/v2/owner/suppressions",
            json=body,
            headers={"Idempotency-Key": IDEMPOTENCY_KEY, "If-Match": '"different"'},
        )
        revoked = client.post(
            "/api/v2/owner/suppressions",
            json=body,
            headers={"Idempotency-Key": IDEMPOTENCY_KEY, "If-Match": f'"{RULE_ID}"'},
        )
        forbidden_safety = client.post(
            "/api/v2/owner/suppressions",
            json={
                "action": "ACTIVATE",
                "scope": "EVENT",
                "target_key": str(RULE_ID),
                "feedback_reason": "SAFETY_DENIAL",
            },
            headers={"Idempotency-Key": IDEMPOTENCY_KEY},
        )

    assert missing_precondition.status_code == 428
    assert mismatch.status_code == 412
    assert revoked.status_code == 201
    assert service.commands[0][3] == RULE_ID
    assert forbidden_safety.status_code == 422
