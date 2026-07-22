# ruff: noqa: RUF001
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.ai_pipeline.content_preparation import (
    PreparationDocument,
    production_policy_for,
)
from srbg_api.ai_pipeline.preparation import DocumentBlock
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
from srbg_worker.ai_content_preparation import PostgresAiPreparationRepository

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


async def test_filtered_decision_is_idempotent_and_has_no_reader_materialization() -> None:
    admin = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    worker = create_async_engine(os.environ["SRBG_WORKER_DATABASE_URL"])
    raw_id = uuid7()
    document_id = uuid7()
    version_id = uuid7()
    unique = sha256(str(version_id).encode()).hexdigest()
    now = datetime.now(UTC)
    try:
        async with admin.begin() as connection:
            source_id = await connection.scalar(text("SELECT id FROM source ORDER BY id LIMIT 1"))
            assert source_id is not None
            await connection.execute(
                text(
                    "INSERT INTO raw_object(id,sha256,object_key,byte_size,declared_mime,"
                    "detected_mime,scan_status,created_at) VALUES(:id,:hash,:key,1,'text/html',"
                    "'text/html','CLEAN',:now)"
                ),
                {"id": raw_id, "hash": unique, "key": f"t41/{unique}", "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO document(id,source_id,canonical_url,document_kind,"
                    "first_discovered_at) VALUES(:id,:source,:url,'HTML',:now)"
                ),
                {
                    "id": document_id,
                    "source": source_id,
                    "url": f"https://example.invalid/t41/{version_id}",
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_version(id,document_id,raw_object_id,version_number,"
                    "content_hash,original_filename,acquired_at) VALUES("
                    ":id,:document,:raw,1,:hash,'fixture.html',:now)"
                ),
                {
                    "id": version_id,
                    "document": document_id,
                    "raw": raw_id,
                    "hash": unique,
                    "now": now,
                },
            )
            await connection.execute(
                text("UPDATE document SET current_version_id=:version WHERE id=:document"),
                {"version": version_id, "document": document_id},
            )
        preparation = PreparationDocument(
            run_id=uuid7(),
            document_version_id=version_id,
            raw_object_id=raw_id,
            source_stream_policy_version="integration-stream-policy-1",
            source_code="T41-INTEGRATION",
            canonical_url=f"https://example.invalid/t41/{version_id}",
            title="旅游消费促销",
            source_name="integration",
            blocks=(
                DocumentBlock(
                    block_id="block-1",
                    page_number=1,
                    text="旅游消费促销活动，与工程无关。",
                    locator_value="html:p:1",
                ),
            ),
        )
        policy = production_policy_for(preparation)
        trace = AutomatedAdjudicationService(
            policy=policy,
            model_edge=ModelMustNotRun(),
            clock=lambda: now,
            id_factory=uuid7,
        ).adjudicate(
            AdjudicationInput(
                document_version_id=version_id,
                raw_object_id=raw_id,
                normalized_input_sha256=unique,
                document_text="旅游消费促销活动，与工程无关。",
                allowed_evidence_locators=frozenset({"block-1"}),
            )
        )
        repository = PostgresAiPreparationRepository(
            engine=worker,
            object_store=cast(Any, object()),
            parser=cast(Any, object()),
            environment="acceptance",
            max_document_bytes=1,
        )
        await repository.append_automated_decision(trace, policy)
        await repository.append_automated_decision(trace, policy)
        async with admin.connect() as connection:
            decision_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM automated_qualification_decision_v2 "
                    "WHERE document_version_id=:version AND disposition='AUTO_FILTERED'"
                ),
                {"version": version_id},
            )
            item_count = await connection.scalar(
                text("SELECT count(*) FROM intelligence_item WHERE primary_document_id=:document"),
                {"document": document_id},
            )
            review_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM owner_review_case_v2 WHERE document_version_id=:version"
                ),
                {"version": version_id},
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
            "An authority issued an accident update for a highway tunnel collision.",
            "ACCIDENT_UPDATE",
            "An authority issued an accident update for a highway tunnel collision.",
            "incident_status",
            "official update issued",
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
    raw_id = uuid7()
    capture_id = uuid7()
    document_id = uuid7()
    version_id = uuid7()
    page_id = uuid7()
    block_id = uuid7()
    run_id = uuid7()
    step_run_id = uuid7()
    now = datetime.now(UTC)
    content_hash = sha256(str(version_id).encode()).hexdigest()
    try:
        async with admin.begin() as connection:
            source = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,registry_code,name FROM source "
                            "WHERE authority_level IN ('A0','A1') "
                            "ORDER BY id LIMIT 1"
                        )
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    "UPDATE source SET desired_enabled=true,lifecycle_state='ACTIVE',"
                    "runtime_state='RUNNING',manual_disabled_at=NULL WHERE id=:source"
                ),
                {"source": source["id"]},
            )
            await connection.execute(
                text(
                    "INSERT INTO raw_object(id,sha256,object_key,byte_size,declared_mime,"
                    "detected_mime,scan_status,created_at) VALUES(:id,:hash,:key,1,'text/html',"
                    "'text/html','CLEAN',:now)"
                ),
                {"id": raw_id, "hash": content_hash, "key": f"t41/{content_hash}", "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO raw_object_security_fact(id,raw_object_id,status,detected_mime,"
                    "rule_version,created_at) VALUES(:id,:raw,'CLEAN','text/html','t41-v1',:now)"
                ),
                {"id": uuid7(), "raw": raw_id, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO raw_object_capture(id,raw_object_id,source_id,fetch_run_id,"
                    "trial_run_id,execution_domain,requested_url,final_url,redirect_chain,"
                    "http_status,response_sha256,arrived_after_close,captured_at) VALUES("
                    ":id,:raw,:source,NULL,NULL,'PRODUCTION',:url,:url,'[]'::jsonb,200,:hash,"
                    "false,:now)"
                ),
                {
                    "id": capture_id,
                    "raw": raw_id,
                    "source": source["id"],
                    "url": f"https://example.invalid/t41/accepted/{version_id}",
                    "hash": content_hash,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document(id,source_id,canonical_url,document_kind,"
                    "first_discovered_at) VALUES(:id,:source,:url,'HTML',:now)"
                ),
                {
                    "id": document_id,
                    "source": source["id"],
                    "url": f"https://example.invalid/t41/accepted/{version_id}",
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_version(id,document_id,raw_object_id,version_number,"
                    "content_hash,original_filename,acquired_at,execution_domain,"
                    "raw_object_capture_id) VALUES("
                    ":id,:document,:raw,1,:hash,'accepted.html',:now,'PRODUCTION',:capture)"
                ),
                {
                    "id": version_id,
                    "document": document_id,
                    "raw": raw_id,
                    "hash": content_hash,
                    "capture": capture_id,
                    "now": now,
                },
            )
            await connection.execute(
                text("UPDATE document SET current_version_id=:version WHERE id=:document"),
                {"version": version_id, "document": document_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO document_page(id,document_version_id,page_number,width_mpt,"
                    "height_mpt,rotation,text_source,normalized_text_sha256,preview_object_key,"
                    "preview_sha256,preview_mime,created_at) VALUES("
                    ":id,:version,1,100000,100000,0,'NATIVE',:hash,'t41/preview',:hash,"
                    "'image/png',:now)"
                ),
                {"id": page_id, "version": version_id, "hash": content_hash, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO document_text_block(id,document_page_id,block_index,block_kind,"
                    "text_source,text,normalized_text,text_sha256,x0_mpt,y0_mpt,x1_mpt,y1_mpt,"
                    "confidence_bps,created_at) VALUES(:id,:page,0,'BODY','NATIVE',:text,:text,"
                    ":hash,0,0,100000,10000,10000,:now)"
                ),
                {
                    "id": block_id,
                    "page": page_id,
                    "text": excerpt,
                    "hash": sha256(excerpt.encode()).hexdigest(),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO ai_pipeline_run(id,document_version_id,mode,status,input_sha256,"
                    "started_at) VALUES(:id,:version,'LIVE','QUEUED',:hash,:now)"
                ),
                {"id": run_id, "version": version_id, "hash": content_hash, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO source_content_outbox(id,document_version_id,pipeline_run_id,"
                    "status,attempt_count,available_at,created_at,updated_at) VALUES("
                    ":id,:version,:run,'WAITING_AI',1,:now,:now,:now)"
                ),
                {"id": uuid7(), "version": version_id, "run": run_id, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO source_admission_assessment_v2(id,source_id,rule_version,"
                    "sample_cutoff,lookback_days,sample_size,sample_manifest_sha256,metrics,"
                    "evidence_refs,verdict,assessed_by,assessed_at) VALUES("
                    ":id,:source,'t41-production-admission-v1',:now,90,0,:hash,'{}'::jsonb,"
                    "'{}'::jsonb,'ADMIT',:actor,:now)"
                ),
                {
                    "id": uuid7(),
                    "source": source["id"],
                    "now": now,
                    "hash": content_hash,
                    "actor": uuid7(),
                },
            )
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
        document = PreparationDocument(
            run_id=run_id,
            document_version_id=version_id,
            raw_object_id=raw_id,
            source_stream_policy_version="integration-stream-policy-1",
            source_code=str(source["registry_code"]),
            canonical_url=f"https://example.invalid/t41/accepted/{version_id}",
            title="Highway section opened",
            source_name=str(source["name"]),
            blocks=(
                DocumentBlock(
                    block_id=str(block_id),
                    page_number=1,
                    text=excerpt,
                    locator_value="html:p:1",
                ),
            ),
        )
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
        repository = PostgresAiPreparationRepository(
            engine=worker,
            object_store=cast(Any, object()),
            parser=cast(Any, object()),
            environment="acceptance",
            max_document_bytes=1,
        )
        authoritative_document = await repository.begin(run_id)
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
        assert await publication.process_ai_projection_refresh_once() is True
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
                .one()
            )
            review_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM owner_review_case_v2 WHERE document_version_id=:version"
                ),
                {"version": version_id},
            )
        assert projection["primary_type"] == primary_type
        assert projection["projection_kind"] == "FULL"
        assert projection["payload"]["human_reviewed"] is False
        assert review_count == 0
    finally:
        await admin.dispose()
        await worker.dispose()
        await publisher.dispose()
