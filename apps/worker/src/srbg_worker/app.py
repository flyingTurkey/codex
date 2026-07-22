"""Celery application and process health task."""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from celery import Celery
from celery.signals import task_failure
from redis.asyncio import Redis, from_url
from sqlalchemy import text
from srbg_api.ai_pipeline.ai_judgments import (
    AiJudgmentResultType,
    SummarizeOutput,
)
from srbg_api.ai_pipeline.content_preparation import (
    AiContentPreparationService,
    PreparationDocument,
    SemanticRecheckRequired,
    adjudicate_candidates,
    production_policy_for,
    try_deterministic_adjudication,
)
from srbg_api.ai_pipeline.contracts import AiStep, ModelRequest, ModelResponse
from srbg_api.ai_pipeline.gateway import ModelOutputRejected, validate_step_output
from srbg_api.ai_pipeline.preparation import PreparedDocumentInput, prepare_document_input
from srbg_api.ai_pipeline.runtime import AttemptKind
from srbg_api.ai_pipeline.security import PromptInjectionScanner
from srbg_api.config import get_settings
from srbg_api.database import create_database_engine, create_publication_engine
from srbg_api.discovery.projections import PostgresDiscoveryProjectionWriter
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.ai_runtime import summary_state_for_failure
from srbg_api.intelligence_v2.autonomous_policy import QualificationPolicyBundle
from srbg_api.intelligence_v2.t06_content_summary import (
    validate_content_summary_output,
)
from srbg_api.internal_projection.audit_anchor import anchor_latest_audit_root
from srbg_api.logging import configure_logging
from srbg_api.observability import (
    INTELLIGENCE_QUALIFICATION_DECISIONS,
    PERSONAL_AUTO_ENABLE_RESULTS,
    PERSONAL_DISCOVERY_RESULTS,
    PERSONAL_SOURCE_PROBE_QUEUE,
    SOURCE_PROFILE_MODEL_ATTEMPTS,
    SOURCE_PROFILE_QUEUE,
    SOURCE_PROFILE_RUNS,
)
from srbg_api.pdf_processing.ocr import TesseractOcrAdapter
from srbg_api.pdf_processing.parser import PdfDocumentParser
from srbg_api.personal_search import (
    BAIDU_SEARCH_API_URL,
    BaiduSearchProvider,
    PinnedBaiduJsonTransport,
    PostgresMonthlyBudgetLedger,
)
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_api.safety_regulations.runner import run_scheduled_mem_discovery
from srbg_api.scheduling.domain import build_fetch_message
from srbg_api.scheduling.service import PostgresSchedulingService
from srbg_api.source_profile_ai import build_profile_request
from srbg_api.source_profiles import (
    ProfileEvidence,
    ProfileRuleInput,
    build_source_profile,
)
from srbg_contracts import (
    AutomatedDisposition,
    AutonomousClassificationCandidate,
    SourceProfileModelOutput,
)

