"""Celery application and process health task."""

import asyncio
from pathlib import Path
from uuid import UUID

from celery import Celery
from redis.asyncio import Redis, from_url
from srbg_api.config import get_settings
from srbg_api.database import create_publication_engine
from srbg_api.discovery.projections import PostgresDiscoveryProjectionWriter
from srbg_api.logging import configure_logging
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_api.safety_regulations.runner import run_scheduled_mem_discovery

configure_logging()
settings = get_settings()
celery_app = Celery("srbg-worker", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    enable_utc=True,
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "discover-mem-safety-regulations": {
            "task": "srbg.safety_regulations.discover",
            "schedule": 900.0,
        },
        "publish-version-lifecycle-events": {
            "task": "srbg.publication.outbox",
            "schedule": 5.0,
            "options": {"queue": "publisher"},
        },
        "apply-publication-projections": {
            "task": "srbg.publication.projections",
            "schedule": 5.0,
            "options": {"queue": "publisher"},
        },
    },
    task_routes={
        "srbg.safety_regulations.discover": {"queue": "parser"},
        "srbg.publication.outbox": {"queue": "publisher"},
        "srbg.publication.projections": {"queue": "publisher"},
    },
)


@celery_app.task(name="srbg.system.health")  # type: ignore[untyped-decorator]
def health() -> dict[str, str]:
    return {"status": "ok", "service": "worker"}


@celery_app.task(name="srbg.safety_regulations.discover")  # type: ignore[untyped-decorator]
def discover_safety_regulations() -> dict[str, object]:
    return asyncio.run(run_scheduled_mem_discovery(settings))


@celery_app.task(name="srbg.publication.outbox")  # type: ignore[untyped-decorator]
def publish_version_lifecycle_events() -> dict[str, int]:
    return asyncio.run(_drain_publication_outbox())


@celery_app.task(name="srbg.publication.projections")  # type: ignore[untyped-decorator]
def apply_publication_projections() -> dict[str, int]:
    return asyncio.run(_drain_publication_projections())


async def _drain_publication_outbox() -> dict[str, int]:
    policy_root = Path("docs/codex-kit/assets/validation")
    service = PublicationService(
        repository=PostgresPublicationRepository(create_publication_engine(settings)),
        gate=PublicationGate.from_files(
            policy_root / "publication_gate.json",
            policy_root / "publication_evaluation.schema.json",
        ),
    )
    processed = 0
    try:
        while processed < 50 and await service.process_outbox_once():
            processed += 1
        return {"processed": processed}
    finally:
        await service.close()


async def _advance_cache_generation(
    cache: Redis, publication_id: UUID, generation: int, visible: bool
) -> None:
    key_prefix = f"srbg:publication:{publication_id}"
    pipeline = cache.pipeline(transaction=True)
    pipeline.set(f"{key_prefix}:generation", str(generation))
    pipeline.set(f"{key_prefix}:visible", "1" if visible else "0")
    await pipeline.execute()


async def _drain_publication_projections() -> dict[str, int]:
    policy_root = Path("docs/codex-kit/assets/validation")
    service = PublicationService(
        repository=PostgresPublicationRepository(create_publication_engine(settings)),
        gate=PublicationGate.from_files(
            policy_root / "publication_gate.json",
            policy_root / "publication_evaluation.schema.json",
        ),
    )
    cache = from_url(settings.redis_url, decode_responses=True)
    projection_writer = PostgresDiscoveryProjectionWriter(create_publication_engine(settings))
    processed = 0
    try:
        async def advance(publication_id: UUID, generation: int, visible: bool) -> None:
            await _advance_cache_generation(cache, publication_id, generation, visible)

        while processed < 150 and await service.process_projection_invalidation_once(
            cache_generation=advance,
            search_projection=projection_writer.apply_search,
            daily_digest=projection_writer.invalidate_daily,
        ):
            processed += 1
        return {"processed": processed}
    finally:
        await cache.aclose()
        await projection_writer.close()
        await service.close()
