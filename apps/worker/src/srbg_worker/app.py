"""Celery application and process health task."""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from celery import Celery
from celery.signals import task_failure
from redis.asyncio import Redis, from_url
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.ai_pipeline.content_preparation import (
    AiContentPreparationService,
    PreparationDocument,
)
from srbg_api.ai_pipeline.contracts import AiStep, ModelResponse
from srbg_api.ai_pipeline.gateway import ModelOutputRejected, validate_step_output
from srbg_api.ai_pipeline.preparation import PreparedDocumentInput, prepare_document_input
from srbg_api.ai_pipeline.runtime import AttemptKind
from srbg_api.ai_pipeline.security import PromptInjectionScanner
from srbg_api.config import Settings, get_settings
from srbg_api.database import create_database_engine, create_publication_engine
from srbg_api.discovery.projections import PostgresDiscoveryProjectionWriter
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.internal_projection.audit_anchor import anchor_latest_audit_root
from srbg_api.logging import configure_logging
from srbg_api.observability import REPLAY_RESULTS
from srbg_api.operations.failures import FailureRecord, failure_record, persist_failure
from srbg_api.operations.replays import (
    ClaimedReplay,
    claim_replay,
    execute_source_fetch_replay,
    finish_replay,
    prepare_task_redelivery,
)
from srbg_api.pdf_processing.ocr import TesseractOcrAdapter
from srbg_api.pdf_processing.parser import PdfDocumentParser
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_api.safety_regulations.runner import run_scheduled_mem_discovery
from srbg_api.scheduling.domain import build_fetch_message
from srbg_api.scheduling.service import PostgresSchedulingService
from srbg_api.source_automation.search import (
    BAIDU_SEARCH_API_URL,
    BaiduSearchProvider,
    PinnedBaiduJsonTransport,
    PostgresMonthlyBudgetLedger,
)