from srbg_worker.ai_content_preparation import PostgresAiPreparationRepository
from srbg_worker.controlled_run_ledger import ControlledRunAttemptObserver
from srbg_worker.personal_source_discovery import (
    PersonalAutoEnableExecutor,
    PostgresAutoEnableGateway,
    PostgresPersonalDiscoveryGateway,
    PostgresPersonalOccurrenceTracker,
    PostgresSavedEvidenceAdapter,
    queue_existing_source_scoring,
)
from srbg_worker.personal_source_probe import (
    PersonalProbeExecutor,
    PostgresPersonalProbeGateway,
    SafePersonalProbeFetcher,
)
from srbg_worker.source_content_bridge import (
    PostgresSourceContentGateway,
    SourceContentOutboxExecutor,
)
from srbg_worker.source_discovery import (
    QUERY_CATALOG,
    DiscoveryExecutor,
    DiscoveryOutcome,
    PublicDiscoveryChannel,
    PublicSeedDiscoveryExecutor,
    SafeDiscoveryTargetProbe,
)
from srbg_worker.source_profile import (
    PostgresSourceProfileGateway,
    PreparedProfile,
    ProfileBinding,
    prepare_profile,
    terminal_profile_fallback_reason,
)
from srbg_worker.source_runtime import (
    LiveRuntimeTransport,
    PostgresRuntimeGateway,
    RuntimeBinding,
    RuntimeFetchExecutor,
)
from srbg_worker.v2_canary import fixed_canary_input

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
        "dispatch-personal-source-probes": {
            "task": "srbg.personal_source.probe",
            "schedule": 5.0,
            "options": {"queue": "personal-source"},
        },
        "dispatch-source-profiles": {
            "task": "srbg.source_profile.run",
            "schedule": 10.0,
            "options": {"queue": "personal-source"},
        },
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
        "reprocess-v2-owner-review": {
            "task": "srbg.intelligence_v2.review_dispatch",
            "schedule": 5.0,
            "options": {"queue": "publisher"},
        },
        "observe-ai-runtime": {
            "task": "srbg.ai.runtime_probe_dispatch",
            "schedule": 30.0,
            "options": {"queue": "celery"},
        },
        "run-ai-v2-fixed-canary": {
            "task": "srbg.ai.v2_canary_dispatch",
            "schedule": 21600.0,
            "options": {"queue": "celery"},
        },
        "anchor-audit-chain": {
            "task": "srbg.audit.anchor",
            "schedule": 86400.0,
            "options": {"queue": "publisher"},
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
        "srbg.personal_source.probe": {"queue": "personal-source"},
        "srbg.source_profile.run": {"queue": "personal-source"},
        "srbg.source_profile.result": {"queue": "personal-source"},
        "srbg.sources.discovery.dispatch": {"queue": "celery"},
        "srbg.sources.discovery.query": {"queue": "discovery"},
        "srbg.sources.discovery.personal_cycle": {"queue": "discovery"},
        "srbg.source_content.outbox": {"queue": "parser"},
        "srbg.ai_content.start": {"queue": "parser"},
        "srbg.ai_content.result": {"queue": "parser"},
        "srbg.ai.generate": {"queue": "ai"},
        "srbg.ai.generate_attempt": {"queue": "ai"},
        "srbg.ai.runtime_probe_dispatch": {"queue": "celery"},
        "srbg.ai.runtime_observation": {"queue": "celery"},
        "srbg.ai.v2_canary_dispatch": {"queue": "celery"},
        "srbg.ai.v2_canary_result": {"queue": "celery"},
        "srbg.ai.v2_campaign_fault_injection": {"queue": "celery"},
        "srbg.publication.outbox": {"queue": "publisher"},
        "srbg.publication.projections": {"queue": "publisher"},
        "srbg.intelligence_v2.review_dispatch": {"queue": "publisher"},
        "srbg.intelligence_v2.review_reprocess": {"queue": "publisher"},
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
    logger.error(
        "personal_task_failed",
        extra={"task_name": name[:120], "task_id": task_id[:80]},
        exc_info=exception,
    )


@celery_app.task(name="srbg.system.health")  # type: ignore[untyped-decorator]
def health() -> dict[str, str]:
    return {"status": "ok", "service": "worker"}


@celery_app.task(name="srbg.ai.runtime_probe_dispatch")  # type: ignore[untyped-decorator]
def dispatch_ai_runtime_probe() -> dict[str, int]:
    callback = celery_app.signature("srbg.ai.runtime_observation", queue="celery")
    celery_app.send_task("srbg.ai.runtime_probe", queue="ai", link=callback)
    return {"dispatched": 1}


@celery_app.task(name="srbg.ai.runtime_observation")  # type: ignore[untyped-decorator]
def record_ai_runtime_observation(result: dict[str, str]) -> dict[str, str]:
    asyncio.run(_record_ai_runtime_observation(result))
    return {"status": "RECORDED"}


async def _record_ai_runtime_observation(result: dict[str, str]) -> None:
    if result.get("status") != "READY":
        raise ValueError("AI_RUNTIME_PROBE_NOT_READY")
    if result.get("environment") != settings.environment:
        raise ValueError("AI_RUNTIME_PROBE_ENVIRONMENT_MISMATCH")
    observed_at = datetime.fromisoformat(result["observed_at"])
    if observed_at.tzinfo is None:
        raise ValueError("AI_RUNTIME_PROBE_TIMEZONE_REQUIRED")
    repository = _ai_repository()
    try:
        await repository.record_runtime_observation(
            provider=result["provider"],
            model="deepseek-v4-flash",
            worker_heartbeat_at=observed_at,
        )
    finally:
        await repository.close()


@celery_app.task(name="srbg.ai.v2_canary_dispatch")  # type: ignore[untyped-decorator]
def dispatch_ai_v2_canary() -> dict[str, object]:
    return asyncio.run(_dispatch_ai_v2_canary())


async def _dispatch_ai_v2_canary() -> dict[str, object]:
    if settings.environment.casefold() not in {"acceptance", "staging", "preproduction"}:
        return {"dispatched": 0, "reason": "AI_CANARY_ENVIRONMENT_NOT_AUTHORIZED"}
    repository = _ai_repository()
    try:
        template = fixed_canary_input("00000000-0000-0000-0000-000000000000")
        created = await repository.create_fixed_canary_run(input_sha256=template.input_sha256)
        if created is None:
            return {"dispatched": 0, "reason": "AI_CANARY_RUNTIME_GATES_DENIED"}
        run_id, document_version_id = created
        prepared = fixed_canary_input(str(document_version_id))
        request = AiContentPreparationService.build_request(AiStep.CLASSIFY, prepared)
        reservation = await repository.reserve(run_id, AiStep.CLASSIFY, 1)
        callback = celery_app.signature(
            "srbg.ai.v2_canary_result",
            kwargs={
                "run_id": str(run_id),
                "document_version_id": str(document_version_id),
                "reservation_id": str(reservation),
            },
            immutable=False,
            queue="celery",
        )
        try:
            celery_app.send_task(
                "srbg.ai.generate_attempt",
                args=[request.model_dump(mode="json")],
                queue="ai",
                link=callback,
            )
        except Exception:
            await repository.release(reservation)
            await repository.complete_fixed_canary(
                run_id=run_id,
                succeeded=False,
                failure_code="AI_CANARY_DISPATCH_FAILED",
            )
            raise
        return {"dispatched": 1, "run_id": str(run_id)}
    finally:
        await repository.close()


@celery_app.task(name="srbg.ai.v2_canary_result")  # type: ignore[untyped-decorator]
def record_ai_v2_canary_result(
    result: dict[str, object],
    *,
    run_id: str,
    document_version_id: str,
    reservation_id: str,
    attempt: int = 1,
    kind: str = AttemptKind.PRIMARY.value,
    campaign_id: str | None = None,
) -> dict[str, str]:
    return asyncio.run(
        _record_ai_v2_canary_result(
            result,
            run_id=UUID(run_id),
            document_version_id=UUID(document_version_id),
            reservation_id=UUID(reservation_id),
            attempt=attempt,
            kind=AttemptKind(kind),
            campaign_id=None if campaign_id is None else UUID(campaign_id),
        )
    )


async def _record_ai_v2_canary_result(
    result: dict[str, object],
    *,
    run_id: UUID,
    document_version_id: UUID,
    reservation_id: UUID,
    attempt: int = 1,
    kind: AttemptKind = AttemptKind.PRIMARY,
    campaign_id: UUID | None = None,
) -> dict[str, str]:
    repository = _ai_repository()
    prepared = fixed_canary_input(str(document_version_id))
    request = AiContentPreparationService.build_request(AiStep.CLASSIFY, prepared)
    try:
        if result.get("status") == "SUCCEEDED" and result.get("runtime_provider") == "deepseek":
            try:
                response = ModelResponse.model_validate(result.get("response"))
                validated = validate_step_output(response.output, request)
            except (ModelOutputRejected, ValueError) as error:
                await repository.settle(reservation_id, None)
                code = _safe_ai_error_code(error)
                await repository.append_failed_step(
                    run_id,
                    AiStep.CLASSIFY,
                    attempt,
                    kind.value,
                    code,
                    request.input_sha256,
                )
                await repository.complete_fixed_canary(
                    run_id=run_id,
                    succeeded=False,
                    failure_code=code,
                )
                await repository.complete_compensation(run_id=run_id, succeeded=False)
                return {"run_id": str(run_id), "status": "FAILED"}
            response = response.model_copy(
                update={"output": validated.model_dump(mode="json", exclude_none=True)}
            )
            await repository.settle(reservation_id, response)
            await repository.append_step(
                run_id,
                AiStep.CLASSIFY,
                attempt,
                kind.value,
                response,
                request.input_sha256,
            )
            await repository.complete_fixed_canary(run_id=run_id, succeeded=True)
            await repository.complete_compensation(run_id=run_id, succeeded=True)
            if campaign_id is not None:
                await repository.append_campaign_event(
                    campaign_id=campaign_id,
                    event_type="FAULT_TRANSIENT_RECOVERED",
                    payload={
                        "run_id": str(run_id),
                        "publication_isolated": True,
                        "document_version_id": str(document_version_id),
                    },
                )
            return {"run_id": str(run_id), "status": "SUCCEEDED"}
        await repository.settle(reservation_id, None)
        code = str(
            result.get("error_code")
            or (
                "AI_CANARY_PROVIDER_MISMATCH"
                if result.get("status") == "SUCCEEDED"
                else "AI_CANARY_FAILED"
            )
        )[:80]
        await repository.append_failed_step(
            run_id,
            AiStep.CLASSIFY,
            attempt,
            kind.value,
            code,
            request.input_sha256,
        )
        if code == "PROVIDER_BALANCE_INSUFFICIENT":
            await repository.record_balance_insufficient(
                provider="deepseek",
                model="deepseek-v4-flash",
            )
        await repository.complete_fixed_canary(
            run_id=run_id,
            succeeded=False,
            failure_code=code,
        )
        await repository.complete_compensation(run_id=run_id, succeeded=False)
        return {"run_id": str(run_id), "status": "FAILED"}
    finally:
        await repository.close()


@celery_app.task(name="srbg.ai.v2_campaign_fault_injection")  # type: ignore[untyped-decorator]
def run_v2_campaign_fault_injection(*, campaign_id: str, fault_kind: str) -> dict[str, object]:
    return asyncio.run(_run_v2_campaign_fault_injection(UUID(campaign_id), fault_kind=fault_kind))


async def _run_v2_campaign_fault_injection(
    campaign_id: UUID, *, fault_kind: str
) -> dict[str, object]:
    if settings.environment.casefold() != "acceptance":
        return {"dispatched": 0, "reason": "FAULT_INJECTION_ENVIRONMENT_DENIED"}
    if fault_kind not in {"TRANSIENT", "PERMANENT"}:
        raise ValueError("FAULT_INJECTION_KIND_INVALID")
    repository = _ai_repository()
    try:
        template = fixed_canary_input("00000000-0000-0000-0000-000000000000")
        created = await repository.create_fixed_canary_run(input_sha256=template.input_sha256)
        if created is None:
            return {"dispatched": 0, "reason": "FAULT_INJECTION_RUNTIME_GATES_DENIED"}
        run_id, document_version_id = created
        prepared = fixed_canary_input(str(document_version_id))
        request = AiContentPreparationService.build_request(AiStep.CLASSIFY, prepared)
        if fault_kind == "PERMANENT":
            await repository.complete_fixed_canary(
                run_id=run_id,
                succeeded=False,
                failure_code="SCHEMA_REJECTED",
            )
            await repository.append_campaign_event(
                campaign_id=campaign_id,
                event_type="FAULT_PERMANENT_INJECTED",
                payload={
                    "run_id": str(run_id),
                    "error_code": "SCHEMA_REJECTED",
                    "synthetic_fault": True,
                },
            )
            await repository.append_campaign_event(
                campaign_id=campaign_id,
                event_type="FAULT_PERMANENT_OBSERVED",
                payload={
                    "run_id": str(run_id),
                    "automatic_retry": False,
                    "publication_isolated": True,
                },
            )
            return {"dispatched": 1, "fault_kind": fault_kind, "run_id": str(run_id)}
        delay = await repository.schedule_compensation(
            run_id=run_id,
            reason_code="PROVIDER_TIMEOUT",
            attempt_count=0,
        )
        if delay is None:
            await repository.complete_fixed_canary(
                run_id=run_id,
                succeeded=False,
                failure_code="FAULT_COMPENSATION_SCHEDULE_DENIED",
            )
            return {"dispatched": 0, "reason": "FAULT_COMPENSATION_SCHEDULE_DENIED"}
        await repository.append_campaign_event(
            campaign_id=campaign_id,
            event_type="FAULT_TRANSIENT_INJECTED",
            payload={
                "run_id": str(run_id),
                "error_code": "PROVIDER_TIMEOUT",
                "synthetic_fault": True,
                "retry_delay_seconds": delay,
            },
        )
        reservation = await repository.reserve(run_id, AiStep.CLASSIFY, 2)
        callback = celery_app.signature(
            "srbg.ai.v2_canary_result",
            kwargs={
                "run_id": str(run_id),
                "document_version_id": str(document_version_id),
                "reservation_id": str(reservation),
                "attempt": 2,
                "kind": AttemptKind.NETWORK_RETRY.value,
                "campaign_id": str(campaign_id),
            },
            immutable=False,
            queue="celery",
        )
        try:
            celery_app.send_task(
                "srbg.ai.generate_attempt",
                args=[request.model_dump(mode="json")],
                queue="ai",
                link=callback,
                countdown=delay,
            )
        except Exception:
            await repository.release(reservation)
            await repository.complete_compensation(run_id=run_id, succeeded=False)
            await repository.complete_fixed_canary(
                run_id=run_id,
                succeeded=False,
                failure_code="FAULT_RETRY_DISPATCH_FAILED",
            )
            raise
        return {"dispatched": 1, "fault_kind": fault_kind, "run_id": str(run_id)}
    finally:
        await repository.close()


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
    return asyncio.run(_drain_source_content_outbox(None if outbox_id is None else UUID(outbox_id)))


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
    semantic_recheck: bool = False,
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
            semantic_recheck=semantic_recheck,
        )
    )


