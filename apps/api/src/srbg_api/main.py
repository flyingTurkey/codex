"""FastAPI application factory and foundational system endpoints."""

import asyncio
import logging
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
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
    UserRole,
    VersionResponse,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from srbg_api.auth import Principal, require_roles
from srbg_api.config import get_settings
from srbg_api.database import create_database_engine, create_publication_engine
from srbg_api.document_vault.security import UploadRejected
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.health import HealthChecker, build_default_checkers, run_check
from srbg_api.identifiers import uuid7
from srbg_api.logging import configure_logging
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

MetricsPrincipal = Annotated[
    Principal,
    Depends(require_roles(UserRole.PLATFORM_ADMIN, UserRole.AUDITOR)),
]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(
    checkers: Mapping[str, HealthChecker] | None = None,
    source_service: AdminSourceService | None = None,
    intelligence_service: IntelligenceQueryService | None = None,
    publication_service: ReviewPublicationService | None = None,
    safety_event_candidate_service: EventCandidateGenerationService | None = None,
) -> FastAPI:
    configure_logging()
    settings = get_settings()
    dependency_checkers = (
        dict(checkers) if checkers is not None else build_default_checkers(settings)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for service in (
            source_service,
            intelligence_service,
            publication_service,
            safety_event_candidate_service,
        ):
            close = getattr(service, "close", None)
            if close is not None:
                await close()

    app = FastAPI(title="SRBG Insight API", version="0.1.0", lifespan=lifespan)
    app.state.source_service = source_service
    app.state.intelligence_service = intelligence_service
    app.state.publication_service = publication_service
    app.state.safety_event_candidate_service = safety_event_candidate_service
    app.state.publication_gate_denials = Counter()
    logger = logging.getLogger("srbg.api")

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = str(uuid7())
        started = perf_counter()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": max(0, round((perf_counter() - started) * 1000)),
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
        )

    app.include_router(source_vault_router)
    app.include_router(intelligence_router)

    @app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
    async def metrics(_principal: MetricsPrincipal) -> str:
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
        return source_metrics + str(processing_metrics) + gate_metrics

    return app


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
        policy_root / "publication_gate_v4.json",
        policy_root / "publication_evaluation_v4.schema.json",
    )
    return create_app(
        source_service=build_default_source_service(settings),
        intelligence_service=PostgresIntelligenceQueryService(
            create_database_engine(settings),
            preview_object_reader=S3ObjectStore(settings),
        ),
        publication_service=PublicationService(
            repository=PostgresPublicationRepository(create_publication_engine(settings)),
            gate=publication_gate,
        ),
        safety_event_candidate_service=SafetyEventCandidateService(
            PostgresEventCandidateStore(create_database_engine(settings))
        ),
    )


app = build_default_app()