from srbg_worker.ai_content_preparation import PostgresAiPreparationRepository
from srbg_worker.source_content_bridge import (
    PostgresSourceContentGateway,
    SourceContentOutboxExecutor,
)
from srbg_worker.source_discovery import (
    QUERY_CATALOG,
    DiscoveryExecutor,
    DiscoveryOutcome,
    PostgresDiscoveryGateway,
    SafeDiscoveryTargetProbe,
)
from srbg_worker.source_qualification import (
    ActivationOutboxExecutor,
    CanonicalTargetProvider,
    DisabledTargetProbe,
    PostgresActivationOutboxGateway,
    PostgresQualificationGateway,
    QualificationExecutor,
    ResilientTargetProbe,
)
from srbg_worker.source_runtime import (
    LiveRuntimeTransport,
    PostgresRuntimeGateway,
    RuntimeBinding,
    RuntimeFetchExecutor,
)

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
        "dispatch-due-source-schedules": {
            "task": "srbg.schedules.dispatch",
            "schedule": 30.0,
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
        "anchor-audit-chain": {
            "task": "srbg.audit.anchor",
            "schedule": 86400.0,
            "options": {"queue": "publisher"},
        },
        "dispatch-source-activation-outbox": {
            "task": "srbg.sources.activation_outbox",
            "schedule": 5.0,
            "options": {"queue": "celery"},
        },
        "dispatch-pending-source-qualifications": {
            "task": "srbg.sources.qualify",
            "schedule": 5.0,
            "options": {"queue": "qualification"},
        },
        "dispatch-automated-source-discovery": {
            "task": "srbg.sources.discovery.dispatch",
            "schedule": 21600.0,
            "options": {"queue": "celery"},
        },
        "dispatch-source-content-outbox": {
            "task": "srbg.source_content.outbox",
            "schedule": 5.0,
            "options": {"queue": "parser"},
        },
    },
    task_routes={
        "srbg.safety_regulations.discover": {"queue": "parser"},
        "srbg.schedules.dispatch": {"queue": "celery"},
        "srbg.source.fetch": {"queue": "parser"},
        "srbg.sources.qualify": {"queue": "qualification"},
        "srbg.sources.activation_outbox": {"queue": "celery"},
        "srbg.sources.discovery.dispatch": {"queue": "celery"},
        "srbg.sources.discovery.query": {"queue": "discovery"},
        "srbg.source_content.outbox": {"queue": "parser"},
        "srbg.ai_content.start": {"queue": "parser"},
        "srbg.ai_content.result": {"queue": "parser"},
        "srbg.publication.outbox": {"queue": "publisher"},
        "srbg.publication.projections": {"queue": "publisher"},
        "srbg.operations.replay": {"queue": "publisher"},
        "srbg.audit.anchor": {"queue": "publisher"},
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


@celery_app.task(name="srbg.schedules.dispatch")  # type: ignore[untyped-decorator]
def dispatch_due_schedules() -> dict[str, int]:
    return asyncio.run(_dispatch_due_schedules())


@celery_app.task(name="srbg.source.fetch")  # type: ignore[untyped-decorator]
def execute_source_fetch(*, source_id: str, run_id: str) -> dict[str, object]:
    return asyncio.run(_execute_source_fetch(UUID(source_id), UUID(run_id)))


@celery_app.task(name="srbg.source_content.outbox")  # type: ignore[untyped-decorator]
def process_source_content_outbox(
    *,
    outbox_id: str | None = None,
) -> dict[str, object]:
    return asyncio.run(
        _drain_source_content_outbox(None if outbox_id is None else UUID(outbox_id))
    )


@celery_app.task(name="srbg.ai_content.start")  # type: ignore[untyped-decorator]
def start_ai_content_preparation(*, run_id: str) -> dict[str, object]:
    return asyncio.run(_start_ai_content_preparation(UUID(run_id)))


@celery_app.task(name="srbg.ai_content.result")  # type: ignore[untyped-decorator]
def handle_ai_content_result(
    result: dict[str, object],
    *,
    run_id: str,
    step: str,
    attempt: int,
    kind: str,
    network_retries: int,
    repair_used: bool,
    reservation_id: str,
) -> dict[str, object]:
    return asyncio.run(
        _handle_ai_content_result(
            result=result,
            run_id=UUID(run_id),
            step=AiStep(step),
            attempt=attempt,
            kind=AttemptKind(kind),
            network_retries=network_retries,
            repair_used=repair_used,
            reservation_id=UUID(reservation_id),
        )
    )


@celery_app.task(name="srbg.sources.qualify")  # type: ignore[untyped-decorator]
def execute_source_qualification(
    *,
    qualification_run_id: str | None = None,
) -> dict[str, object]:
    if qualification_run_id is None:
        return asyncio.run(_dispatch_pending_source_qualifications())
    return asyncio.run(_execute_source_qualification(UUID(qualification_run_id)))


@celery_app.task(name="srbg.sources.activation_outbox")  # type: ignore[untyped-decorator]
def process_source_activation_outbox(
    *,
    outbox_id: str | None = None,
) -> dict[str, object]:
    return asyncio.run(
        _drain_source_activation_outbox(
            None if outbox_id is None else UUID(outbox_id),
        )
    )


@celery_app.task(name="srbg.sources.discovery.dispatch")  # type: ignore[untyped-decorator]
def dispatch_automated_source_discovery() -> dict[str, object]:
    return _dispatch_automated_source_discovery()


@celery_app.task(name="srbg.sources.discovery.query")  # type: ignore[untyped-decorator]
def execute_automated_source_discovery_query(
    *,
    query_code: str,
    discovery_run_id: str,
) -> dict[str, object]:
    return asyncio.run(
        _execute_automated_source_discovery_query(
            query_code=query_code,
            discovery_run_id=UUID(discovery_run_id),
        )
    )


def _dispatch_automated_source_discovery() -> dict[str, object]:
    if not (settings.source_discovery_enabled and settings.baidu_search_enabled):
        return {"disabled": True, "dispatched": 0, "discovery_run_id": None}
    discovery_run_id = uuid7()
    for query_code in sorted(QUERY_CATALOG):
        celery_app.send_task(
            "srbg.sources.discovery.query",
            kwargs={
                "query_code": query_code,
                "discovery_run_id": str(discovery_run_id),
            },
            queue="discovery",
        )
    return {
        "disabled": False,
        "dispatched": len(QUERY_CATALOG),
        "discovery_run_id": str(discovery_run_id),
    }


async def _execute_automated_source_discovery_query(
    *,
    query_code: str,
    discovery_run_id: UUID,
) -> dict[str, object]:
    enabled = settings.source_discovery_enabled and settings.baidu_search_enabled
    if not enabled:
        return DiscoveryOutcome(
            discovery_run_id,
            query_code,
            disabled=True,
        ).as_task_result()
    api_key = settings.baidu_search_api_key
    if api_key is None or not api_key.get_secret_value():
        return DiscoveryOutcome(
            discovery_run_id,
            query_code,
            provider_failures=1,
        ).as_task_result()

    engine = create_database_engine(settings)
    gateway = PostgresDiscoveryGateway(engine)
    provider = BaiduSearchProvider(
        api_url=BAIDU_SEARCH_API_URL,
        api_key=api_key.get_secret_value(),
        transport=PinnedBaiduJsonTransport(),
        budget_ledger=PostgresMonthlyBudgetLedger(
            engine,
            provider="BAIDU_SEARCH",
            monthly_cap_micrormb=min(
                settings.baidu_search_monthly_cap_micrormb,
                200_000_000,
            ),
            free_calls_per_month=min(
                settings.baidu_search_free_calls_per_month,
                1_500,
            ),
            alert_threshold_bps=min(
                settings.baidu_search_budget_alert_bps,
                8_000,
            ),
        ),
        cost_per_call_micrormb=36_000,
        timeout_seconds=settings.baidu_search_timeout_seconds,
    )
    try:
        outcome = await DiscoveryExecutor(
            enabled=True,
            provider=provider,
            probe=SafeDiscoveryTargetProbe(settings),
            gateway=gateway,
        ).run(
            query_code=query_code,
            discovery_run_id=discovery_run_id,
            now=datetime.now(UTC),
        )
        if outcome.budget_alerts:
            logger.warning(
                "baidu_search_monthly_budget_threshold_reached",
                extra={"discovery_run_id": str(discovery_run_id)},
            )
        return outcome.as_task_result()
    finally:
        await gateway.close()


async def _dispatch_due_schedules() -> dict[str, int]:
    service = PostgresSchedulingService(create_database_engine(settings))
    dispatched = 0
    try:
        while dispatched < 100:
            claimed = await service.claim_due()
            if claimed is None:
                break
            message = build_fetch_message(source_id=claimed.source_id, run_id=claimed.run_id)
            celery_app.send_task("srbg.source.fetch", kwargs=message)
            await service.mark_dispatched(claimed.run_id)
            dispatched += 1
        return {"dispatched": dispatched}
    finally:
        await service.close()


async def _execute_source_fetch(source_id: UUID, run_id: UUID) -> dict[str, object]:
    gateway = PostgresRuntimeGateway(settings)

    def live_transport(binding: RuntimeBinding) -> LiveRuntimeTransport:
        return LiveRuntimeTransport(
            binding,
            before_request=lambda url: gateway.reserve_request(binding, url=url),
            after_response=lambda url, response_bytes: gateway.record_response_bytes(
                binding,
                url=url,
                response_bytes=response_bytes,
            ),
        )

    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=live_transport,
        max_document_bytes=settings.fixture_max_bytes,
    )
    result = await executor.run(source_id=source_id, run_id=run_id)
    return {
        "acquired": result.acquired,
        "cancelled": result.cancelled,
        "source_id": str(source_id),
        "run_id": str(run_id),
        "discovered_count": result.discovered_count,
        "fetched_count": result.fetched_count,
        "failed_count": result.failed_count,
        "request_count": result.request_count,
        "response_bytes": result.response_bytes,
    }


