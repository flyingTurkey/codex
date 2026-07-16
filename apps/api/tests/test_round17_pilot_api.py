from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.auth import Principal, get_current_principal
from srbg_api.config import get_settings
from srbg_api.main import create_app
from srbg_contracts import (
    GoldAnnotationRequest,
    GoldAnnotationView,
    OperatorTaskCompleteRequest,
    OperatorTaskCreateRequest,
    OperatorTaskStatus,
    OperatorTaskView,
    OperatorWorkCategory,
    OperatorWorkSessionCorrectionRequest,
    OperatorWorkSessionHeartbeatRequest,
    OperatorWorkSessionView,
    PilotSourceResumeRequest,
    PilotWindowCompleteRequest,
    PilotWindowCreateRequest,
    PilotWindowStartRequest,
    PilotWindowState,
    PilotWindowView,
    UserRole,
)

WINDOW_ID = UUID("019b1700-0000-7000-8000-000000000001")
TASK_ID = UUID("019b1700-0000-7000-8000-000000000002")
ANNOTATION_ID = UUID("019b1700-0000-7000-8000-000000000003")
SESSION_ID = UUID("019b1700-0000-7000-8000-000000000004")
OPERATOR_TASK_ID = UUID("019b1700-0000-7000-8000-000000000005")
YINZI_ID = UUID("019b1700-0000-7000-8000-000000000099")


def _source_codes() -> list[str]:
    return [f"GOV-{index:03d}" for index in range(1, 21)]


