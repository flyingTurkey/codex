"""Administrative source registry and raw-document HTTP API."""

from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from srbg_contracts import (
    CreateSourceRequest,
    DocumentDetail,
    FixtureUploadResponse,
    MeResponse,
    SourceActionRequest,
    SourceDetail,
    SourceEligibility,
    SourceOnboardingSubmission,
    SourcePolicySubmission,
    SourceSummary,
    SourceTransitionRequest,
    UserRole,
)

from srbg_api.auth import (
    Principal,
    get_current_principal,
    require_roles,
    require_roles_with_step_up,
)
from srbg_api.config import get_settings

READ_ROLES = (UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN, UserRole.AUDITOR)
WRITE_ROLES = (UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN)
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
ReadPrincipal = Annotated[Principal, Depends(require_roles(*READ_ROLES))]
WritePrincipal = Annotated[Principal, Depends(require_roles_with_step_up(*WRITE_ROLES))]
FixtureFilename = Annotated[
    str,
    Header(alias="X-Filename", min_length=1, max_length=255),
]
FixtureCanonicalUrl = Annotated[
    str,
    Header(alias="X-Document-URL", min_length=1, max_length=2048),
]


async def _read_fixture_body(request: Request, max_bytes: int) -> bytes:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Fixture is too large",
            )
        content.extend(chunk)
    return bytes(content)


class AdminSourceService(Protocol):
    async def list_sources(self) -> list[SourceSummary]: ...

    async def create_source(
        self,
        payload: CreateSourceRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def get_source(self, source_id: UUID) -> SourceDetail: ...

    async def get_eligibility(self, source_id: UUID) -> SourceEligibility: ...

    async def save_policy(
        self,
        source_id: UUID,
        payload: SourcePolicySubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def save_onboarding(
        self,
        source_id: UUID,
        payload: SourceOnboardingSubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def transition(
        self,
        source_id: UUID,
        payload: SourceTransitionRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def set_enabled(
        self,
        source_id: UUID,
        enabled: bool,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def upload_fixture(
        self,
        source_id: UUID,
        *,
        content: bytes,
        filename: str,
        declared_mime: str,
        canonical_url: str,
        actor_id: UUID,
        request_id: str,
    ) -> FixtureUploadResponse: ...

    async def get_document(self, document_id: UUID) -> DocumentDetail: ...


router = APIRouter(prefix="/api/v1", tags=["source-vault"])


def _service(request: Request) -> AdminSourceService:
    service = getattr(request.app.state, "source_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Source vault service is unavailable",
        )
    return cast(AdminSourceService, service)


@router.get("/me", response_model=MeResponse)
async def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        display_name=principal.display_name,
        roles=sorted(principal.roles, key=lambda role: role.value),
        local_identity=principal.local_identity,
    )


@router.get("/admin/sources", response_model=list[SourceSummary])
async def list_sources(
    request: Request,
    _: ReadPrincipal,
) -> list[SourceSummary]:
    return await _service(request).list_sources()


@router.post("/admin/sources", response_model=SourceDetail, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: CreateSourceRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).create_source(
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get("/admin/sources/{source_id}", response_model=SourceDetail)
async def get_source(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> SourceDetail:
    return await _service(request).get_source(source_id)


@router.get("/admin/sources/{source_id}/eligibility", response_model=SourceEligibility)
async def get_eligibility(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> SourceEligibility:
    return await _service(request).get_eligibility(source_id)


@router.put("/admin/sources/{source_id}/policy", response_model=SourceDetail)
async def save_policy(
    source_id: UUID,
    payload: SourcePolicySubmission,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).save_policy(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post("/admin/sources/{source_id}/onboarding-records", response_model=SourceDetail)
async def save_onboarding(
    source_id: UUID,
    payload: SourceOnboardingSubmission,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).save_onboarding(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post("/admin/sources/{source_id}/transitions", response_model=SourceDetail)
async def transition(
    source_id: UUID,
    payload: SourceTransitionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).transition(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post("/admin/sources/{source_id}/enable", response_model=SourceDetail)
async def enable_source(
    source_id: UUID,
    payload: SourceActionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).set_enabled(
        source_id,
        True,
        payload.reason,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post("/admin/sources/{source_id}/disable", response_model=SourceDetail)
async def disable_source(
    source_id: UUID,
    payload: SourceActionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).set_enabled(
        source_id,
        False,
        payload.reason,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post(
    "/admin/sources/{source_id}/fixture",
    response_model=FixtureUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_fixture(
    source_id: UUID,
    request: Request,
    principal: WritePrincipal,
    filename: FixtureFilename,
    canonical_url: FixtureCanonicalUrl,
) -> FixtureUploadResponse:
    max_fixture_bytes = get_settings().fixture_max_bytes
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            exceeds_limit = int(content_length) > max_fixture_bytes
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        if exceeds_limit:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Fixture is too large",
            )
    content = await _read_fixture_body(request, max_fixture_bytes)
    return await _service(request).upload_fixture(
        source_id,
        content=content,
        filename=filename,
        declared_mime=request.headers.get("content-type", ""),
        canonical_url=canonical_url,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get("/admin/documents/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> DocumentDetail:
    return await _service(request).get_document(document_id)