@celery_app.task(name="srbg.personal_source.probe")  # type: ignore[untyped-decorator]
def execute_personal_source_probe(*, probe_run_id: str | None = None) -> dict[str, object]:
    return asyncio.run(
        _dispatch_or_execute_personal_source_probe(
            None if probe_run_id is None else UUID(probe_run_id)
        )
    )


@celery_app.task(name="srbg.source_profile.run")  # type: ignore[untyped-decorator]
def execute_source_profile(*, profile_run_id: str | None = None) -> dict[str, object]:
    return asyncio.run(
        _dispatch_or_start_source_profile(None if profile_run_id is None else UUID(profile_run_id))
    )


@celery_app.task(name="srbg.source_profile.result")  # type: ignore[untyped-decorator]
def handle_source_profile_result(
    result: dict[str, object],
    *,
    prepared_payload: dict[str, object],
    attempt: int,
    kind: str,
    network_retries: int,
    repair_used: bool,
    reservation_id: str,
) -> dict[str, object]:
    return asyncio.run(
        _handle_source_profile_result(
            result=result,
            prepared=_deserialize_prepared_profile(prepared_payload),
            attempt=attempt,
            kind=AttemptKind(kind),
            network_retries=network_retries,
            repair_used=repair_used,
            reservation_id=UUID(reservation_id),
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


@celery_app.task(name="srbg.sources.discovery.personal_cycle")  # type: ignore[untyped-decorator]
def execute_personal_source_discovery_cycle(*, discovery_run_id: str) -> dict[str, object]:
    return asyncio.run(_execute_personal_source_discovery_cycle(UUID(discovery_run_id)))


def _dispatch_automated_source_discovery() -> dict[str, object]:
    if not settings.source_discovery_enabled:
        return {"disabled": True, "dispatched": 0, "discovery_run_id": None}
    discovery_run_id = uuid7()
    celery_app.send_task(
        "srbg.sources.discovery.personal_cycle",
        kwargs={"discovery_run_id": str(discovery_run_id)},
        queue="discovery",
    )
    return {
        "disabled": False,
        "dispatched": 1,
        "discovery_run_id": str(discovery_run_id),
    }


async def _execute_personal_source_discovery_cycle(discovery_run_id: UUID) -> dict[str, object]:
    engine = create_database_engine(settings)
    auto_enable_gateway = PostgresAutoEnableGateway(engine)
    try:
        if not await auto_enable_gateway.discovery_enabled():
            return {"disabled": True, "considered": 0, "enabled": 0, "deferred": 0}
        now = datetime.now(UTC)
        existing = await queue_existing_source_scoring(engine, now=now)
        occurrence_tracker = PostgresPersonalOccurrenceTracker(engine)
        discovery_gateway = PostgresPersonalDiscoveryGateway(engine)
        object_store = S3ObjectStore(settings)
        discovered = 0
        probed = 0
        free_adapters: tuple[tuple[str, PublicDiscoveryChannel, str], ...] = (
            ("PERSONAL_RSS", "RSS", "RSS_ATOM"),
            ("PERSONAL_SITEMAP", "SITEMAP", "SITEMAP"),
            ("PERSONAL_OUTBOUND", "OUTBOUND_LINK", "LIST_DETAIL"),
        )
        for adapter_code, channel, stream_type in free_adapters:
            discovery = await PublicSeedDiscoveryExecutor(
                enabled=True,
                adapter=PostgresSavedEvidenceAdapter(
                    engine,
                    object_store,
                    adapter_code=adapter_code,
                    channel=channel,
                    stream_type=stream_type,
                ),
                probe=SafeDiscoveryTargetProbe(settings),
                gateway=discovery_gateway,
                occurrence_tracker=occurrence_tracker,
                max_candidates_per_run=50,
            ).run(discovery_run_id=uuid7(), now=now)
            discovered += discovery.targets_seen
            probed += discovery.targets_probed
            PERSONAL_DISCOVERY_RESULTS.labels(channel, "SEEN").inc(discovery.targets_seen)
            PERSONAL_DISCOVERY_RESULTS.labels(channel, "PROBED").inc(discovery.targets_probed)
        outcome = await PersonalAutoEnableExecutor(auto_enable_gateway).run(now=now)
        PERSONAL_AUTO_ENABLE_RESULTS.labels("ENABLED").inc(outcome.enabled)
        PERSONAL_AUTO_ENABLE_RESULTS.labels("DEFERRED").inc(outcome.deferred)
        baidu_dispatched = 0
        if (
            settings.baidu_search_enabled
            and settings.baidu_search_api_key is not None
            and settings.baidu_search_api_key.get_secret_value()
        ):
            for query_code in sorted(QUERY_CATALOG):
                celery_app.send_task(
                    "srbg.sources.discovery.query",
                    kwargs={
                        "query_code": query_code,
                        "discovery_run_id": str(discovery_run_id),
                    },
                    queue="discovery",
                )
                baidu_dispatched += 1
        return {
            "disabled": False,
            "discovered": discovered,
            "probed": probed,
            "existing_profiles": existing["profiles"],
            "existing_probes": existing["probes"],
            "considered": outcome.considered,
            "enabled": outcome.enabled,
            "deferred": outcome.deferred,
            "baidu_dispatched": baidu_dispatched,
        }
    finally:
        await engine.dispose()


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
    gateway = PostgresPersonalDiscoveryGateway(engine)
    occurrence_tracker = PostgresPersonalOccurrenceTracker(engine)
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
            occurrence_tracker=occurrence_tracker,
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
        if binding.controlled_run_id is None:
            return LiveRuntimeTransport(
                binding,
                before_request=lambda url: gateway.reserve_request(binding, url=url),
                after_response=lambda url, response_bytes: gateway.record_response_bytes(
                    binding, url=url, response_bytes=response_bytes
                ),
            )
        return LiveRuntimeTransport(
            binding,
            before_request=lambda url: gateway.reserve_request(binding, url=url),
            after_response=lambda url, response_bytes: gateway.record_response_bytes(
                binding, url=url, response_bytes=response_bytes
            ),
            attempt_observer=(
                ControlledRunAttemptObserver(
                    gateway.engine,
                    run_id=binding.controlled_run_id,
                    source_id=binding.source_id,
                    purpose="FETCH",
                )
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
        local_fact_count = 0
        scan = PromptInjectionScanner().scan(extract_input.text)
        await repository.record_security(document, scan.detected)
        if scan.detected:
            await repository.materialize_judgment(
                document,
                None,
                None,
                AiJudgmentResultType.AI_PROCESSING_FAILED.value,
                ("PROMPT_INJECTION_RISK",),
            )
            await repository.fail(run_id, "DEGRADED", "PROMPT_INJECTION_R4")
            return {"run_id": str(run_id), "status": "DEGRADED"}
        await repository.transition(run_id, "CLASSIFYING")
        policy = production_policy_for(document)
        deterministic_trace = try_deterministic_adjudication(
            document=document, prepared=classify_input, policy=policy
        )
        if deterministic_trace is not None:
            if document.run_mode == "SHADOW":
                await repository.append_shadow_decision(deterministic_trace, policy)
            else:
                await repository.append_automated_decision(deterministic_trace, policy)
            await repository.transition(run_id, "SUCCEEDED")
            return {
                "run_id": str(run_id),
                "status": "SUCCEEDED",
                "disposition": deterministic_trace.disposition.value,
                "local_fact_count": local_fact_count,
            }
        await _dispatch_ai_attempt(
            repository,
            run_id=run_id,
            step=AiStep.CLASSIFY,
            prepared=classify_input,
            attempt=1,
            kind=AttemptKind.PRIMARY,
            network_retries=0,
            repair_used=False,
            policy=policy,
        )
        return {
            "run_id": str(run_id),
            "status": "CLASSIFYING",
            "local_fact_count": local_fact_count,
        }
    except Exception as error:
        code = _safe_ai_error_code(error)
        if code in {"MODEL_DISABLED", "PROVIDER_BALANCE_INSUFFICIENT"}:
            await repository.fail(run_id, "DEGRADED", code)
            return {"run_id": str(run_id), "status": "DEGRADED", "failure_code": code}
        await repository.fail(run_id, "FAILED", code)
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
    semantic_recheck: bool = False,
) -> dict[str, object]:
    repository = _ai_repository()
    try:
        try:
            document = await repository.begin(run_id)
        except RuntimeError as error:
            if str(error) != "AI01_SHADOW_AUTHORITY_INVALID":
                raise
            return await _terminalize_unauthorized_ai_callback(
                repository=repository,
                result=result,
                run_id=run_id,
                step=step,
                attempt=attempt,
                kind=kind,
                reservation_id=reservation_id,
            )
        if not await repository.authorize_real_run(document):
            return await _terminalize_unauthorized_ai_callback(
                repository=repository,
                result=result,
                run_id=run_id,
                step=step,
                attempt=attempt,
                kind=kind,
                reservation_id=reservation_id,
            )
        classify_input, extract_input = _prepare_ai_inputs_for_document(document)
        if step is AiStep.SUMMARIZE:
            request = await repository.prepare_t06_content_summary(
                document, append_processing=False
            )
            prepared = PreparedDocumentInput(
                text=request.user_prompt,
                input_sha256=request.input_sha256,
                anchors={},
                block_ids=(),
            )
        else:
            prepared = await _prepared_for_step(
                repository,
                document=document,
                run_id=run_id,
                step=step,
                classify_input=classify_input,
                extract_input=extract_input,
            )
            policy = production_policy_for(document)
            request = AiContentPreparationService.build_request(
                step,
                prepared,
                policy=policy if step is AiStep.CLASSIFY else None,
            )
        if result.get("status") == "SUCCEEDED":
            runtime_provider = str(result.get("runtime_provider") or "")
            runtime_model = str(result.get("runtime_model") or "")
            if runtime_provider != "deepseek" or runtime_model != "deepseek-v4-flash":
                raise RuntimeError("RUNTIME_PROVIDER_CONFIG_MISMATCH")
            response = ModelResponse.model_validate(result.get("response"))
            validated = (
                validate_content_summary_output(response.output, request=request)
                if step is AiStep.SUMMARIZE
                else validate_step_output(response.output, request)
            )
            response = response.model_copy(
                update={"output": validated.model_dump(mode="json", exclude_none=True)}
            )
            if not await repository.authorize_model_call(run_id):
                unauthorized = await _terminalize_unauthorized_ai_callback(
                    repository=repository,
                    result=result,
                    run_id=run_id,
                    step=step,
                    attempt=attempt,
                    kind=kind,
                    reservation_id=reservation_id,
                )
                return {key: str(value) for key, value in unauthorized.items()}
            await repository.settle(reservation_id, response)
            step_run_id = await repository.append_step(
                run_id,
                step,
                attempt,
                kind.value,
                response,
                request.input_sha256,
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
            )
            await repository.complete_compensation(run_id=run_id, succeeded=True)
            if step is AiStep.CLASSIFY:
                classification = AutonomousClassificationCandidate.model_validate(response.output)
                classification_candidates: list[dict[str, object]] = []
                if semantic_recheck:
                    classification_candidates.append(
                        await repository.successful_output_before_attempt(
                            run_id, AiStep.CLASSIFY, attempt=attempt
                        )
                    )
                classification_candidates.append(classification.model_dump(mode="json"))
                policy = production_policy_for(document)
                try:
                    trace = adjudicate_candidates(
                        document=document,
                        prepared=classify_input,
                        policy=policy,
                        candidates=classification_candidates,
                    )
                except SemanticRecheckRequired:
                    await _dispatch_ai_attempt(
                        repository,
                        run_id=run_id,
                        step=AiStep.CLASSIFY,
                        prepared=classify_input,
                        attempt=attempt + 1,
                        kind=AttemptKind.PRIMARY,
                        network_retries=0,
                        repair_used=False,
                        policy=policy,
                        semantic_recheck=True,
                    )
                    return {
                        "run_id": str(run_id),
                        "status": "CLASSIFYING",
                        "semantic_recheck_count": 1,
                    }
                if document.run_mode == "SHADOW":
                    await repository.append_shadow_decision(trace, policy)
                else:
                    await repository.append_automated_decision(trace, policy)
                INTELLIGENCE_QUALIFICATION_DECISIONS.labels(
                    outcome=trace.disposition.value,
                    reason=trace.reason_codes[0].value,
                ).inc()
                if document.run_mode != "LIVE":
                    await repository.transition(run_id, "SUCCEEDED")
                    return {
                        "run_id": str(run_id),
                        "status": "SUCCEEDED",
                        "disposition": trace.disposition.value,
                        "projection_eligible": False,
                    }
                if trace.disposition is not AutomatedDisposition.AUTO_ACCEPTED:
                    await repository.transition(run_id, "SUCCEEDED")
                    return {
                        "run_id": str(run_id),
                        "status": "SUCCEEDED",
                        "disposition": trace.disposition.value,
                    }
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
            if step is AiStep.EXTRACT:
                classification_payload = await repository.successful_output(run_id, AiStep.CLASSIFY)
                await repository.transition(run_id, "EVIDENCE_GATING")
                candidates = await repository.materialize(
                    document,
                    classification_payload,
                    response.output,
                )
                if candidates < 1:
                    raise RuntimeError("NO_VALID_CANDIDATES")
                summary_request = await repository.prepare_t06_content_summary(
                    document, append_processing=True
                )
                await repository.transition(run_id, "SUMMARIZING")
                await _dispatch_ai_attempt(
                    repository,
                    run_id=run_id,
                    step=AiStep.SUMMARIZE,
                    prepared=extract_input,
                    attempt=1,
                    kind=AttemptKind.PRIMARY,
                    network_retries=0,
                    repair_used=False,
                    request_override=summary_request,
                )
                return {"run_id": str(run_id), "status": "SUMMARIZING"}
            if step is AiStep.SUMMARIZE:
                await repository.record_approved_content_success(
                    document,
                    step_run_id=step_run_id,
                    provider=runtime_provider,
                    model=runtime_model,
                    request=request,
                )
                candidate_id = await repository.materialize_t06_content_summary(
                    document,
                    request=request,
                    summary=validated,
                )
                await repository.append_summary_state(
                    document,
                    status="SUCCEEDED",
                    reason_code="SCHEMA_VALID_APPROVED_CONTENT",
                    candidate_id=candidate_id,
                )
                await repository.transition(run_id, "SUCCEEDED")
                return {
                    "run_id": str(run_id),
                    "status": "SUCCEEDED",
                    "candidate_id": str(candidate_id),
                }
            raise RuntimeError("UNEXPECTED_AI_STEP")

        await repository.settle(reservation_id, None)
        code = str(result.get("error_code") or "MODEL_ATTEMPT_FAILED")[:80]
        if code == "PROVIDER_BALANCE_INSUFFICIENT":
            await repository.record_balance_insufficient(
                provider="deepseek",
                model="deepseek-v4-flash",
            )
        await repository.append_failed_step(
            run_id,
            step,
            attempt,
            kind.value,
            code,
            request.input_sha256,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
        )
        retryable = result.get("retryable") is True
        repairable = result.get("repairable") is True
        if retryable and network_retries < 3:
            delay = await repository.schedule_compensation(
                run_id=run_id,
                reason_code=code,
                attempt_count=network_retries,
            )
            if delay is not None:
                if step is AiStep.SUMMARIZE:
                    await repository.append_summary_state(
                        document,
                        status="TEMPORARILY_UNAVAILABLE",
                        reason_code=code,
                    )
                await _dispatch_ai_attempt(
                    repository,
                    run_id=run_id,
                    step=step,
                    prepared=prepared,
                    attempt=attempt + 1,
                    kind=AttemptKind.NETWORK_RETRY,
                    network_retries=network_retries + 1,
                    repair_used=repair_used,
                    countdown_seconds=delay,
                    request_override=request,
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
                request_override=request,
            )
            return {"run_id": str(run_id), "status": "REPAIRING"}
        failure_status = "FAILED" if step is AiStep.CLASSIFY else "DEGRADED"
        if step in {AiStep.SUMMARIZE, AiStep.VERIFY}:
            await repository.append_summary_state(
                document,
                status=summary_state_for_failure(code, retry_scheduled=False),
                reason_code=code,
            )
        await repository.fail(run_id, failure_status, code)
        if retryable:
            await repository.complete_compensation(run_id=run_id, succeeded=False)
        return {"run_id": str(run_id), "status": failure_status}
    except (ModelOutputRejected, ValueError) as error:
        await repository.settle(reservation_id, None)
        code = _safe_ai_error_code(error)
        await repository.append_failed_step(
            run_id,
            step,
            attempt,
            kind.value,
            code,
            request.input_sha256,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
        )
        if not repair_used and step is not AiStep.SUMMARIZE:
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
                request_override=request,
            )
            return {"run_id": str(run_id), "status": "REPAIRING"}
        failure_status = "FAILED" if step is AiStep.CLASSIFY else "DEGRADED"
        if step in {AiStep.SUMMARIZE, AiStep.VERIFY}:
            await repository.append_summary_state(
                document,
                status=summary_state_for_failure(code, retry_scheduled=False),
                reason_code=code,
            )
        await repository.fail(run_id, failure_status, code)
        return {"run_id": str(run_id), "status": failure_status}
    except Exception as error:
        failure_status = "FAILED" if step is AiStep.CLASSIFY else "DEGRADED"
        await repository.fail(run_id, failure_status, _safe_ai_error_code(error))
        raise
    finally:
        await repository.close()


async def _terminalize_unauthorized_ai_callback(
    *,
    repository: PostgresAiPreparationRepository,
    result: dict[str, object],
    run_id: UUID,
    step: AiStep,
    attempt: int,
    kind: AttemptKind,
    reservation_id: UUID,
) -> dict[str, object]:
    """Settle verifiable billing without reading or retaining revoked model content."""

    billable_response: ModelResponse | None = None
    if result.get("status") == "SUCCEEDED":
        try:
            billable_response = ModelResponse.model_validate(result.get("response"))
        except ValueError:
            billable_response = None
    await repository.settle(reservation_id, billable_response)
    await repository.append_failed_step(
        run_id,
        step,
        attempt,
        kind.value,
        "AI_RUNTIME_AUTHORIZATION_DENIED",
        None,
        billing_response=billable_response,
    )
    await repository.fail(run_id, "FAILED", "AI_RUNTIME_AUTHORIZATION_DENIED")
    return {
        "run_id": str(run_id),
        "status": "FAILED",
        "failure_code": "AI_RUNTIME_AUTHORIZATION_DENIED",
    }


async def _prepare_ai_inputs(
    repository: PostgresAiPreparationRepository,
    run_id: UUID,
    *,
    authorize: bool = True,
) -> tuple[PreparationDocument, PreparedDocumentInput, PreparedDocumentInput]:
    document = await repository.begin(run_id)
    if authorize and not await repository.authorize_real_run(document):
        await repository.fail(run_id, "FAILED", "AI_RUNTIME_AUTHORIZATION_DENIED")
        raise PermissionError("AI_RUNTIME_AUTHORIZATION_DENIED")
    classify_input, extract_input = _prepare_ai_inputs_for_document(document)
    return document, classify_input, extract_input


def _prepare_ai_inputs_for_document(
    document: PreparationDocument,
) -> tuple[PreparedDocumentInput, PreparedDocumentInput]:
    return (
        prepare_document_input(
            document_version_id=str(document.document_version_id),
            title=document.title,
            source_name=document.source_name,
            blocks=list(document.blocks),
            max_characters=32_000,
        ),
        prepare_document_input(
            document_version_id=str(document.document_version_id),
            title=document.title,
            source_name=document.source_name,
            blocks=list(document.blocks),
            max_characters=128_000,
        ),
    )


async def _prepared_for_step(
    repository: PostgresAiPreparationRepository,
    *,
    document: PreparationDocument,
    run_id: UUID,
    step: AiStep,
    classify_input: PreparedDocumentInput,
    extract_input: PreparedDocumentInput,
) -> PreparedDocumentInput:
    if step is AiStep.CLASSIFY:
        return classify_input
    if step is AiStep.EXTRACT:
        return extract_input
    facts = await repository.load_judgment_facts(document)
    if step is AiStep.SUMMARIZE:
        return AiContentPreparationService.prepare_summarize_input(facts)
    summary = SummarizeOutput.model_validate(
        await repository.successful_output(run_id, AiStep.SUMMARIZE)
    )
    return AiContentPreparationService.prepare_verify_input(facts, summary)


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
    countdown_seconds: int = 0,
    request_override: ModelRequest | None = None,
    policy: QualificationPolicyBundle | None = None,
    semantic_recheck: bool = False,
) -> None:
    request = request_override or AiContentPreparationService.build_request(
        step,
        prepared,
        policy=policy if step is AiStep.CLASSIFY else None,
        semantic_recheck=semantic_recheck,
    )
    if repair_code:
        request = request.model_copy(
            update={
                "user_prompt": request.user_prompt
                + "\n<controlled_repair>Return valid JSON. Error code: "
                + repair_code
                + ".</controlled_repair>"
            }
        )
    if not await repository.authorize_model_call(run_id):
        raise PermissionError("AI_RUNTIME_AUTHORIZATION_DENIED")
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
            "semantic_recheck": semantic_recheck,
        },
        immutable=False,
    )
    try:
        options: dict[str, object] = {}
        if countdown_seconds:
            options["countdown"] = countdown_seconds
        celery_app.send_task(
            "srbg.ai.generate_attempt",
            args=[request.model_dump(mode="json")],
            link=callback,
            **options,
        )
    except Exception:
        await repository.release(reservation)
        raise


