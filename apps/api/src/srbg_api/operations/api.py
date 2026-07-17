"""Fail-closed operational APIs with bounded replay and feedback inputs."""

from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response, status
from srbg_contracts import (
    FeedbackRequest,
    FetchScheduleUpdate,
    FetchScheduleView,
    GoldAnnotationRequest,
    GoldAnnotationView,
    GoldArbitrationPacket,
    GoldArbitrationRequest,
    GoldReleaseRequest,
    GoldReleaseView,
    GoldTaskCreateRequest,
    GoldTaskView,
    OperationsOverview,
    OperatorTaskCompleteRequest,
    OperatorTaskCreateRequest,
    OperatorTaskView,
    OperatorWorkSessionCorrectionRequest,
    OperatorWorkSessionHeartbeatRequest,
    OperatorWorkSessionStart,
    OperatorWorkSessionStopRequest,
    OperatorWorkSessionView,
    PilotMetrics,
    PilotSourceResumeRequest,
    PilotWindowCompleteRequest,
    PilotWindowCreateRequest,
    PilotWindowStartRequest,
    PilotWindowView,
    ReplayRequest,
    ReplayResult,
    ReplayTaskView,
    SourceHealthView,
    SourceLifecycleActionRequest,
    UserRole,
)

from srbg_api.auth import (
    Principal,
    get_current_principal,
    require_roles,
    require_roles_with_step_up,
)
from srbg_api.config import Settings, get_settings

ReadPrincipal = Annotated[
    Principal,
    Depends(require_roles(UserRole.PLATFORM_ADMIN, UserRole.AUDITOR)),
]
WritePrincipal = Annotated[Principal, Depends(require_roles(UserRole.PLATFORM_ADMIN))]
ScheduleReadPrincipal = Annotated[
    Principal,
    Depends(require_roles(UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN, UserRole.AUDITOR)),
]
ScheduleWritePrincipal = Annotated[
    Principal,
    Depends(require_roles_with_step_up(UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN)),
]
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
PilotPreparePrincipal = Annotated[
    Principal,
    Depends(require_roles_with_step_up(UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN)),
]
PilotReadPrincipal = Annotated[
    Principal,
    Depends(
        require_roles(
            UserRole.SOURCE_ADMIN,
            UserRole.PLATFORM_ADMIN,
            UserRole.AUDITOR,
            UserRole.GOLD_ARBITRATOR,
        )
    ),
]
PilotStartPrincipal = Annotated[
    Principal,
    Depends(require_roles_with_step_up(UserRole.GOLD_ARBITRATOR)),
]
PilotLifecyclePrincipal = PilotStartPrincipal
GoldAnnotatorPrincipal = Annotated[
    Principal,
    Depends(require_roles(UserRole.GOLD_ANNOTATOR)),
]
GoldArbitratorPrincipal = Annotated[
    Principal,
    Depends(require_roles_with_step_up(UserRole.GOLD_ARBITRATOR)),
]
GoldReadPrincipal = Annotated[
    Principal,
    Depends(
        require_roles(
            UserRole.GOLD_ANNOTATOR,
            UserRole.GOLD_ARBITRATOR,
            UserRole.AUDITOR,
        )
    ),
]
WorkPrincipal = Annotated[
    Principal,
    Depends(
        require_roles(
            UserRole.SOURCE_ADMIN,
            UserRole.REVIEWER,
            UserRole.GOLD_ANNOTATOR,
            UserRole.GOLD_ARBITRATOR,
        )
    ),
]
WorkCorrectionPrincipal = Annotated[
    Principal,
    Depends(
        require_roles_with_step_up(
            UserRole.SOURCE_ADMIN,
            UserRole.PLATFORM_ADMIN,
            UserRole.GOLD_ARBITRATOR,
        )
    ),
]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]