class StubRound17Operations:
    async def list_operator_tasks(self, *, actor_id: UUID) -> list[OperatorTaskView]:
        return [_operator_task(assigned_to=actor_id)]

    async def create_operator_task(
        self, payload: OperatorTaskCreateRequest, *, actor_id: UUID
    ) -> OperatorTaskView:
        assert payload.window_id == WINDOW_ID
        assert payload.category is OperatorWorkCategory.SOURCE_MAINTENANCE
        assert actor_id == UUID("019b1700-0000-7000-8000-000000000098")
        return _operator_task()

    async def complete_operator_task(
        self,
        task_id: UUID,
        payload: OperatorTaskCompleteRequest,
        *,
        actor_id: UUID,
    ) -> OperatorTaskView:
        assert task_id == OPERATOR_TASK_ID and payload.expected_version == 2
        assert actor_id == UUID("019b1700-0000-7000-8000-000000000098")
        return _operator_task(
            status=OperatorTaskStatus.COMPLETED,
            version=3,
            completed_by=actor_id,
        )

    async def prepare_pilot_window(
        self,
        payload: PilotWindowCreateRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView:
        assert actor_id and idempotency_key == "round17-prepare"
        return _window(PilotWindowState.PREPARING)

    async def start_pilot_window(
        self,
        window_id: UUID,
        payload: PilotWindowStartRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView:
        raise AssertionError("local identities must be rejected before service invocation")

    async def resume_pilot_source(
        self,
        window_id: UUID,
        source_code: str,
        payload: PilotSourceResumeRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView:
        assert window_id == WINDOW_ID
        assert source_code == "GOV-001"
        assert payload.expected_version == 4
        assert actor_id and idempotency_key == "round17-resume-source"
        return _window(PilotWindowState.RUNNING, version=5, running=True)

    async def complete_pilot_window(
        self,
        window_id: UUID,
        payload: PilotWindowCompleteRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView:
        assert window_id == WINDOW_ID
        assert payload.expected_version == 5
        assert actor_id and idempotency_key == "round17-complete-window"
        return _window(PilotWindowState.COMPLETED, version=6, running=True)

    async def start_work_session(
        self, *, actor_id: UUID, task_id: UUID
    ) -> OperatorWorkSessionView:
        now = datetime.now(UTC)
        assert task_id == OPERATOR_TASK_ID
        return OperatorWorkSessionView(
            id=SESSION_ID,
            task_id=task_id,
            window_id=WINDOW_ID,
            actor_id=actor_id,
            category=OperatorWorkCategory.SOURCE_MAINTENANCE,
            started_at=now,
            last_activity_at=now,
            stopped_at=None,
            active_seconds=None,
            corrected=False,
        )

    async def heartbeat_work_session(
        self,
        session_id: UUID,
        payload: OperatorWorkSessionHeartbeatRequest,
        *,
        actor_id: UUID,
    ) -> OperatorWorkSessionView:
        assert session_id == SESSION_ID and payload.expected_version == 1
        now = datetime.now(UTC)
        return OperatorWorkSessionView(
            id=session_id,
            task_id=OPERATOR_TASK_ID,
            window_id=WINDOW_ID,
            actor_id=actor_id,
            category=OperatorWorkCategory.SOURCE_MAINTENANCE,
            started_at=now,
            last_activity_at=now,
            stopped_at=None,
            active_seconds=None,
            corrected=False,
            version=2,
        )

    async def correct_work_session(
        self,
        session_id: UUID,
        payload: OperatorWorkSessionCorrectionRequest,
        *,
        reviewer_id: UUID,
    ) -> OperatorWorkSessionView:
        assert session_id == SESSION_ID
        assert payload.active_seconds == 300
        assert reviewer_id == UUID("019b1700-0000-7000-8000-000000000098")
        now = datetime.now(UTC)
        return OperatorWorkSessionView(
            id=session_id,
            task_id=OPERATOR_TASK_ID,
            window_id=WINDOW_ID,
            actor_id=UUID("019b1700-0000-7000-8000-000000000099"),
            category=OperatorWorkCategory.SOURCE_MAINTENANCE,
            started_at=now - timedelta(minutes=10),
            last_activity_at=now - timedelta(minutes=5),
            stopped_at=now,
            active_seconds=payload.active_seconds,
            corrected=True,
            version=3,
        )

    async def submit_gold_annotation(
        self, payload: GoldAnnotationRequest, *, actor_id: UUID
    ) -> GoldAnnotationView:
        return GoldAnnotationView(
            id=ANNOTATION_ID,
            task_id=payload.task_id,
            annotator_id=actor_id,
            sample_kind=payload.sample_kind,
            decision_code=payload.decision_code,
            submitted_at=datetime.now(UTC),
            status="SUBMITTED",
        )


def _window(
    state: PilotWindowState, *, version: int = 1, running: bool = False
) -> PilotWindowView:
    now = datetime.now(UTC)
    return PilotWindowView(
        id=WINDOW_ID,
        roster_version="r17-sources-v0.1",
        metric_definition_version="phase2-round17-metrics-v1.0.0",
        gold_definition_version="phase2-round17-gold-v1.0.0",
        baseline_commit="b08513965e931f363283384037fc1c1f068a1b1c",
        config_version="round17-config-v1",
        database_revision="0017b_round17_pilot",
        environment="PREPRODUCTION",
        duration_hours=168,
        source_count=20,
        state=state,
        version=version,
        prepared_at=now,
        started_at=now - timedelta(hours=1) if running else None,
        ends_at=now + timedelta(hours=167) if running else None,
        blocker_codes=["OIDC_IDENTITIES_MISSING", "SOURCE_APPROVALS_MISSING"],
    )


def _operator_task(
    *,
    assigned_to: UUID = YINZI_ID,
    status: OperatorTaskStatus = OperatorTaskStatus.PENDING,
    version: int = 1,
    completed_by: UUID | None = None,
) -> OperatorTaskView:
    now = datetime.now(UTC)
    return OperatorTaskView(
        id=OPERATOR_TASK_ID,
        window_id=WINDOW_ID,
        source_id=None,
        category=OperatorWorkCategory.SOURCE_MAINTENANCE,
        assigned_to=assigned_to,
        status=status,
        created_by=UUID("019b1700-0000-7000-8000-000000000098"),
        created_at=now,
        started_at=now if status is not OperatorTaskStatus.PENDING else None,
        completed_by=completed_by,
        completed_at=now if status is OperatorTaskStatus.COMPLETED else None,
        version=version,
    )


def _client() -> TestClient:
    return TestClient(create_app(checkers={}, operations_service=StubRound17Operations()))


def _oidc_client(*, identity_bound: bool = True) -> TestClient:
    app = create_app(checkers={}, operations_service=StubRound17Operations())
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=UUID("019b1700-0000-7000-8000-000000000099"),
        display_name="yinzi",
        roles=frozenset({UserRole.SOURCE_ADMIN}),
        local_identity=False,
        oidc_issuer="https://identity.srbg.example" if identity_bound else None,
        oidc_subject="yinzi-round17" if identity_bound else None,
    )
    return TestClient(app)


def _leo_client(*, mfa: bool = True, trusted_actor: bool = True) -> TestClient:
    app = create_app(checkers={}, operations_service=StubRound17Operations())
    leo_actor_id = UUID("019b1700-0000-7000-8000-000000000098")
    settings = get_settings().model_copy(
        update={
            "oidc_step_up_acr_values": ["urn:srbg:mfa"],
            "round17_leo_approver_actor_id": (
                leo_actor_id
                if trusted_actor
                else UUID("019b1700-0000-7000-8000-000000000097")
            ),
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=leo_actor_id,
        display_name="LEO",
        roles=frozenset({UserRole.GOLD_ARBITRATOR, UserRole.SOURCE_ADMIN}),
        local_identity=False,
        acr="urn:srbg:mfa" if mfa else None,
        amr=frozenset({"mfa"}) if mfa else frozenset(),
        authenticated_at=datetime.now(UTC),
        oidc_issuer="https://identity.srbg.example",
        oidc_subject="leo-round17",
    )
    return TestClient(app)


def test_source_admin_can_prepare_but_viewer_cannot() -> None:
    payload = {
        "roster_version": "r17-sources-v0.1",
        "metric_definition_version": "phase2-round17-metrics-v1.0.0",
        "gold_definition_version": "phase2-round17-gold-v1.0.0",
        "baseline_commit": "b08513965e931f363283384037fc1c1f068a1b1c",
        "config_version": "round17-config-v1",
        "database_revision": "0017b_round17_pilot",
        "source_codes": _source_codes(),
        "reason": "prepare the approved Round 17 pilot cohort",
    }
    assert _client().post("/api/v1/admin/pilot-windows", json=payload).status_code == 403
    response = _client().post(
        "/api/v1/admin/pilot-windows",
        headers={
            "X-SRBG-Local-Roles": "source_admin",
            "X-SRBG-Local-Step-Up": "true",
            "Idempotency-Key": "round17-prepare",
        },
        json=payload,
    )
    assert response.status_code == 201
    assert response.json()["state"] == "PREPARING"


def test_local_identity_cannot_start_a_real_window_even_with_role_and_step_up() -> None:
    response = _client().post(
        f"/api/v1/admin/pilot-windows/{WINDOW_ID}/start",
        headers={
            "X-SRBG-Local-Roles": "gold_arbitrator",
            "X-SRBG-Local-Step-Up": "true",
            "Idempotency-Key": "round17-start",
        },
        json={"expected_version": 1, "reason": "start approved 168 hour observation"},
    )
    assert response.status_code == 403


def test_controlled_mfa_leo_can_resume_a_paused_source_and_complete_window() -> None:
    client = _leo_client()
    resume = client.post(
        f"/api/v1/admin/pilot-windows/{WINDOW_ID}/sources/GOV-001/resume",
        headers={"Idempotency-Key": "round17-resume-source"},
        json={
            "expected_version": 4,
            "reason": "resume after the authoritative source approval was repaired",
        },
    )
    assert resume.status_code == 200
    assert resume.json()["version"] == 5

    complete = client.post(
        f"/api/v1/admin/pilot-windows/{WINDOW_ID}/complete",
        headers={"Idempotency-Key": "round17-complete-window"},
        json={
            "expected_version": 5,
            "reason": "complete the elapsed observation window with honest source states",
        },
    )
    assert complete.status_code == 200
    assert complete.json()["state"] == "COMPLETED"


def test_round17_lifecycle_commands_require_recent_mfa_and_nonlocal_identity() -> None:
    payload = {
        "expected_version": 4,
        "reason": "resume after the authoritative source approval was repaired",
    }
    no_mfa = _leo_client(mfa=False).post(
        f"/api/v1/admin/pilot-windows/{WINDOW_ID}/sources/GOV-001/resume",
        headers={"Idempotency-Key": "round17-resume-source"},
        json=payload,
    )
    assert no_mfa.status_code == 403

    local = _client().post(
        f"/api/v1/admin/pilot-windows/{WINDOW_ID}/complete",
        headers={
            "X-SRBG-Local-Roles": "gold_arbitrator",
            "X-SRBG-Local-Step-Up": "true",
            "Idempotency-Key": "round17-complete-window",
        },
        json={
            "expected_version": 5,
            "reason": "complete the elapsed observation window with honest source states",
        },
    )
    assert local.status_code == 403


def test_second_same_name_arbitrator_cannot_act_as_the_sole_attested_leo() -> None:
    response = _leo_client(trusted_actor=False).post(
        f"/api/v1/admin/pilot-windows/{WINDOW_ID}/sources/GOV-001/resume",
        headers={"Idempotency-Key": "round17-untrusted-leo"},
        json={
            "expected_version": 4,
            "reason": "attempt lifecycle action as a second same-name approver",
        },
    )

    assert response.status_code == 403


def test_work_timer_requires_controlled_identity_and_rejects_content() -> None:
    timer = _client().post(
        "/api/v1/admin/operator-work-sessions",
        headers={"X-SRBG-Local-Roles": "source_admin"},
        json={"task_id": str(OPERATOR_TASK_ID)},
    )
    assert timer.status_code == 403
    assert (
        _client().post(
            "/api/v1/admin/operator-work-sessions",
            headers={"X-SRBG-Local-Roles": "source_admin"},
            json={
                "task_id": str(OPERATOR_TASK_ID),
                "body": "forbidden",
            },
        ).status_code
        == 422
    )


def test_controlled_operator_can_start_and_heartbeat_window_bound_timer() -> None:
    client = _oidc_client()
    timer = client.post(
        "/api/v1/admin/operator-work-sessions",
        json={"task_id": str(OPERATOR_TASK_ID)},
    )
    assert timer.status_code == 201
    assert timer.json()["task_id"] == str(OPERATOR_TASK_ID)
    assert timer.json()["window_id"] == str(WINDOW_ID)
    heartbeat = client.post(
        f"/api/v1/admin/operator-work-sessions/{SESSION_ID}/heartbeat",
        json={"expected_version": 1},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["version"] == 2


def test_round17_operator_requires_verified_oidc_issuer_and_subject() -> None:
    response = _oidc_client(identity_bound=False).post(
        "/api/v1/admin/operator-work-sessions",
        json={"task_id": str(OPERATOR_TASK_ID)},
    )

    assert response.status_code == 403


def test_only_attested_leo_can_create_and_complete_yinzi_operator_tasks() -> None:
    payload = {
        "window_id": str(WINDOW_ID),
        "source_id": None,
        "category": "SOURCE_MAINTENANCE",
        "reason": "assign bounded source maintenance to yinzi",
    }
    assert _oidc_client().post("/api/v1/admin/operator-tasks", json=payload).status_code == 403

    leo = _leo_client()
    created = leo.post("/api/v1/admin/operator-tasks", json=payload)
    assert created.status_code == 201
    assert created.json()["assigned_to"] == "019b1700-0000-7000-8000-000000000099"
    completed = leo.post(
        f"/api/v1/admin/operator-tasks/{OPERATOR_TASK_ID}/complete",
        json={
            "expected_version": 2,
            "reason": "close the stopped and reviewed yinzi task",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"


def test_only_controlled_mfa_second_person_can_correct_operator_work() -> None:
    payload = {
        "expected_version": 2,
        "active_seconds": 300,
        "reason_code": "TIMER_INTERRUPTED",
    }
    operator_attempt = _oidc_client().post(
        f"/api/v1/admin/operator-work-sessions/{SESSION_ID}/corrections",
        json=payload,
    )
    assert operator_attempt.status_code == 403

    corrected = _leo_client().post(
        f"/api/v1/admin/operator-work-sessions/{SESSION_ID}/corrections",
        json=payload,
    )
    assert corrected.status_code == 200
    assert corrected.json()["actor_id"] == "019b1700-0000-7000-8000-000000000099"
    assert corrected.json()["corrected"] is True


def test_local_identity_cannot_submit_human_gold() -> None:

    annotation = _client().post(
        f"/api/v1/admin/gold-tasks/{TASK_ID}/annotations",
        headers={"X-SRBG-Local-Roles": "gold_annotator"},
        json={
            "task_id": str(TASK_ID),
            "sample_kind": "CLAIM_EVIDENCE",
            "decision_code": "SUPPORTED",
            "label_value": "publication_date=2026-07-16",
            "evidence_ids": [],
            "related_sample_refs": [],
        },
    )
    assert annotation.status_code == 403
