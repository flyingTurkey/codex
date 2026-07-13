"""FastAPI application factory and foundational system endpoints."""

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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

from srbg_api.config import get_settings
from srbg_api.health import HealthChecker, build_default_checkers, run_check
from srbg_api.identifiers import uuid7
from srbg_api.logging import configure_logging


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(checkers: Mapping[str, HealthChecker] | None = None) -> FastAPI:
    configure_logging()
    settings = get_settings()
    dependency_checkers = (
        dict(checkers) if checkers is not None else build_default_checkers(settings)
    )
    app = FastAPI(title="SRBG Insight API", version="0.1.0")
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

    return app


async def _missing_checker() -> None:
    raise RuntimeError("dependency checker is not configured")


app = create_app()
