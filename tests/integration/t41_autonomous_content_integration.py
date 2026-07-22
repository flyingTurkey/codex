# ruff: noqa: RUF001
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.acquisition.contracts import FetchResult, SourceCheckpoint
from srbg_api.ai_pipeline.content_preparation import (
    production_policy_for,
)
from srbg_api.config import Settings
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.autonomous_policy import (
    AdjudicationInput,
    AutomatedAdjudicationService,
)
from srbg_api.intelligence_v2.content_candidate_repository import (
    PostgresContentCandidateRepository,
)
from srbg_api.intelligence_v2.content_candidates import StructuredSummaryCandidate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_api.scheduling.service import PostgresSchedulingService
from srbg_api.source_registry.controlled_stream import (
    AdmissionGates,
    PostgresControlledStreamRepository,
)
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_api.source_registry.v2_rollout import (
    SourceAdmissionMetrics,
    append_production_admission_assessment,
)
from srbg_contracts import PersonalSourceCreateRequest
from srbg_worker.ai_content_preparation import PostgresAiPreparationRepository
from srbg_worker.source_content_bridge import (
    PostgresSourceContentGateway,
    SourceContentOutboxExecutor,
)
from srbg_worker.source_runtime import PostgresRuntimeGateway, RuntimeBinding, RuntimeFetchExecutor

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        "SRBG_TEST_ADMIN_DATABASE_URL" not in os.environ,
        reason="isolated integration database is required",
    ),
]


class ModelMustNotRun:
    def classify(
        self, *, system_prompt: str, document_text: str, semantic_recheck: bool
    ) -> dict[str, object]:
        raise AssertionError("locked negative must filter before model dispatch")


class AcceptedModel:
    def __init__(
        self, locator: str, *, primary_type: str, core_new_fact: str, content_form: str
    ) -> None:
        self._locator = locator
        self._primary_type = primary_type
        self._core_new_fact = core_new_fact
        self._content_form = content_form

    def classify(
        self, *, system_prompt: str, document_text: str, semantic_recheck: bool
    ) -> dict[str, object]:
        return {
            "direct_relevance": "RELEVANT",
            "core_new_fact": self._core_new_fact,
            "primary_type": self._primary_type,
            "engineering_objects": ["HIGHWAY"],
            "specialty_facets": [],
            "equipment_domains": [],
            "content_form": self._content_form,
            "evidence_locators": [self._locator],
            "confidence": 0.91,
            "ambiguity_indicators": [],
            "security_signals": [],
        }


@dataclass(frozen=True, slots=True)
class AcquiredDocument:
    source_id: Any
    document_id: Any
    document_version_id: Any
    raw_object_id: Any
    pipeline_run_id: Any
    content_sha256: str


class DeterministicRuntimeTransport:
    def __init__(
        self,
        *,
        binding: RuntimeBinding,
        gateway: PostgresRuntimeGateway,
        feed_url: str,
        article_url: str,
        excerpt: str,
        now: datetime,
    ) -> None:
        self._binding = binding
        self._gateway = gateway
        self._feed_url = feed_url
        self._article_url = article_url
        self._excerpt = excerpt
        self._now = now
        self.request_count = 0

    async def fetch(
        self,
        url: str,
        *,
        checkpoint: SourceCheckpoint,
        accept: str,
        exact_redirect_host: str,
    ) -> FetchResult:
        del checkpoint, accept, exact_redirect_host
        await self._gateway.reserve_request(self._binding, url=url)
        self.request_count += 1
        if url == self._feed_url:
            content = (
                "<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel>"
                f"<title>T41</title><link>{self._feed_url}</link><description>T41</description>"
                f"<item><guid>{self._article_url}</guid><title>T41 article</title>"
                f"<link>{self._article_url}</link></item></channel></rss>"
            ).encode()
            content_type = "application/rss+xml"
        elif url == self._article_url:
            content = f"<!doctype html><html><body><p>{self._excerpt}</p></body></html>".encode()
            content_type = "text/html"
        else:
            raise AssertionError(f"unexpected deterministic URL: {url}")
        await self._gateway.record_response_bytes(
            self._binding, url=url, response_bytes=len(content)
        )
        return FetchResult(
            url=url,
            status_code=200,
            content=content,
            content_type=content_type,
            etag=None,
            last_modified=None,
            fetched_at=self._now,
            request_url=url,
            response_sha256=sha256(content).hexdigest(),
        )

    async def close(self) -> None:
        return None