def _safe_ai_error_code(error: Exception) -> str:
    value = str(error).strip()
    if value in {
        "AI01_PILOT_SCOPE_DENIED",
        "AI_RUNTIME_AUTHORIZATION_DENIED",
        "MODEL_DISABLED",
        "PROVIDER_BALANCE_INSUFFICIENT",
        "PROMPT_INJECTION_R4",
        "NO_VALID_CANDIDATES",
        "SUMMARY_SCHEMA_REJECTED",
        "RUNTIME_PROVIDER_CONFIG_MISMATCH",
    }:
        return value
    return type(error).__name__.upper()[:80]


async def _dispatch_or_execute_personal_source_probe(
    probe_run_id: UUID | None,
) -> dict[str, object]:
    engine = create_database_engine(settings)
    gateway = PostgresPersonalProbeGateway(engine)
    try:
        if probe_run_id is None:
            pending_ids = await gateway.pending_ids(limit=50)
            PERSONAL_SOURCE_PROBE_QUEUE.set(len(pending_ids))
            for pending_id in pending_ids:
                celery_app.send_task(
                    "srbg.personal_source.probe",
                    kwargs={"probe_run_id": str(pending_id)},
                    queue="personal-source",
                )
            return {"dispatched": len(pending_ids)}
        outcome = await PersonalProbeExecutor(
            gateway=gateway,
            fetcher=SafePersonalProbeFetcher(engine),
            object_store=S3ObjectStore(settings),
        ).run(probe_run_id)
        return {"probe_run_id": str(probe_run_id), "status": outcome}
    finally:
        await engine.dispose()