async def _drain_source_content_outbox(
    outbox_id: UUID | None,
) -> dict[str, object]:
    gateway = PostgresSourceContentGateway(engine=create_database_engine(settings))
    try:
        if outbox_id is None:
            pending_ids = await gateway.pending_ids(limit=50)
            for pending_id in pending_ids:
                celery_app.send_task(
                    "srbg.source_content.outbox",
                    kwargs={"outbox_id": str(pending_id)},
                )
            return {"dispatched": len(pending_ids)}

        outcome = await SourceContentOutboxExecutor(gateway=gateway).run(outbox_id)
        if outcome is None:
            return {
                "outbox_id": str(outbox_id),
                "document_version_id": None,
                "pipeline_run_id": None,
                "status": "ALREADY_CLAIMED",
                "queued": False,
            }
        response = {
            "outbox_id": str(outcome.outbox_id),
            "document_version_id": str(outcome.document_version_id),
            "pipeline_run_id": str(outcome.pipeline_run_id),
            "status": outcome.status,
            "queued": outcome.queued,
        }
        if outcome.queued:
            celery_app.send_task(
                "srbg.ai_content.start",
                kwargs={"run_id": str(outcome.pipeline_run_id)},
            )
        return response
    finally:
        await gateway.close()


def _ai_repository() -> PostgresAiPreparationRepository:
    parser = PdfDocumentParser(
        ocr_adapter=TesseractOcrAdapter(timeout_seconds=settings.ocr_timeout_seconds),
        max_ocr_pages=settings.pdf_max_ocr_pages,
        max_page_pixels=settings.pdf_max_page_pixels,
    )
    return PostgresAiPreparationRepository(
        engine=create_database_engine(settings),
        object_store=S3ObjectStore(settings),
        parser=parser,
        environment=settings.environment,
        max_document_bytes=settings.fixture_max_bytes,
    )


