"""Owner-local v2 intelligence reader and append-only review API."""

from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from srbg_contracts import (
    EventAppendixV2,
    EventProjectionV2,
    FeedPageV2,
    PrimaryIntelligenceType,
    ReviewCaseV2,
    ReviewDecisionCommandV2,
    ReviewDecisionReceiptV2,
)

from srbg_api.auth import Principal, get_current_principal, require_local_owner
from srbg_api.intelligence_v2.cursor import InvalidV2Cursor
from srbg_api.intelligence_v2.service import ProjectionNotFound, ReviewConflict


class V2IntelligenceService(Protocol):
    async def feed(self, **filters: object) -> FeedPageV2: ...
    async def search(self, **filters: object) -> FeedPageV2: ...
    async def hotspots(self, **filters: object) -> FeedPageV2: ...
    async def event(self, event_id: UUID) -> EventProjectionV2: ...
    async def appendix(self, event_id: UUID) -> EventAppendixV2: ...
    async def review_cases(self, **filters: object) -> list[ReviewCaseV2]: ...
    async def review_case(self, case_id: UUID) -> ReviewCaseV2: ...
    async def decide(
        self,
        *,
        case_id: UUID,
        command: ReviewDecisionCommandV2,
        owner_id: UUID,
        idempotency_key: UUID,
    ) -> ReviewDecisionReceiptV2: ...


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
OwnerPrincipal = Annotated[Principal, Depends(require_local_owner)]
router = APIRouter(prefix="/api/v2", tags=["intelligence-v2"])


def _service(request: Request) -> V2IntelligenceService:
    value = getattr(request.app.state, "v2_intelligence_service", None)
    if value is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "V2_SERVICE_UNAVAILABLE",
                "title": "V2 intelligence service unavailable",
            },
        )
    return cast(V2IntelligenceService, value)


@router.get("/feed", response_model=FeedPageV2)
async def feed(
    request: Request,
    _: CurrentPrincipal,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    primary_type: PrimaryIntelligenceType | None = None,
) -> FeedPageV2:
    try:
        return await _service(request).feed(
            cursor=cursor,
            limit=limit,
            primary_type=primary_type.value if primary_type else None,
        )
    except InvalidV2Cursor as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CURSOR", "title": "Invalid v2 feed cursor"},
        ) from exc


@router.get("/search", response_model=FeedPageV2)
async def search(
    request: Request,
    _: CurrentPrincipal,
    q: str = Query(min_length=1, max_length=200),
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> FeedPageV2:
    try:
        return await _service(request).search(query=q, cursor=cursor, limit=limit)
    except InvalidV2Cursor as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CURSOR", "title": "Invalid v2 search cursor"},
        ) from exc


@router.get("/hotspots", response_model=FeedPageV2)
async def hotspots(
    request: Request,
    _: CurrentPrincipal,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> FeedPageV2:
    try:
        return await _service(request).hotspots(cursor=cursor, limit=limit)
    except InvalidV2Cursor as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CURSOR", "title": "Invalid v2 hotspot cursor"},
        ) from exc


@router.get("/events/{event_id}", response_model=EventProjectionV2)
async def event(event_id: UUID, request: Request, _: CurrentPrincipal) -> EventProjectionV2:
    try:
        return await _service(request).event(event_id)
    except ProjectionNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "EVENT_NOT_FOUND", "title": "Event not found"},
        ) from exc


@router.get("/events/{event_id}/appendix", response_model=EventAppendixV2)
async def appendix(event_id: UUID, request: Request, _: OwnerPrincipal) -> EventAppendixV2:
    try:
        return await _service(request).appendix(event_id)
    except ProjectionNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "EVENT_APPENDIX_NOT_FOUND", "title": "Event appendix not found"},
        ) from exc


@router.get("/review/cases", response_model=list[ReviewCaseV2])
async def review_cases(
    request: Request, _: OwnerPrincipal, state: str | None = Query(default=None, max_length=50)
) -> list[ReviewCaseV2]:
    return await _service(request).review_cases(state=state)


@router.get("/review/cases/{case_id}", response_model=ReviewCaseV2)
async def review_case(case_id: UUID, request: Request, _: OwnerPrincipal) -> ReviewCaseV2:
    try:
        return await _service(request).review_case(case_id)
    except ProjectionNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "REVIEW_CASE_NOT_FOUND", "title": "Review case not found"},
        ) from exc


@router.post(
    "/review/cases/{case_id}/decisions",
    response_model=ReviewDecisionReceiptV2,
    status_code=status.HTTP_202_ACCEPTED,
)
async def decide(
    case_id: UUID,
    payload: ReviewDecisionCommandV2,
    request: Request,
    principal: OwnerPrincipal,
    if_match: Annotated[str, Header(alias="If-Match")],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ReviewDecisionReceiptV2:
    if if_match != f'"{payload.expected_version}"':
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "code": "REVIEW_VERSION_HEADER_MISMATCH",
                "title": "Review version header mismatch",
            },
        )
    try:
        return await _service(request).decide(
            case_id=case_id,
            command=payload,
            owner_id=principal.user_id,
            idempotency_key=idempotency_key,
        )
    except ReviewConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "code": "REVIEW_VERSION_CONFLICT",
                "title": "Review case has changed",
                "detail": "Refresh the case and retry with its current version",
            },
        ) from exc


@router.get("/media/{media_id}/preview")
async def media_preview(media_id: UUID, request: Request, _: CurrentPrincipal) -> Response:
    method = getattr(_service(request), "media_preview", None)
    if method is None:
        raise HTTPException(status_code=404, detail="Media preview not found")
    try:
        content, media_type = await method(media_id)
    except ProjectionNotFound as exc:
        raise HTTPException(status_code=404, detail="Media preview not found") from exc
    return Response(
        content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=300"}
    )


@router.get("/media/{media_id}/download")
async def media_download(media_id: UUID, request: Request, _: OwnerPrincipal) -> RedirectResponse:
    method = getattr(_service(request), "media_download", None)
    if method is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    try:
        url = await method(media_id, max_age_seconds=300)
    except ProjectionNotFound as exc:
        raise HTTPException(status_code=404, detail="Media download not found") from exc
    return RedirectResponse(url=url, status_code=302, headers={"Cache-Control": "no-store"})