async def _dispatch_or_start_source_profile(
    profile_run_id: UUID | None,
) -> dict[str, object]:
    gateway = PostgresSourceProfileGateway(create_database_engine(settings))
    try:
        if profile_run_id is None:
            pending = await gateway.pending_ids(limit=100)
            SOURCE_PROFILE_QUEUE.set(len(pending))
            for pending_id in pending:
                celery_app.send_task(
                    "srbg.source_profile.run",
                    kwargs={"profile_run_id": str(pending_id)},
                    queue="personal-source",
                )
            return {"dispatched": len(pending)}
        binding = await gateway.acquire(profile_run_id)
        if binding is None:
            return {"profile_run_id": str(profile_run_id), "status": "DUPLICATE"}
        prepared = await prepare_profile(binding, S3ObjectStore(settings))
        fallback_reason = terminal_profile_fallback_reason(binding.attempt_count)
        if fallback_reason is not None:
            profile = build_source_profile(
                prepared.rule_input,
                model_output=None,
                partial_reason=fallback_reason,
            )
            await gateway.persist_snapshot(
                prepared,
                profile,
                failure_code=fallback_reason,
            )
            SOURCE_PROFILE_RUNS.labels("PARTIAL", fallback_reason).inc()
            return {"profile_run_id": str(profile_run_id), "status": "PARTIAL"}
        try:
            request = build_profile_request(prepared.rule_input.evidence)
        except PermissionError:
            profile = build_source_profile(
                prepared.rule_input,
                model_output=None,
                partial_reason="PROMPT_INJECTION_DETECTED",
            )
            await gateway.persist_snapshot(
                prepared, profile, failure_code="PROMPT_INJECTION_DETECTED"
            )
            SOURCE_PROFILE_RUNS.labels("PARTIAL", "PROMPT_INJECTION_DETECTED").inc()
            return {"profile_run_id": str(profile_run_id), "status": "PARTIAL"}
        dispatched = await _dispatch_source_profile_attempt(
            gateway,
            prepared=prepared,
            request=request,
            attempt=1,
            kind=AttemptKind.PRIMARY,
            network_retries=0,
            repair_used=False,
        )
        if not dispatched:
            await _persist_partial_and_maybe_requeue(gateway, prepared, "BUDGET_DISABLED")
            return {"profile_run_id": str(profile_run_id), "status": "PARTIAL"}
        return {"profile_run_id": str(profile_run_id), "status": "RUNNING"}
    finally:
        await gateway.close()