async def _start_ai_content_preparation(run_id: UUID) -> dict[str, object]:
    repository = _ai_repository()
    try:
        document, classify_input, extract_input = await _prepare_ai_inputs(repository, run_id)
        scan = PromptInjectionScanner().scan(extract_input.text)
        await repository.record_security(document, scan.detected)
        if scan.detected:
            await repository.fail(run_id, "DEGRADED", "PROMPT_INJECTION_R4")
            return {"run_id": str(run_id), "status": "DEGRADED"}
        await repository.transition(run_id, "CLASSIFYING")
        await _dispatch_ai_attempt(
            repository,
            run_id=run_id,
            step=AiStep.CLASSIFY,
            prepared=classify_input,
            attempt=1,
            kind=AttemptKind.PRIMARY,
            network_retries=0,
            repair_used=False,
        )
        return {"run_id": str(run_id), "status": "CLASSIFYING"}
    except Exception as error:
        await repository.fail(run_id, "FAILED", _safe_ai_error_code(error))
        raise
    finally:
        await repository.close()


async def _handle_ai_content_result(
    *,
    result: dict[str, object],
    run_id: UUID,
    step: AiStep,
    attempt: int,
    kind: AttemptKind,
    network_retries: int,
    repair_used: bool,
    reservation_id: UUID,
) -> dict[str, object]:
    repository = _ai_repository()
    try:
        document, classify_input, extract_input = await _prepare_ai_inputs(repository, run_id)
        prepared = classify_input if step is AiStep.CLASSIFY else extract_input
        request = AiContentPreparationService.build_request(step, prepared)
        if result.get("status") == "SUCCEEDED":
            response = ModelResponse.model_validate(result.get("response"))
            validated = validate_step_output(response.output, request)
            response = response.model_copy(
                update={"output": validated.model_dump(mode="json", exclude_none=True)}
            )
            await repository.settle(reservation_id, response)
            await repository.append_step(
                run_id,
                step,
                attempt,
                kind.value,
                response,
                request.input_sha256,
            )
            if step is AiStep.CLASSIFY:
                await repository.transition(run_id, "EXTRACTING")
                await _dispatch_ai_attempt(
                    repository,
                    run_id=run_id,
                    step=AiStep.EXTRACT,
                    prepared=extract_input,
                    attempt=1,
                    kind=AttemptKind.PRIMARY,
                    network_retries=0,
                    repair_used=False,
                )
                return {"run_id": str(run_id), "status": "EXTRACTING"}
            classification = await repository.successful_output(run_id, AiStep.CLASSIFY)
            candidates = await repository.materialize(
                document,
                classification,
                response.output,
            )
            if candidates < 1:
                raise RuntimeError("NO_VALID_CANDIDATES")
            await repository.transition(run_id, "WAITING_CLAIM_REVIEW")
            return {
                "run_id": str(run_id),
                "status": "WAITING_CLAIM_REVIEW",
                "candidate_count": candidates,
            }

        await repository.settle(reservation_id, None)
        code = str(result.get("error_code") or "MODEL_ATTEMPT_FAILED")[:80]
        await repository.append_failed_step(
            run_id, step, attempt, kind.value, code, request.input_sha256
        )
        retryable = result.get("retryable") is True
        repairable = result.get("repairable") is True
        if retryable and network_retries < 2:
            await _dispatch_ai_attempt(
                repository,
                run_id=run_id,
                step=step,
                prepared=prepared,
                attempt=attempt + 1,
                kind=AttemptKind.NETWORK_RETRY,
                network_retries=network_retries + 1,
                repair_used=repair_used,
            )
            return {"run_id": str(run_id), "status": "RETRYING"}
        if repairable and not repair_used:
            await _dispatch_ai_attempt(
                repository,
                run_id=run_id,
                step=step,
                prepared=prepared,
                attempt=attempt + 1,
                kind=AttemptKind.REPAIR,
                network_retries=network_retries,
                repair_used=True,
                repair_code=code,
            )
            return {"run_id": str(run_id), "status": "REPAIRING"}
        failure_status = "FAILED" if step is AiStep.CLASSIFY else "DEGRADED"
        await repository.fail(run_id, failure_status, code)
        return {"run_id": str(run_id), "status": failure_status}
    except (ModelOutputRejected, ValueError) as error:
        await repository.settle(reservation_id, None)
        code = _safe_ai_error_code(error)
        await repository.append_failed_step(
            run_id, step, attempt, kind.value, code, request.input_sha256
        )
        if not repair_used:
            await _dispatch_ai_attempt(
                repository,
                run_id=run_id,
                step=step,
                prepared=prepared,
                attempt=attempt + 1,
                kind=AttemptKind.REPAIR,
                network_retries=network_retries,
                repair_used=True,
                repair_code=code,
            )
            return {"run_id": str(run_id), "status": "REPAIRING"}
        failure_status = "FAILED" if step is AiStep.CLASSIFY else "DEGRADED"
        await repository.fail(run_id, failure_status, code)
        return {"run_id": str(run_id), "status": failure_status}
    except Exception as error:
        failure_status = "FAILED" if step is AiStep.CLASSIFY else "DEGRADED"
        await repository.fail(run_id, failure_status, _safe_ai_error_code(error))
        raise
    finally:
        await repository.close()


