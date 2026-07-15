"""Celery application and process health task."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from celery import Celery
from celery.signals import task_failure
from redis.asyncio import Redis, from_url
from srbg_api.config import get_settings
from srbg_api.database import create_database_engine, create_publication_engine
from srbg_api.discovery.projections import PostgresDiscoveryProjectionWriter
from srbg_api.logging import configure_logging
from srbg_api.operations.failures import FailureRecord, failure_record, persist_failure
from srbg_api.operations.replays import ClaimedReplay, claim_replay, finish_replay
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_api.safety_regulations.runner import run_scheduled_mem_discovery

configure_logging()
settings = get_settings()
logger = logging.getLogger("srbg.worker")
celery_app = Celery("srbg-worker", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    enable_utc=True,
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_priority=5,
    broker_transport_options={"priority_steps": list(range(10)), "visibility_timeout": 3600},
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
        "execute-priority-replays": {
            "task": "srbg.operations.replay",
            "schedule": 5.0,
            "options": {"queue": "publisher", "priority": 9},
        },
    },
    task_routes={
        "srbg.safety_regulations.discover": {"queue": "parser"},
        "srbg.publication.outbox": {"queue": "publisher"},
        "srbg.publication.projections": {"queue": "publisher"},
        "srbg.operations.replay": {"queue": "publisher"},
    },
)


@task_failure.connect  # type: ignore[untyped-decorator]
def record_task_failure(
    sender: object | None = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: tuple[object, ...] | None = None,
    kwargs: dict[str, object] | None = None,
    **_: object,
) -> None:
    if task_id is None or exception is None:
        return
    name = str(getattr(sender, "name", "unknown"))
    record = failure_record(
        task_name=name,
        task_id=task_id,
        args=args or (),
        kwargs=kwargs or {},
        exception=exception,
    )
    try:
        asyncio.run(_persist_task_failure(record))
    except Exception:
        logger.warning("failed_task_recording_failed", extra={"task_kind": record.task_kind})
        return


async def _persist_task_failure(record: FailureRecord) -> None:
    engine = create_database_engine(settings)
    try:
        await persist_failure(engine, record)
    finally:
        await engine.dispose()


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


@celery_app.task(name="srbg.operations.replay")  # type: ignore[untyped-decorator]
def execute_priority_replay() -> dict[str, object]:
    return asyncio.run(_execute_priority_replay())


async def _execute_priority_replay() -> dict[str, object]:
    engine = create_database_engine(settings)
    replay = await claim_replay(engine)
    if replay is None:
        await engine.dispose()
        return {"processed": 0}
    succeeded = False
    try:
        await _execute_replay_kind(replay)
        succeeded = True
        return {"processed": 1, "status": "SUCCEEDED", "kind": replay.task_kind}
    finally:
        await finish_replay(engine, replay, succeeded=succeeded)
        await engine.dispose()


async def _execute_replay_kind(replay: ClaimedReplay) -> None:
    if replay.task_kind == "SOURCE_FETCH":
        await run_scheduled_mem_discovery(settings)
        return
    if replay.task_kind == "PUBLICATION_OUTBOX":
        await _drain_publication_outbox()
        return
    if replay.task_kind == "PROJECTION":
        await _drain_publication_projections()
        return
    raise RuntimeError(
        f"replay kind requires a dedicated reconstruction adapter: {replay.task_kind}"
    )


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
