"""Authenticated Round 10 portal API with conditional reads and fail-closed writes."""

from __future__ import annotations

import re
from datetime import date
from time import perf_counter
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from srbg_contracts import (
    CollectionCreateRequest,
    CollectionPatchRequest,
    CollectionSummary,
    DailyReport,
    FeedPage,
    FingerprintResponse,
    SaveEventRequest,
    SaveItemRequest,
)

from srbg_api.auth import Principal, get_current_principal, require_local_owner
from srbg_api.config import get_settings
from srbg_api.discovery.domain import normalize_search_query
from srbg_api.event_unification.compatibility import item_deprecation_headers
from srbg_api.http_cache import contract_etag_response
from srbg_api.observability import SEARCH_DURATION


class PortalService(Protocol):
    async def close(self) -> None: ...

    async def search(
        self,
        *,
        query: str,
        tokens: tuple[str, ...],
        domain: str | None,
        content_type: str | None,
        region: str | None,
        source_id: UUID | None,
        evidence_status: str | None,
        sort: str,
        cursor: str | None,
        limit: int,
        principal: Principal,
    ) -> FeedPage: ...

    async def list_saved(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID | None,
        cursor: str | None,
        limit: int,
        principal: Principal,
    ) -> FeedPage: ...

    async def save_item(
        self, *, owner_id: UUID, item_id: UUID, collection_id: UUID | None, idempotency_key: str
    ) -> None: ...

    async def remove_saved_item(
        self, *, owner_id: UUID, item_id: UUID, collection_id: UUID | None
    ) -> None: ...

    async def save_event(
        self, *, owner_id: UUID, event_id: UUID, collection_id: UUID | None, idempotency_key: str
    ) -> None: ...

    async def remove_saved_event(
        self, *, owner_id: UUID, event_id: UUID, collection_id: UUID | None
    ) -> None: ...

    async def list_collections(
        self, *, owner_id: UUID, include_archived: bool
    ) -> list[CollectionSummary]: ...

    async def create_collection(
        self, *, owner_id: UUID, name: str, idempotency_key: str
    ) -> CollectionSummary: ...

    async def patch_collection(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID,
        name: str | None,
        archived: bool | None,
        expected_version: int,
    ) -> CollectionSummary: ...

    async def get_daily(self, *, report_date: date | None, principal: Principal) -> DailyReport: ...

    async def get_report(self, *, report_id: UUID, principal: Principal) -> DailyReport: ...

    async def export_markdown(self, *, report_id: UUID, principal: Principal) -> str: ...

    async def fingerprint(self, *, principal: Principal) -> FingerprintResponse: ...


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
ReviewPrincipal = Annotated[Principal, Depends(require_local_owner)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]
router = APIRouter(prefix="/api/v1", tags=["portal"])
_IF_MATCH = re.compile('^(?:W/)?"(?P<version>[1-9][0-9]*)"$')


def _service(request: Request) -> PortalService:
    service = getattr(request.app.state, "portal_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Portal service is unavailable"
        )
    return cast(PortalService, service)


def _publication_service(request: Request) -> Any:
    service = getattr(request.app.state, "publication_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Publication service is unavailable",
        )
    return service


def _expected_version(raw_value: str | None) -> int:
    if raw_value is None:
        raise HTTPException(status_code=428, detail="If-Match is required")
    match = _IF_MATCH.fullmatch(raw_value)
    if match is None:
        raise HTTPException(status_code=400, detail="If-Match must contain a collection version")
    return int(match.group("version"))


async def search(
    request: Request,
    principal: CurrentPrincipal,
    q: str = Query(min_length=1, max_length=200),
    domain: Literal["digital", "safety"] | None = None,
    content_type: str | None = Query(default=None, max_length=100),
    region: str | None = Query(default=None, max_length=100),
    source_id: UUID | None = None,
    evidence_status: Literal["WITHHELD", "VERIFIED"] | None = None,
    sort: Literal["relevance", "latest"] = "relevance",
    cursor: str | None = Query(default=None, max_length=2000),
    limit: int = Query(default=20, ge=1, le=100),
) -> Response:
    tokens = normalize_search_query(q)
    if not tokens:
        raise HTTPException(status_code=422, detail="Search query must contain a searchable term")
    started = perf_counter()
    try:
        page = await _service(request).search(
            query=q,
            tokens=tokens,
            domain=domain.upper() if domain else None,
            content_type=content_type,
            region=region,
            source_id=source_id,
            evidence_status=evidence_status,
            sort=sort,
            cursor=cursor,
            limit=limit,
            principal=principal,
        )
    finally:
        SEARCH_DURATION.observe(max(0.0, perf_counter() - started))
    return contract_etag_response(request, page, exclude_unset=True)