class OperationsService(Protocol):
    async def overview(self) -> OperationsOverview: ...

    async def request_replay(
        self,
        payload: ReplayRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> ReplayResult: ...

    async def get_schedule(self, source_id: UUID) -> FetchScheduleView: ...

    async def update_schedule(
        self,
        source_id: UUID,
        payload: FetchScheduleUpdate,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> FetchScheduleView: ...

    async def repair_schedule(
        self,
        source_id: UUID,
        payload: SourceLifecycleActionRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> FetchScheduleView: ...

    async def source_health(self) -> list[SourceHealthView]: ...

    async def list_replays(self) -> list[ReplayTaskView]: ...

    async def record_feedback(
        self,
        *,
        item_id: UUID | None,
        event_id: UUID | None = None,
        value: str,
        actor_id: UUID,
    ) -> None: ...

    async def record_usage(
        self,
        *,
        event_type: str,
    ) -> None: ...

    async def pilot_metrics(self) -> PilotMetrics: ...

    async def prepare_pilot_window(
        self,
        payload: PilotWindowCreateRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView: ...

    async def list_pilot_windows(self) -> list[PilotWindowView]: ...

    async def start_pilot_window(
        self,
        window_id: UUID,
        payload: PilotWindowStartRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView: ...

    async def resume_pilot_source(
        self,
        window_id: UUID,
        source_code: str,
        payload: PilotSourceResumeRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView: ...

    async def complete_pilot_window(
        self,
        window_id: UUID,
        payload: PilotWindowCompleteRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView: ...

    async def list_gold_tasks(self, *, actor_id: UUID) -> list[GoldTaskView]: ...

    async def create_gold_task(
        self, payload: GoldTaskCreateRequest, *, actor_id: UUID
    ) -> GoldTaskView: ...

    async def submit_gold_annotation(
        self, payload: GoldAnnotationRequest, *, actor_id: UUID
    ) -> GoldAnnotationView: ...

    async def arbitrate_gold_task(
        self, payload: GoldArbitrationRequest, *, actor_id: UUID
    ) -> GoldTaskView: ...

    async def get_gold_arbitration_packet(
        self, task_id: UUID, *, actor_id: UUID
    ) -> GoldArbitrationPacket: ...

    async def freeze_gold_release(
        self, payload: GoldReleaseRequest, *, actor_id: UUID
    ) -> GoldReleaseView: ...

    async def start_work_session(
        self, *, actor_id: UUID, task_id: UUID
    ) -> OperatorWorkSessionView: ...

    async def list_operator_tasks(self, *, actor_id: UUID) -> list[OperatorTaskView]: ...

    async def create_operator_task(
        self, payload: OperatorTaskCreateRequest, *, actor_id: UUID
    ) -> OperatorTaskView: ...

    async def complete_operator_task(
        self,
        task_id: UUID,
        payload: OperatorTaskCompleteRequest,
        *,
        actor_id: UUID,
    ) -> OperatorTaskView: ...

    async def heartbeat_work_session(
        self,
        session_id: UUID,
        payload: OperatorWorkSessionHeartbeatRequest,
        *,
        actor_id: UUID,
    ) -> OperatorWorkSessionView: ...

    async def stop_work_session(
        self,
        session_id: UUID,
        payload: OperatorWorkSessionStopRequest,
        *,
        actor_id: UUID,
    ) -> OperatorWorkSessionView: ...

    async def correct_work_session(
        self,
        session_id: UUID,
        payload: OperatorWorkSessionCorrectionRequest,
        *,
        reviewer_id: UUID,
    ) -> OperatorWorkSessionView: ...


router = APIRouter(prefix="/api/v1", tags=["operations"])


def _service(request: Request) -> OperationsService:
    service = getattr(request.app.state, "operations_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operations service is unavailable",
        )
    return cast(OperationsService, service)


def _require_attested_round17_leo(principal: Principal, settings: Settings) -> None:
    signed_local = settings.round17_authority_mode == "SIGNED_LOCAL_PILOT"
    if signed_local:
        if settings.environment.lower() != "test" or not principal.local_identity:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Signed local Round 17 authority is restricted to the test environment",
            )
    else:
        _require_controlled_round17_identity(principal)
    if (
        settings.round17_leo_approver_actor_id is None
        or principal.user_id != settings.round17_leo_approver_actor_id
        or principal.display_name != "LEO"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Round 17 approval requires the sole attested LEO identity",
        )


def _require_controlled_round17_identity(principal: Principal) -> None:
    if (
        principal.local_identity
        or principal.oidc_issuer is None
        or principal.oidc_subject is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Round 17 requires a verified non-local OIDC issuer and subject",
        )


@router.get("/admin/operations/overview", response_model=OperationsOverview)
async def overview(request: Request, _: ReadPrincipal) -> OperationsOverview:
    return await _service(request).overview()


@router.post(
    "/admin/operations/replays",
    response_model=ReplayResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replay(
    payload: ReplayRequest,
    request: Request,
    principal: WritePrincipal,
    idempotency_key: IdempotencyKey,
) -> ReplayResult:
    return await _service(request).request_replay(
        payload,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
    )


@router.get("/admin/sources/{source_id}/schedule", response_model=FetchScheduleView)
async def get_schedule(
    source_id: UUID, request: Request, _: ScheduleReadPrincipal
) -> FetchScheduleView:
    return await _service(request).get_schedule(source_id)


@router.put("/admin/sources/{source_id}/schedule", response_model=FetchScheduleView)
async def update_schedule(
    source_id: UUID,
    payload: FetchScheduleUpdate,
    request: Request,
    principal: ScheduleWritePrincipal,
    idempotency_key: IdempotencyKey,
) -> FetchScheduleView:
    return await _service(request).update_schedule(
        source_id,
        payload,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/admin/sources/{source_id}/schedule/repair",
    response_model=FetchScheduleView,
)
async def repair_schedule(
    source_id: UUID,
    payload: SourceLifecycleActionRequest,
    request: Request,
    principal: ScheduleWritePrincipal,
    idempotency_key: IdempotencyKey,
) -> FetchScheduleView:
    return await _service(request).repair_schedule(
        source_id,
        payload,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
    )


@router.get("/admin/operations/source-health", response_model=list[SourceHealthView])
async def source_health(request: Request, _: ScheduleReadPrincipal) -> list[SourceHealthView]:
    return await _service(request).source_health()


@router.get("/admin/operations/replays", response_model=list[ReplayTaskView])
async def list_replays(request: Request, _: ReadPrincipal) -> list[ReplayTaskView]:
    return await _service(request).list_replays()


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def feedback(
    payload: FeedbackRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    service = _service(request)
    if payload.event_id is None:
        await service.record_feedback(
            item_id=payload.item_id,
            value=payload.value,
            actor_id=principal.user_id,
        )
    else:
        await service.record_feedback(
            item_id=None,
            event_id=payload.event_id,
            value=payload.value,
            actor_id=principal.user_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/pilot-metrics", response_model=PilotMetrics)
async def pilot_metrics(request: Request, _: ReadPrincipal) -> PilotMetrics:
    return await _service(request).pilot_metrics()


@router.post(
    "/admin/pilot-windows",
    response_model=PilotWindowView,
    status_code=status.HTTP_201_CREATED,
)
async def prepare_pilot_window(
    payload: PilotWindowCreateRequest,
    request: Request,
    principal: PilotPreparePrincipal,
    idempotency_key: IdempotencyKey,
) -> PilotWindowView:
    return await _service(request).prepare_pilot_window(
        payload,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
    )


@router.get("/admin/pilot-windows", response_model=list[PilotWindowView])
async def list_pilot_windows(
    request: Request, _: PilotReadPrincipal
) -> list[PilotWindowView]:
    return await _service(request).list_pilot_windows()


@router.post(
    "/admin/pilot-windows/{window_id}/start",
    response_model=PilotWindowView,
)
async def start_pilot_window(
    window_id: UUID,
    payload: PilotWindowStartRequest,
    request: Request,
    principal: PilotStartPrincipal,
    idempotency_key: IdempotencyKey,
    settings: CurrentSettings,
) -> PilotWindowView:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).start_pilot_window(
        window_id,
        payload,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/admin/pilot-windows/{window_id}/sources/{source_code}/resume",
    response_model=PilotWindowView,
)
async def resume_pilot_source(
    window_id: UUID,
    source_code: Annotated[str, Path(pattern=r"^[A-Z]{3}-[0-9]{3}$")],
    payload: PilotSourceResumeRequest,
    request: Request,
    principal: PilotLifecyclePrincipal,
    idempotency_key: IdempotencyKey,
    settings: CurrentSettings,
) -> PilotWindowView:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).resume_pilot_source(
        window_id,
        source_code,
        payload,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/admin/pilot-windows/{window_id}/complete",
    response_model=PilotWindowView,
)
async def complete_pilot_window(
    window_id: UUID,
    payload: PilotWindowCompleteRequest,
    request: Request,
    principal: PilotLifecyclePrincipal,
    idempotency_key: IdempotencyKey,
    settings: CurrentSettings,
) -> PilotWindowView:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).complete_pilot_window(
        window_id,
        payload,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
    )


@router.get("/admin/gold-tasks", response_model=list[GoldTaskView])
async def list_gold_tasks(
    request: Request, principal: GoldReadPrincipal
) -> list[GoldTaskView]:
    _require_controlled_round17_identity(principal)
    return await _service(request).list_gold_tasks(actor_id=principal.user_id)


@router.post(
    "/admin/gold-tasks",
    response_model=GoldTaskView,
    status_code=status.HTTP_201_CREATED,
)
async def create_gold_task(
    payload: GoldTaskCreateRequest,
    request: Request,
    principal: GoldArbitratorPrincipal,
    settings: CurrentSettings,
) -> GoldTaskView:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).create_gold_task(payload, actor_id=principal.user_id)


@router.post(
    "/admin/gold-tasks/{task_id}/annotations",
    response_model=GoldAnnotationView,
    status_code=status.HTTP_201_CREATED,
)
async def submit_gold_annotation(
    task_id: UUID,
    payload: GoldAnnotationRequest,
    request: Request,
    principal: GoldAnnotatorPrincipal,
) -> GoldAnnotationView:
    _require_controlled_round17_identity(principal)
    if task_id != payload.task_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Gold task identity mismatch",
        )
    return await _service(request).submit_gold_annotation(payload, actor_id=principal.user_id)


@router.post(
    "/admin/gold-tasks/{task_id}/arbitrations",
    response_model=GoldTaskView,
)
async def arbitrate_gold_task(
    task_id: UUID,
    payload: GoldArbitrationRequest,
    request: Request,
    principal: GoldArbitratorPrincipal,
    settings: CurrentSettings,
) -> GoldTaskView:
    _require_attested_round17_leo(principal, settings)
    if task_id != payload.task_id:
        raise HTTPException(status_code=409, detail="Gold task identity mismatch")
    return await _service(request).arbitrate_gold_task(payload, actor_id=principal.user_id)


@router.get(
    "/admin/gold-tasks/{task_id}/arbitration-packet",
    response_model=GoldArbitrationPacket,
)
async def get_gold_arbitration_packet(
    task_id: UUID,
    request: Request,
    principal: GoldArbitratorPrincipal,
    settings: CurrentSettings,
) -> GoldArbitrationPacket:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).get_gold_arbitration_packet(
        task_id, actor_id=principal.user_id
    )


@router.post("/admin/gold-releases", response_model=GoldReleaseView)
async def freeze_gold_release(
    payload: GoldReleaseRequest,
    request: Request,
    principal: GoldArbitratorPrincipal,
    settings: CurrentSettings,
) -> GoldReleaseView:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).freeze_gold_release(payload, actor_id=principal.user_id)


@router.post(
    "/admin/operator-tasks",
    response_model=OperatorTaskView,
    status_code=status.HTTP_201_CREATED,
)
async def create_operator_task(
    payload: OperatorTaskCreateRequest,
    request: Request,
    principal: WorkCorrectionPrincipal,
    settings: CurrentSettings,
) -> OperatorTaskView:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).create_operator_task(
        payload,
        actor_id=principal.user_id,
    )


@router.get(
    "/admin/operator-tasks",
    response_model=list[OperatorTaskView],
)
async def list_operator_tasks(
    request: Request,
    principal: WorkPrincipal,
) -> list[OperatorTaskView]:
    _require_controlled_round17_identity(principal)
    return await _service(request).list_operator_tasks(actor_id=principal.user_id)


@router.post(
    "/admin/operator-tasks/{task_id}/complete",
    response_model=OperatorTaskView,
)
async def complete_operator_task(
    task_id: UUID,
    payload: OperatorTaskCompleteRequest,
    request: Request,
    principal: WorkCorrectionPrincipal,
    settings: CurrentSettings,
) -> OperatorTaskView:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).complete_operator_task(
        task_id,
        payload,
        actor_id=principal.user_id,
    )