class DeterministicCleanScanner:
    async def scan(self, content: bytes) -> None:
        assert content


async def acquire_through_live_source_stream(
    *,
    admin: Any,
    worker: Any,
    excerpt: str,
    now: datetime,
) -> AcquiredDocument:
    unique = uuid7().hex
    host = f"t41-{unique[:12]}.example.test"
    feed_url = f"https://{host}/feed.xml"
    article_url = f"https://{host}/article.html"
    owner_id = uuid7()
    source = await SourceVaultRepository(admin).create_personal_source(
        PersonalSourceCreateRequest(url=feed_url),
        actor_id=owner_id,
        request_id=f"t41-source-{unique}",
        now=now,
    )
    stream_id = source.streams[0].id
    config_id = uuid7()
    schedule_id = uuid7()
    config = {"allowed_hosts": [host], "feed_url": feed_url}
    config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
    config_hash = sha256(config_json.encode()).hexdigest()
    async with admin.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO stream_config_version(id,stream_id,probe_run_id,connector_type,"
                "definition_version,schema_version,config,config_sha256,"
                "discovery_method,created_at) "
                "SELECT :config,:stream,probe.id,'RSS_ATOM','1.0.0','2020-12',"
                "CAST(:document AS jsonb),:hash,'DIRECT',:now FROM stream_probe_run probe "
                "WHERE probe.stream_id=:stream ORDER BY probe.created_at DESC LIMIT 1"
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
                "UPDATE source_stream SET status='READY',stream_type='RSS_ATOM',"
                "allowed_hosts=ARRAY[CAST(:host AS varchar(253))],config_sha256=:hash,"
                "discovery_method='DIRECT',failure_reason=NULL WHERE id=:stream"
            ),
            {"stream": stream_id, "hash": config_hash, "host": host},
        )
        await connection.execute(
            text(
                "INSERT INTO fetch_schedule(id,source_id,source_stream_id,stream_config_version_id,"
                "authority_mode,authority_level,status,interval_seconds,next_run_at,"
                "backoff_base_seconds,backoff_cap_seconds,max_attempts,consecutive_failures,"
                "circuit_state,freshness_slo_seconds,rate_limit_per_minute,daily_request_budget,"
                "daily_byte_budget,requests_used,bytes_used,budget_window_started_at,"
                "version,updated_at) "
                "VALUES(:schedule,:source,:stream,:config,'PERSONAL_STREAM','PERSONAL','ACTIVE',"
                "3600,:due,1,60,3,0,'CLOSED',86400,60,20,1048576,0,0,:now,1,:now)"
            ),
            {
                "schedule": schedule_id,
                "source": source.id,
                "stream": stream_id,
                "config": config_id,
                "due": datetime(2000, 1, 1, tzinfo=UTC),
                "now": now,
            },
        )
        await connection.execute(
            text("UPDATE source_stream SET schedule_id=:schedule WHERE id=:stream"),
            {"schedule": schedule_id, "stream": stream_id},
        )
    admission = PostgresControlledStreamRepository(admin, now=lambda: now)
    await admission.record_owner_intent(
        source_id=source.id,
        source_stream_id=stream_id,
        desired_enabled=True,
        actor_id=owner_id,
        request_id=f"t41-enable-{unique}",
    )
    assert (
        await admission.record_admission_decision(
            source_id=source.id,
            source_stream_id=stream_id,
            gates=AdmissionGates(**{name: True for name in AdmissionGates.__dataclass_fields__}),
            evidence_sha256=sha256(f"admission:{unique}".encode()).hexdigest(),
            actor_id=owner_id,
            valid_for=timedelta(hours=1),
            rule_version="t41-live-source-admission-v1",
        )
        == "ADMIT"
    )
    async with admin.begin() as connection:
        assert (
            await append_production_admission_assessment(
                connection,
                source_id=source.id,
                metrics=SourceAdmissionMetrics(
                    sample_size=0,
                    robots_allowed=None,
                    terms_allowed=None,
                    copyright_reviewed=None,
                    public_network_safe=True,
                    fetch_success_bps=0,
                    parse_evidence_success_bps=0,
                    metadata_success_bps=0,
                    useful_yield_bps=0,
                    duplicate_bps=0,
                    hard_negative_leaks=0,
                    hard_negative_evaluated=False,
                ),
                sample_cutoff=now,
                sample_manifest_sha256=sha256(f"manifest:{unique}".encode()).hexdigest(),
                evidence_refs={"source_stream_id": str(stream_id)},
                actor_id=owner_id,
                assessed_at=now,
                rule_version="t41-production-admission-v1",
            )
            == "ADMIT"
        )
        # Source auto-enablement is an independently tested controller. This fixture starts
        # from its authorized terminal state so #41 exercises the downstream content seam.
        await connection.execute(
            text(
                "UPDATE source SET runtime_state='RUNNING',enabled=true,state='ACTIVE',"
                "updated_at=:now WHERE id=:source"
            ),
            {"source": source.id, "now": now},
        )
        model_id = await connection.scalar(
            text("SELECT id FROM ai_model_profile ORDER BY created_at DESC LIMIT 1")
        )
        assert model_id is not None
        await connection.execute(
            text(
                "INSERT INTO ai_provider_activation(id,provider,model_profile_id,environment,"
                "active,created_by,created_at) VALUES(:id,'deepseek',:model,'acceptance',"
                "true,:actor,:now)"
            ),
            {
                "id": uuid7(),
                "model": model_id,
                "actor": owner_id,
                "now": now,
            },
        )
    scheduling = PostgresSchedulingService(worker)
    claimed = await scheduling.claim_due(now=now)
    assert claimed is not None and claimed.source_id == source.id
    settings = Settings(database_url=os.environ["SRBG_WORKER_DATABASE_URL"])
    gateway = PostgresRuntimeGateway(
        settings,
        engine=worker,
        malware_scanner=cast(Any, DeterministicCleanScanner()),
    )
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda binding: DeterministicRuntimeTransport(
            binding=binding,
            gateway=gateway,
            feed_url=feed_url,
            article_url=article_url,
            excerpt=excerpt,
            now=now,
        ),
        authority_heartbeat_seconds=1,
    )
    result = await executor.run(source_id=source.id, run_id=claimed.run_id)
    assert result.fetched_count == 1 and result.failed_count == 0
    async with admin.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT document.id AS document_id,version.id AS version_id,"
                        "version.raw_object_id,version.content_hash,outbox.id AS outbox_id "
                        "FROM document JOIN document_version version "
                        "ON version.document_id=document.id JOIN source_content_outbox outbox "
                        "ON outbox.document_version_id=version.id "
                        "WHERE document.source_id=:source AND document.canonical_url=:url"
                    ),
                    {"source": source.id, "url": article_url},
                )
            )
            .mappings()
            .one()
        )
        authority = (
            (
                await connection.execute(
                    text(
                        "SELECT document.current_version_id=version.id AS current_version,"
                        "document.admission_fixture,version.execution_domain AS version_domain,"
                        "capture.execution_domain AS capture_domain,"
                        "run.execution_domain AS run_domain,"
                        "run.run_origin,run.trigger,run.pilot_window_source_id,"
                        "version.content_hash=raw.sha256 AS hash_matches,raw.scan_status,"
                        "EXISTS(SELECT 1 FROM raw_object_security_fact fact "
                        "WHERE fact.raw_object_id=raw.id AND fact.status='CLEAN') AS has_clean,"
                        "EXISTS(SELECT 1 FROM raw_object_security_fact fact "
                        "WHERE fact.raw_object_id=raw.id AND fact.status IN "
                        "('REJECTED','QUARANTINED')) AS has_rejection,"
                        "(SELECT state.state FROM document_version_state_event state "
                        "WHERE state.document_version_id=version.id ORDER BY state.created_at DESC,"
                        "CASE state.state WHEN 'FAILED' THEN 90 WHEN 'QUARANTINED' THEN 90 "
                        "WHEN 'READY' THEN 80 WHEN 'OCR_COMPLETE' THEN 70 "
                        "WHEN 'SECURITY_PASSED' THEN 60 WHEN 'OCR_PENDING' THEN 50 "
                        "WHEN 'PARSING' THEN 40 WHEN 'RECEIVED' THEN 30 ELSE 0 END DESC,"
                        "state.id DESC LIMIT 1) AS latest_state "
                        "FROM document_version version JOIN document "
                        "ON document.id=version.document_id "
                        "JOIN raw_object raw ON raw.id=version.raw_object_id "
                        "JOIN raw_object_capture capture "
                        "ON capture.id=version.raw_object_capture_id "
                        "JOIN fetch_run run ON run.id=capture.fetch_run_id "
                        "WHERE version.id=:version"
                    ),
                    {"version": row["version_id"]},
                )
            )
            .mappings()
            .one()
        )
        assert dict(authority) == {
            "current_version": True,
            "admission_fixture": False,
            "version_domain": "PRODUCTION",
            "capture_domain": "PRODUCTION",
            "run_domain": "PRODUCTION",
            "run_origin": "SCHEDULED",
            "trigger": "SCHEDULED",
            "pilot_window_source_id": None,
            "hash_matches": True,
            "scan_status": "CLEAN",
            "has_clean": True,
            "has_rejection": False,
            "latest_state": "READY",
        }
    handoff = await SourceContentOutboxExecutor(
        gateway=PostgresSourceContentGateway(engine=worker)
    ).run(row["outbox_id"])
    assert handoff is not None and handoff.queued
    return AcquiredDocument(
        source_id=source.id,
        document_id=row["document_id"],
        document_version_id=row["version_id"],
        raw_object_id=row["raw_object_id"],
        pipeline_run_id=handoff.pipeline_run_id,
        content_sha256=row["content_hash"],
    )