async def _handle_source_profile_result(
    *,
    result: dict[str, object],
    prepared: PreparedProfile,
    attempt: int,
    kind: AttemptKind,
    network_retries: int,
    repair_used: bool,
    reservation_id: UUID,
) -> dict[str, object]:
    gateway = PostgresSourceProfileGateway(create_database_engine(settings))
    try:
        request = build_profile_request(prepared.rule_input.evidence)
        if kind is AttemptKind.REPAIR:
            request = request.model_copy(
                update={
                    "user_prompt": request.user_prompt
                    + "\n<controlled_repair>Return one valid JSON object only.</controlled_repair>"
                }
            )
        if result.get("status") == "SUCCEEDED":
            response = ModelResponse.model_validate(result.get("response"))
            validated = validate_step_output(response.output, request)
            output = SourceProfileModelOutput.model_validate(validated.model_dump(mode="json"))
            profile = build_source_profile(
                prepared.rule_input, model_output=output, partial_reason=None
            )
            await gateway.settle_budget(reservation_id, response)
            await gateway.record_model_attempt(
                run_id=prepared.binding.run_id,
                attempt=attempt,
                kind=kind.value,
                input_sha256=request.input_sha256,
                response=response,
                error_code=None,
            )
            await gateway.persist_snapshot(prepared, profile)
            SOURCE_PROFILE_MODEL_ATTEMPTS.labels(kind.value, "SUCCEEDED").inc()
            SOURCE_PROFILE_RUNS.labels(profile.status, "NONE").inc()
            return {
                "profile_run_id": str(prepared.binding.run_id),
                "status": profile.status,
            }
        await gateway.settle_budget(reservation_id, None)
        code = str(result.get("error_code") or "MODEL_UNAVAILABLE")[:80]
        await gateway.record_model_attempt(
            run_id=prepared.binding.run_id,
            attempt=attempt,
            kind=kind.value,
            input_sha256=request.input_sha256,
            response=None,
            error_code=code,
        )
        SOURCE_PROFILE_MODEL_ATTEMPTS.labels(kind.value, "FAILED").inc()
        retryable = result.get("retryable") is True
        repairable = result.get("repairable") is True
        next_kind: AttemptKind | None = None
        next_network_retries = network_retries
        next_repair_used = repair_used
        if retryable and network_retries < 2:
            next_kind = AttemptKind.NETWORK_RETRY
            next_network_retries += 1
        elif repairable and not repair_used:
            next_kind = AttemptKind.REPAIR
            next_repair_used = True
        if next_kind is not None:
            dispatched = await _dispatch_source_profile_attempt(
                gateway,
                prepared=prepared,
                request=request,
                attempt=attempt + 1,
                kind=next_kind,
                network_retries=next_network_retries,
                repair_used=next_repair_used,
            )
            if dispatched:
                return {
                    "profile_run_id": str(prepared.binding.run_id),
                    "status": "RETRYING",
                }
            code = "BUDGET_DISABLED"
        await _persist_partial_and_maybe_requeue(gateway, prepared, code)
        return {"profile_run_id": str(prepared.binding.run_id), "status": "PARTIAL"}
    except (ModelOutputRejected, ValueError) as error:
        await gateway.settle_budget(reservation_id, None)
        code = type(error).__name__.upper()[:80]
        await gateway.record_model_attempt(
            run_id=prepared.binding.run_id,
            attempt=attempt,
            kind=kind.value,
            input_sha256=build_profile_request(prepared.rule_input.evidence).input_sha256,
            response=None,
            error_code=code,
        )
        if not repair_used:
            request = build_profile_request(prepared.rule_input.evidence)
            dispatched = await _dispatch_source_profile_attempt(
                gateway,
                prepared=prepared,
                request=request,
                attempt=attempt + 1,
                kind=AttemptKind.REPAIR,
                network_retries=network_retries,
                repair_used=True,
            )
            if dispatched:
                return {
                    "profile_run_id": str(prepared.binding.run_id),
                    "status": "REPAIRING",
                }
        await _persist_partial_and_maybe_requeue(gateway, prepared, code)
        return {"profile_run_id": str(prepared.binding.run_id), "status": "PARTIAL"}
    finally:
        await gateway.close()


