"""One bounded real-source acceptance run for the existing ``/sources`` view.

This module is excluded from ordinary test targets. It runs only through the
guarded ``phase4-source-display`` live profile against disposable resources.
Source content is persisted but never included in logs or acceptance evidence.
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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from srbg_api.acquisition.contracts import DiscoveryRecord, FetchResult
from srbg_api.acquisition.live import HttpxTransport
from srbg_api.config import Settings
from srbg_api.connectors.config import ConnectorKind
from srbg_api.connectors.parsers import CONNECTOR_PARSERS, ListDetailConnector
from srbg_api.identifiers import uuid7
from srbg_api.scheduling.service import PostgresSchedulingService
from srbg_api.source_registry.controlled_stream import (
    AdmissionGates,
    PostgresControlledStreamRepository,
    SourceResearchDisposition,
)
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_api.source_registry.service import SourceRegistryService
from srbg_api.source_registry.v2_rollout import (
    SourceAdmissionMetrics,
    append_production_admission_assessment,
)
from srbg_contracts import PersonalSourceCreateRequest
from srbg_worker.controlled_run_ledger import ControlledRunAttemptObserver
from srbg_worker.source_runtime import (
    LiveRuntimeTransport,
    PostgresRuntimeGateway,
    RuntimeFetchExecutor,
)

from scripts.run_phase4_real_event_acceptance import require_source_display_projection

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
MAX_WALL_SECONDS = 600
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


class _SourceDisplayDocumentVault:
    """Satisfy the read-only source module's metrics-bearing dependency."""

    metrics = object()


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
        output.write(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


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

    async with admin.begin() as connection:
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
                "id,state,wall_started_at,wall_deadline,last_resumed_at,created_at,updated_at) "
                "VALUES(:id,'PREPARING',:now,:deadline,:now,:now,:now)"
            ),
            {
                "id": controlled_run_id,
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
        research_sha256=RESEARCH_SHA256,
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
        gates=AdmissionGates(**{name: True for name in AdmissionGates.__dataclass_fields__}),
        evidence_sha256=RESEARCH_SHA256,
        actor_id=owner_id,
        valid_for=timedelta(minutes=30),
        rule_version="phase4-source-display-admission-v1",
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
            sample_manifest_sha256=RESEARCH_SHA256,
            evidence_refs={
                "research_manifest": str(RESEARCH_PATH),
                "source_stream_id": str(stream_id),
            },
            actor_id=owner_id,
            assessed_at=now,
            rule_version="phase4-source-display-production-admission-v1",
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
        await PostgresSchedulingService(admin).cancel_ineligible(
            source_id=source_id,
            run_id=fetch_run_id,
            now=stopped_at,
        )
    if controlled_run_id is not None:
        async with admin.begin() as connection:
            active = int(
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM fetch_run WHERE controlled_run_id=:run "
                        "AND status IN ('PENDING_DISPATCH','DISPATCHED','RUNNING','RETRY_WAIT')"
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
    client = redis.from_url(os.environ["SRBG_REDIS_URL"], decode_responses=False)
    try:
        redis_keys = int(await client.dbsize())
    finally:
        await client.aclose()
    return {
        "active_database_tasks": active,
        "redis_keys": redis_keys,
        "drained": active == 0 and redis_keys == 0,
    }


async def test_one_controlled_source_display(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    worker = create_async_engine(os.environ["SRBG_WORKER_DATABASE_URL"])
    started_at = datetime.now(UTC)
    deadline = started_at + timedelta(seconds=MAX_WALL_SECONDS)
    report: dict[str, Any] = {
        "schema_version": "phase4-source-display-acceptance-v1",
        "status": "NO_GO",
        "release_candidate_sha": os.environ["SRBG_PHASE4_RELEASE_CANDIDATE_SHA"],
        "source_stream_key": SOURCE_STREAM_KEY,
        "max_wall_seconds": MAX_WALL_SECONDS,
        "model_calls": 0,
        "ai_cost_microusd": 0,
        "ai_required": False,
        "network_route": (
            "PINNED_LOCAL_SOCKS5"
            if Settings().acquisition_socks5_proxy_url is not None
            else "PINNED_DIRECT"
        ),
        "fixed_document_url": FIXED_DOCUMENT_URL,
        "started_at": started_at.isoformat(),
    }
    source_id: UUID | None = None
    stream_id: UUID | None = None
    owner_id: UUID | None = None
    controlled_run_id: UUID | None = None
    fetch_run_id: UUID | None = None
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

    try:
        source_id, stream_id, owner_id, controlled_run_id, _ = await _seed_stream(
            admin, now=started_at
        )
        if stream_id != fixed_stream_id:
            raise RuntimeError("SOURCE_STREAM_ID_NOT_FIXED")
        report.update(
            {
                "source_id": str(source_id),
                "source_stream_id": str(stream_id),
                "controlled_run_id": str(controlled_run_id),
                "source_admission": "ADMIT",
            }
        )

        scheduling = PostgresSchedulingService(worker)
        claimed = await scheduling.claim_due(now=started_at)
        if claimed is None or claimed.source_id != source_id:
            raise RuntimeError("SOURCE_SCHEDULE_NOT_CLAIMED")
        fetch_run_id = claimed.run_id
        async with admin.connect() as connection:
            fetch_controlled_run_id = await connection.scalar(
                text("SELECT controlled_run_id FROM fetch_run WHERE id=:run"),
                {"run": claimed.run_id},
            )
        report["fetch_controlled_run_id"] = (
            str(fetch_controlled_run_id) if fetch_controlled_run_id is not None else None
        )
        if fetch_controlled_run_id != controlled_run_id:
            raise RuntimeError("FETCH_CONTROLLED_RUN_MISMATCH")
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
        if datetime.now(UTC) >= deadline:
            raise RuntimeError("HARD_DEADLINE_REACHED")

        async with admin.connect() as connection:
            document = (
                (
                    await connection.execute(
                        text(
                            "SELECT document.id AS document_id,version.id AS version_id,"
                            "version.raw_object_id,version.content_hash,version.acquired_at,"
                            "raw.sha256 AS raw_sha256,document.canonical_url,"
                            "document.first_discovered_at "
                            "FROM document JOIN document_version version "
                            "ON version.id=document.current_version_id "
                            "JOIN raw_object raw ON raw.id=version.raw_object_id "
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
        report.update(
            {
                "document_id": str(document["document_id"]),
                "document_version_id": str(document["version_id"]),
                "raw_object_id": str(document["raw_object_id"]),
                "raw_sha256": document["raw_sha256"],
                "document_content_hash": document["content_hash"],
                "original_url": document["canonical_url"],
                "acquired_at": document["acquired_at"].isoformat(),
                "first_discovered_at": document["first_discovered_at"].isoformat(),
                "bounded_source": {
                    "fixed_url_match": True,
                    "bounded_path_match": True,
                    "research_sha256": RESEARCH_SHA256,
                },
            }
        )

        source_registry = SourceRegistryService(
            SourceVaultRepository(admin), cast(Any, _SourceDisplayDocumentVault())
        )
        sources = await source_registry.list_personal_sources()
        visible_source = next((item for item in sources if item.id == source_id), None)
        visible_stream = (
            next((item for item in visible_source.streams if item.id == stream_id), None)
            if visible_source is not None
            else None
        )
        activity = await source_registry.get_personal_source_activity(
            source_id, cursor=None, limit=30
        )
        require_source_display_projection(
            source_visible=visible_source is not None,
            stream_visible=visible_stream is not None,
            normalized_url=(str(visible_stream.normalized_url) if visible_stream else ""),
            expected_url=COLLECTION_URL,
            last_successful_fetch_at=(
                visible_stream.last_successful_fetch_at if visible_stream else None
            ),
            last_content_discovered_at=(
                visible_stream.last_content_discovered_at if visible_stream else None
            ),
            discovered_count=activity.run_summary.discovered_count,
            fetched_count=activity.run_summary.fetched_count,
            failed_count=activity.run_summary.failed_count,
        )
        assert visible_source is not None
        assert visible_stream is not None
        report["sources_projection"] = {
            "route": "/sources",
            "source_visible": True,
            "stream_visible": True,
            "source_id": str(visible_source.id),
            "stream_id": str(visible_stream.id),
            "normalized_url": str(visible_stream.normalized_url),
            "stream_status": visible_stream.status.value,
            "runtime_state": visible_stream.runtime_state.value,
            "last_successful_fetch_at": visible_stream.last_successful_fetch_at.isoformat(),
            "last_content_discovered_at": (
                visible_stream.last_content_discovered_at.isoformat()
            ),
            "run_summary": activity.run_summary.model_dump(mode="json"),
        }
        report["status"] = "PASS"
    except Exception as error:
        report["first_blocker"] = type(error).__name__
        report["first_blocker_code"] = str(error)[:160]
        raise
    finally:
        try:
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
            _write_report(report)
            await admin.dispose()
            await worker.dispose()

    assert report["status"] == "PASS"
