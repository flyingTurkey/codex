from collections.abc import Callable
from datetime import date
from uuid import UUID

import pytest
import srbg_api.main as main
from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_api.safety_cases.candidates import (
    EventCandidateAlreadyDecided,
    EventCandidateContext,
    EventCandidateRecord,
    PostgresEventCandidateStore,
    SafetyEventCandidateService,
)
from srbg_api.safety_cases.domain import EventIdentity

EVENT_ID = UUID("019b0000-0000-7000-8000-000000043001")
ITEM_ID = UUID("019b0000-0000-7000-8000-000000043002")
CANDIDATE_ID = UUID("019b0000-0000-7000-8000-000000043003")
CALLER_ID = UUID("019b0000-0000-7000-8000-000000043004")


class RecordingCandidateStore:
    def __init__(self) -> None:
        self.saved: EventCandidateRecord | None = None
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def create_candidate(
        self,
        *,
        event_id: UUID,
        item_id: UUID,
        build: Callable[[EventCandidateContext, EventIdentity], EventCandidateRecord | None],
    ) -> UUID | None:
        assert event_id == EVENT_ID
        assert item_id == ITEM_ID
        candidate = build(
            EventCandidateContext(
                identity=_matching_identity(),
                confirmation_status="CONFIRMED",
                member_count=1,
                candidate_count=0,
            ),
            _matching_identity(),
        )
        if candidate is None:
            return None
        self.saved = candidate
        return CANDIDATE_ID


class NoCandidateService:
    called_with: tuple[UUID, UUID] | None = None

    async def generate_candidate(self, *, event_id: UUID, item_id: UUID) -> None:
        self.called_with = (event_id, item_id)


class FailedCandidateService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def generate_candidate(self, *, event_id: UUID, item_id: UUID) -> None:
        assert (event_id, item_id) == (EVENT_ID, ITEM_ID)
        raise self.error


def _matching_identity() -> EventIdentity:
    return EventIdentity(
        occurred_on=date(2024, 5, 1),
        region="广东省梅州市大埔县",
        project="梅大高速东延线K11+900~K11+950",
        subjects=("广东博大高速公路有限公司梅大分公司",),
        accident_type="ROADBED_COLLAPSE",
    )


def _client(service: object) -> TestClient:
    return TestClient(
        create_app(
            checkers={},
            safety_event_candidate_service=service,  # type: ignore[arg-type]
        )
    )


def test_viewer_cannot_generate_safety_event_candidates() -> None:
    store = RecordingCandidateStore()
    client = _client(SafetyEventCandidateService(store))

    response = client.post(
        f"/api/v1/admin/events/{EVENT_ID}/candidate-items/{ITEM_ID}",
        headers={"X-SRBG-Local-Roles": "viewer"},
    )

    assert response.status_code == 403
    assert store.saved is None


@pytest.mark.parametrize("role", ["editor", "reviewer", "platform_admin"])
def test_authorized_role_invokes_real_candidate_service_and_gets_review_queue_contract(
    role: str,
) -> None:
    store = RecordingCandidateStore()
    client = _client(SafetyEventCandidateService(store))

    response = client.post(
        f"/api/v1/admin/events/{EVENT_ID}/candidate-items/{ITEM_ID}",
        headers={"X-SRBG-Local-Roles": role},
    )

    assert response.status_code == 202
    assert response.json() == {
        "candidate_id": str(CANDIDATE_ID),
        "status": "PENDING_REVIEW",
        "requires_human_review": True,
    }
    assert store.saved is not None
    assert store.saved.event_id == EVENT_ID
    assert store.saved.item_id == ITEM_ID
    assert store.saved.requires_human_review is True


def test_candidate_generation_has_no_caller_supplied_submitter_contract() -> None:
    store = RecordingCandidateStore()
    client = _client(SafetyEventCandidateService(store))
    path = f"/api/v1/admin/events/{EVENT_ID}/candidate-items/{ITEM_ID}"

    response = client.post(
        path,
        headers={"X-SRBG-Local-Roles": "editor"},
        json={"submitted_by": str(CALLER_ID)},
    )

    assert response.status_code == 202
    assert store.saved is not None
    assert not hasattr(store.saved, "submitted_by")
    operation = client.get("/openapi.json").json()["paths"][
        "/api/v1/admin/events/{event_id}/candidate-items/{item_id}"
    ]["post"]
    assert "requestBody" not in operation


def test_candidate_below_threshold_returns_conflict() -> None:
    service = NoCandidateService()
    client = _client(service)

    response = client.post(
        f"/api/v1/admin/events/{EVENT_ID}/candidate-items/{ITEM_ID}",
        headers={"X-SRBG-Local-Roles": "editor"},
    )

    assert response.status_code == 409
    assert service.called_with == (EVENT_ID, ITEM_ID)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (LookupError("missing"), 404),
        (EventCandidateAlreadyDecided("decided"), 409),
    ],
)
def test_candidate_generation_maps_expected_domain_errors_to_problem_details(
    error: Exception,
    expected_status: int,
) -> None:
    response = _client(FailedCandidateService(error)).post(
        f"/api/v1/admin/events/{EVENT_ID}/candidate-items/{ITEM_ID}",
        headers={"X-SRBG-Local-Roles": "editor"},
    )

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/problem+json")


def test_candidate_service_participates_in_application_lifespan() -> None:
    store = RecordingCandidateStore()

    with _client(SafetyEventCandidateService(store)):
        assert store.closed is False

    assert store.closed is True


def test_default_app_wires_postgres_candidate_service(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_engine = object()
    monkeypatch.setattr(main, "create_database_engine", lambda _settings: runtime_engine)
    monkeypatch.setattr(main, "create_publication_engine", lambda _settings: object())
    monkeypatch.setattr(main, "build_default_source_service", lambda _settings: None)

    app = main.build_default_app()

    service = app.state.safety_event_candidate_service
    assert isinstance(service, SafetyEventCandidateService)
    assert isinstance(service._store, PostgresEventCandidateStore)
