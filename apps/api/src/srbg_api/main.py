"""FastAPI application factory and foundational system endpoints."""

import asyncio
import hmac
import logging
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from srbg_contracts import (
    API_VERSION,
    CONTENT_SCHEMA_VERSION,
    DependencyCheck,
    DependencyName,
    LivenessResponse,
    ProblemDetails,
    ReadinessResponse,
    VersionResponse,
)
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from srbg_api.auth import Principal
from srbg_api.config import get_settings
from srbg_api.database import (
    create_database_engine,
    create_projection_reader_engine,
    create_publication_engine,
)
from srbg_api.discovery.api import PortalService
from srbg_api.discovery.api import router as portal_router
from srbg_api.discovery.domain import CursorBindingError
from srbg_api.discovery.repository import (
    PortalRepositoryConflict,
    PortalRepositoryNotFound,
    PostgresPortalRepository,
)
from srbg_api.discovery.service import PortalApplicationService
from srbg_api.document_vault.security import UploadRejected
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.health import HealthChecker, build_default_checkers, run_check
from srbg_api.identifiers import uuid7
from srbg_api.internal_projection.reader import PublishedProjectionReader
from srbg_api.internal_projection.service import PublishedIntelligenceQueryService
from srbg_api.logging import configure_logging
from srbg_api.observability import (
    API_DURATION,
    API_REQUESTS,
    configure_observability,
    render_metrics,
    set_internal_projection_metrics,
    set_operations_metrics,
    set_round17_metrics,
)
from srbg_api.operations.api import OperationsService
from srbg_api.operations.api import router as operations_router
from srbg_api.operations.service import OperationsRejected, PostgresOperationsService
from srbg_api.publication.api import (
    EventCandidateGenerationService,
    IntelligenceQueryService,
    ReviewPublicationService,
)
from srbg_api.publication.api import router as intelligence_router
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationDenied, PublicationService
from srbg_api.safety_cases.candidates import (
    PostgresEventCandidateStore,
    SafetyEventCandidateService,
)
from srbg_api.safety_regulations.query import (
    IntelligenceNotFound,
    InvalidFeedCursor,
    PostgresIntelligenceQueryService,
)
from srbg_api.source_registry.api import AdminSourceService
from srbg_api.source_registry.api import router as source_vault_router
from srbg_api.source_registry.repository import RepositoryConflict, SourceNotFound
from srbg_api.source_registry.service import SourceServiceRejected, build_default_source_service


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(
    checkers: Mapping[str, HealthChecker] | None = None,
    source_service: AdminSourceService | None = None,
    intelligence_service: IntelligenceQueryService | None = None,
    public_intelligence_service: Any | None = None,
    publication_service: ReviewPublicationService | None = None,
    safety_event_candidate_service: EventCandidateGenerationService | None = None,
    portal_service: PortalService | None = None,
    operations_service: OperationsService | None = None,
) -> FastAPI:
    configure_logging()
    settings = get_settings()
    configure_observability(settings)
    dependency_checkers = (
        dict(checkers) if checkers is not None else build_default_checkers(settings)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for service in (
            source_service,
            intelligence_service,
            public_intelligence_service,
            publication_service,
            safety_event_candidate_service,
            portal_service,
            operations_service,
        ):
            close = getattr(service, "close", None)
            if close is not None:
                await close()

    app = FastAPI(title="SRBG Insight API", version="0.1.0", lifespan=lifespan)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )
    app.state.source_service = source_service
    app.state.intelligence_service = intelligence_service
    app.state.public_intelligence_service = public_intelligence_service
    app.state.publication_service = publication_service
    app.state.safety_event_candidate_service = safety_event_candidate_service
    app.state.portal_service = portal_service
    app.state.operations_service = operations_service
    app.state.publication_gate_denials = Counter()
    logger = logging.getLogger("srbg.api")

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = str(uuid7())
        started = perf_counter()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        route = getattr(request.scope.get("route"), "path", "unmatched")
        duration_seconds = max(0.0, perf_counter() - started)
        API_REQUESTS.labels(route, request.method, str(response.status_code)).inc()
        API_DURATION.labels(route, request.method).observe(duration_seconds)
        principal = getattr(request.state, "principal", None)
        usage_event = _usage_event(request.method, request.url.path)
        if (
            response.status_code < 400
            and isinstance(principal, Principal)
            and usage_event is not None
            and operations_service is not None
        ):
            try:
                await operations_service.record_usage(
                    event_type=usage_event,
                )
            except Exception:
                logger.warning(
                    "usage_event_recording_failed",
                    extra={"request_id": request_id, "event_type": usage_event},
                )
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": max(0, round(duration_seconds * 1000)),
            },
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        problem = ProblemDetails(
            title=str(exc.detail),
            status=exc.status_code,
            detail=None,
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        _: RequestValidationError,
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Request validation failed",
            status=422,
            detail="The request does not match the API contract",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=422,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(SourceNotFound)
    async def not_found_handler(request: Request, exc: SourceNotFound) -> JSONResponse:
        problem = ProblemDetails(
            title="Resource not found",
            status=404,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=404,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(SourceServiceRejected)
    async def source_rejected_handler(
        request: Request,
        exc: SourceServiceRejected,
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Source admission rejected",
            status=exc.status_code,
            detail=exc.detail,
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(UploadRejected)
    async def upload_rejected_handler(
        request: Request,
        exc: UploadRejected,
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Fixture rejected",
            status=422,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=422,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(PublicationDenied)
    async def publication_denied_handler(
        request: Request,
        exc: PublicationDenied,
    ) -> JSONResponse:
        app.state.publication_gate_denials.update(exc.reasons)
        logger.warning(
            "publication_gate_denied",
            extra={
                "request_id": request.state.request_id,
                "path": request.url.path,
                "reason_codes": list(exc.reasons),
            },
        )
        problem = ProblemDetails(
            title="Publication gate denied the operation",
            status=409,
            detail=", ".join(exc.reasons),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=409,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(IntelligenceNotFound)
    async def intelligence_not_found_handler(
        request: Request,
        exc: IntelligenceNotFound,
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Resource not found",
            status=404,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=404,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(InvalidFeedCursor)
    async def invalid_feed_cursor_handler(
        request: Request,
        exc: InvalidFeedCursor,
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Invalid feed cursor",
            status=400,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=400,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(CursorBindingError)
    async def cursor_binding_handler(request: Request, exc: CursorBindingError) -> JSONResponse:
        problem = ProblemDetails(
            title="Invalid cursor",
            status=400,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=400,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(PortalRepositoryNotFound)
    async def portal_not_found_handler(
        request: Request, exc: PortalRepositoryNotFound
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Resource not found",
            status=404,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=404,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(PortalRepositoryConflict)
    async def portal_conflict_handler(
        request: Request, exc: PortalRepositoryConflict
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Portal state conflict",
            status=409,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=409,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(RepositoryConflict)
    async def repository_conflict_handler(
        request: Request,
        exc: RepositoryConflict,
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Source vault conflict",
            status=409,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=409,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(OperationsRejected)
    async def operations_rejected_handler(
        request: Request, exc: OperationsRejected
    ) -> JSONResponse:
        problem = ProblemDetails(
            title="Operational request rejected",
            status=409,
            detail=str(exc),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=409,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "request_failed",
            exc_info=exc,
            extra={"request_id": request.state.request_id, "path": request.url.path},
        )
        problem = ProblemDetails(
            title="Internal server error",
            status=500,
            detail="The service could not complete the request",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=500,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
        )

    @app.get("/health/live", response_model=LivenessResponse)
    async def live() -> LivenessResponse:
        return LivenessResponse(timestamp=_utc_now())

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        responses={503: {"model": ReadinessResponse}},
    )
    async def ready() -> JSONResponse:
        names = tuple(DependencyName)
        tasks = [
            run_check(
                dependency_checkers.get(name.value, _missing_checker),
                settings.external_io_timeout_seconds,
            )
            for name in names
        ]
        results = await asyncio.gather(*tasks)
        checks: dict[DependencyName, DependencyCheck] = dict(zip(names, results, strict=True))
        is_ready = all(result.status == "up" for result in results)
        body = ReadinessResponse(
            status="ready" if is_ready else "not_ready",
            timestamp=_utc_now(),
            checks=checks,
        )
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content=body.model_dump(mode="json"),
        )

    @app.get("/api/v1/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        return VersionResponse(
            api_version=API_VERSION,
            content_schema_version=CONTENT_SCHEMA_VERSION,
            semantic_search_enabled=settings.semantic_search_enabled,
        )

    app.include_router(source_vault_router)
    app.include_router(intelligence_router)
    app.include_router(portal_router)
    app.include_router(operations_router)

    @app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
    async def metrics(authorization: str | None = Header(default=None)) -> PlainTextResponse:
        configured = settings.metrics_bearer_token
        expected = configured.get_secret_value() if configured is not None else None
        supplied = authorization.removeprefix("Bearer ") if authorization else None
        if expected is None or supplied is None or not hmac.compare_digest(expected, supplied):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Metrics service authentication required",
            )
        service = app.state.source_service
        source_metrics = (
            str(service.metrics.render_prometheus())
            if service is not None and hasattr(service, "metrics")
            else ""
        )
        intelligence = app.state.intelligence_service
        processing_metrics = (
            await intelligence.render_processing_metrics()
            if intelligence is not None and hasattr(intelligence, "render_processing_metrics")
            else ""
        )
        gate_metrics = _render_publication_gate_denial_metrics(app.state.publication_gate_denials)
        operations = app.state.operations_service
        if operations is not None:
            overview = await operations.overview()
            set_operations_metrics(overview.metrics)
            if hasattr(operations, "round17_observability"):
                set_round17_metrics(await operations.round17_observability())
        publication = app.state.publication_service
        if publication is not None and hasattr(publication, "internal_projection_metrics"):
            projection_metrics = await publication.internal_projection_metrics()
            set_internal_projection_metrics(projection_metrics)
        standard, media_type = render_metrics()
        content = standard.decode() + source_metrics + str(processing_metrics) + gate_metrics
        return PlainTextResponse(content, media_type=media_type)

    return app


def _usage_event(method: str, path: str) -> str | None:
    if method == "GET" and path == "/api/v1/search":
        return "SEARCH"
    if method == "GET" and path in {"/api/v1/daily", "/api/v1/daily/reports"}:
        return "READ_DAILY"
    if method == "POST" and path == "/api/v1/saved-items":
        return "SAVE_ITEM"
    if method == "GET" and "/document-versions/" in path and "/pages/" in path:
        return "VIEW_EVIDENCE"
    if method == "GET" and path.endswith(("/bibtex", "/ris", "/gbt7714")):
        return "EXPORT"
    return None


async def _missing_checker() -> None:
    raise RuntimeError("dependency checker is not configured")


def _render_publication_gate_denial_metrics(denials: Counter[str]) -> str:
    if not denials:
        return ""
    bounded_denials: Counter[str] = Counter()
    for reason, count in denials.items():
        safe_reason = (
            reason
            if reason
            and reason.isascii()
            and all(
                character.isupper() or character.isdigit() or character == "_"
                for character in reason
            )
            else "UNKNOWN"
        )
        bounded_denials[safe_reason] += count
    rendered = "# TYPE srbg_publication_gate_denials_total counter\n"
    for safe_reason, count in sorted(bounded_denials.items()):
        rendered += f'srbg_publication_gate_denials_total{{reason="{safe_reason}"}} {count}\n'
    return rendered


def build_default_app() -> FastAPI:
    settings = get_settings()
    policy_root = Path("docs/codex-kit/assets/validation")
    publication_gate = PublicationGate.from_files(
        policy_root / "publication_gate.json",
        policy_root / "publication_evaluation.schema.json",
    )
    intelligence_service = PostgresIntelligenceQueryService(
        create_database_engine(settings),
        preview_object_reader=S3ObjectStore(settings),
    )
    published_reader = PublishedIntelligenceQueryService(
        PublishedProjectionReader(create_projection_reader_engine(settings))
    )
    return create_app(
        source_service=build_default_source_service(settings),
        intelligence_service=intelligence_service,
        public_intelligence_service=published_reader,
        publication_service=PublicationService(
            repository=PostgresPublicationRepository(create_publication_engine(settings)),
            gate=publication_gate,
        ),
        safety_event_candidate_service=SafetyEventCandidateService(
            PostgresEventCandidateStore(create_database_engine(settings))
        ),
        portal_service=PortalApplicationService(
            repository=PostgresPortalRepository(create_database_engine(settings)),
            intelligence=published_reader,
            cursor_signing_key=settings.cursor_signing_key.get_secret_value().encode(),
            semantic_enabled=settings.semantic_search_enabled,
            semantic_timeout_seconds=settings.semantic_search_timeout_seconds,
        ),
        operations_service=PostgresOperationsService(
            create_database_engine(settings),
            projection_engine=create_projection_reader_engine(settings),
            environment=settings.environment,
            ai_enabled=False,
            semantic_search_enabled=settings.semantic_search_enabled,
            external_notifications_enabled=False,
            round17_baseline_commit_attestation=(
                settings.round17_baseline_commit_attestation
            ),
            round17_config_version_attestation=(
                settings.round17_config_version_attestation
            ),
            round17_roster_source_codes=settings.round17_roster_source_codes,
            round17_source_schedule_attestations=(
                settings.round17_source_schedule_attestations
            ),
            round17_leo_approver_actor_id=settings.round17_leo_approver_actor_id,
            round17_authority_mode=settings.round17_authority_mode,
            round17_leo_signing_public_key_base64=(
                settings.round17_leo_signing_public_key_base64
            ),
            round17_leo_signing_public_key_sha256=(
                settings.round17_leo_signing_public_key_sha256
            ),
            round17_eventization_trusted_public_key_base64=(
                settings.round17_eventization_trusted_public_key_base64
            ),
            round17_eventization_trusted_public_key_sha256=(
                settings.round17_eventization_trusted_public_key_sha256
            ),
        ),
    )


app = build_default_app()