@router.get("/saved-events", response_model=FeedPage, response_model_exclude_unset=True)
@router.get("/saved-items", response_model=FeedPage, response_model_exclude_unset=True)
async def list_saved_items(
    request: Request,
    principal: CurrentPrincipal,
    collection_id: UUID | None = None,
    cursor: str | None = Query(default=None, max_length=2000),
    limit: int = Query(default=20, ge=1, le=100),
) -> Response:
    page = await _service(request).list_saved(
        owner_id=principal.user_id,
        collection_id=collection_id,
        cursor=cursor,
        limit=limit,
        principal=principal,
    )
    return contract_etag_response(request, page, exclude_unset=True)


@router.post("/saved-items", status_code=status.HTTP_204_NO_CONTENT)
async def save_item(payload: SaveItemRequest, request: Request, _: CurrentPrincipal) -> Response:
    resolver = getattr(_service(request), "resolve_item_event", None)
    event_id = await resolver(payload.item_id) if resolver is not None else payload.item_id
    settings = get_settings()
    return Response(
        status_code=status.HTTP_410_GONE,
        headers=item_deprecation_headers(
            event_id,
            deprecation_at=settings.item_api_deprecation_at,
            sunset_at=settings.item_api_sunset_at,
        ),
    )


@router.delete("/saved-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_saved_item(item_id: UUID, request: Request, _: CurrentPrincipal) -> Response:
    resolver = getattr(_service(request), "resolve_item_event", None)
    event_id = await resolver(item_id) if resolver is not None else item_id
    settings = get_settings()
    return Response(
        status_code=status.HTTP_410_GONE,
        headers=item_deprecation_headers(
            event_id,
            deprecation_at=settings.item_api_deprecation_at,
            sunset_at=settings.item_api_sunset_at,
        ),
    )


@router.post("/saved-events", status_code=status.HTTP_204_NO_CONTENT)
async def save_event(
    payload: SaveEventRequest,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> Response:
    await _service(request).save_event(
        owner_id=principal.user_id,
        event_id=payload.event_id,
        collection_id=payload.collection_id,
        idempotency_key=idempotency_key,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/saved-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_saved_event(
    event_id: UUID, request: Request, principal: CurrentPrincipal, collection_id: UUID | None = None
) -> Response:
    await _service(request).remove_saved_event(
        owner_id=principal.user_id, event_id=event_id, collection_id=collection_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/collections", response_model=list[CollectionSummary])
async def list_collections(
    request: Request, principal: CurrentPrincipal, include_archived: bool = False
) -> Response:
    collections = await _service(request).list_collections(
        owner_id=principal.user_id, include_archived=include_archived
    )
    return contract_etag_response(request, collections)


@router.post("/collections", response_model=CollectionSummary, status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreateRequest,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> CollectionSummary:
    return await _service(request).create_collection(
        owner_id=principal.user_id, name=payload.name, idempotency_key=idempotency_key
    )


@router.patch("/collections/{collection_id}", response_model=CollectionSummary)
async def patch_collection(
    collection_id: UUID,
    payload: CollectionPatchRequest,
    request: Request,
    principal: CurrentPrincipal,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> CollectionSummary:
    return await _service(request).patch_collection(
        owner_id=principal.user_id,
        collection_id=collection_id,
        name=payload.name,
        archived=payload.archived,
        expected_version=_expected_version(if_match),
    )


@router.get("/daily", response_model=DailyReport)
async def get_daily(
    request: Request,
    principal: CurrentPrincipal,
    report_date: Annotated[date | None, Query(alias="date")] = None,
) -> Response:
    return contract_etag_response(
        request, await _service(request).get_daily(report_date=report_date, principal=principal)
    )


@router.get("/reports/{report_id}", response_model=DailyReport)
async def get_report(report_id: UUID, request: Request, principal: CurrentPrincipal) -> Response:
    return contract_etag_response(
        request, await _service(request).get_report(report_id=report_id, principal=principal)
    )


@router.get("/export/markdown")
async def export_markdown(
    report_id: UUID, request: Request, principal: CurrentPrincipal
) -> Response:
    content = await _service(request).export_markdown(report_id=report_id, principal=principal)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="daily-report-{report_id}.md"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/fingerprint", response_model=FingerprintResponse)
async def fingerprint(request: Request, principal: CurrentPrincipal) -> Response:
    return contract_etag_response(request, await _service(request).fingerprint(principal=principal))