async def test_filtered_decision_is_idempotent_and_has_no_reader_materialization() -> None:
    admin = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    worker = create_async_engine(os.environ["SRBG_WORKER_DATABASE_URL"])
    now = datetime.now(UTC)
    filtered_text = "旅游消费促销活动，与工程无关。"
    try:
        acquired = await acquire_through_live_source_stream(
            admin=admin,
            worker=worker,
            excerpt=filtered_text,
            now=now,
        )
        repository = PostgresAiPreparationRepository(
            engine=worker,
            object_store=S3ObjectStore(Settings()),
            parser=cast(Any, object()),
            environment="acceptance",
            max_document_bytes=1024 * 1024,
        )
        preparation = await repository.begin(acquired.pipeline_run_id)
        await repository.transition(acquired.pipeline_run_id, "CLASSIFYING")
        policy = production_policy_for(preparation)
        trace = AutomatedAdjudicationService(
            policy=policy,
            model_edge=ModelMustNotRun(),
            clock=lambda: now,
            id_factory=uuid7,
        ).adjudicate(
            AdjudicationInput(
                document_version_id=acquired.document_version_id,
                raw_object_id=acquired.raw_object_id,
                normalized_input_sha256=acquired.content_sha256,
                document_text=filtered_text,
                allowed_evidence_locators=frozenset(block.block_id for block in preparation.blocks),
            )
        )
        await repository.append_automated_decision(trace, policy)
        await repository.append_automated_decision(trace, policy)
        await repository.transition(acquired.pipeline_run_id, "SUCCEEDED")
        async with admin.connect() as connection:
            decision_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM automated_qualification_decision_v2 "
                    "WHERE document_version_id=:version AND disposition='AUTO_FILTERED'"
                ),
                {"version": acquired.document_version_id},
            )
            item_count = await connection.scalar(
                text("SELECT count(*) FROM intelligence_item WHERE primary_document_id=:document"),
                {"document": acquired.document_id},
            )
            review_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM owner_review_case_v2 WHERE document_version_id=:version"
                ),
                {"version": acquired.document_version_id},
            )
        assert decision_count == 1
        assert item_count == 0
        assert review_count == 0
    finally:
        await admin.dispose()
        await worker.dispose()


