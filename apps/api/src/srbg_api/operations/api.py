"""Fail-closed operational APIs with bounded replay and feedback inputs."""

from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from srbg_contracts import (
    FeedbackRequest,
    FetchScheduleUpdate,
    FetchScheduleView,
    OperationsOverview,
    PilotMetrics,
    ReplayRequest,
    ReplayResult,
    ReplayTaskView,
    SourceHealthView,
    UserRole,
)

from srbg_api.auth import (
    Principal,
    get_current_principal,
    require_roles,
    require_roles_with_step_up,
)

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
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


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


router = APIRouter(prefix="/api/v1", tags=["operations"])


def _service(request: Request) -> OperationsService:
    service = getattr(request.app.state, "operations_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operations service is unavailable",
        )
    return cast(OperationsService, service)


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
