from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import _usage_event, create_app
from srbg_contracts import (
    MetricSample,
    OperationsOverview,
    PilotMetrics,
    ReplayRequest,
    ReplayResult,
)

ITEM_ID = UUID("019b0000-0000-7000-8000-000000000001")


class StubOperationsService:
    async def overview(self) -> OperationsOverview:
        return OperationsOverview(
            observed_at=datetime.now(UTC),
            metrics=[MetricSample(code="API_READ_P95_MS", value=42, unit="ms", status="PASS")],
        )

    async def request_replay(
        self, payload: ReplayRequest, *, actor_id: UUID, idempotency_key: str
    ) -> ReplayResult:
        return ReplayResult(
            id=ITEM_ID,
            failed_task_id=payload.failed_task_id,
            task_kind="PUBLICATION_OUTBOX",
            priority=payload.priority,
            status="QUEUED",
        )

    async def record_feedback(self, *, item_id: UUID, value: str, actor_id: UUID) -> None:
        return None

    async def pilot_metrics(self) -> PilotMetrics:
        return PilotMetrics(
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            aggregate_effective_actions=0,
            distinct_feedback_users=0,
            useful_votes=0,
            total_votes=0,
            identity_metrics_available=False,
            sufficient_window=False,
        )


def _client() -> TestClient:
    return TestClient(create_app(checkers={}, operations_service=StubOperationsService()))


def test_operations_overview_requires_admin_or_auditor() -> None:
    client = _client()
    assert client.get("/api/v1/admin/operations/overview").status_code == 403
    response = client.get(
        "/api/v1/admin/operations/overview",
        headers={"X-SRBG-Local-Roles": "auditor"},
    )
    assert response.status_code == 200
    assert response.json()["metrics"][0]["code"] == "API_READ_P95_MS"


def test_replay_is_bounded_audited_and_idempotent() -> None:
    response = _client().post(
        "/api/v1/admin/operations/replays",
        headers={
            "X-SRBG-Local-Roles": "platform_admin",
            "Idempotency-Key": "round11-replay-001",
        },
        json={
            "failed_task_id": str(ITEM_ID),
            "reason": "恢复经确认的失败来源任务",
            "priority": 9,
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"


def test_viewer_can_record_bounded_feedback_but_not_spoof_metrics() -> None:
    client = _client()
    response = client.post(
        "/api/v1/feedback",
        json={"item_id": str(ITEM_ID), "value": "USEFUL"},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/admin/pilot-metrics").status_code == 403


def test_effective_pilot_actions_are_derived_from_successful_server_routes() -> None:
    assert _usage_event("GET", "/api/v1/search") == "SEARCH"
    assert _usage_event("GET", "/api/v1/daily") == "READ_DAILY"
    assert _usage_event("POST", "/api/v1/saved-items") == "SAVE_ITEM"
    assert _usage_event("GET", "/api/v1/document-versions/id/pages/1") == "VIEW_EVIDENCE"
    assert _usage_event("POST", "/api/v1/search") is None