async def _prepare_ai_inputs(
    repository: PostgresAiPreparationRepository,
    run_id: UUID,
) -> tuple[PreparationDocument, PreparedDocumentInput, PreparedDocumentInput]:
    document = await repository.begin(run_id)
    if (
        document.source_code != AiContentPreparationService.PILOT_SOURCE
        or document.canonical_url != AiContentPreparationService.PILOT_URL
    ):
        raise PermissionError("AI01_PILOT_SCOPE_DENIED")
    return (
        document,
        prepare_document_input(
            document_version_id=document.document_version_id,
            title=document.title,
            source_name=document.source_name,
            blocks=list(document.blocks),
            max_characters=32_000,
        ),
        prepare_document_input(
            document_version_id=document.document_version_id,
            title=document.title,
            source_name=document.source_name,
            blocks=list(document.blocks),
            max_characters=128_000,
        ),
    )


async def _dispatch_ai_attempt(
    repository: PostgresAiPreparationRepository,
    *,
    run_id: UUID,
    step: AiStep,
    prepared: PreparedDocumentInput,
    attempt: int,
    kind: AttemptKind,
    network_retries: int,
    repair_used: bool,
    repair_code: str | None = None,
) -> None:
    request = AiContentPreparationService.build_request(step, prepared)
    if repair_code:
        request = request.model_copy(
            update={
                "user_prompt": request.user_prompt
                + "\n<controlled_repair>Return valid JSON. Error code: "
                + repair_code
                + ".</controlled_repair>"
            }
        )
    reservation = await repository.reserve(run_id, step, attempt)
    callback = celery_app.signature(
        "srbg.ai_content.result",
        kwargs={
            "run_id": str(run_id),
            "step": step.value,
            "attempt": attempt,
            "kind": kind.value,
            "network_retries": network_retries,
            "repair_used": repair_used,
            "reservation_id": str(reservation),
        },
        immutable=False,
    )
    try:
        celery_app.send_task(
            "srbg.ai.generate_attempt",
            args=[request.model_dump(mode="json")],
            link=callback,
        )
    except Exception:
        await repository.release(reservation)
        raise