async def _dispatch_source_profile_attempt(
    gateway: PostgresSourceProfileGateway,
    *,
    prepared: PreparedProfile,
    request: ModelRequest,
    attempt: int,
    kind: AttemptKind,
    network_retries: int,
    repair_used: bool,
) -> bool:
    reservation = await gateway.reserve_budget(prepared.binding.run_id, attempt)
    if reservation is None:
        return False
    callback = celery_app.signature(
        "srbg.source_profile.result",
        kwargs={
            "prepared_payload": _serialize_prepared_profile(prepared),
            "attempt": attempt,
            "kind": kind.value,
            "network_retries": network_retries,
            "repair_used": repair_used,
            "reservation_id": str(reservation),
        },
        immutable=False,
    )
    try:
        model_request = request
        if kind is AttemptKind.REPAIR:
            model_request = build_profile_request(prepared.rule_input.evidence).model_copy(
                update={
                    "user_prompt": build_profile_request(prepared.rule_input.evidence).user_prompt
                    + "\n<controlled_repair>Return one valid JSON object only.</controlled_repair>"
                }
            )
        celery_app.send_task(
            "srbg.ai.generate_attempt",
            args=[model_request.model_dump(mode="json")],
            link=callback,
        )
        return True
    except Exception:
        await gateway.settle_budget(reservation, None)
        raise


