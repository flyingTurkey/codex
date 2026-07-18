"""Feed, item detail, and R3 review HTTP API."""

from datetime import date
from typing import Annotated, Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from srbg_contracts import (
    AutomaticRelationshipView,
    DocumentPageView,
    EventDetail,
    FeedPage,
    HotTopicPage,
    ItemDetail,
    OwnerRelationshipCorrectionRequest,
    OwnerRelationshipCorrectionResponse,
    SourceComparison,
    VersionDiffResponse,
    VersionTimelineResponse,
)

from srbg_api.auth import Principal, get_current_principal, require_local_owner
from srbg_api.config import get_settings
from srbg_api.event_unification.compatibility import item_deprecation_headers
from srbg_api.http_cache import contract_etag_response


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

    async def get_citation(self, item_id: UUID, citation_format: str) -> tuple[str, str]: ...

    async def get_event(self, event_id: UUID) -> EventDetail: ...

    async def list_automatic_relationships(
        self, event_id: UUID
    ) -> list[AutomaticRelationshipView]: ...

    async def get_event_item_projection(self, event_id: UUID) -> ItemDetail: ...

    async def list_hot_topics(
        self, *, domain: str | None, window_days: int, cursor: str | None, limit: int
    ) -> HotTopicPage: ...

    async def get_source_comparison(self, event_id: UUID) -> SourceComparison: ...

    async def get_versions(
        self, item_id: UUID, *, include_restricted: bool
    ) -> VersionTimelineResponse: ...

    async def get_diff(
        self, item_id: UUID, *, from_version_id: UUID, to_version_id: UUID, include_restricted: bool
    ) -> VersionDiffResponse: ...

    async def get_document_page(
        self, document_version_id: UUID, page_number: int, *, include_restricted: bool
    ) -> DocumentPageView: ...

    async def get_page_preview(
        self, document_version_id: UUID, page_number: int, *, include_restricted: bool
    ) -> tuple[bytes, str]: ...


class PersonalPublicationService(Protocol):
    async def correct_automatic_relationship(
        self, event_id: UUID, *, payload: OwnerRelationshipCorrectionRequest, owner_id: UUID
    ) -> OwnerRelationshipCorrectionResponse: ...


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
OwnerPrincipal = Annotated[Principal, Depends(require_local_owner)]
FromVersionQuery = Annotated[UUID, Query(alias="from")]
ToVersionQuery = Annotated[UUID, Query(alias="to")]
ReviewReadPrincipal = Annotated[Principal, Depends(require_local_owner)]
ReviewWritePrincipal = Annotated[Principal, Depends(require_local_owner)]
EventCandidateWritePrincipal = Annotated[Principal, Depends(require_local_owner)]
router = APIRouter(prefix="/api/v1", tags=["intelligence"])


def _query_service(request: Request) -> IntelligenceQueryService:
    service = getattr(request.app.state, "intelligence_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence query service is unavailable",
        )
    return cast(IntelligenceQueryService, service)


def _public_query_service(request: Request) -> IntelligenceQueryService:
    service = getattr(request.app.state, "public_intelligence_service", None)
    return (
        cast(IntelligenceQueryService, service) if service is not None else _query_service(request)
    )


async def _item_compatibility_headers(
    service: IntelligenceQueryService, item_id: UUID
) -> dict[str, str]:
    resolver = getattr(service, "resolve_item_event", None)
    event_id = await resolver(item_id) if resolver is not None else item_id
    settings = get_settings()
    return item_deprecation_headers(
        event_id,
        deprecation_at=settings.item_api_deprecation_at,
        sunset_at=settings.item_api_sunset_at,
    )


def _publication_service(request: Request) -> PersonalPublicationService:
    service = getattr(request.app.state, "publication_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Publication service is unavailable",
        )
    return cast(PersonalPublicationService, service)


@router.get("/feed", response_model=FeedPage, response_model_exclude_unset=True)
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
    if published_from and published_to and (published_from > published_to):
        raise HTTPException(status_code=422, detail="published_from must not exceed published_to")
    page = await _public_query_service(request).get_feed(
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


@router.get("/hot-topics", response_model=HotTopicPage, response_model_exclude_none=True)
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


@router.get("/items/{item_id}", response_model=ItemDetail, response_model_exclude_unset=True)
async def get_item(item_id: UUID, request: Request, _: CurrentPrincipal) -> Response:
    service = _query_service(request)
    return contract_etag_response(
        request,
        await service.get_item(item_id),
        exclude_unset=True,
        extra_headers=await _item_compatibility_headers(service, item_id),
    )


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
        }
        | await _item_compatibility_headers(_query_service(request), item_id),
    )