def _safe_ai_error_code(error: Exception) -> str:
    value = str(error).strip()
    if value in {
        "AI01_PILOT_SCOPE_DENIED",
        "MODEL_DISABLED",
        "PROMPT_INJECTION_R4",
        "NO_VALID_CANDIDATES",
    }:
        return value
    return type(error).__name__.upper()[:80]


async def _execute_source_qualification(
    qualification_run_id: UUID,
) -> dict[str, object]:
    if not settings.source_qualification_enabled:
        return {
            "qualification_run_id": str(qualification_run_id),
            "status": "DISABLED",
            "acquired": False,
            "target_evidence_count": 0,
            "disabled": True,
        }
    result = await QualificationExecutor(
        gateway=PostgresQualificationGateway(settings),
        provider=CanonicalTargetProvider(),
        target_probe=_build_qualification_target_probe(settings),
    ).run(
        qualification_run_id=qualification_run_id,
    )
    return {
        "qualification_run_id": str(result.qualification_run_id),
        "status": result.status,
        "acquired": result.acquired,
        "target_evidence_count": result.target_evidence_count,
    }


def _build_qualification_target_probe(
    config: Settings,
) -> DisabledTargetProbe | ResilientTargetProbe:
    if not config.source_qualification_enabled:
        return DisabledTargetProbe()
    return ResilientTargetProbe(config)


async def _dispatch_pending_source_qualifications() -> dict[str, object]:
    if not settings.source_qualification_enabled:
        return {"disabled": True, "dispatched": 0}
    gateway = PostgresQualificationGateway(settings)
    try:
        pending_ids = await gateway.pending_ids(limit=50)
        for pending_id in pending_ids:
            celery_app.send_task(
                "srbg.sources.qualify",
                kwargs={"qualification_run_id": str(pending_id)},
                queue="qualification",
            )
        return {"dispatched": len(pending_ids)}
    finally:
        await gateway.close()


