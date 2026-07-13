"""Dependency health checks with bounded external I/O."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from time import perf_counter
from typing import Any

import aioboto3
import redis.asyncio as redis
from aiobotocore.config import AioConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_contracts import DependencyCheck, DependencyName

from srbg_api.config import Settings

type HealthCheckResult = DependencyCheck | Mapping[str, Any] | None
type HealthChecker = Callable[[], Awaitable[HealthCheckResult]]


async def run_check(checker: HealthChecker, timeout_seconds: float) -> DependencyCheck:
    started = perf_counter()
    try:
        raw_result = await asyncio.wait_for(checker(), timeout=timeout_seconds)
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        if raw_result is None:
            return DependencyCheck(status="up", latency_ms=latency_ms)
        return DependencyCheck.model_validate(raw_result)
    except TimeoutError:
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        return DependencyCheck(status="down", latency_ms=latency_ms, error_code="timeout")
    except Exception:
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        return DependencyCheck(status="down", latency_ms=latency_ms, error_code="unavailable")


def build_default_checkers(settings: Settings) -> dict[str, HealthChecker]:
    async def postgresql() -> None:
        engine = create_async_engine(
            settings.database_url,
            pool_timeout=settings.external_io_timeout_seconds,
        )
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        finally:
            await engine.dispose()

    async def redis_ping() -> None:
        client = redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.external_io_timeout_seconds,
            socket_timeout=settings.external_io_timeout_seconds,
        )
        try:
            await client.ping()
        finally:
            await client.aclose()

    async def object_storage() -> None:
        timeout = settings.external_io_timeout_seconds
        config = AioConfig(
            connect_timeout=timeout,
            read_timeout=timeout,
            retries={"max_attempts": 0},
        )
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=config,
        ) as client:
            await client.head_bucket(Bucket=settings.s3_bucket)

    return {
        DependencyName.POSTGRESQL.value: postgresql,
        DependencyName.REDIS.value: redis_ping,
        DependencyName.OBJECT_STORAGE.value: object_storage,
    }