@router.get("/events/{event_id}", response_model=EventDetail)
async def get_event(event_id: UUID, request: Request, _: CurrentPrincipal) -> Response:
    service = _public_query_service(request)
    resolver = getattr(service, "resolve_event_redirect", None)
    canonical_id = await resolver(event_id) if resolver is not None else None
    if canonical_id is not None and canonical_id != event_id:
        return RedirectResponse(
            url=f"/api/v1/events/{canonical_id}", status_code=status.HTTP_308_PERMANENT_REDIRECT
        )
    return contract_etag_response(request, await service.get_event(event_id))


@router.get(
    "/events/{event_id}/content", response_model=ItemDetail, response_model_exclude_unset=True
)
async def get_event_content(event_id: UUID, request: Request, _: CurrentPrincipal) -> Response:
    return contract_etag_response(
        request,
        await _query_service(request).get_event_item_projection(event_id),
        exclude_unset=True,
    )


@router.get(
    "/events/{event_id}/automatic-relationships", response_model=list[AutomaticRelationshipView]
)
async def list_automatic_relationships(
    event_id: UUID, request: Request, _: CurrentPrincipal
) -> list[AutomaticRelationshipView]:
    return await _query_service(request).list_automatic_relationships(event_id)


@router.post(
    "/events/{event_id}/relationship-corrections",
    response_model=OwnerRelationshipCorrectionResponse,
)
async def correct_automatic_relationship(
    event_id: UUID,
    payload: OwnerRelationshipCorrectionRequest,
    request: Request,
    principal: OwnerPrincipal,
) -> OwnerRelationshipCorrectionResponse:
    return await _publication_service(request).correct_automatic_relationship(
        event_id, payload=payload, owner_id=principal.user_id
    )


@router.get("/events/{event_id}/citation")
async def get_event_citation(
    event_id: UUID,
    request: Request,
    _: CurrentPrincipal,
    citation_format: Literal["ris", "bibtex", "gb-t-7714"] = Query(alias="format"),
) -> Response:
    service = _query_service(request)
    content_projection = await service.get_event_item_projection(event_id)
    content, media_type = await service.get_citation(content_projection.item.id, citation_format)
    extension = {"ris": "ris", "bibtex": "bib", "gb-t-7714": "txt"}[citation_format]
    return Response(
        content=content.encode("utf-8"),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="event-{event_id}.{extension}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/events/{event_id}/source-comparison", response_model=SourceComparison)
async def get_event_source_comparison(
    event_id: UUID, request: Request, _: CurrentPrincipal
) -> SourceComparison:
    return await _query_service(request).get_source_comparison(event_id)


@router.get("/items/{item_id}/versions", response_model=VersionTimelineResponse)
async def get_versions(item_id: UUID, request: Request, principal: CurrentPrincipal) -> Response:
    service = _query_service(request)
    result = await service.get_versions(item_id, include_restricted=principal.local_identity)
    return contract_etag_response(
        request, result, extra_headers=await _item_compatibility_headers(service, item_id)
    )


@router.get("/items/{item_id}/diff", response_model=VersionDiffResponse)
async def get_diff(
    item_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    from_version_id: FromVersionQuery,
    to_version_id: ToVersionQuery,
) -> Response:
    service = _query_service(request)
    result = await service.get_diff(
        item_id,
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        include_restricted=principal.local_identity,
    )
    return contract_etag_response(
        request, result, extra_headers=await _item_compatibility_headers(service, item_id)
    )


@router.get(
    "/document-versions/{document_version_id}/pages/{page_number}", response_model=DocumentPageView
)
async def get_document_page(
    document_version_id: UUID, page_number: int, request: Request, principal: CurrentPrincipal
) -> DocumentPageView:
    return await _query_service(request).get_document_page(
        document_version_id, page_number, include_restricted=principal.local_identity
    )


@router.get("/document-versions/{document_version_id}/pages/{page_number}/preview")
async def get_page_preview(
    document_version_id: UUID, page_number: int, request: Request, principal: CurrentPrincipal
) -> Response:
    content, digest = await _query_service(request).get_page_preview(
        document_version_id, page_number, include_restricted=principal.local_identity
    )
    return Response(
        content=content,
        media_type="image/png",
        headers={"ETag": f'"sha256:{digest}"', "Cache-Control": "private, max-age=300"},
    )
