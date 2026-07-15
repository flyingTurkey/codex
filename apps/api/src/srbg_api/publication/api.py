"""Feed, item detail, and R3 review HTTP API."""

from datetime import date
from typing import Annotated, Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from srbg_contracts import (
    ClaimConflict,
    ClaimConflictDecisionRequest,
    ClaimConflictDecisionResponse,
    ClusterCandidateView,
    ClusterDecisionRequest,
    DigitalCaseReviewPatch,
    DocumentPageView,
    EventCandidateGenerationResponse,
    EventDetail,
    FeedPage,
    HotTopicPage,
    ItemDetail,
    ProductNormalizationCandidateView,
    ProductNormalizationDecisionRequest,
    PublicationRevisionRequest,
    PublicationWithdrawalRequest,
    ReviewCandidateDecisionRequest,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewTaskDetail,
    ReviewTaskSummary,
    ScoreDimension,
    ScoreOverrideRequest,
    SourceComparison,
    UserRole,
    VersionChangeEscalationRequest,
    VersionDiffResponse,
    VersionTimelineResponse,
)

from srbg_api.auth import (
    Principal,
    get_current_principal,
    require_roles,
    require_roles_with_step_up,
)
from srbg_api.http_cache import contract_etag_response
from srbg_api.safety_cases.candidates import EventCandidateAlreadyDecided


class IntelligenceQueryService(Protocol):
    async def get_feed(
        self,
        *,
        mode: str,
        domain: str | None,
        content_type: str | None,
        engineering_domain: str | None,
        scenario: str | None,
        maturity: str | None,
        source_nature: str | None,
        paper_type: str | None,
        technology_tag: str | None,
        access_level: str | None,
        year: int | None,
        product_kind: str | None,
        evidence_level: str | None,
        deployment_mode: str | None,
        region: str | None,
        source_id: UUID | None,
        source_authority: str | None,
        published_from: date | None,
        published_to: date | None,
        review_status: str | None,
        evidence_status: str | None,
        sort: str,
        cursor: str | None,
        limit: int,
    ) -> FeedPage: ...

    async def get_item(self, item_id: UUID) -> ItemDetail: ...

    async def list_product_normalization_candidates(
        self, *, status: str
    ) -> list[ProductNormalizationCandidateView]: ...

    async def get_citation(self, item_id: UUID, citation_format: str) -> tuple[str, str]: ...

    async def get_event(self, event_id: UUID) -> EventDetail: ...

    async def list_hot_topics(
        self,
        *,
        domain: str | None,
        window_days: int,
        cursor: str | None,
        limit: int,
    ) -> HotTopicPage: ...

    async def get_source_comparison(self, event_id: UUID) -> SourceComparison: ...

    async def list_cluster_candidates(
        self, *, kind: str, status: str
    ) -> list[ClusterCandidateView]: ...

    async def list_review_tasks(self) -> list[ReviewTaskSummary]: ...

    async def get_review_task(self, task_id: UUID) -> ReviewTaskDetail: ...

    async def get_versions(
        self, item_id: UUID, *, include_restricted: bool
    ) -> VersionTimelineResponse: ...

    async def get_diff(
        self,
        item_id: UUID,
        *,
        from_version_id: UUID,
        to_version_id: UUID,
        include_restricted: bool,
    ) -> VersionDiffResponse: ...

    async def get_document_page(
        self,
        document_version_id: UUID,
        page_number: int,
        *,
        include_restricted: bool,
    ) -> DocumentPageView: ...

    async def get_page_preview(
        self,
        document_version_id: UUID,
        page_number: int,
        *,
        include_restricted: bool,
    ) -> tuple[bytes, str]: ...