@pytest.mark.parametrize(
    ("primary_type", "core_new_fact", "content_form", "excerpt", "claim_field", "claim_value"),
    (
        (
            "INDUSTRY_UPDATE",
            "A highway construction section opened to traffic.",
            "OPERATION_UPDATE",
            "A highway construction section opened to traffic after completion.",
            "project_status",
            "opened to traffic",
        ),
        (
            "SAFETY_INTELLIGENCE",
            "An authority issued an accident update during highway tunnel operation.",
            "ACCIDENT_UPDATE",
            "An authority issued an accident update during highway tunnel operation.",
            "incident_status",
            "accident update",
        ),
    ),
)
async def test_accepted_decision_reaches_v2_feed_through_evidence_and_publication(
    primary_type: str,
    core_new_fact: str,
    content_form: str,
    excerpt: str,
    claim_field: str,
    claim_value: str,
) -> None:
    admin = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    worker = create_async_engine(os.environ["SRBG_WORKER_DATABASE_URL"])
    publisher = create_async_engine(os.environ["SRBG_PUBLICATION_DATABASE_URL"])
    step_run_id = uuid7()
    now = datetime.now(UTC)
    try:
        acquired = await acquire_through_live_source_stream(
            admin=admin,
            worker=worker,
            excerpt=excerpt,
            now=now,
        )
        version_id = acquired.document_version_id
        raw_id = acquired.raw_object_id
        run_id = acquired.pipeline_run_id
        content_hash = acquired.content_sha256
        async with admin.begin() as connection:
            registry = (
                (
                    await connection.execute(
                        text(
                            "SELECT (SELECT id FROM ai_prompt_version WHERE step='EXTRACT' "
                            "ORDER BY created_at DESC LIMIT 1) AS prompt_id,"
                            "(SELECT id FROM ai_schema_version WHERE step='EXTRACT' "
                            "ORDER BY created_at DESC LIMIT 1) AS schema_id,"
                            "(SELECT id FROM ai_model_profile ORDER BY created_at DESC LIMIT 1) "
                            "AS model_id"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert all(registry.values())
            await connection.execute(
                text(
                    "INSERT INTO ai_provider_activation(id,provider,model_profile_id,environment,"
                    "active,created_by,created_at) VALUES(:id,'deepseek',:model,'acceptance',"
                    "true,:actor,:now)"
                ),
                {
                    "id": uuid7(),
                    "model": registry["model_id"],
                    "actor": uuid7(),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO ai_step_run(id,pipeline_run_id,step,attempt,prompt_version_id,"
                    "schema_version_id,model_profile_id,input_sha256,raw_output,validated_output,"
                    "status,created_at) VALUES(:id,:run,'EXTRACT',1,:prompt,:schema,:model,:hash,"
                    "'{}',CAST('{}' AS jsonb),'SUCCEEDED',:now)"
                ),
                {
                    "id": step_run_id,
                    "run": run_id,
                    "prompt": registry["prompt_id"],
                    "schema": registry["schema_id"],
                    "model": registry["model_id"],
                    "hash": content_hash,
                    "now": now,
                },
            )
        repository = PostgresAiPreparationRepository(
            engine=worker,
            object_store=S3ObjectStore(Settings()),
            parser=cast(Any, object()),
            environment="acceptance",
            max_document_bytes=1024 * 1024,
        )
        document = await repository.begin(run_id)
        block_id = document.blocks[0].block_id
        policy = production_policy_for(document)
        trace = AutomatedAdjudicationService(
            policy=policy,
            model_edge=AcceptedModel(
                str(block_id),
                primary_type=primary_type,
                core_new_fact=core_new_fact,
                content_form=content_form,
            ),
            clock=lambda: now,
            id_factory=uuid7,
        ).adjudicate(
            AdjudicationInput(
                document_version_id=version_id,
                raw_object_id=raw_id,
                normalized_input_sha256=content_hash,
                document_text=excerpt,
                allowed_evidence_locators=frozenset({str(block_id)}),
            )
        )
        assert trace.disposition.value == "AUTO_ACCEPTED"
        authoritative_document = document
        assert authoritative_document.run_mode == "LIVE"
        assert authoritative_document.document_version_id == version_id
        await repository.transition(run_id, "CLASSIFYING")
        await repository.transition(run_id, "EXTRACTING")
        await repository.append_automated_decision(trace, policy)
        candidate = cast(Any, trace.model_candidate).model_dump(mode="json")
        count = await repository.materialize(
            document,
            candidate,
            {
                "claims": [
                    {
                        "claim_id": "project-status-1",
                        "field": claim_field,
                        "value": claim_value,
                        "claim_status": "UNVERIFIED",
                        "confidence": 0.99,
                        "evidence_ids": ["evidence-1"],
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": "evidence-1",
                        "document_block_id": str(block_id),
                        "locator": {"type": "HTML_PARAGRAPH", "value": "html:p:1"},
                        "excerpt": excerpt,
                        "supports": ["project-status-1"],
                    }
                ],
                "security": {
                    "prompt_injection_detected": False,
                    "prompt_injection_status": "NONE",
                    "suspicious_patterns": [],
                },
            },
        )
        assert count == 1
        claims = await PostgresContentCandidateRepository(worker).load_active_claims(version_id)
        assert len(claims) == 1
        paragraph = "x" * 100
        summary = StructuredSummaryCandidate.model_validate(
            {
                "paragraphs": [
                    {
                        "kind": "FACT",
                        "section": "WHAT_HAPPENED",
                        "text": paragraph,
                        "claim_ids": [str(claims[0].claim_id)],
                    },
                    {
                        "kind": "JUDGMENT",
                        "section": "ENGINEERING_IMPACT",
                        "text": paragraph,
                        "claim_ids": [],
                        "judgment_type": "ENGINEERING_SIGNIFICANCE",
                    },
                    {
                        "kind": "JUDGMENT",
                        "section": "LIMITATIONS_AND_FOLLOW_UP",
                        "text": paragraph,
                        "claim_ids": [],
                        "judgment_type": "LIMITATION_AND_FOLLOW_UP",
                    },
                ]
            }
        )
        summary_request = await repository.prepare_t06_content_summary(
            document, append_processing=True
        )
        candidate_id = await repository.materialize_t06_content_summary(
            document, request=summary_request, summary=summary
        )
        await repository.append_summary_state(
            document,
            status="SUCCEEDED",
            reason_code="SCHEMA_VALID_APPROVED_CONTENT",
            candidate_id=candidate_id,
        )
        publication = PublicationService(
            repository=PostgresPublicationRepository(publisher),
            gate=cast(Any, object()),
            now=lambda: now + timedelta(minutes=1),
        )
        for _ in range(4):
            assert await publication.process_ai_projection_refresh_once() is True
            async with admin.connect() as connection:
                projected = await connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM intelligence_projection_v2 "
                        "WHERE document_version_id=:version)"
                    ),
                    {"version": version_id},
                )
            if projected:
                break
        async with admin.connect() as connection:
            projection = (
                (
                    await connection.execute(
                        text(
                            "SELECT primary_type,projection_kind,payload FROM "
                            "intelligence_projection_v2 WHERE document_version_id=:version"
                        ),
                        {"version": version_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            refresh = (
                (
                    await connection.execute(
                        text(
                            "SELECT status,last_error_code FROM ai_projection_refresh_outbox_v2 "
                            "WHERE document_version_id=:version ORDER BY created_at DESC LIMIT 1"
                        ),
                        {"version": version_id},
                    )
                )
                .mappings()
                .one()
            )
            review_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM owner_review_case_v2 WHERE document_version_id=:version"
                ),
                {"version": version_id},
            )
        assert projection is not None, dict(refresh)
        assert projection["primary_type"] == primary_type
        assert projection["projection_kind"] == "FULL"
        assert projection["payload"]["human_reviewed"] is False
        assert review_count == 0
    finally:
        await admin.dispose()
        await worker.dispose()
        await publisher.dispose()
