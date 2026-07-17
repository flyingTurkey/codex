"""HTTP boundary for automated source discovery, qualification and activation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from srbg_contracts import (
    DiscoveryChannel,
    QualificationRunView,
    QualificationVerdict,
    SourceAttentionPage,
    SourceCandidateBatchDecisionRequest,
    SourceCandidateBatchDecisionResult,
    SourceCandidateCreateRequest,
    SourceCandidateDecisionRequest,
    SourceCandidateDecisionResult,
    SourceCandidateDetail,
    SourceCandidatePage,
    SourceCandidateQualificationRequest,
    SourceCandidateStatus,
    SourceContentDomain,
    SourceIndustry,
    SourceStreamPage,
    UserRole,
)

from srbg_api.auth import Principal, require_roles, require_roles_with_step_up
from srbg_api.config import Settings, get_settings

READ_ROLES = (UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN, UserRole.AUDITOR)
OPERATE_ROLES = (UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN)

ReadPrincipal = Annotated[Principal, Depends(require_roles(*READ_ROLES))]
OperatorPrincipal = Annotated[Principal, Depends(require_roles(*OPERATE_ROLES))]
StepUpOperatorPrincipal = Annotated[
    Principal,
    Depends(require_roles_with_step_up(*OPERATE_ROLES)),
]
_StepUpPlatformPrincipal = Annotated[
    Principal,
    Depends(require_roles_with_step_up(UserRole.PLATFORM_ADMIN)),
]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[^\x00-\x1f\x7f]+$"),
]


class SourceAutomationAdminService(Protocol):
    async def list_candidates(
        self,
        *,
        limit: int,
        cursor: str | None,
        status: SourceCandidateStatus | None,
        verdict: QualificationVerdict | None,
        discovery_channel: DiscoveryChannel | None,
        industry: SourceIndustry | None,
        content_domain: SourceContentDomain | None,
        language_tag: str | None,
        query: str | None,
    ) -> SourceCandidatePage: ...

    async def create_candidate(
        self,
        payload: SourceCandidateCreateRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceCandidateDetail: ...

    async def get_candidate(self, candidate_id: UUID) -> SourceCandidateDetail: ...

    async def request_qualification(
        self,
        candidate_id: UUID,
        payload: SourceCandidateQualificationRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> QualificationRunView: ...

    async def decide_candidate(
        self,
        candidate_id: UUID,
        payload: SourceCandidateDecisionRequest,
        *,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
    ) -> SourceCandidateDecisionResult: ...

    async def decide_candidate_batch(
        self,
        payload: SourceCandidateBatchDecisionRequest,
        *,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
    ) -> SourceCandidateBatchDecisionResult: ...

    async def list_streams(
        self,
        *,
        limit: int,
        cursor: str | None,
        query: str | None,
    ) -> SourceStreamPage: ...

    async def list_attention(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> SourceAttentionPage: ...

    async def close(self) -> None: ...


async def _recent_platform_step_up(
    principal: _StepUpPlatformPrincipal,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Apply the five-minute source-decision freshness bound on top of normal MFA."""

    if principal.local_identity:
        return principal
    authenticated_at = principal.authenticated_at
    if authenticated_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Source activation requires MFA within the last five minutes",
        )
    age_seconds = (datetime.now(UTC) - authenticated_at).total_seconds()
    if not 0 <= age_seconds <= 300:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Source activation requires MFA within the last five minutes",
        )
    del settings
    return principal


PlatformDecisionPrincipal = Annotated[Principal, Depends(_recent_platform_step_up)]

router = APIRouter(prefix="/api/v1", tags=["source-automation"])


def _service(request: Request) -> SourceAutomationAdminService:
    service = getattr(request.app.state, "source_automation_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Source automation service is unavailable",
        )
    return cast(SourceAutomationAdminService, service)


@router.get("/admin/source-candidates", response_model=SourceCandidatePage)
async def list_candidates(
    request: Request,
    _: ReadPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(min_length=16, max_length=2048)] = None,
    candidate_status: Annotated[SourceCandidateStatus | None, Query(alias="status")] = None,
    verdict: QualificationVerdict | None = None,
    discovery_channel: DiscoveryChannel | None = None,
    industry: SourceIndustry | None = None,
    content_domain: SourceContentDomain | None = None,
    language_tag: Annotated[
        str | None,
        Query(min_length=2, max_length=35, pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$"),
    ] = None,
    query: Annotated[str | None, Query(alias="q", min_length=1, max_length=200)] = None,
) -> SourceCandidatePage:
    return await _service(request).list_candidates(
        limit=limit,
        cursor=cursor,
        status=candidate_status,
        verdict=verdict,
        discovery_channel=discovery_channel,
        industry=industry,
        content_domain=content_domain,
        language_tag=language_tag,
        query=query,
    )


@router.post(
    "/admin/source-candidates",
    response_model=SourceCandidateDetail,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_candidate(
    payload: SourceCandidateCreateRequest,
    request: Request,
    principal: OperatorPrincipal,
) -> SourceCandidateDetail:
    return await _service(request).create_candidate(
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get("/admin/source-candidates/{candidate_id}", response_model=SourceCandidateDetail)
async def get_candidate(
    candidate_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> SourceCandidateDetail:
    return await _service(request).get_candidate(candidate_id)


@router.post(
    "/admin/source-candidates/{candidate_id}/qualification-runs",
    response_model=QualificationRunView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_qualification(
    candidate_id: UUID,
    payload: SourceCandidateQualificationRequest,
    request: Request,
    principal: StepUpOperatorPrincipal,
) -> QualificationRunView:
    return await _service(request).request_qualification(
        candidate_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post(
    "/admin/source-candidates/{candidate_id}/decisions",
    response_model=SourceCandidateDecisionResult,
)
async def decide_candidate(
    candidate_id: UUID,
    payload: SourceCandidateDecisionRequest,
    request: Request,
    principal: PlatformDecisionPrincipal,
    idempotency_key: IdempotencyKey,
) -> SourceCandidateDecisionResult:
    return await _service(request).decide_candidate(
        candidate_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/admin/source-candidates/batch-decisions",
    response_model=SourceCandidateBatchDecisionResult,
)
async def decide_candidate_batch(
    payload: SourceCandidateBatchDecisionRequest,
    request: Request,
    principal: PlatformDecisionPrincipal,
    idempotency_key: IdempotencyKey,
) -> SourceCandidateBatchDecisionResult:
    return await _service(request).decide_candidate_batch(
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
        idempotency_key=idempotency_key,
    )


@router.get("/admin/source-streams", response_model=SourceStreamPage)
async def list_streams(
    request: Request,
    _: ReadPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(min_length=16, max_length=2048)] = None,
    query: Annotated[str | None, Query(alias="q", min_length=1, max_length=200)] = None,
) -> SourceStreamPage:
    return await _service(request).list_streams(limit=limit, cursor=cursor, query=query)


@router.get("/admin/source-attention", response_model=SourceAttentionPage)
async def list_attention(
    request: Request,
    _: ReadPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(min_length=16, max_length=2048)] = None,
) -> SourceAttentionPage:
    return await _service(request).list_attention(limit=limit, cursor=cursor)