@router.post(
    "/admin/operator-work-sessions",
    response_model=OperatorWorkSessionView,
    status_code=status.HTTP_201_CREATED,
)
async def start_work_session(
    payload: OperatorWorkSessionStart,
    request: Request,
    principal: WorkPrincipal,
) -> OperatorWorkSessionView:
    _require_controlled_round17_identity(principal)
    return await _service(request).start_work_session(
        actor_id=principal.user_id,
        task_id=payload.task_id,
    )


@router.post(
    "/admin/operator-work-sessions/{session_id}/heartbeat",
    response_model=OperatorWorkSessionView,
)
async def heartbeat_work_session(
    session_id: UUID,
    payload: OperatorWorkSessionHeartbeatRequest,
    request: Request,
    principal: WorkPrincipal,
) -> OperatorWorkSessionView:
    _require_controlled_round17_identity(principal)
    return await _service(request).heartbeat_work_session(
        session_id, payload, actor_id=principal.user_id
    )


@router.post(
    "/admin/operator-work-sessions/{session_id}/stop",
    response_model=OperatorWorkSessionView,
)
async def stop_work_session(
    session_id: UUID,
    payload: OperatorWorkSessionStopRequest,
    request: Request,
    principal: WorkPrincipal,
) -> OperatorWorkSessionView:
    _require_controlled_round17_identity(principal)
    return await _service(request).stop_work_session(
        session_id,
        payload,
        actor_id=principal.user_id,
    )


@router.post(
    "/admin/operator-work-sessions/{session_id}/corrections",
    response_model=OperatorWorkSessionView,
)
async def correct_work_session(
    session_id: UUID,
    payload: OperatorWorkSessionCorrectionRequest,
    request: Request,
    principal: WorkCorrectionPrincipal,
    settings: CurrentSettings,
) -> OperatorWorkSessionView:
    _require_attested_round17_leo(principal, settings)
    return await _service(request).correct_work_session(
        session_id,
        payload,
        reviewer_id=principal.user_id,
    )
