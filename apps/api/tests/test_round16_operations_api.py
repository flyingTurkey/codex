from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import (
    CircuitState,
    FetchScheduleStatus,
    FetchScheduleUpdate,
    FetchScheduleView,
    OperationsOverview,
    PilotMetrics,
    ReplayRequest,
    ReplayResult,
    SourceLifecycleActionRequest,
)

SOURCE_ID = UUID("019b1600-0000-7000-8000-000000000001")


class Stub:
    async def overview(self) -> OperationsOverview:
        return OperationsOverview(observed_at=datetime.now(UTC), metrics=[])

    async def get_schedule(self, source_id: UUID) -> FetchScheduleView:
        return self._view(source_id, 1)

    async def update_schedule(
        self,
        source_id: UUID,
        payload: FetchScheduleUpdate,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> FetchScheduleView:
        assert actor_id and idempotency_key == "round16-schedule"
        return self._view(source_id, payload.expected_version + 1)

    async def repair_schedule(
        self,
        source_id: UUID,
        payload: SourceLifecycleActionRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> FetchScheduleView:
        assert actor_id and payload.reason and idempotency_key == "round18-repair"
        return self._view(source_id, 2)

    async def source_health(self) -> list[object]:
        return []

    async def list_replays(self) -> list[object]:
        return []

    async def request_replay(
        self, payload: ReplayRequest, *, actor_id: UUID, idempotency_key: str
    ) -> ReplayResult:
        raise AssertionError("not used")

    async def pilot_metrics(self) -> PilotMetrics:
        now = datetime.now(UTC)
        return PilotMetrics(
            started_at=now,
            ended_at=now,
            aggregate_effective_actions=0,
            distinct_feedback_users=0,
            useful_votes=0,
            total_votes=0,
            identity_metrics_available=False,
            sufficient_window=False,
        )

    @staticmethod
    def _view(source_id: UUID, version: int) -> FetchScheduleView:
        now = datetime.now(UTC)
        return FetchScheduleView(
            source_id=source_id,
            authority_level="A1",
            status=FetchScheduleStatus.ACTIVE,
            interval_seconds=3600,
            next_run_at=now,
            circuit_state=CircuitState.CLOSED,
            consecutive_failures=0,
            freshness_slo_seconds=86400,
            rate_limit_per_minute=1,
            daily_request_budget=24,
            daily_byte_budget=10_000_000,
            requests_used=0,
            bytes_used=0,
            version=version,
            updated_at=now,
        )


def test_schedule_rbac_step_up_and_strict_payload() -> None:
    client = TestClient(create_app(checkers={}, operations_service=Stub()))
    endpoint = f"/api/v1/admin/sources/{SOURCE_ID}/schedule"
    payload = {
        "status": "ACTIVE",
        "interval_seconds": 3600,
        "freshness_slo_seconds": 86400,
        "rate_limit_per_minute": 1,
        "daily_request_budget": 24,
        "daily_byte_budget": 10_000_000,
        "expected_version": 0,
        "reason": "approved source scheduling update",
    }
    assert client.get(endpoint, headers={"X-SRBG-Local-Roles": "auditor"}).status_code == 200
    assert (
        client.put(
            endpoint,
            headers={"X-SRBG-Local-Roles": "source_admin", "Idempotency-Key": "round16-schedule"},
            json=payload,
        ).status_code
        == 403
    )
    response = client.put(
        endpoint,
        headers={
            "X-SRBG-Local-Roles": "source_admin",
            "X-SRBG-Local-Step-Up": "true",
            "Idempotency-Key": "round16-schedule",
        },
        json=payload,
    )
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert (
        client.put(
            endpoint,
            headers={
                "X-SRBG-Local-Roles": "source_admin",
                "X-SRBG-Local-Step-Up": "true",
                "Idempotency-Key": "round16-schedule",
            },
            json=payload | {"body": "forbidden"},
        ).status_code
        == 422
    )


def test_health_and_replay_lists_are_read_only_for_auditor() -> None:
    client = TestClient(create_app(checkers={}, operations_service=Stub()))
    headers = {"X-SRBG-Local-Roles": "auditor"}
    assert client.get("/api/v1/admin/operations/source-health", headers=headers).status_code == 200
    assert client.get("/api/v1/admin/operations/replays", headers=headers).status_code == 200


def test_schedule_repair_requires_step_up_and_uses_a_bounded_command() -> None:
    client = TestClient(create_app(checkers={}, operations_service=Stub()))
    endpoint = f"/api/v1/admin/sources/{SOURCE_ID}/schedule/repair"
    payload = {"reason": "reset the open circuit after verified connector repair"}

    assert (
        client.post(
            endpoint,
            headers={
                "X-SRBG-Local-Roles": "source_admin",
                "Idempotency-Key": "round18-repair",
            },
            json=payload,
        ).status_code
        == 403
    )
    response = client.post(
        endpoint,
        headers={
            "X-SRBG-Local-Roles": "source_admin",
            "X-SRBG-Local-Step-Up": "true",
            "Idempotency-Key": "round18-repair",
        },
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["circuit_state"] == "CLOSED"
    assert response.json()["consecutive_failures"] == 0