class ReviewPublicationService(Protocol):
    async def list_claim_conflicts(self) -> list[ClaimConflict]: ...

    async def decide_review(
        self,
        review_task_id: UUID,
        *,
        action: Literal["APPROVE", "REJECT"],
        reason: str,
        reviewer_id: UUID,
        digital_case_patch: DigitalCaseReviewPatch | None = None,
    ) -> ReviewDecisionResponse: ...

    async def revise(
        self,
        review_task_id: UUID,
        *,
        reason: str,
        reviewer_id: UUID,
    ) -> ReviewDecisionResponse: ...

    async def republish(
        self,
        review_task_id: UUID,
        *,
        reason: str,
        reviewer_id: UUID,
    ) -> ReviewDecisionResponse: ...

    async def withdraw(
        self,
        publication_id: UUID,
        *,
        reason: str,
        actor_id: UUID,
        evidence_id: UUID,
    ) -> UUID: ...

    async def decide_candidate(
        self,
        candidate_kind: Literal[
            "RELATION",
            "REGULATION_STATUS",
            "EVENT_LINK",
            "EVENT_RELATION",
            "CLAIM",
            "PAPER_RELATION",
        ],
        candidate_id: UUID,
        *,
        action: Literal["ACCEPT", "REJECT", "CONFIRM_UNRESOLVED"],
        target_document_id: UUID | None,
        reason: str,
        reviewer_id: UUID,
    ) -> None: ...

    async def escalate_version_change(
        self,
        version_change_id: UUID,
        *,
        reason: str,
        reviewer_id: UUID,
    ) -> None: ...

    async def resolve_claim_conflict(
        self,
        conflict_id: UUID,
        *,
        action: Literal["ACCEPT_CANDIDATE", "KEEP_CURRENT", "MARK_UNRESOLVED"],
        reason: str,
        reviewer_id: UUID,
    ) -> ClaimConflictDecisionResponse: ...

    async def decide_product_normalization(
        self,
        candidate_id: UUID,
        *,
        action: Literal["MERGE_ALIAS", "LINK_AS_NEW_VERSION", "KEEP_DISTINCT"],
        reason: str,
        reviewer_id: UUID,
    ) -> None: ...

    async def decide_cluster(
        self,
        candidate_id: UUID,
        *,
        candidate_kind: Literal["DUPLICATE", "EVENT", "TOPIC", "RELATION"],
        action: Literal["MERGE", "SPLIT", "KEEP_DISTINCT", "LINK_RELATION"],
        member_ids: list[UUID],
        relation_type: str | None,
        reason: str,
        reviewer_id: UUID,
    ) -> None: ...

    async def override_score(
        self,
        item_id: UUID,
        *,
        dimension: ScoreDimension,
        score: int,
        reason: str,
        reviewer_id: UUID,
    ) -> None: ...


class EventCandidateGenerationService(Protocol):
    async def generate_candidate(
        self,
        *,
        event_id: UUID,
        item_id: UUID,
    ) -> UUID | None: ...


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
FromVersionQuery = Annotated[UUID, Query(alias="from")]
ToVersionQuery = Annotated[UUID, Query(alias="to")]
ReviewReadPrincipal = Annotated[
    Principal,
    Depends(require_roles(UserRole.REVIEWER, UserRole.PLATFORM_ADMIN, UserRole.AUDITOR)),
]
ReviewWritePrincipal = Annotated[
    Principal,
    Depends(require_roles_with_step_up(UserRole.REVIEWER, UserRole.PLATFORM_ADMIN)),
]
EventCandidateWritePrincipal = Annotated[
    Principal,
    Depends(require_roles(UserRole.EDITOR, UserRole.REVIEWER, UserRole.PLATFORM_ADMIN)),
]

router = APIRouter(prefix="/api/v1", tags=["intelligence"])

_RESTRICTED_READ_ROLES = frozenset({UserRole.REVIEWER, UserRole.PLATFORM_ADMIN, UserRole.AUDITOR})


def _query_service(request: Request) -> IntelligenceQueryService:
    service = getattr(request.app.state, "intelligence_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence query service is unavailable",
        )
    return cast(IntelligenceQueryService, service)


def _publication_service(request: Request) -> ReviewPublicationService:
    service = getattr(request.app.state, "publication_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Publication service is unavailable",
        )
    return cast(ReviewPublicationService, service)


def _event_candidate_service(request: Request) -> EventCandidateGenerationService:
    service = getattr(request.app.state, "safety_event_candidate_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Safety event candidate service is unavailable",
        )
    return cast(EventCandidateGenerationService, service)


