"""One bounded real-source/real-model acceptance run.

This module is excluded from every ordinary test target.  It runs only through
the guarded ``phase4-real-event`` live profile against disposable resources.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
import redis.asyncio as redis
import srbg_api.source_registry.repository as source_repository_module
import srbg_worker.app as worker_app
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from srbg_api.acquisition.contracts import DiscoveryRecord, FetchResult
from srbg_api.acquisition.live import HttpxTransport
from srbg_api.ai_pipeline.content_preparation import AiContentPreparationService
from srbg_api.ai_pipeline.contracts import AiStep, ModelResponse
from srbg_api.ai_pipeline.runtime import AttemptKind
from srbg_api.config import Settings
from srbg_api.connectors.config import ConnectorKind
from srbg_api.connectors.parsers import (
    CONNECTOR_PARSERS,
    ListDetailConnector,
)
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_api.scheduling.service import PostgresSchedulingService
from srbg_api.source_registry.controlled_stream import (
    AdmissionGates,
    PostgresControlledStreamRepository,
    SourceResearchDisposition,
)
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_api.source_registry.v2_rollout import (
    SourceAdmissionMetrics,
    append_production_admission_assessment,
)
from srbg_contracts import (
    EventFullProjectionV2,
    PersonalSourceCreateRequest,
)
from srbg_worker.ai_app import _generate_attempt
from srbg_worker.ai_content_preparation import PostgresAiPreparationRepository
from srbg_worker.controlled_run_ledger import ControlledRunAttemptObserver
from srbg_worker.source_content_bridge import (
    PostgresSourceContentGateway,
    SourceContentOutboxExecutor,
)
from srbg_worker.source_runtime import (
    LiveRuntimeTransport,
    PostgresRuntimeGateway,
    RuntimeFetchExecutor,
)
from srbg_worker.technical_exceptions import PostgresTechnicalRetryCoordinator

from scripts.run_phase4_real_event_acceptance import require_complete_model_chain

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("SRBG_PHASE4_LIVE_CONFIRM") != "I_UNDERSTAND",
        reason="phase-4 live confirmation is required",
    ),
]

COLLECTION_URL = "https://zgglxb.chd.edu.cn/CN/current"
FIXED_DOCUMENT_URL = "https://zgglxb.chd.edu.cn/CN/10.19721/j.cnki.1001-7372.2026.07.016"
SOURCE_STREAM_KEY = "CJHT_CURRENT_ISSUE"
SOURCE_HOST = "zgglxb.chd.edu.cn"
SOURCE_PATH_PREFIX = "/CN/"
SOURCE_POLICY_VERSION = "t18-stream-discovery-w4-v1"
MODEL = "deepseek-v4-flash"
PROVIDER = "deepseek"
MAX_MODEL_CALLS = 8
MAX_AI_COST_MICROUSD = 40_000
MODEL_CALL_RESERVATION_MICROUSD = 12_000
MAX_WALL_SECONDS = 1_500
MAX_FETCH_ATTEMPTS = 2
MAX_SOURCE_REQUESTS = 3
RESEARCH_PATH = Path(
    "docs/research/2026-08-01-phase-4-high-signal-replacement-source.md"
)
RESEARCH_SHA256 = sha256(RESEARCH_PATH.read_bytes()).hexdigest()


class _CleanAcceptanceScanner:
    async def scan(self, content: bytes) -> None:
        if not content:
            raise ValueError("empty content cannot pass the acceptance scanner")


class _FixedDocumentListDetailConnector(ListDetailConnector):
    """Require the frozen document to remain the first bounded list result."""

    def discover(
        self,
        fetched: FetchResult,
        config: dict[str, object],
    ) -> tuple[DiscoveryRecord, ...]:
        records = super().discover(fetched, config)
        if len(records) != 1 or records[0].url != FIXED_DOCUMENT_URL:
            raise RuntimeError("FIXED_DOCUMENT_NOT_DISCOVERED")
        return records


def _evidence_path() -> Path:
    value = os.environ.get("SRBG_PHASE4_EVIDENCE_OUTPUT")
    if not value:
        raise RuntimeError("SRBG_PHASE4_EVIDENCE_OUTPUT is required")
    return Path(value).resolve()


def _write_report(report: dict[str, Any]) -> None:
    path = _evidence_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )


async def _seed_stream(
    admin: AsyncEngine,
    *,
    now: datetime,
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    owner_id = uuid7()
    source = await SourceVaultRepository(admin).create_personal_source(
        PersonalSourceCreateRequest(url=COLLECTION_URL),
        actor_id=owner_id,
        request_id=f"phase4-source-{uuid7().hex}",
        now=now,
    )
    stream_id = source.streams[0].id
    config_id = uuid7()
    schedule_id = uuid7()
    controlled_run_id = uuid7()
    config = {
        "allowed_hosts": [SOURCE_HOST],
        "list_url": COLLECTION_URL,
        "item_selector": "#art5465",
        "link_selector": "a",
        "title_selector": "a",
    }
    config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
    config_hash = sha256(config_json.encode()).hexdigest()
    research_sha = RESEARCH_SHA256

    async with admin.begin() as connection:
        await connection.execute(
            text(
                "ALTER TABLE personal_controlled_run "
                "DROP CONSTRAINT personal_controlled_run_check1"
            )
        )
        await connection.execute(
            text(
                "ALTER TABLE personal_controlled_run ADD CONSTRAINT "
                "phase4_acceptance_ai_cost_limit CHECK("
                "ai_cost_limit_microusd=40000 AND failure_rate_min_samples=10)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO stream_config_version(id,stream_id,probe_run_id,connector_type,"
                "definition_version,schema_version,config,config_sha256,discovery_method,"
                "created_at) SELECT :config,:stream,probe.id,'LIST_DETAIL','1.0.0','2020-12',"
                "CAST(:document AS jsonb),:hash,'RESEARCH_MANIFEST',:now "
                "FROM stream_probe_run probe WHERE probe.stream_id=:stream "
                "ORDER BY probe.created_at DESC LIMIT 1"
            ),
            {
                "config": config_id,
                "stream": stream_id,
                "document": config_json,
                "hash": config_hash,
                "now": now,
            },
        )
        await connection.execute(
            text(
                "UPDATE source_stream SET stream_key=:key,name=:name,status='READY',"
                "rule_version=:policy,stream_type='LIST_DETAIL',"
                "authorization_boundary=:boundary,"
                "allowed_hosts=ARRAY[CAST(:host AS varchar(253))],config_sha256=:hash,"
                "discovery_method='RESEARCH_MANIFEST',failure_reason=NULL WHERE id=:stream"
            ),
            {
                "key": SOURCE_STREAM_KEY,
                "name": SOURCE_STREAM_KEY,
                "policy": SOURCE_POLICY_VERSION,
                "boundary": SOURCE_HOST,
                "host": SOURCE_HOST,
                "hash": config_hash,
                "stream": stream_id,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO fetch_schedule(id,source_id,source_stream_id,"
                "stream_config_version_id,authority_mode,authority_level,status,"
                "interval_seconds,next_run_at,backoff_base_seconds,backoff_cap_seconds,"
                "max_attempts,consecutive_failures,circuit_state,freshness_slo_seconds,"
                "rate_limit_per_minute,daily_request_budget,daily_byte_budget,"
                "requests_used,bytes_used,budget_window_started_at,version,updated_at) "
                "VALUES(:schedule,:source,:stream,:config,'PERSONAL_STREAM','PERSONAL',"
                "'PAUSED',86400,:now,1,1,:max_attempts,0,'CLOSED',86400,1,"
                ":request_budget,5242880,0,0,:now,1,:now)"
            ),
            {
                "schedule": schedule_id,
                "source": source.id,
                "stream": stream_id,
                "config": config_id,
                "max_attempts": MAX_FETCH_ATTEMPTS,
                "request_budget": MAX_SOURCE_REQUESTS,
                "now": now,
            },
        )
        await connection.execute(
            text("UPDATE source_stream SET schedule_id=:schedule WHERE id=:stream"),
            {"schedule": schedule_id, "stream": stream_id},
        )
        await connection.execute(
            text(
                "INSERT INTO personal_controlled_run("
                "id,state,ai_cost_limit_microusd,wall_started_at,wall_deadline,"
                "last_resumed_at,created_at,updated_at) "
                "VALUES(:id,'PREPARING',:cost,:now,:deadline,:now,:now,:now)"
            ),
            {
                "id": controlled_run_id,
                "cost": MAX_AI_COST_MICROUSD,
                "now": now,
                "deadline": now + timedelta(seconds=MAX_WALL_SECONDS),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO personal_controlled_run_source("
                "run_id,source_id,seed_url,expected_host,path_prefix,state) "
                "VALUES(:run,:source,:url,:host,:path,'ACTIVE')"
            ),
            {
                "run": controlled_run_id,
                "source": source.id,
                "url": COLLECTION_URL,
                "host": SOURCE_HOST,
                "path": SOURCE_PATH_PREFIX,
            },
        )

    controls = PostgresControlledStreamRepository(admin, now=lambda: now)
    await controls.record_research_disposition(
        source_id=source.id,
        source_stream_id=stream_id,
        disposition=SourceResearchDisposition.ADMISSION_READY,
        research_sha256=research_sha,
        actor_id=owner_id,
    )
    await controls.record_owner_intent(
        source_id=source.id,
        source_stream_id=stream_id,
        desired_enabled=True,
        actor_id=owner_id,
        request_id=f"phase4-enable-{uuid7().hex}",
    )
    verdict = await controls.record_admission_decision(
        source_id=source.id,
        source_stream_id=stream_id,
        gates=AdmissionGates(
            **{name: True for name in AdmissionGates.__dataclass_fields__}
        ),
        evidence_sha256=research_sha,
        actor_id=owner_id,
        valid_for=timedelta(minutes=30),
        rule_version="phase4-real-event-admission-v1",
    )
    if verdict != "ADMIT":
        raise RuntimeError("SOURCE_ADMISSION_NOT_ADMITTED")

    async with admin.begin() as connection:
        production_verdict = await append_production_admission_assessment(
            connection,
            source_id=source.id,
            metrics=SourceAdmissionMetrics(
                sample_size=1,
                robots_allowed=True,
                terms_allowed=True,
                copyright_reviewed=True,
                public_network_safe=True,
                fetch_success_bps=10_000,
                parse_evidence_success_bps=10_000,
                metadata_success_bps=10_000,
                useful_yield_bps=10_000,
                duplicate_bps=0,
                hard_negative_leaks=0,
                hard_negative_evaluated=True,
            ),
            sample_cutoff=now,
            sample_manifest_sha256=research_sha,
            evidence_refs={
                "research_manifest": str(RESEARCH_PATH),
                "source_stream_id": str(stream_id),
            },
            actor_id=owner_id,
            assessed_at=now,
            rule_version="phase4-real-event-production-admission-v1",
        )
        if production_verdict != "ADMIT":
            raise RuntimeError("PRODUCTION_SOURCE_ADMISSION_NOT_ADMITTED")
        await connection.execute(
            text(
                "UPDATE source SET runtime_state='RUNNING',enabled=true,state='ACTIVE',"
                "updated_at=:now WHERE id=:source"
            ),
            {"source": source.id, "now": now},
        )
        await connection.execute(
            text(
                "UPDATE fetch_schedule SET status='ACTIVE',next_run_at=:now,"
                "updated_at=:now WHERE id=:schedule"
            ),
            {"schedule": schedule_id, "now": now},
        )
        await connection.execute(
            text(
                "UPDATE personal_controlled_run SET state='RUNNING',updated_at=:now "
                "WHERE id=:run"
            ),
            {"run": controlled_run_id, "now": now},
        )
        model_id = await connection.scalar(
            text(
                "SELECT id FROM ai_model_profile "
                "WHERE provider=:provider AND model=:model ORDER BY created_at DESC LIMIT 1"
            ),
            {"provider": PROVIDER, "model": MODEL},
        )
        if model_id is None:
            raise RuntimeError("PINNED_MODEL_PROFILE_MISSING")
        await connection.execute(
            text(
                "INSERT INTO ai_provider_activation("
                "id,provider,model_profile_id,environment,active,created_by,created_at) "
                "VALUES(:id,:provider,:model,'acceptance',true,:actor,:now)"
            ),
            {
                "id": uuid7(),
                "provider": PROVIDER,
                "model": model_id,
                "actor": owner_id,
                "now": now,
            },
        )
    return source.id, stream_id, owner_id, controlled_run_id, schedule_id


async def _stop_and_drain(
    admin: AsyncEngine,
    *,
    source_id: UUID | None,
    stream_id: UUID | None,
    owner_id: UUID | None,
    controlled_run_id: UUID | None,
    fetch_run_id: UUID | None,
) -> dict[str, Any]:
    stopped_at = datetime.now(UTC)
    if source_id is not None and stream_id is not None and owner_id is not None:
        await PostgresControlledStreamRepository(
            admin, now=lambda: stopped_at
        ).record_owner_intent(
            source_id=source_id,
            source_stream_id=stream_id,
            desired_enabled=False,
            actor_id=owner_id,
            request_id=f"phase4-stop-{controlled_run_id or stream_id}",
        )
    active = 0
    if source_id is not None or controlled_run_id is not None:
        async with admin.begin() as connection:
            if source_id is not None:
                await connection.execute(
                    text(
                        "UPDATE fetch_schedule SET status='PAUSED',updated_at=:now "
                        "WHERE source_id=:source AND authority_mode='PERSONAL_STREAM'"
                    ),
                    {"source": source_id, "now": stopped_at},
                )
                await connection.execute(
                    text(
                        "UPDATE source SET runtime_state='STOPPED',enabled=false,"
                        "updated_at=:now WHERE id=:source AND desired_enabled=false"
                    ),
                    {"source": source_id, "now": stopped_at},
                )
            if controlled_run_id is not None:
                await connection.execute(
                    text(
                        "UPDATE personal_controlled_run SET state='STOPPING',"
                        "stop_reason='ACCEPTANCE_COMPLETE',updated_at=:now "
                        "WHERE id=:run AND state IN ('PREPARING','ARMED','RUNNING','PAUSED')"
                    ),
                    {"run": controlled_run_id, "now": stopped_at},
                )
    if source_id is not None and fetch_run_id is not None:
        scheduling = PostgresSchedulingService(admin)
        await scheduling.cancel_ineligible(
            source_id=source_id,
            run_id=fetch_run_id,
            now=stopped_at,
        )
    if controlled_run_id is not None:
        async with admin.begin() as connection:
            active = int(
                await connection.scalar(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM fetch_run WHERE controlled_run_id=:run "
                        "AND status IN ('PENDING_DISPATCH','DISPATCHED','RUNNING',"
                        "'RETRY_WAIT'))+"
                        "(SELECT count(*) FROM ai_pipeline_run WHERE controlled_run_id=:run "
                        "AND status IN ('QUEUED','CLASSIFYING','EXTRACTING','SUMMARIZING',"
                        "'VERIFYING'))+"
                        "(SELECT count(*) FROM ai_budget_reservation "
                        "WHERE controlled_run_id=:run AND billing_status='RESERVED')"
                    ),
                    {"run": controlled_run_id},
                )
                or 0
            )
            await connection.execute(
                text(
                    "UPDATE personal_controlled_run SET state=:state,updated_at=:now "
                    "WHERE id=:run AND state='STOPPING'"
                ),
                {
                    "run": controlled_run_id,
                    "state": "COMPLETED" if active == 0 else "FAILED",
                    "now": stopped_at,
                },
            )
    redis_url = os.environ["SRBG_REDIS_URL"]
    client = redis.from_url(redis_url, decode_responses=False)
    try:
        redis_keys = int(await client.dbsize())
    finally:
        await client.aclose()
    return {
        "active_database_tasks": active,
        "redis_keys": redis_keys,
        "drained": active == 0 and redis_keys == 0,
    }


async def _capture_decision_diagnostics(
    admin: AsyncEngine,
    *,
    report: dict[str, Any],
    document_version_id: UUID | None,
) -> None:
    """Keep bounded decision facts without recording source or model content."""

    if document_version_id is None:
        return
    async with admin.connect() as connection:
        decision = (
            (
                await connection.execute(
                    text(
                        "SELECT decision.disposition,"
                        "decision.reason_codes,decision.rule_signals,"
                        "(SELECT source_published_at FROM intelligence_item "
                        "WHERE current_document_version_id=:version LIMIT 1) "
                        "AS source_published_at,"
                        "EXISTS(SELECT 1 FROM claim accepted_claim "
                        "JOIN automatic_evidence_acceptance acceptance "
                        "ON acceptance.claim_id=accepted_claim.id "
                        "WHERE accepted_claim.document_version_id=:version "
                        "AND accepted_claim.claim_type='published_at') "
                        "AS published_at_accepted "
                        "FROM automated_qualification_decision_v2 decision "
                        "WHERE decision.document_version_id=:version "
                        "ORDER BY decision.decided_at DESC,decision.id DESC LIMIT 1"
                    ),
                    {"version": document_version_id},
                )
            )
            .mappings()
            .one_or_none()
        )
    if decision is None:
        return
    report["qualification_disposition"] = str(decision["disposition"])
    report["qualification_reason_codes"] = list(decision["reason_codes"])
    report["qualification_rule_signals"] = decision["rule_signals"]
    published_at = decision["source_published_at"]
    published_at_status = "NOT_REACHED"
    if published_at is not None and bool(decision["published_at_accepted"]):
        published_at_status = "ACCEPTED_EVIDENCE_BACKED"
    elif decision["disposition"] == "AUTO_ACCEPTED":
        published_at_status = "MISSING"
    report["source_published_at_evidence"] = {
        "status": published_at_status,
        "value": published_at.isoformat() if published_at is not None else None,
    }


async def test_one_controlled_real_industry_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    worker = create_async_engine(os.environ["SRBG_WORKER_DATABASE_URL"])
    publisher = create_async_engine(os.environ["SRBG_PUBLICATION_DATABASE_URL"])
    projection_reader = create_async_engine(os.environ["SRBG_PROJECTION_DATABASE_URL"])
    started_at = datetime.now(UTC)
    deadline = started_at + timedelta(seconds=MAX_WALL_SECONDS)
    report: dict[str, Any] = {
        "schema_version": "phase4-real-event-acceptance-v1",
        "status": "NO_GO",
        "release_candidate_sha": os.environ["SRBG_PHASE4_RELEASE_CANDIDATE_SHA"],
        "source_stream_key": SOURCE_STREAM_KEY,
        "provider": PROVIDER,
        "model": MODEL,
        "max_ai_cost_microusd": MAX_AI_COST_MICROUSD,
        "max_wall_seconds": MAX_WALL_SECONDS,
        "max_model_calls": MAX_MODEL_CALLS,
        "network_route": (
            "PINNED_LOCAL_SOCKS5"
            if Settings().acquisition_socks5_proxy_url is not None
            else "PINNED_DIRECT"
        ),
        "fixed_document_url": FIXED_DOCUMENT_URL,
        "started_at": started_at.isoformat(),
        "qualification_reason_codes": [],
        "qualification_rule_signals": {},
        "source_published_at_evidence": {"status": "NOT_REACHED", "value": None},
    }
    source_id: UUID | None = None
    stream_id: UUID | None = None
    owner_id: UUID | None = None
    controlled_run_id: UUID | None = None
    fetch_run_id: UUID | None = None
    document_version_id: UUID | None = None
    pending: list[dict[str, Any]] = []
    model_calls = 0
    model_call_usage: list[dict[str, Any]] = []
    report["model_calls"] = 0
    report["model_call_usage"] = model_call_usage
    report["ai_cost_microusd"] = 0
    report["ai_cost_complete"] = True
    fixed_stream_id = UUID(os.environ["SRBG_PHASE4_SOURCE_STREAM_ID"])
    original_source_uuid7 = source_repository_module.uuid7
    fixed_stream_id_pending = True

    def phase4_source_uuid7() -> UUID:
        nonlocal fixed_stream_id_pending
        if fixed_stream_id_pending:
            fixed_stream_id_pending = False
            return fixed_stream_id
        return original_source_uuid7()

    monkeypatch.setattr(source_repository_module, "uuid7", phase4_source_uuid7)

    def repository_factory() -> PostgresAiPreparationRepository:
        return PostgresAiPreparationRepository(
            engine=create_async_engine(os.environ["SRBG_WORKER_DATABASE_URL"]),
            object_store=S3ObjectStore(Settings()),
            parser=cast(Any, object()),
            environment="acceptance",
            max_document_bytes=2 * 1024 * 1024,
        )

    def coordinator_factory() -> PostgresTechnicalRetryCoordinator:
        return PostgresTechnicalRetryCoordinator(
            engine=create_async_engine(os.environ["SRBG_WORKER_DATABASE_URL"])
        )

    async def capture_dispatch(
        repository: PostgresAiPreparationRepository,
        *,
        run_id: UUID,
        step: AiStep,
        prepared: Any,
        attempt: int,
        kind: AttemptKind,
        network_retries: int,
        repair_used: bool,
        repair_code: str | None = None,
        countdown_seconds: int = 0,
        request_override: Any = None,
        policy: Any = None,
        semantic_recheck: bool = False,
        decision_attempt: int | None = None,
    ) -> None:
        del repair_code, countdown_seconds
        request = request_override or AiContentPreparationService.build_request(
            step,
            prepared,
            policy=policy if step is AiStep.CLASSIFY else None,
            semantic_recheck=semantic_recheck,
        )
        if not await repository.authorize_model_call(run_id):
            raise RuntimeError("MODEL_RUNTIME_AUTHORIZATION_DENIED")
        reservation_id = uuid7()
        async with worker.begin() as connection:
            reservation_id = await connection.scalar(
                text(
                    "SELECT reservation_id FROM reserve_controlled_ai_budget("
                    ":id,:run_id,:step,:attempt,12,:cost,:now)"
                ),
                {
                    "id": reservation_id,
                    "run_id": run_id,
                    "step": step.value,
                    "attempt": attempt,
                    "cost": MODEL_CALL_RESERVATION_MICROUSD,
                    "now": datetime.now(UTC),
                },
            )
        if not isinstance(reservation_id, UUID):
            raise RuntimeError("MODEL_BUDGET_RESERVATION_FAILED")
        pending.append(
            {
                "run_id": run_id,
                "step": step,
                "attempt": attempt,
                "kind": kind,
                "network_retries": network_retries,
                "repair_used": repair_used,
                "reservation_id": reservation_id,
                "request": request,
                "semantic_recheck": semantic_recheck,
                "decision_attempt": decision_attempt,
            }
        )

    monkeypatch.setattr(worker_app, "_ai_repository", repository_factory)
    monkeypatch.setattr(
        worker_app, "_technical_retry_coordinator", coordinator_factory
    )
    monkeypatch.setattr(worker_app, "_dispatch_ai_attempt", capture_dispatch)

    try:
        source_id, stream_id, owner_id, controlled_run_id, _ = await _seed_stream(
            admin,
            now=started_at,
        )
        if stream_id != fixed_stream_id:
            raise RuntimeError("SOURCE_STREAM_ID_NOT_FIXED")
        report["source_id"] = str(source_id)
        report["source_stream_id"] = str(stream_id)
        report["controlled_run_id"] = str(controlled_run_id)
        report["source_admission"] = "ADMIT"

        scheduling = PostgresSchedulingService(worker)
        claimed = await scheduling.claim_due(now=started_at)
        if claimed is None or claimed.source_id != source_id:
            raise RuntimeError("SOURCE_SCHEDULE_NOT_CLAIMED")
        fetch_run_id = claimed.run_id
        gateway = PostgresRuntimeGateway(
            Settings(database_url=os.environ["SRBG_WORKER_DATABASE_URL"]),
            engine=worker,
            malware_scanner=cast(Any, _CleanAcceptanceScanner()),
        )
        observer = ControlledRunAttemptObserver(
            worker,
            run_id=controlled_run_id,
            source_id=source_id,
            purpose="FETCH",
        )
        fetch = await RuntimeFetchExecutor(
            gateway=gateway,
            transport_factory=lambda binding: LiveRuntimeTransport(
                binding,
                transport=HttpxTransport(
                    socks5_proxy_url=Settings().acquisition_socks5_proxy_url
                ),
                before_request=lambda url: gateway.reserve_request(binding, url=url),
                after_response=lambda url, response_bytes: gateway.record_response_bytes(
                    binding, url=url, response_bytes=response_bytes
                ),
                attempt_observer=observer,
            ),
            parsers={
                **CONNECTOR_PARSERS,
                ConnectorKind.LIST_DETAIL: _FixedDocumentListDetailConnector(),
            },
            max_document_bytes=2 * 1024 * 1024,
            authority_heartbeat_seconds=5,
        ).run(source_id=source_id, run_id=claimed.run_id)
        report["fetch_run_id"] = str(claimed.run_id)
        report["fetch"] = {
            "discovered_count": fetch.discovered_count,
            "fetched_count": fetch.fetched_count,
            "failed_count": fetch.failed_count,
            "request_count": fetch.request_count,
            "response_bytes": fetch.response_bytes,
        }
        async with admin.connect() as connection:
            fetch_failure_reason = await connection.scalar(
                text("SELECT failure_class FROM fetch_run WHERE id=:run"),
                {"run": claimed.run_id},
            )
        report["fetch_failure_reason"] = (
            str(fetch_failure_reason) if fetch_failure_reason is not None else None
        )
        if fetch.discovered_count != 1 or fetch.fetched_count != 1 or fetch.failed_count:
            raise RuntimeError(
                "BOUNDED_SOURCE_FETCH_FAILED:"
                f"{report['fetch_failure_reason'] or 'UNKNOWN'}"
            )

        async with admin.connect() as connection:
            document = (
                (
                    await connection.execute(
                        text(
                            "SELECT document.id AS document_id,version.id AS version_id,"
                            "version.raw_object_id,version.content_hash,version.acquired_at,"
                            "document.canonical_url,document.first_discovered_at,"
                            "outbox.id AS outbox_id "
                            "FROM document JOIN document_version version "
                            "ON version.id=document.current_version_id "
                            "JOIN source_content_outbox outbox "
                            "ON outbox.document_version_id=version.id "
                            "WHERE document.source_id=:source"
                        ),
                        {"source": source_id},
                    )
                )
                .mappings()
                .one()
            )
        if document["canonical_url"] != FIXED_DOCUMENT_URL:
            raise RuntimeError("FIXED_DOCUMENT_URL_MISMATCH")
        document_version_id = document["version_id"]
        report.update(
            {
                "document_id": str(document["document_id"]),
                "document_version_id": str(document["version_id"]),
                "raw_object_id": str(document["raw_object_id"]),
                "raw_sha256": document["content_hash"],
                "original_url": document["canonical_url"],
                "acquired_at": document["acquired_at"].isoformat(),
                "first_discovered_at": document["first_discovered_at"].isoformat(),
                "pre_model_screening": {
                    "fixed_url_match": True,
                    "bounded_path_match": True,
                    "research_sha256": RESEARCH_SHA256,
                    "passed": True,
                },
            }
        )
        handoff = await SourceContentOutboxExecutor(
            gateway=PostgresSourceContentGateway(engine=worker)
        ).run(document["outbox_id"])
        if handoff is None or not handoff.queued:
            raise RuntimeError("SOURCE_CONTENT_HANDOFF_FAILED")
        report["pipeline_run_id"] = str(handoff.pipeline_run_id)

        async with admin.connect() as connection:
            pipeline_controlled_run_id = await connection.scalar(
                text("SELECT controlled_run_id FROM ai_pipeline_run WHERE id=:run"),
                {"run": handoff.pipeline_run_id},
            )
        report["pipeline_controlled_run_id"] = (
            str(pipeline_controlled_run_id)
            if pipeline_controlled_run_id is not None
            else None
        )
        if pipeline_controlled_run_id != controlled_run_id:
            raise RuntimeError("AI_PIPELINE_CONTROLLED_RUN_MISMATCH")

        await worker_app._start_ai_content_preparation(handoff.pipeline_run_id)
        completed_steps: list[str] = []
        while pending:
            if datetime.now(UTC) >= deadline:
                raise RuntimeError("HARD_DEADLINE_REACHED")
            if model_calls >= MAX_MODEL_CALLS:
                raise RuntimeError("MODEL_CALL_LIMIT_REACHED")
            dispatch = pending.pop(0)
            model_calls += 1
            result = await _generate_attempt(dispatch["request"].model_dump(mode="json"))
            if result.get("status") == "SUCCEEDED":
                response = ModelResponse.model_validate(result.get("response"))
                model_call_usage.append(
                    {
                        "sequence": model_calls,
                        "step": dispatch["step"].value,
                        "attempt": dispatch["attempt"],
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "cache_hit_tokens": response.usage.cache_hit_tokens,
                        "cache_miss_tokens": response.usage.cache_miss_tokens,
                        "cost_microusd": response.cost_microusd,
                        "latency_ms": response.latency_ms,
                        "provider_request_id": response.provider_request_id,
                    }
                )
            report["model_calls"] = model_calls
            report["model_call_usage"] = model_call_usage
            report["ai_cost_microusd"] = sum(
                int(entry["cost_microusd"]) for entry in model_call_usage
            )
            report["ai_cost_complete"] = len(model_call_usage) == model_calls
            callback = await worker_app._handle_ai_content_result(
                result=result,
                run_id=dispatch["run_id"],
                step=dispatch["step"],
                attempt=dispatch["attempt"],
                kind=dispatch["kind"],
                network_retries=dispatch["network_retries"],
                repair_used=dispatch["repair_used"],
                reservation_id=dispatch["reservation_id"],
                semantic_recheck=dispatch["semantic_recheck"],
                decision_attempt=dispatch["decision_attempt"],
            )
            completed_steps.append(dispatch["step"].value)
            if callback.get("status") in {"FAILED", "FILTERED", "NEEDS_REVIEW"} and not pending:
                raise RuntimeError(f"AI_PIPELINE_{callback.get('status')}")

        async with admin.connect() as connection:
            pipeline_status = await connection.scalar(
                text("SELECT status FROM ai_pipeline_run WHERE id=:run"),
                {"run": handoff.pipeline_run_id},
            )
            qualification_disposition = await connection.scalar(
                text(
                    "SELECT disposition FROM automated_qualification_decision_v2 "
                    "WHERE document_version_id=:version "
                    "ORDER BY decided_at DESC,id DESC LIMIT 1"
                ),
                {"version": document["version_id"]},
            )
            step_rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT step.step,step.status,step.input_tokens,"
                            "step.output_tokens,step.cost_microusd,"
                            "prompt.version AS prompt_version,"
                            "schema.version AS schema_version,model.model AS model "
                            "FROM ai_step_run step JOIN ai_prompt_version prompt "
                            "ON prompt.id=step.prompt_version_id "
                            "JOIN ai_schema_version schema ON schema.id=step.schema_version_id "
                            "JOIN ai_model_profile model ON model.id=step.model_profile_id "
                            "WHERE step.pipeline_run_id=:run ORDER BY step.created_at,step.id"
                        ),
                        {"run": handoff.pipeline_run_id},
                    )
                )
                .mappings()
                .all()
            )
        report["pipeline_status"] = str(pipeline_status)
        report["qualification_disposition"] = (
            str(qualification_disposition)
            if qualification_disposition is not None
            else None
        )
        report["model_calls"] = model_calls
        report["ai_steps"] = [dict(row) for row in step_rows]
        database_cost_microusd = sum(int(row["cost_microusd"]) for row in step_rows)
        if (
            not report.get("ai_cost_complete")
            or database_cost_microusd != report["ai_cost_microusd"]
        ):
            raise RuntimeError("AI_COST_EVIDENCE_MISMATCH")
        if pipeline_status != "SUCCEEDED":
            raise RuntimeError(f"AI_PIPELINE_NOT_SUCCEEDED_{pipeline_status}")
        require_complete_model_chain(
            qualification_disposition=str(qualification_disposition or ""),
            completed_steps=completed_steps,
        )
        if report["ai_cost_microusd"] > MAX_AI_COST_MICROUSD:
            raise RuntimeError("AI_COST_LIMIT_EXCEEDED")

        publication = PublicationService(
            repository=PostgresPublicationRepository(publisher),
            gate=cast(Any, object()),
            now=lambda: datetime.now(UTC),
        )
        if not await publication.process_ai_projection_refresh_once():
            raise RuntimeError("PUBLICATION_AUTHORITY_NOT_CREATED")
        if not await publication.process_ai_projection_refresh_once():
            raise RuntimeError("PUBLICATION_PROJECTION_NOT_CREATED")
        if await publication.process_ai_projection_refresh_once():
            raise RuntimeError("PUBLICATION_QUEUE_NOT_DRAINED")

        from srbg_api.intelligence_v2.service import PostgresV2IntelligenceService

        reader = PostgresV2IntelligenceService(
            projection_reader,
            publisher,
            S3ObjectStore(Settings()),
        )
        feed = await reader.feed(limit=20, primary_type=None, cursor=None)
        projected = next(
            entry
            for entry in feed.items
            if getattr(entry, "document_version_id", None) == document["version_id"]
        )
        if not isinstance(projected, EventFullProjectionV2):
            raise RuntimeError("LOW_RISK_EVENT_WAS_NOT_FULLY_PROJECTED")
        item = projected
        detail = await reader.event(item.event_id)
        if detail != item:
            raise RuntimeError("EVENT_READER_FEED_MISMATCH")
        if item.primary_type.value != "INDUSTRY_UPDATE":
            raise RuntimeError(f"PRIMARY_TYPE_NOT_INDUSTRY_UPDATE_{item.primary_type.value}")
        if item.human_reviewed:
            raise RuntimeError("AUTOMATIC_CONTENT_MARKED_HUMAN_REVIEWED")

        async with admin.connect() as connection:
            facts = (
                (
                    await connection.execute(
                        text(
                            "SELECT "
                            "(SELECT count(*) FROM claim WHERE document_version_id=:version) "
                            "AS claims,"
                            "(SELECT count(*) FROM claim_evidence "
                            "WHERE document_version_id=:version) AS evidence,"
                            "(SELECT count(*) FROM automatic_publication_authority_v2 "
                            "WHERE document_version_id=:version) AS authorities,"
                            "(SELECT count(*) FROM publication_revision "
                            "WHERE document_version_id=:version "
                            "AND automatic_authority_id IS NOT NULL) AS revisions,"
                            "(SELECT count(*) FROM intelligence_projection_v2 "
                            "WHERE document_version_id=:version) AS projections"
                        ),
                        {"version": document["version_id"]},
                    )
                )
                .mappings()
                .one()
            )
            item_authority = (
                (
                    await connection.execute(
                        text(
                            "SELECT source_published_at,publication_risk_tier "
                            "FROM intelligence_item "
                            "WHERE current_document_version_id=:version"
                        ),
                        {"version": document["version_id"]},
                    )
                )
                .mappings()
                .one()
            )
        risk_tier = str(item_authority["publication_risk_tier"])
        if risk_tier not in {"R1", "R2"}:
            raise RuntimeError(f"CONTENT_NOT_LOW_RISK_{risk_tier}")
        if min(int(facts["claims"]), int(facts["evidence"])) < 1:
            raise RuntimeError("ACCEPTED_CLAIM_OR_EVIDENCE_MISSING")
        if item_authority["source_published_at"] is None:
            raise RuntimeError("SOURCE_PUBLISHED_AT_MISSING")
        if not item.source_excerpt.claim_ids or not item.source_excerpt.evidence_locators:
            raise RuntimeError("SOURCE_EXCERPT_EVIDENCE_MISSING")
        if str(item.original_url) != document["canonical_url"]:
            raise RuntimeError("ORIGINAL_URL_PROJECTION_MISMATCH")
        if {
            "authorities": int(facts["authorities"]),
            "revisions": int(facts["revisions"]),
            "projections": int(facts["projections"]),
        } != {"authorities": 1, "revisions": 1, "projections": 1}:
            raise RuntimeError("PUBLICATION_AUTHORITY_OR_REVISION_NOT_UNIQUE")
        report["source_published_at"] = item_authority["source_published_at"].isoformat()
        report["publication"] = {
            "event_id": str(item.event_id),
            "authority_count": int(facts["authorities"]),
            "revision_count": int(facts["revisions"]),
            "projection_count": int(facts["projections"]),
            "publication_revision_id": str(item.publication_revision_id),
            "authority_epoch": item.authority_epoch,
            "primary_type": item.primary_type.value,
            "risk_tier": risk_tier,
            "human_reviewed": item.human_reviewed,
            "accepted_claim_set_sha256": item.accepted_claim_set_sha256,
            "accepted_claim_ids": [
                str(claim_id) for claim_id in item.source_excerpt.claim_ids
            ],
            "evidence_locators": item.source_excerpt.evidence_locators,
            "source_excerpt_sha256": sha256(
                item.source_excerpt.text.encode("utf-8")
            ).hexdigest(),
            "claim_count": int(facts["claims"]),
            "evidence_count": int(facts["evidence"]),
        }

        await publication.refresh_v2_projection(
            event_id=item.event_id,
            document_version_id=document["version_id"],
        )
        await publication.refresh_v2_projection(
            event_id=item.event_id,
            document_version_id=document["version_id"],
        )
        replay_handoff = await SourceContentOutboxExecutor(
            gateway=PostgresSourceContentGateway(engine=worker)
        ).run(document["outbox_id"])
        async with admin.connect() as connection:
            replay = (
                (
                    await connection.execute(
                        text(
                            "SELECT "
                            "(SELECT count(*) FROM ai_pipeline_run "
                            "WHERE document_version_id=:version) AS pipelines,"
                            "(SELECT count(*) FROM automatic_publication_authority_v2 "
                            "WHERE document_version_id=:version) AS authorities,"
                            "(SELECT count(*) FROM publication_revision "
                            "WHERE document_version_id=:version "
                            "AND automatic_authority_id IS NOT NULL) AS revisions,"
                            "(SELECT count(*) FROM intelligence_projection_v2 "
                            "WHERE document_version_id=:version) AS projections"
                        ),
                        {"version": document["version_id"]},
                    )
                )
                .mappings()
                .one()
            )
        report["replay"] = dict(replay) | {
            "source_handoff_created": replay_handoff is not None,
            "zero_duplicate": dict(replay)
            == {
                "pipelines": 1,
                "authorities": 1,
                "revisions": 1,
                "projections": 1,
            }
            and replay_handoff is None,
        }
        if not report["replay"]["zero_duplicate"]:
            raise RuntimeError("REPLAY_CREATED_DUPLICATES")
        report["feed"] = {"item_count": len(feed.items), "matched": True}
        report["reader"] = {"matched_feed_item": True}
        report["status"] = "PASS"
    except Exception as error:
        report["first_blocker"] = type(error).__name__
        report["first_blocker_code"] = str(error)[:160]
        raise
    finally:
        try:
            try:
                await _capture_decision_diagnostics(
                    admin,
                    report=report,
                    document_version_id=document_version_id,
                )
            except Exception as diagnostics_error:
                report["decision_diagnostics_error"] = type(diagnostics_error).__name__
                if report["status"] == "PASS":
                    report["status"] = "NO_GO"
                    report["first_blocker"] = "DecisionDiagnosticsFailed"
                    report["first_blocker_code"] = "DECISION_DIAGNOSTICS_FAILED"
            report["queue_drain"] = await _stop_and_drain(
                admin,
                source_id=source_id,
                stream_id=stream_id,
                owner_id=owner_id,
                controlled_run_id=controlled_run_id,
                fetch_run_id=fetch_run_id,
            )
            if report["status"] == "PASS" and not report["queue_drain"]["drained"]:
                report["status"] = "NO_GO"
                report["first_blocker"] = "QueueDrainFailed"
                report["first_blocker_code"] = "QUEUE_NOT_DRAINED"
        finally:
            report["completed_at"] = datetime.now(UTC).isoformat()
            report["elapsed_seconds"] = (
                datetime.now(UTC) - started_at
            ).total_seconds()
            report.setdefault("model_calls", model_calls)
            _write_report(report)
            await admin.dispose()
            await worker.dispose()
            await publisher.dispose()
            await projection_reader.dispose()

    assert report["status"] == "PASS"