async def _persist_partial_and_maybe_requeue(
    gateway: PostgresSourceProfileGateway,
    prepared: PreparedProfile,
    code: str,
) -> None:
    profile = build_source_profile(prepared.rule_input, model_output=None, partial_reason=code)
    await gateway.persist_snapshot(prepared, profile, failure_code=code)
    SOURCE_PROFILE_RUNS.labels("PARTIAL", code).inc()
    await gateway.requeue(prepared.binding.run_id, failure_code=code)


def _serialize_prepared_profile(prepared: PreparedProfile) -> dict[str, object]:
    return {
        "run_id": str(prepared.binding.run_id),
        "source_id": str(prepared.binding.source_id),
        "origin": prepared.binding.origin,
        "stream_types": list(prepared.binding.stream_types),
        "attempt_count": prepared.binding.attempt_count,
        "input_sha256": prepared.input_sha256,
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "url": item.url,
                "sha256": item.sha256,
                "excerpt": item.excerpt,
            }
            for item in prepared.rule_input.evidence
        ],
    }


def _deserialize_prepared_profile(payload: dict[str, object]) -> PreparedProfile:
    evidence_value = payload.get("evidence")
    if not isinstance(evidence_value, list):
        raise ValueError("profile evidence payload is invalid")
    evidence = tuple(ProfileEvidence(**item) for item in evidence_value if isinstance(item, dict))
    stream_value = payload.get("stream_types")
    if not isinstance(stream_value, list):
        raise ValueError("profile stream payload is invalid")
    attempt_value = payload.get("attempt_count")
    if not isinstance(attempt_value, int) or isinstance(attempt_value, bool):
        raise ValueError("profile attempt payload is invalid")
    binding = ProfileBinding(
        run_id=UUID(str(payload["run_id"])),
        source_id=UUID(str(payload["source_id"])),
        origin=str(payload["origin"]),
        stream_types=tuple(str(item) for item in stream_value),
        captures=(),
        attempt_count=attempt_value,
    )
    rule_input = ProfileRuleInput(binding.origin, binding.stream_types, evidence)
    return PreparedProfile(binding, rule_input, str(payload["input_sha256"]))


@celery_app.task(name="srbg.publication.outbox")  # type: ignore[untyped-decorator]
def publish_version_lifecycle_events() -> dict[str, int]:
    return asyncio.run(_drain_publication_outbox())


@celery_app.task(name="srbg.publication.projections")  # type: ignore[untyped-decorator]
def apply_publication_projections() -> dict[str, int]:
    return asyncio.run(_drain_publication_projections())


@celery_app.task(name="srbg.intelligence_v2.review_dispatch")  # type: ignore[untyped-decorator]
def dispatch_v2_review_reprocessing() -> dict[str, int]:
    return asyncio.run(_dispatch_v2_review_reprocessing())


@celery_app.task(name="srbg.intelligence_v2.review_reprocess")  # type: ignore[untyped-decorator]
def reprocess_v2_review(outbox_id: str) -> dict[str, str]:
    asyncio.run(_reprocess_v2_review(UUID(outbox_id)))
    return {"outbox_id": outbox_id, "status": "COMPLETED"}


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
        while processed < 50:
            if await service.process_personal_content_once():
                processed += 1
                continue
            break
        return {"processed": processed}
    finally:
        await service.close()


async def _dispatch_v2_review_reprocessing() -> dict[str, int]:
    engine = create_publication_engine(settings)
    try:
        async with engine.connect() as connection:
            outbox_ids = list(
                (
                    await connection.scalars(
                        text(
                            "SELECT id FROM owner_review_reprocessing_outbox_v2 "
                            "WHERE status IN ('PENDING','FAILED') AND available_at<=:now "
                            "AND attempt_count<3 ORDER BY available_at,id LIMIT 50"
                        ),
                        {"now": datetime.now(UTC)},
                    )
                ).all()
            )
        for outbox_id in outbox_ids:
            celery_app.send_task(
                "srbg.intelligence_v2.review_reprocess",
                kwargs={"outbox_id": str(outbox_id)},
                queue="publisher",
            )
        return {"dispatched": len(outbox_ids)}
    finally:
        await engine.dispose()


async def _reprocess_v2_review(outbox_id: UUID) -> None:
    policy_root = Path("docs/codex-kit/assets/validation")
    service = PublicationService(
        repository=PostgresPublicationRepository(create_publication_engine(settings)),
        gate=PublicationGate.from_files(
            policy_root / "publication_gate.json",
            policy_root / "publication_evaluation.schema.json",
        ),
    )
    try:
        await service.process_v2_review_reprocessing(outbox_id=outbox_id)
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
        while processed < 150 and await service.process_ai_projection_refresh_once():
            processed += 1
        return {"processed": processed}
    finally:
        await cache.aclose()
        await projection_writer.close()
        await service.close()