async def _drain_source_activation_outbox(
    outbox_id: UUID | None,
) -> dict[str, object]:
    gateway = PostgresActivationOutboxGateway(settings)
    try:
        if outbox_id is None:
            pending_ids = await gateway.pending_ids(limit=50)
            for pending_id in pending_ids:
                celery_app.send_task(
                    "srbg.sources.activation_outbox",
                    kwargs={"outbox_id": str(pending_id)},
                )
            return {"dispatched": len(pending_ids)}

        async def dispatch_source_fetch(source_id: UUID, run_id: UUID) -> None:
            celery_app.send_task(
                "srbg.source.fetch",
                kwargs={"source_id": str(source_id), "run_id": str(run_id)},
            )

        outcome = await ActivationOutboxExecutor(
            gateway=gateway,
            dispatch_source_fetch=dispatch_source_fetch,
        ).run(outbox_id)
        return {
            "outbox_id": str(outcome.outbox_id),
            "source_id": None if outcome.source_id is None else str(outcome.source_id),
            "fetch_run_id": (None if outcome.fetch_run_id is None else str(outcome.fetch_run_id)),
            "status": outcome.status,
            "dispatched": outcome.dispatched,
        }
    finally:
        await gateway.close()


@celery_app.task(name="srbg.publication.outbox")  # type: ignore[untyped-decorator]
def publish_version_lifecycle_events() -> dict[str, int]:
    return asyncio.run(_drain_publication_outbox())


@celery_app.task(name="srbg.publication.projections")  # type: ignore[untyped-decorator]
def apply_publication_projections() -> dict[str, int]:
    return asyncio.run(_drain_publication_projections())


@celery_app.task(name="srbg.operations.replay")  # type: ignore[untyped-decorator]
def execute_priority_replay() -> dict[str, object]:
    return asyncio.run(_execute_priority_replay())


@celery_app.task(name="srbg.audit.anchor")  # type: ignore[untyped-decorator]
def anchor_audit_chain() -> dict[str, object]:
    return asyncio.run(_anchor_audit_chain())


async def _anchor_audit_chain() -> dict[str, object]:
    engine = create_publication_engine(settings)
    try:
        result = await anchor_latest_audit_root(engine, settings)
        return {
            "anchored": 0 if result.already_anchored else 1,
            "already_anchored": result.already_anchored,
        }
    finally:
        await engine.dispose()


async def _execute_priority_replay() -> dict[str, object]:
    engine = create_database_engine(settings)
    replay = await claim_replay(engine)
    if replay is None:
        await engine.dispose()
        return {"processed": 0}
    succeeded = False
    outcome_reason: str | None = None
    try:
        await _execute_replay_kind(replay, engine)
        succeeded = True
        return {"processed": 1, "status": "SUCCEEDED", "kind": replay.task_kind}
    except Exception as error:
        outcome_reason = type(error).__name__.upper()[:80]
        raise
    finally:
        await finish_replay(
            engine,
            replay,
            succeeded=succeeded,
            outcome_reason=outcome_reason,
        )
        metric_kind = (
            replay.task_kind
            if replay.task_kind
            in {
                "SOURCE_FETCH",
                "SOURCE_QUALIFICATION",
                "SOURCE_ACTIVATION_OUTBOX",
                "SOURCE_CONTENT_OUTBOX",
                "PARSER",
                "AI",
                "PUBLICATION_OUTBOX",
                "PROJECTION",
            }
            else "UNKNOWN"
        )
        REPLAY_RESULTS.labels(
            kind=metric_kind,
            outcome="SUCCEEDED" if succeeded else "FAILED",
        ).inc()
        await engine.dispose()


async def _execute_replay_kind(replay: ClaimedReplay, engine: AsyncEngine) -> None:
    if replay.task_kind in {
        "SOURCE_QUALIFICATION",
        "SOURCE_ACTIVATION_OUTBOX",
        "SOURCE_CONTENT_OUTBOX",
    }:
        redelivery = await prepare_task_redelivery(engine, replay)
        if redelivery is not None:
            celery_app.send_task(
                redelivery.task_name,
                kwargs=redelivery.task_kwargs(),
            )
        return
    if replay.task_kind == "SOURCE_FETCH":
        await execute_source_fetch_replay(
            engine,
            replay,
            S3ObjectStore(settings),
            max_bytes=settings.fixture_max_bytes,
        )
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