@router.get(
    "/feed",
    response_model=FeedPage,
    response_model_exclude_unset=True,
)
async def get_feed(
    request: Request,
    _: CurrentPrincipal,
    mode: Literal["selected", "all"] = "all",
    domain: Literal["digital", "safety"] | None = None,
    content_type: str | None = Query(default=None, max_length=100),
    engineering_domain: str | None = Query(default=None, max_length=100),
    scenario: str | None = Query(default=None, max_length=100),
    maturity: str | None = Query(default=None, max_length=100),
    source_nature: str | None = Query(default=None, max_length=100),
    paper_type: str | None = Query(default=None, max_length=100),
    technology_tag: str | None = Query(default=None, max_length=100),
    access_level: str | None = Query(default=None, max_length=100),
    year: int | None = Query(default=None, ge=1000, le=9999),
    product_kind: str | None = Query(default=None, max_length=100),
    evidence_level: str | None = Query(default=None, max_length=100),
    deployment_mode: str | None = Query(default=None, max_length=100),
    region: str | None = Query(default=None, max_length=100),
    source_id: UUID | None = None,
    source_authority: Literal["A0", "A1", "B1", "B2", "C1", "C2"] | None = None,
    published_from: date | None = None,
    published_to: date | None = None,
    review_status: Literal["PENDING", "APPROVED"] | None = None,
    evidence_status: Literal["WITHHELD", "VERIFIED"] | None = None,
    sort: Literal["latest", "relevance", "impact", "heat"] = "latest",
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=20, ge=1, le=100),
) -> Response:
    if published_from and published_to and published_from > published_to:
        raise HTTPException(status_code=422, detail="published_from must not exceed published_to")
    page = await _query_service(request).get_feed(
        mode=mode,
        domain=domain,
        content_type=content_type,
        engineering_domain=engineering_domain,
        scenario=scenario,
        maturity=maturity,
        source_nature=source_nature,
        paper_type=paper_type,
        technology_tag=technology_tag,
        access_level=access_level,
        year=year,
        product_kind=product_kind,
        evidence_level=evidence_level,
        deployment_mode=deployment_mode,
        region=region,
        source_id=source_id,
        source_authority=source_authority,
        published_from=published_from,
        published_to=published_to,
        review_status=review_status,
        evidence_status=evidence_status,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )
    return contract_etag_response(request, page, exclude_unset=True)


@router.get(
    "/hot-topics",
    response_model=HotTopicPage,
    response_model_exclude_none=True,
)
async def list_hot_topics(
    request: Request,
    _: CurrentPrincipal,
    domain: Literal["digital", "safety"] | None = None,
    window: Literal["7d", "14d", "30d"] = "7d",
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
) -> Response:
    page = await _query_service(request).list_hot_topics(
        domain=domain.upper() if domain else None,
        window_days=int(window.removesuffix("d")),
        cursor=cursor,
        limit=limit,
    )
    return contract_etag_response(request, page, exclude_none=True)


@router.get(
    "/items/{item_id}",
    response_model=ItemDetail,
    response_model_exclude_unset=True,
)
async def get_item(
    item_id: UUID,
    request: Request,
    _: CurrentPrincipal,
) -> Response:
    return contract_etag_response(
        request, await _query_service(request).get_item(item_id), exclude_unset=True
    )


@router.get(
    "/admin/product-normalization-candidates",
    response_model=list[ProductNormalizationCandidateView],
)
async def list_product_normalization_candidates(
    request: Request,
    _: ReviewReadPrincipal,
    candidate_status: Literal["PENDING_REVIEW", "ACCEPTED", "REJECTED"] = Query(
        default="PENDING_REVIEW", alias="status"
    ),
) -> list[ProductNormalizationCandidateView]:
    return await _query_service(request).list_product_normalization_candidates(
        status=candidate_status
    )


