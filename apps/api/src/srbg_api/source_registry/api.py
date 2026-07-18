"""Owner-only personal source HTTP API."""

from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from srbg_contracts import (
    DiscoveryDailyUsageView,
    DiscoverySettingPatchRequest,
    DiscoverySettingView,
    DiscoveryTopicPatchRequest,
    DiscoveryTopicView,
    MeResponse,
    PersonalSourceActivityPage,
    PersonalSourceCreateRequest,
    PersonalSourcePatchRequest,
    PersonalSourceReprobeRequest,
    PersonalSourceView,
    SourceAutoScoreDetailView,
    SourceProfileOverrideRequest,
    SourceProfileView,
)

from srbg_api.auth import Principal, get_current_principal, require_local_owner

CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
OwnerPrincipal = Annotated[Principal, Depends(require_local_owner)]
class PersonalSourceService(Protocol):
    async def get_discovery_setting(self) -> DiscoverySettingView: ...

    async def patch_discovery_setting(
        self, payload: DiscoverySettingPatchRequest, *, actor_id: UUID, request_id: str
    ) -> DiscoverySettingView: ...

    async def list_discovery_topics(self) -> list[DiscoveryTopicView]: ...

    async def patch_discovery_topic(
        self,
        topic_id: UUID,
        payload: DiscoveryTopicPatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> DiscoveryTopicView: ...

    async def get_discovery_usage(self) -> DiscoveryDailyUsageView: ...

    async def get_auto_score(self, source_id: UUID) -> SourceAutoScoreDetailView: ...

    async def create_personal_source(
        self, payload: PersonalSourceCreateRequest, *, actor_id: UUID, request_id: str
    ) -> PersonalSourceView: ...

    async def reprobe_personal_source(
        self,
        source_id: UUID,
        payload: PersonalSourceReprobeRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> PersonalSourceView: ...

    async def list_personal_sources(self) -> list[PersonalSourceView]: ...

    async def get_personal_source(self, source_id: UUID) -> PersonalSourceView: ...

    async def get_personal_source_activity(
        self, source_id: UUID, *, cursor: str | None, limit: int
    ) -> PersonalSourceActivityPage: ...

    async def get_source_profile(self, source_id: UUID) -> SourceProfileView: ...

    async def patch_source_profile_override(
        self,
        source_id: UUID,
        payload: SourceProfileOverrideRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceProfileView: ...

    async def revoke_source_profile_override(
        self, source_id: UUID, *, actor_id: UUID, request_id: str
    ) -> SourceProfileView: ...

    async def patch_personal_source(
        self,
        source_id: UUID,
        payload: PersonalSourcePatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> PersonalSourceView: ...


router = APIRouter(prefix="/api/v1", tags=["source-vault"])


def _service(request: Request) -> PersonalSourceService:
    service = getattr(request.app.state, "source_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Source vault service is unavailable",
        )
    return cast(PersonalSourceService, service)


@router.get("/me", response_model=MeResponse)
async def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        display_name=principal.display_name,
        roles=sorted(principal.roles, key=lambda role: role.value),
        local_identity=principal.local_identity,
    )


@router.get("/sources", response_model=list[PersonalSourceView], tags=["personal-sources"])
async def list_personal_sources(request: Request, _: OwnerPrincipal) -> list[PersonalSourceView]:
    return await _service(request).list_personal_sources()


@router.get(
    "/source-discovery/settings",
    response_model=DiscoverySettingView,
    tags=["personal-source-discovery"],
)
async def get_discovery_setting(request: Request, _: OwnerPrincipal) -> DiscoverySettingView:
    return await _service(request).get_discovery_setting()


@router.patch(
    "/source-discovery/settings",
    response_model=DiscoverySettingView,
    tags=["personal-source-discovery"],
)
async def patch_discovery_setting(
    payload: DiscoverySettingPatchRequest, request: Request, principal: OwnerPrincipal
) -> DiscoverySettingView:
    return await _service(request).patch_discovery_setting(
        payload, actor_id=principal.user_id, request_id=request.state.request_id
    )


@router.get(
    "/source-discovery/topics",
    response_model=list[DiscoveryTopicView],
    tags=["personal-source-discovery"],
)
async def list_discovery_topics(request: Request, _: OwnerPrincipal) -> list[DiscoveryTopicView]:
    return await _service(request).list_discovery_topics()


@router.patch(
    "/source-discovery/topics/{topic_id}",
    response_model=DiscoveryTopicView,
    tags=["personal-source-discovery"],
)
async def patch_discovery_topic(
    topic_id: UUID, payload: DiscoveryTopicPatchRequest, request: Request, principal: OwnerPrincipal
) -> DiscoveryTopicView:
    return await _service(request).patch_discovery_topic(
        topic_id, payload, actor_id=principal.user_id, request_id=request.state.request_id
    )


@router.get(
    "/source-discovery/usage",
    response_model=DiscoveryDailyUsageView,
    tags=["personal-source-discovery"],
)
async def get_discovery_usage(request: Request, _: OwnerPrincipal) -> DiscoveryDailyUsageView:
    return await _service(request).get_discovery_usage()


@router.post(
    "/sources",
    response_model=PersonalSourceView,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["personal-sources"],
)
async def create_personal_source(
    payload: PersonalSourceCreateRequest, request: Request, principal: OwnerPrincipal
) -> PersonalSourceView:
    return await _service(request).create_personal_source(
        payload, actor_id=principal.user_id, request_id=request.state.request_id
    )


@router.get("/sources/{source_id}", response_model=PersonalSourceView, tags=["personal-sources"])
async def get_personal_source(
    source_id: UUID, request: Request, _: OwnerPrincipal
) -> PersonalSourceView:
    return await _service(request).get_personal_source(source_id)


@router.get(
    "/sources/{source_id}/activity",
    response_model=PersonalSourceActivityPage,
    tags=["personal-sources"],
)
async def get_personal_source_activity(
    source_id: UUID,
    request: Request,
    _: OwnerPrincipal,
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=30, ge=1, le=100),
) -> PersonalSourceActivityPage:
    try:
        return await _service(request).get_personal_source_activity(
            source_id, cursor=cursor, limit=limit
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/sources/{source_id}/auto-score",
    response_model=SourceAutoScoreDetailView,
    tags=["personal-source-discovery"],
)
async def get_source_auto_score(
    source_id: UUID, request: Request, _: OwnerPrincipal
) -> SourceAutoScoreDetailView:
    return await _service(request).get_auto_score(source_id)


@router.patch("/sources/{source_id}", response_model=PersonalSourceView, tags=["personal-sources"])
async def patch_personal_source(
    source_id: UUID,
    payload: PersonalSourcePatchRequest,
    request: Request,
    principal: OwnerPrincipal,
) -> PersonalSourceView:
    return await _service(request).patch_personal_source(
        source_id, payload, actor_id=principal.user_id, request_id=request.state.request_id
    )


@router.post(
    "/sources/{source_id}/reprobe",
    response_model=PersonalSourceView,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["personal-sources"],
)
async def reprobe_personal_source(
    source_id: UUID,
    payload: PersonalSourceReprobeRequest,
    request: Request,
    principal: OwnerPrincipal,
) -> PersonalSourceView:
    return await _service(request).reprobe_personal_source(
        source_id, payload, actor_id=principal.user_id, request_id=request.state.request_id
    )


@router.get(
    "/sources/{source_id}/profile", response_model=SourceProfileView, tags=["personal-sources"]
)
async def get_source_profile(
    source_id: UUID, request: Request, _: OwnerPrincipal
) -> SourceProfileView:
    return await _service(request).get_source_profile(source_id)


@router.patch(
    "/sources/{source_id}/profile-override",
    response_model=SourceProfileView,
    tags=["personal-sources"],
)
async def patch_source_profile_override(
    source_id: UUID,
    payload: SourceProfileOverrideRequest,
    request: Request,
    principal: OwnerPrincipal,
) -> SourceProfileView:
    return await _service(request).patch_source_profile_override(
        source_id, payload, actor_id=principal.user_id, request_id=request.state.request_id
    )


@router.delete(
    "/sources/{source_id}/profile-override",
    response_model=SourceProfileView,
    tags=["personal-sources"],
)
async def revoke_source_profile_override(
    source_id: UUID, request: Request, principal: OwnerPrincipal
) -> SourceProfileView:
    return await _service(request).revoke_source_profile_override(
        source_id, actor_id=principal.user_id, request_id=request.state.request_id
    )