@router.post(
    "/admin/product-normalization-candidates/{candidate_id}/decision",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def decide_product_normalization(
    candidate_id: UUID,
    payload: ProductNormalizationDecisionRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> Response:
    await _publication_service(request).decide_product_normalization(
        candidate_id,
        action=payload.action,
        reason=payload.reason,
        reviewer_id=principal.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/items/{item_id}/citation")
async def get_item_citation(
    item_id: UUID,
    request: Request,
    _: CurrentPrincipal,
    citation_format: Literal["ris", "bibtex", "gb-t-7714"] = Query(alias="format"),
) -> Response:
    content, media_type = await _query_service(request).get_citation(item_id, citation_format)
    extension = {"ris": "ris", "bibtex": "bib", "gb-t-7714": "txt"}[citation_format]
    return Response(
        content=content.encode("utf-8"),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="paper-{item_id}.{extension}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get(
    "/events/{event_id}",
    response_model=EventDetail,
)
async def get_event(
    event_id: UUID,
    request: Request,
    _: CurrentPrincipal,
) -> Response:
    return contract_etag_response(request, await _query_service(request).get_event(event_id))


@router.get(
    "/events/{event_id}/source-comparison",
    response_model=SourceComparison,
)
async def get_event_source_comparison(
    event_id: UUID,
    request: Request,
    _: CurrentPrincipal,
) -> SourceComparison:
    return await _query_service(request).get_source_comparison(event_id)


@router.get(
    "/admin/clustering-workbench",
    response_model=list[ClusterCandidateView],
)
async def list_cluster_candidates(
    request: Request,
    _: ReviewReadPrincipal,
    kind: Literal["DUPLICATE", "EVENT", "TOPIC", "RELATION"] = "DUPLICATE",
    candidate_status: Literal["PENDING_REVIEW", "ACCEPTED", "REJECTED"] = Query(
        default="PENDING_REVIEW", alias="status"
    ),
) -> list[ClusterCandidateView]:
    return await _query_service(request).list_cluster_candidates(kind=kind, status=candidate_status)


@router.post(
    "/admin/clustering-workbench/{candidate_kind}/{candidate_id}/decisions",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def decide_cluster(
    candidate_kind: Literal["DUPLICATE", "EVENT", "TOPIC", "RELATION"],
    candidate_id: UUID,
    payload: ClusterDecisionRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> Response:
    await _publication_service(request).decide_cluster(
        candidate_id,
        candidate_kind=candidate_kind,
        action=payload.action,
        member_ids=payload.member_ids,
        relation_type=payload.relation_type,
        reason=payload.reason,
        reviewer_id=principal.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/items/{item_id}/score-overrides",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def override_score(
    item_id: UUID,
    payload: ScoreOverrideRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> Response:
    await _publication_service(request).override_score(
        item_id,
        dimension=payload.dimension,
        score=payload.score,
        reason=payload.reason,
        reviewer_id=principal.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/events/{event_id}/candidate-items/{item_id}",
    response_model=EventCandidateGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_event_candidate(
    event_id: UUID,
    item_id: UUID,
    request: Request,
    _: EventCandidateWritePrincipal,
) -> EventCandidateGenerationResponse:
    try:
        candidate_id = await _event_candidate_service(request).generate_candidate(
            event_id=event_id,
            item_id=item_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The safety event or case item was not found",
        ) from exc
    except EventCandidateAlreadyDecided as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The event candidate already has a terminal review decision",
        ) from exc
    if candidate_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The item does not meet the event-candidate threshold",
        )
    return EventCandidateGenerationResponse(
        candidate_id=candidate_id,
        status="PENDING_REVIEW",
        requires_human_review=True,
    )


@router.get("/items/{item_id}/versions", response_model=VersionTimelineResponse)
async def get_versions(
    item_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> VersionTimelineResponse:
    return await _query_service(request).get_versions(
        item_id,
        include_restricted=not principal.roles.isdisjoint(_RESTRICTED_READ_ROLES),
    )


@router.get("/items/{item_id}/diff", response_model=VersionDiffResponse)
async def get_diff(
    item_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    from_version_id: FromVersionQuery,
    to_version_id: ToVersionQuery,
) -> VersionDiffResponse:
    return await _query_service(request).get_diff(
        item_id,
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        include_restricted=not principal.roles.isdisjoint(_RESTRICTED_READ_ROLES),
    )


@router.get(
    "/document-versions/{document_version_id}/pages/{page_number}",
    response_model=DocumentPageView,
)
async def get_document_page(
    document_version_id: UUID,
    page_number: int,
    request: Request,
    principal: CurrentPrincipal,
) -> DocumentPageView:
    return await _query_service(request).get_document_page(
        document_version_id,
        page_number,
        include_restricted=not principal.roles.isdisjoint(_RESTRICTED_READ_ROLES),
    )


@router.get("/document-versions/{document_version_id}/pages/{page_number}/preview")
async def get_page_preview(
    document_version_id: UUID,
    page_number: int,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    content, digest = await _query_service(request).get_page_preview(
        document_version_id,
        page_number,
        include_restricted=not principal.roles.isdisjoint(_RESTRICTED_READ_ROLES),
    )
    return Response(
        content=content,
        media_type="image/png",
        headers={"ETag": f'"sha256:{digest}"', "Cache-Control": "private, max-age=300"},
    )


@router.get("/admin/review-tasks", response_model=list[ReviewTaskSummary])
async def list_review_tasks(
    request: Request,
    _: ReviewReadPrincipal,
) -> list[ReviewTaskSummary]:
    return await _query_service(request).list_review_tasks()


@router.get("/admin/review-tasks/{task_id}", response_model=ReviewTaskDetail)
async def get_review_task(
    task_id: UUID,
    request: Request,
    _: ReviewReadPrincipal,
) -> ReviewTaskDetail:
    return await _query_service(request).get_review_task(task_id)


@router.get("/admin/claim-conflicts", response_model=list[ClaimConflict])
async def list_claim_conflicts(
    request: Request,
    _: ReviewReadPrincipal,
) -> list[ClaimConflict]:
    return await _publication_service(request).list_claim_conflicts()


@router.post(
    "/admin/review-tasks/{task_id}/decisions",
    response_model=ReviewDecisionResponse,
)
async def decide_review(
    task_id: UUID,
    payload: ReviewDecisionRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> ReviewDecisionResponse:
    return await _publication_service(request).decide_review(
        task_id,
        action=payload.action,
        reason=payload.reason,
        reviewer_id=principal.user_id,
        digital_case_patch=payload.digital_case_patch,
    )


@router.post(
    "/admin/review-tasks/{task_id}/revisions",
    response_model=ReviewDecisionResponse,
)
async def revise_publication(
    task_id: UUID,
    payload: PublicationRevisionRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> ReviewDecisionResponse:
    return await _publication_service(request).revise(
        task_id,
        reason=payload.reason,
        reviewer_id=principal.user_id,
    )


@router.post(
    "/admin/review-tasks/{task_id}/republish",
    response_model=ReviewDecisionResponse,
)
async def republish_publication(
    task_id: UUID,
    payload: PublicationRevisionRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> ReviewDecisionResponse:
    return await _publication_service(request).republish(
        task_id,
        reason=payload.reason,
        reviewer_id=principal.user_id,
    )


@router.post(
    "/admin/publications/{publication_id}/withdrawals",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def withdraw_publication(
    publication_id: UUID,
    payload: PublicationWithdrawalRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> Response:
    await _publication_service(request).withdraw(
        publication_id,
        reason=payload.reason,
        actor_id=principal.user_id,
        evidence_id=payload.evidence_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/review-candidates/{candidate_kind}/{candidate_id}/decisions",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def decide_candidate(
    candidate_kind: Literal[
        "RELATION",
        "REGULATION_STATUS",
        "EVENT_LINK",
        "EVENT_RELATION",
        "CLAIM",
        "PAPER_RELATION",
    ],
    candidate_id: UUID,
    payload: ReviewCandidateDecisionRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> Response:
    await _publication_service(request).decide_candidate(
        candidate_kind,
        candidate_id,
        action=payload.action,
        target_document_id=payload.target_document_id,
        reason=payload.reason,
        reviewer_id=principal.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/claim-conflicts/{conflict_id}/decisions",
    response_model=ClaimConflictDecisionResponse,
)
async def resolve_claim_conflict(
    conflict_id: UUID,
    payload: ClaimConflictDecisionRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> ClaimConflictDecisionResponse:
    return await _publication_service(request).resolve_claim_conflict(
        conflict_id,
        action=payload.action.value,
        reason=payload.reason,
        reviewer_id=principal.user_id,
    )


@router.post(
    "/admin/version-changes/{version_change_id}/escalations",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def escalate_version_change(
    version_change_id: UUID,
    payload: VersionChangeEscalationRequest,
    request: Request,
    principal: ReviewWritePrincipal,
) -> Response:
    await _publication_service(request).escalate_version_change(
        version_change_id,
        reason=payload.reason,
        reviewer_id=principal.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
