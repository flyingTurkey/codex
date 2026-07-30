"""PostgreSQL/object-store boundary for the R-AI01 preparation service."""

from __future__ import annotations

import asyncio
import json
import logging
from base64 import b64decode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.ai_pipeline.ai_judgments import EvidenceFactInput, EvidenceSnippet
from srbg_api.ai_pipeline.content_preparation import PreparationDocument
from srbg_api.ai_pipeline.contracts import AiStep, ModelRequest, ModelResponse
from srbg_api.ai_pipeline.evidence_gate import (
    AiJudgment,
    AutomaticEvidenceCandidate,
    AutomaticEvidenceContext,
    AutomaticEvidenceGate,
    EvidenceFact,
    EvidenceGateEvidence,
)
from srbg_api.ai_pipeline.local_evidence import extract_local_evidence_candidates
from srbg_api.ai_pipeline.preparation import DocumentBlock
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.autonomous_policy import QualificationPolicyBundle
from srbg_api.intelligence_v2.compensation import compensation_plan
from srbg_api.intelligence_v2.content_candidate_repository import (
    PostgresContentCandidateRepository,
)
from srbg_api.intelligence_v2.content_candidate_service import ContentSummaryRequest
from srbg_api.intelligence_v2.content_candidates import (
    StructuredSummaryCandidate,
    build_content_candidate,
)
from srbg_api.intelligence_v2.qualification_decisions import append_qualification_decision
from srbg_api.intelligence_v2.t06_content_summary import build_content_summary_request
from srbg_api.observability import (
    INTELLIGENCE_QUALIFICATION_REVIEW_BACKLOG,
    T06_AI_SUMMARY_STATE_TRANSITIONS,
)
from srbg_api.pdf_processing.parser import (
    ParsedPage,
    ParsedPdfDocument,
    ParsedTextBlock,
    PdfDocumentParser,
)
from srbg_contracts import AutomatedDecisionReason, QualificationDecisionTrace

logger = logging.getLogger("srbg.worker.ai_content_preparation")


class _ArticleHtmlParser(HTMLParser):
    _content_tags = frozenset({"p", "li", "h1", "h2", "h3", "h4", "blockquote"})
    _ignored_tags = frozenset({"script", "style", "nav", "footer", "form", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._active: list[str] | None = None
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._ignored_tags:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and tag in self._content_tags:
            self._active = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0 and self._active is not None:
            self._active.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
        elif self._ignored_depth == 0 and tag in self._content_tags and self._active is not None:
            value = " ".join("".join(self._active).split())
            if value:
                self.paragraphs.append(value)
            self._active = None


def parse_html_document(content: bytes) -> ParsedPdfDocument:
    """Create stable paragraph-addressed blocks for a bounded public HTML response."""

    parser = _ArticleHtmlParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    if not parser.paragraphs:
        raise ValueError("HTML_BODY_EMPTY")
    blocks = tuple(
        ParsedTextBlock(
            block_index=index,
            kind="BODY",
            text_source="NATIVE",
            text=value,
            normalized_text=value,
            text_sha256=sha256(value.encode()).hexdigest(),
            bbox_mpt=(0, index * 1000, 800_000, (index + 1) * 1000),
            confidence_bps=10_000,
        )
        for index, value in enumerate(parser.paragraphs)
    )
    normalized = "\n".join(parser.paragraphs)
    digest = sha256(normalized.encode()).hexdigest()
    preview = b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    page = ParsedPage(
        page_number=1,
        width_mpt=800_000,
        height_mpt=max(len(blocks), 1) * 1000,
        rotation=0,
        text_source="NATIVE",
        blocks=blocks,
        table_cells=(),
        preview_png=preview,
        preview_sha256=sha256(preview).hexdigest(),
        normalized_text_sha256=digest,
    )
    return ParsedPdfDocument(
        pages=(page,),
        normalized_text=normalized,
        semantic_body=normalized,
        normalized_text_sha256=digest,
        semantic_body_sha256=digest,
        metadata_sha256=sha256(b"html-v1").hexdigest(),
        ocr_page_count=0,
        ocr_usable_page_count=0,
        low_confidence_critical_count=0,
        parser_version="srbg-html-paragraph-1.0.0",
    )


class PostgresAiPreparationRepository:
    """Worker-side repository; the isolated model process never imports this module."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        object_store: S3ObjectStore,
        parser: PdfDocumentParser,
        environment: str,
        max_document_bytes: int,
    ) -> None:
        self._engine = engine
        self._object_store = object_store
        self._parser = parser
        self._environment = environment.casefold()
        self._max_document_bytes = max_document_bytes

    async def begin(self, run_id: UUID) -> PreparationDocument:
        async with self._engine.begin() as connection:
            promoted = await connection.scalar(
                text(_AUTHORIZE_PERSONAL_SQL),
                {"run_id": run_id, "environment": self._environment},
            )
            if promoted != run_id:
                raise RuntimeError("AI01_SHADOW_AUTHORITY_INVALID")
            await connection.execute(
                text(
                    "UPDATE ai_pipeline_run SET status='PREPARING' WHERE id=:run_id "
                    "AND status='QUEUED'"
                ),
                {"run_id": run_id},
            )
            facts = (
                (await connection.execute(text(_DOCUMENT_SQL), {"run_id": run_id})).mappings().one()
            )
            blocks = await _load_blocks(connection, cast(UUID, facts["document_version_id"]))
        if not blocks:
            content = await self._object_store.get_bytes(
                str(facts["object_key"]), max_bytes=self._max_document_bytes
            )
            if sha256(content).hexdigest() != facts["content_hash"]:
                raise RuntimeError("RAW_OBJECT_HASH_MISMATCH")
            mime_type = str(facts["mime_type"] or "").casefold()
            if "html" in mime_type or content.lstrip().startswith((b"<html", b"<!doctype")):
                parsed = await asyncio.to_thread(parse_html_document, content)
            elif "pdf" in mime_type or content.startswith(b"%PDF-"):
                parsed = await asyncio.to_thread(self._parser.parse, content)
            else:
                raise RuntimeError("UNSUPPORTED_DOCUMENT_MIME")
            await self._persist_parsed(cast(UUID, facts["document_version_id"]), parsed)
            async with self._engine.connect() as connection:
                blocks = await _load_blocks(connection, cast(UUID, facts["document_version_id"]))
        return PreparationDocument(
            run_id=run_id,
            document_version_id=cast(UUID, facts["document_version_id"]),
            raw_object_id=cast(UUID, facts["raw_object_id"]),
            source_stream_policy_version=str(facts["source_stream_policy_version"]),
            source_code=str(facts["registry_code"]),
            canonical_url=str(facts["canonical_url"]),
            title=str(facts["title"] or "交通运输部公开 PDF"),
            source_name=str(facts["source_name"]),
            blocks=tuple(blocks),
            policy_bundle=_policy_bundle_from_facts(facts),
            run_mode=str(facts["run_mode"]),
            technical_retry_max_retries=int(facts["technical_retry_max_retries"]),
        )

    async def load_technical_context(self, run_id: UUID) -> PreparationDocument:
        """Load ID-only retry authority without touching untrusted object bytes."""

        async with self._engine.connect() as connection:
            facts = (
                (await connection.execute(text(_DOCUMENT_SQL), {"run_id": run_id}))
                .mappings()
                .one()
            )
        return PreparationDocument(
            run_id=run_id,
            document_version_id=cast(UUID, facts["document_version_id"]),
            raw_object_id=cast(UUID, facts["raw_object_id"]),
            source_stream_policy_version=str(facts["source_stream_policy_version"]),
            source_code=str(facts["registry_code"]),
            canonical_url=str(facts["canonical_url"]),
            title=str(facts["title"] or "Untitled source document"),
            source_name=str(facts["source_name"]),
            blocks=(),
            policy_bundle=_policy_bundle_from_facts(facts),
            run_mode=str(facts["run_mode"]),
            technical_retry_max_retries=int(facts["technical_retry_max_retries"]),
        )

    async def authorize_real_run(self, document: PreparationDocument) -> bool:
        """Recheck the current version and all server-controlled runtime gates."""

        return await self.authorize_model_call(
            document.run_id,
            document_version_id=document.document_version_id,
        )

    async def append_automated_decision(
        self, trace: QualificationDecisionTrace, policy: QualificationPolicyBundle
    ) -> None:
        """Append the exact immutable policy bundle and its server decision atomically."""

        async with self._engine.begin() as connection:
            await append_qualification_decision(connection, trace=trace, policy=policy)

    async def append_shadow_decision(
        self, trace: QualificationDecisionTrace, policy: QualificationPolicyBundle
    ) -> None:
        """Append a shadow evaluation that is structurally unable to affect production."""

        identity = policy.identity
        policy_payload = {
            "identity": identity.model_dump(mode="json"),
            "source_allow_terms": list(policy.source_allow_terms),
            "source_exclude_terms": list(policy.source_exclude_terms),
            "maximum_semantic_rechecks": 1,
        }
        dispositions = {
            value: int(trace.disposition.value == value)
            for value in (
                "AUTO_ACCEPTED",
                "AUTO_FILTERED",
                "TECHNICAL_RETRY",
                "TECHNICAL_FAILED",
                "SAFETY_HOLD",
                "OWNER_SUPPRESSED",
            )
        }
        schema_valid_bps = (
            0 if AutomatedDecisionReason.AI_SCHEMA_INVALID in trace.reason_codes else 10_000
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO qualification_policy_bundle_v2("
                    "id,policy_version,global_rule_version,source_stream_policy_version,"
                    "ai_provider,ai_model,prompt_version,schema_version,code_version,"
                    "authorization_basis,policy_payload,bundle_sha256,created_at) VALUES("
                    ":id,:policy_version,:global_rule_version,:stream_version,:provider,:model,"
                    ":prompt_version,:schema_version,:code_version,'SERVER_ADJUDICATION_ONLY',"
                    "CAST(:payload AS jsonb),:bundle_sha256,:now) "
                    "ON CONFLICT (bundle_sha256) DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "policy_version": identity.policy_version,
                    "global_rule_version": identity.global_rule_version,
                    "stream_version": identity.source_stream_policy_version,
                    "provider": identity.ai_provider,
                    "model": identity.ai_model,
                    "prompt_version": identity.prompt_version,
                    "schema_version": identity.schema_version,
                    "code_version": identity.code_version,
                    "payload": json.dumps(policy_payload, ensure_ascii=False, sort_keys=True),
                    "bundle_sha256": identity.bundle_sha256,
                    "now": trace.decided_at,
                },
            )
            bundle_id = await connection.scalar(
                text(
                    "SELECT id FROM qualification_policy_bundle_v2 "
                    "WHERE bundle_sha256=:bundle_sha256"
                ),
                {"bundle_sha256": identity.bundle_sha256},
            )
            if bundle_id is None:
                raise RuntimeError("QUALIFICATION_POLICY_BUNDLE_NOT_PERSISTED")
            await connection.execute(
                text(
                    "INSERT INTO qualification_policy_evaluation_v2("
                    "id,policy_bundle_id,mode,benchmark_version,corpus_manifest_sha256,"
                    "total_cases,auto_accepted_count,auto_filtered_count,technical_retry_count,"
                    "technical_failed_count,safety_hold_count,owner_suppressed_count,"
                    "precision_bps,recall_bps,locked_negative_leaks,schema_valid_bps,"
                    "new_owner_semantic_tasks,gate_passed,authorizes_production,evaluated_at) "
                    "VALUES(:id,:bundle,'SHADOW','runtime-shadow-v1',:manifest,1,:accepted,"
                    ":filtered,:retry,:failed,:safety,:suppressed,0,0,0,:schema_valid,0,false,"
                    "false,:now) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": trace.decision_id,
                    "bundle": bundle_id,
                    "manifest": trace.normalized_input_sha256,
                    "accepted": dispositions["AUTO_ACCEPTED"],
                    "filtered": dispositions["AUTO_FILTERED"],
                    "retry": dispositions["TECHNICAL_RETRY"],
                    "failed": dispositions["TECHNICAL_FAILED"],
                    "safety": dispositions["SAFETY_HOLD"],
                    "suppressed": dispositions["OWNER_SUPPRESSED"],
                    "schema_valid": schema_valid_bps,
                    "now": trace.decided_at,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO qualification_shadow_decision_v2("
                    "id,evaluation_id,policy_bundle_id,document_version_id,raw_object_id,"
                    "disposition,reason_codes,decision_trace,affects_production,decided_at) "
                    "VALUES(:id,:evaluation,:bundle,:version,:raw,:disposition,:reasons,"
                    "CAST(:trace AS jsonb),false,:now) ON CONFLICT "
                    "(evaluation_id,document_version_id) DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "evaluation": trace.decision_id,
                    "bundle": bundle_id,
                    "version": trace.document_version_id,
                    "raw": trace.raw_object_id,
                    "disposition": trace.disposition.value,
                    "reasons": [reason.value for reason in trace.reason_codes],
                    "trace": json.dumps(trace.model_dump(mode="json"), ensure_ascii=False),
                    "now": trace.decided_at,
                },
            )

    async def authorize_model_call(
        self, run_id: UUID, *, document_version_id: UUID | None = None
    ) -> bool:
        """Recheck all authoritative gates immediately before one physical call."""

        async with self._engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ai_pipeline_run run "
                        "JOIN document_version version ON version.id=run.document_version_id "
                        "JOIN raw_object raw ON raw.id=version.raw_object_id "
                        "JOIN document doc ON doc.id=version.document_id "
                        "JOIN source src ON src.id=doc.source_id "
                        "WHERE run.id=:run_id AND (CAST(:version_id AS uuid) IS NULL OR "
                        "version.id=CAST(:version_id AS uuid)) "
                        "AND doc.current_version_id=version.id AND raw.scan_status='CLEAN' "
                        "AND EXISTS(SELECT 1 FROM raw_object_security_fact security "
                        "WHERE security.raw_object_id=raw.id AND security.status='CLEAN') "
                        "AND NOT EXISTS(SELECT 1 FROM raw_object_security_fact security "
                        "WHERE security.raw_object_id=raw.id "
                        "AND security.status IN ('REJECTED','QUARANTINED')) "
                        "AND version.execution_domain IN ('TRIAL','PRODUCTION') "
                        "AND src.desired_enabled AND src.manual_disabled_at IS NULL "
                        "AND src.runtime_state='RUNNING' "
                        "AND (SELECT assessment.verdict "
                        "FROM source_admission_assessment_v2 assessment "
                        "WHERE assessment.source_id=src.id "
                        "ORDER BY assessment.assessed_at DESC,assessment.id DESC LIMIT 1)="
                        "'ADMIT' "
                        "AND EXISTS(SELECT 1 FROM ai_budget_policy budget "
                        "LEFT JOIN ai_budget_month month ON month.policy_id=budget.id "
                        "AND month.month_start=date_trunc('month',now())::date "
                        "WHERE budget.provider='deepseek' AND budget.active "
                        "AND COALESCE(month.reserved_points,0)+"
                        "COALESCE(month.settled_points,0)<budget.monthly_points) "
                        "AND true=(SELECT activation.active AND profile.enabled "
                        "AND profile.provider='deepseek' AND profile.model='deepseek-v4-flash' "
                        "FROM ai_provider_activation activation JOIN ai_model_profile profile "
                        "ON profile.id=activation.model_profile_id "
                        "WHERE activation.provider='deepseek' "
                        "AND activation.environment=:environment ORDER BY "
                        "activation.created_at DESC,activation.id DESC LIMIT 1))"
                    ),
                    {
                        "run_id": run_id,
                        "version_id": document_version_id,
                        "environment": self._environment,
                    },
                )
            )

    async def create_fixed_canary_run(
        self, *, input_sha256: str
    ) -> tuple[UUID, UUID, QualificationPolicyBundle] | None:
        """Create one isolated SHADOW run only when every real-call gate is current."""

        now = datetime.now(UTC)
        run_id = uuid7()
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "INSERT INTO ai_pipeline_run("
                            "id,document_version_id,mode,status,input_sha256,started_at,"
                            "policy_bundle_id) "
                            "SELECT :run_id,version.id,'SHADOW','QUEUED',:input_hash,:now,"
                            "COALESCE(challenger.policy_bundle_id,active.policy_bundle_id) "
                            "FROM document doc JOIN document_version version "
                            "ON version.id=doc.current_version_id "
                            "JOIN raw_object raw ON raw.id=version.raw_object_id "
                            "JOIN source src ON src.id=doc.source_id "
                            "JOIN LATERAL(SELECT COALESCE(config.config_sha256,"
                            "source_policy.policy_version,'legacy-source-policy') AS version "
                            "FROM (SELECT 1) seed "
                            "LEFT JOIN LATERAL(SELECT stream_config.config_sha256 "
                            "FROM raw_object_capture capture "
                            "JOIN fetch_run fetch_row ON fetch_row.id=capture.fetch_run_id "
                            "JOIN stream_config_version stream_config "
                            "ON stream_config.id=fetch_row.stream_config_version_id "
                            "WHERE capture.raw_object_id=raw.id "
                            "ORDER BY capture.captured_at DESC LIMIT 1) config ON true "
                            "LEFT JOIN LATERAL(SELECT policy.policy_version "
                            "FROM source_policy policy WHERE policy.source_id=src.id "
                            "AND policy.status='VALID' ORDER BY policy.created_at DESC "
                            "LIMIT 1) source_policy ON true) stream_policy ON true "
                            "JOIN active_qualification_policy_v2 active "
                            "ON active.source_stream_policy_version=stream_policy.version "
                            "LEFT JOIN LATERAL(SELECT evaluation.policy_bundle_id "
                            "FROM qualification_policy_evaluation_v2 evaluation "
                            "JOIN qualification_policy_evaluation_invariant_v2 invariant "
                            "ON invariant.evaluation_id=evaluation.id "
                            "JOIN qualification_policy_bundle_v2 bundle "
                            "ON bundle.id=evaluation.policy_bundle_id "
                            "WHERE evaluation.mode='OFFLINE_REPLAY' "
                            "AND evaluation.gate_passed "
                            "AND evaluation.authorizes_production=false "
                            "AND evaluation.total_cases>0 "
                            "AND invariant.terminal_cases=evaluation.total_cases "
                            "AND evaluation.precision_bps>=9000 "
                            "AND evaluation.recall_bps>=9000 "
                            "AND evaluation.locked_negative_leaks=0 "
                            "AND evaluation.schema_valid_bps=10000 "
                            "AND evaluation.new_owner_semantic_tasks=0 "
                            "AND invariant.authority_violations=0 "
                            "AND invariant.evidence_violations=0 "
                            "AND invariant.projection_failures=0 "
                            "AND bundle.source_stream_policy_version=stream_policy.version "
                            "AND bundle.ai_provider='deepseek' "
                            "AND bundle.ai_model='deepseek-v4-flash' "
                            "AND bundle.prompt_version='autonomous-classify-2.7.0' "
                            "AND bundle.schema_version='autonomous-classify-output-2.0.0' "
                            "AND evaluation.policy_bundle_id<>active.policy_bundle_id "
                            "ORDER BY evaluation.evaluated_at DESC,evaluation.id DESC LIMIT 1) "
                            "challenger ON true "
                            "JOIN LATERAL(SELECT assessment.verdict "
                            "FROM source_admission_assessment_v2 assessment "
                            "WHERE assessment.source_id=src.id "
                            "ORDER BY assessment.assessed_at DESC,assessment.id DESC LIMIT 1) "
                            "latest_assessment ON latest_assessment.verdict='ADMIT' "
                            "WHERE raw.scan_status='CLEAN' "
                            "AND version.execution_domain IN ('TRIAL','PRODUCTION') "
                            "AND src.desired_enabled AND src.manual_disabled_at IS NULL "
                            "AND src.runtime_state='RUNNING' "
                            "AND NOT EXISTS(SELECT 1 "
                            "FROM qualification_shadow_decision_v2 prior_shadow "
                            "WHERE prior_shadow.document_version_id=version.id "
                            "AND prior_shadow.policy_bundle_id="
                            "COALESCE(challenger.policy_bundle_id,active.policy_bundle_id)) "
                            "AND EXISTS(SELECT 1 FROM ai_budget_policy budget "
                            "WHERE budget.provider='deepseek' AND budget.active) "
                            "ORDER BY version.acquired_at DESC,version.id DESC LIMIT 1 "
                            "RETURNING id,document_version_id,policy_bundle_id"
                        ),
                        {"run_id": run_id, "input_hash": input_sha256, "now": now},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        policy = await self.load_policy_bundle(cast(UUID, row["id"]))
        return cast(UUID, row["id"]), cast(UUID, row["document_version_id"]), policy

    async def bind_shadow_input(self, run_id: UUID, *, input_sha256: str) -> None:
        """Replace the selection placeholder with the real document input digest."""

        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    "UPDATE ai_pipeline_run SET input_sha256=:input_hash "
                    "WHERE id=:run_id AND mode='SHADOW' "
                    "AND status IN ('QUEUED','PREPARING')"
                ),
                {"run_id": run_id, "input_hash": input_sha256},
            )
            if result.rowcount != 1:
                raise RuntimeError("SHADOW_INPUT_BINDING_INVALID")

    async def load_policy_bundle(self, run_id: UUID) -> QualificationPolicyBundle:
        """Load the immutable bundle selected when the run was created."""

        async with self._engine.connect() as connection:
            facts = (
                (
                    await connection.execute(
                        text(
                            "SELECT bundle.policy_version,bundle.global_rule_version,"
                            "bundle.source_stream_policy_version,bundle.ai_provider,"
                            "bundle.ai_model,bundle.prompt_version,bundle.schema_version,"
                            "bundle.code_version,bundle.bundle_sha256,bundle.policy_payload "
                            "FROM ai_pipeline_run run JOIN qualification_policy_bundle_v2 bundle "
                            "ON bundle.id=run.policy_bundle_id WHERE run.id=:run_id"
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .one()
            )
        return _policy_bundle_from_facts(facts)

    async def complete_fixed_canary(
        self,
        *,
        run_id: UUID,
        succeeded: bool,
        failure_code: str | None = None,
    ) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    "UPDATE ai_pipeline_run SET status=:status,completed_at=:now,"
                    "failure_code=:failure WHERE id=:id AND mode='SHADOW' "
                    "AND status IN ('QUEUED','PREPARING')"
                ),
                {
                    "id": run_id,
                    "status": "SUCCEEDED" if succeeded else "FAILED",
                    "failure": failure_code,
                    "now": datetime.now(UTC),
                },
            )
            if result.rowcount != 1:
                raise RuntimeError("AI_CANARY_STATE_CONFLICT")

    async def append_campaign_event(
        self,
        *,
        campaign_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        """Append an explicitly labelled acceptance-only fault-injection fact."""

        payload_text = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO engineering_closeout_campaign_event_v2("
                    "id,campaign_id,event_type,payload,payload_sha256,occurred_at) "
                    "VALUES(:id,:campaign,:event,CAST(:payload AS jsonb),:hash,:now) "
                    "ON CONFLICT(campaign_id,event_type,payload_sha256) DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "campaign": campaign_id,
                    "event": event_type,
                    "payload": payload_text,
                    "hash": sha256(payload_text.encode()).hexdigest(),
                    "now": datetime.now(UTC),
                },
            )

    async def schedule_compensation(
        self,
        *,
        run_id: UUID,
        reason_code: str,
        attempt_count: int,
    ) -> int | None:
        """Persist one bounded retry schedule and return its delay in seconds."""

        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,status,started_at FROM ai_compensation_run_v2 "
                            "WHERE original_pipeline_run_id=:run_id FOR UPDATE"
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            started_at = (
                cast(datetime, existing["started_at"])
                if existing is not None and existing["status"] in {"PENDING", "PROCESSING"}
                else now
            )
            state, available_at = compensation_plan(
                reason_code,
                attempt_count=attempt_count,
                started_at=started_at,
                now=now,
            )
            if state != "PENDING" or available_at is None:
                if existing is not None:
                    await connection.execute(
                        text(
                            "UPDATE ai_compensation_run_v2 SET status='DEAD_LETTER',"
                            "completed_at=:now WHERE id=:id"
                        ),
                        {"id": existing["id"], "now": now},
                    )
                return None
            if existing is None:
                await connection.execute(
                    text(
                        "INSERT INTO ai_compensation_run_v2("
                        "id,original_pipeline_run_id,recovery_pipeline_run_id,reason_code,"
                        "status,attempt_count,available_at,started_at,completed_at) VALUES("
                        ":id,:run_id,NULL,:reason,'PENDING',:attempts,:available,:started,NULL)"
                    ),
                    {
                        "id": uuid7(),
                        "run_id": run_id,
                        "reason": reason_code,
                        "attempts": attempt_count + 1,
                        "available": available_at,
                        "started": started_at,
                    },
                )
            else:
                await connection.execute(
                    text(
                        "UPDATE ai_compensation_run_v2 SET reason_code=:reason,"
                        "status='PENDING',attempt_count=:attempts,available_at=:available,"
                        "started_at=:started,completed_at=NULL WHERE id=:id"
                    ),
                    {
                        "id": existing["id"],
                        "reason": reason_code,
                        "attempts": attempt_count + 1,
                        "available": available_at,
                        "started": started_at,
                    },
                )
        return max(0, int((available_at - now).total_seconds()))

    async def complete_compensation(self, *, run_id: UUID, succeeded: bool) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE ai_compensation_run_v2 SET status=:status,completed_at=:now "
                    "WHERE original_pipeline_run_id=:run_id "
                    "AND status IN ('PENDING','PROCESSING')"
                ),
                {
                    "run_id": run_id,
                    "status": "SUCCEEDED" if succeeded else "DEAD_LETTER",
                    "now": datetime.now(UTC),
                },
            )

    async def record_security(self, document: PreparationDocument, detected: bool) -> None:
        joined = "\n".join(block.text for block in document.blocks)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO ai_security_scan(id,document_version_id,input_sha256,"
                    "scanner_version,detected,patterns,risk_level,created_at) VALUES("
                    ":id,:version_id,:input_hash,'prompt-injection-scanner-1.0.0',"
                    ":detected,ARRAY[]::varchar[],:risk,now())"
                ),
                {
                    "id": uuid7(),
                    "version_id": document.document_version_id,
                    "input_hash": sha256(joined.encode()).hexdigest(),
                    "detected": detected,
                    "risk": "R4" if detected else "R1",
                },
            )

    async def transition(self, run_id: UUID, status: str) -> None:
        allowed_previous = {
            "CLASSIFYING": "PREPARING",
            "EXTRACTING": "CLASSIFYING",
            "EVIDENCE_GATING": "EXTRACTING",
            "SUMMARIZING": "EVIDENCE_GATING",
            "VERIFYING": "SUMMARIZING",
            "SUCCEEDED": "SUMMARIZING",
        }
        previous = allowed_previous.get(status)
        if previous is None:
            raise ValueError("pipeline transition is invalid")
        async with self._engine.begin() as connection:
            statement = (
                text(
                    "UPDATE ai_pipeline_run SET status=:status WHERE id=:run_id "
                    "AND status IN ('CLASSIFYING','SUMMARIZING','VERIFYING')"
                )
                if status == "SUCCEEDED"
                else text(
                    "UPDATE ai_pipeline_run SET status=:status WHERE id=:run_id "
                    "AND status=:previous"
                )
            )
            result = await connection.execute(
                statement,
                {"status": status, "run_id": run_id, "previous": previous},
            )
            if result.rowcount != 1:
                current = await connection.scalar(
                    text("SELECT status FROM ai_pipeline_run WHERE id=:run_id"),
                    {"run_id": run_id},
                )
                if current != status:
                    raise RuntimeError("AI_PIPELINE_STATE_CONFLICT")
            if status == "SUCCEEDED":
                await connection.execute(
                    text("SELECT finalize_source_content_ai_run(:run_id,:status,NULL,:now)"),
                    {
                        "run_id": run_id,
                        "status": status,
                        "now": datetime.now(UTC),
                    },
                )

    async def reserve(self, run_id: UUID, step: AiStep, attempt: int) -> object:
        reservation_id = uuid7()
        async with self._engine.begin() as connection:
            controlled_run_id = await connection.scalar(
                text("SELECT controlled_run_id FROM ai_pipeline_run WHERE id=:run_id"),
                {"run_id": run_id},
            )
            if controlled_run_id is not None:
                budget_sql = (
                    "SELECT reservation_id,alert_crossed FROM reserve_controlled_ai_budget("
                    ":id,:run_id,:step,:attempt,12,:controlled_cost_reservation_microusd,:now)"
                )
            else:
                budget_sql = (
                    "SELECT reservation_id,alert_crossed FROM reserve_ai_budget("
                    ":id,:run_id,:step,:attempt,12,:now)"
                )
            row = (
                (
                    await connection.execute(
                        text(budget_sql),
                        {
                            "id": reservation_id,
                            "run_id": run_id,
                            "step": step.value,
                            "attempt": attempt,
                            "controlled_cost_reservation_microusd": 75_000,
                            "now": datetime.now(UTC),
                        },
                    )
                )
                .mappings()
                .one()
            )
        if row["alert_crossed"]:
            logger.warning(
                "ai_monthly_budget_alert_crossed",
                extra={"pipeline_run_id": str(run_id)},
            )
        return cast(UUID, row["reservation_id"])

    async def settle(self, reservation: object, response: ModelResponse | None) -> None:
        if not isinstance(reservation, UUID):
            raise ValueError("budget reservation identifier is invalid")
        async with self._engine.begin() as connection:
            controlled_run_id = await connection.scalar(
                text("SELECT controlled_run_id FROM ai_budget_reservation WHERE id=:id"),
                {"id": reservation},
            )
            await connection.execute(
                text(
                    "SELECT settle_controlled_ai_budget(:id,:cost,:status,:now)"
                    if controlled_run_id is not None
                    else "SELECT settle_ai_budget(:id,:cost,:status,:now)"
                ),
                {
                    "id": reservation,
                    "cost": response.cost_microusd if response is not None else 0,
                    "status": "SETTLED" if response is not None else "UNKNOWN",
                    "now": datetime.now(UTC),
                },
            )

    async def release(self, reservation: object) -> None:
        if not isinstance(reservation, UUID):
            raise ValueError("budget reservation identifier is invalid")
        async with self._engine.begin() as connection:
            controlled_run_id = await connection.scalar(
                text("SELECT controlled_run_id FROM ai_budget_reservation WHERE id=:id"),
                {"id": reservation},
            )
            await connection.execute(
                text(
                    "SELECT release_controlled_ai_budget(:id,:now)"
                    if controlled_run_id is not None
                    else "SELECT release_ai_budget(:id,:now)"
                ),
                {"id": reservation, "now": datetime.now(UTC)},
            )

    async def append_step(
        self,
        run_id: UUID,
        step: AiStep,
        attempt: int,
        kind: str,
        response: ModelResponse,
        input_sha256: str,
        prompt_version: str | None = None,
        schema_version: str | None = None,
    ) -> UUID:
        return await self._append_step_row(
            run_id=run_id,
            step=step,
            attempt=attempt,
            kind=kind,
            response=response,
            status="SUCCEEDED",
            error_code=None,
            input_sha256=input_sha256,
            prompt_version=prompt_version,
            schema_version=schema_version,
        )

    async def prepare_t06_content_summary(
        self, document: PreparationDocument, *, append_processing: bool
    ) -> ModelRequest:
        candidate_repository = PostgresContentCandidateRepository(self._engine)
        version_id = document.document_version_id
        claims = await candidate_repository.load_active_claims(version_id)
        request = build_content_summary_request(claims, current_document_version_id=version_id)
        if append_processing:
            await self.append_summary_state(
                document,
                status="PROCESSING",
                reason_code="SUMMARY_DISPATCHED",
            )
        return request

    async def materialize_t06_content_summary(
        self,
        document: PreparationDocument,
        *,
        request: ModelRequest,
        summary: StructuredSummaryCandidate,
    ) -> UUID:
        candidate_repository = PostgresContentCandidateRepository(self._engine)
        version_id = document.document_version_id
        claims = await candidate_repository.load_active_claims(version_id)
        candidate = build_content_candidate(
            claims=claims,
            current_document_version_id=version_id,
            summary=summary,
        )
        return await candidate_repository.append_candidate(
            candidate,
            ContentSummaryRequest(
                document_version_id=version_id,
                model="deepseek-v4-flash",
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                payload=cast(dict[str, Any], json.loads(request.user_prompt)),
                response_schema=request.response_schema,
                input_sha256=request.input_sha256,
            ),
            create_review_case=False,
        )

    async def append_summary_state(
        self,
        document: PreparationDocument,
        *,
        status: str,
        reason_code: str,
        candidate_id: UUID | None = None,
    ) -> UUID:
        now = datetime.now(UTC)
        state_id = uuid7()
        async with self._engine.begin() as connection:
            event_id = await connection.scalar(
                text(
                    "SELECT binding.event_id FROM intelligence_item item "
                    "JOIN event_identity_binding binding ON binding.item_id=item.id "
                    "WHERE item.current_document_version_id=:version_id"
                ),
                {"version_id": document.document_version_id},
            )
            if event_id is None:
                raise RuntimeError("CURRENT_EVENT_REQUIRED")
            persisted = await connection.scalar(
                text(
                    "INSERT INTO ai_summary_state_event_v2("
                    "id,event_id,document_version_id,pipeline_run_id,candidate_id,status,"
                    "reason_code,created_at) VALUES(:id,:event_id,:version_id,:run_id,"
                    ":candidate_id,:status,:reason,:now) ON CONFLICT("
                    "pipeline_run_id,status,reason_code) DO NOTHING RETURNING id"
                ),
                {
                    "id": state_id,
                    "event_id": event_id,
                    "version_id": document.document_version_id,
                    "run_id": document.run_id,
                    "candidate_id": candidate_id,
                    "status": status,
                    "reason": reason_code,
                    "now": now,
                },
            )
            newly_persisted = persisted is not None
            if persisted is None:
                persisted = await connection.scalar(
                    text(
                        "SELECT id FROM ai_summary_state_event_v2 WHERE "
                        "pipeline_run_id=:run_id AND status=:status AND reason_code=:reason"
                    ),
                    {"run_id": document.run_id, "status": status, "reason": reason_code},
                )
            if persisted is None:
                raise RuntimeError("SUMMARY_STATE_NOT_PERSISTED")
            state_id = UUID(str(persisted))
            await connection.execute(
                text(
                    "INSERT INTO ai_projection_refresh_outbox_v2("
                    "id,event_id,document_version_id,summary_state_event_id,status,"
                    "attempt_count,available_at,last_error_code,created_at,updated_at) "
                    "VALUES(:id,:event_id,:version_id,:state_id,'PENDING',0,:now,NULL,:now,:now) "
                    "ON CONFLICT(summary_state_event_id) DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "event_id": event_id,
                    "version_id": document.document_version_id,
                    "state_id": state_id,
                    "now": now,
                },
            )
        if newly_persisted:
            T06_AI_SUMMARY_STATE_TRANSITIONS.labels(state=status).inc()
        return state_id

    async def record_approved_content_success(
        self,
        document: PreparationDocument,
        *,
        step_run_id: UUID,
        provider: str,
        model: str,
        request: ModelRequest,
    ) -> UUID:
        """Record availability evidence only for a legal durable content handoff."""

        if provider != "deepseek" or model != "deepseek-v4-flash":
            raise RuntimeError("RUNTIME_PROVIDER_CONFIG_MISMATCH")
        now = datetime.now(UTC)
        success_id = uuid7()
        async with self._engine.begin() as connection:
            persisted = await connection.scalar(
                text(
                    "INSERT INTO ai_approved_content_success_v2("
                    "id,pipeline_run_id,ai_step_run_id,document_version_id,provider,model,"
                    "environment,model_profile_version,prompt_version,schema_version,"
                    "success_kind,succeeded_at) SELECT :id,run.id,step.id,run.document_version_id,"
                    ":provider,:model,:environment,profile.version,prompt.version,schema.version,"
                    "'APPROVED_CONTENT',:now FROM ai_pipeline_run run "
                    "JOIN ai_step_run step ON step.id=:step_id AND step.pipeline_run_id=run.id "
                    "JOIN ai_model_profile profile ON profile.id=step.model_profile_id "
                    "JOIN ai_prompt_version prompt ON prompt.id=step.prompt_version_id "
                    "JOIN ai_schema_version schema ON schema.id=step.schema_version_id "
                    "JOIN source_content_outbox handoff ON handoff.pipeline_run_id=run.id "
                    "JOIN document_version version ON version.id=run.document_version_id "
                    "JOIN raw_object raw ON raw.id=version.raw_object_id "
                    "JOIN document document ON document.id=version.document_id "
                    "JOIN source source ON source.id=document.source_id "
                    "WHERE run.id=:run_id AND run.document_version_id=:version_id "
                    "AND step.step='SUMMARIZE' AND step.status='SUCCEEDED' "
                    "AND prompt.version=:prompt AND schema.version=:schema "
                    "AND profile.version=:profile AND handoff.status='WAITING_AI' "
                    "AND document.current_version_id=version.id AND raw.scan_status='CLEAN' "
                    "AND EXISTS(SELECT 1 FROM raw_object_security_fact security "
                    "WHERE security.raw_object_id=raw.id AND security.status='CLEAN') "
                    "AND NOT EXISTS(SELECT 1 FROM raw_object_security_fact security "
                    "WHERE security.raw_object_id=raw.id "
                    "AND security.status IN ('REJECTED','QUARANTINED')) "
                    "AND version.execution_domain IN ('TRIAL','PRODUCTION') "
                    "AND source.desired_enabled AND source.manual_disabled_at IS NULL "
                    "AND source.runtime_state='RUNNING' "
                    "AND 'ADMIT'=(SELECT assessment.verdict "
                    "FROM source_admission_assessment_v2 assessment "
                    "WHERE assessment.source_id=source.id ORDER BY assessment.assessed_at DESC,"
                    "assessment.id DESC LIMIT 1) "
                    "AND EXISTS(SELECT 1 FROM ai_budget_policy budget "
                    "LEFT JOIN ai_budget_month month ON month.policy_id=budget.id "
                    "AND month.month_start=date_trunc('month',now())::date "
                    "WHERE budget.provider='deepseek' AND budget.active "
                    "AND COALESCE(month.reserved_points,0)+COALESCE(month.settled_points,0)"
                    "<budget.monthly_points) "
                    "AND true=(SELECT activation.active AND activation.model_profile_id=profile.id "
                    "FROM ai_provider_activation activation WHERE activation.provider=:provider "
                    "AND activation.environment=:environment ORDER BY activation.created_at DESC,"
                    "activation.id DESC LIMIT 1) "
                    "ON CONFLICT(ai_step_run_id) DO NOTHING RETURNING id"
                ),
                {
                    "id": success_id,
                    "run_id": document.run_id,
                    "version_id": document.document_version_id,
                    "step_id": step_run_id,
                    "provider": provider,
                    "model": model,
                    "environment": self._environment,
                    "prompt": request.prompt_version,
                    "schema": request.schema_version,
                    "profile": request.model_profile,
                    "now": now,
                },
            )
            if persisted is None:
                persisted = await connection.scalar(
                    text(
                        "SELECT id FROM ai_approved_content_success_v2 "
                        "WHERE ai_step_run_id=:step_id"
                    ),
                    {"step_id": step_run_id},
                )
            if persisted is None:
                raise RuntimeError("APPROVED_CONTENT_SUCCESS_NOT_AUTHORIZED")
            success_id = UUID(str(persisted))
            await connection.execute(
                text(
                    "INSERT INTO ai_runtime_health_v2(id,provider,model,environment,"
                    "worker_heartbeat_at,queue_healthy,budget_healthy,"
                    "last_real_schema_success_at,observed_at) VALUES("
                    ":id,:provider,:model,:environment,:now,true,true,:now,:now) "
                    "ON CONFLICT(provider,environment) DO UPDATE SET model=EXCLUDED.model,"
                    "worker_heartbeat_at=EXCLUDED.worker_heartbeat_at,queue_healthy=true,"
                    "budget_healthy=true,last_real_schema_success_at=EXCLUDED.last_real_schema_success_at,"
                    "observed_at=EXCLUDED.observed_at"
                ),
                {
                    "id": uuid7(),
                    "provider": provider,
                    "model": model,
                    "environment": self._environment,
                    "now": now,
                },
            )
        return success_id

    async def record_runtime_health(self, *, provider: str, model: str) -> None:
        """Compatibility heartbeat; it never creates real-content success evidence."""

        now = datetime.now(UTC)
        await self.record_runtime_observation(
            provider=provider,
            model=model,
            worker_heartbeat_at=now,
        )

    async def record_runtime_observation(
        self,
        *,
        provider: str,
        model: str,
        worker_heartbeat_at: datetime,
    ) -> None:
        """Append one content-free queue/budget observation for closeout evidence."""

        if provider != "deepseek":
            raise RuntimeError("RUNTIME_PROVIDER_MISMATCH")
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            budget_healthy = bool(
                await connection.scalar(
                    text(
                        "SELECT COALESCE(bool_and(COALESCE(month.reserved_points,0)+"
                        "COALESCE(month.settled_points,0)<policy.monthly_points),false) "
                        "FROM ai_budget_policy policy LEFT JOIN ai_budget_month month "
                        "ON month.policy_id=policy.id AND month.month_start=date_trunc("
                        "'month',CAST(:now AS timestamptz))::date WHERE policy.active "
                        "AND policy.provider=:provider"
                    ),
                    {"provider": provider, "now": now},
                )
            )
            last_success = await connection.scalar(
                text(
                    "SELECT max(succeeded_at) FROM ai_approved_content_success_v2 "
                    "WHERE provider=:provider AND model=:model AND environment=:environment "
                    "AND success_kind='APPROVED_CONTENT'"
                ),
                {"provider": provider, "model": model, "environment": self._environment},
            )
            latest_balance = await connection.scalar(
                text(
                    "SELECT external_balance_state FROM ai_runtime_observation_v2 "
                    "WHERE provider=:provider AND environment=:environment "
                    "ORDER BY observed_at DESC,id DESC LIMIT 1"
                ),
                {"provider": provider, "environment": self._environment},
            )
            balance = "UNKNOWN"
            if latest_balance == "INSUFFICIENT":
                balance = "INSUFFICIENT"
            elif last_success is not None and now - last_success <= timedelta(hours=24):
                balance = "SUFFICIENT_AT_LAST_REAL_CALL"
            await connection.execute(
                text(
                    "INSERT INTO ai_runtime_observation_v2("
                    "id,provider,model,environment,worker_heartbeat_at,queue_healthy,"
                    "budget_healthy,last_real_schema_success_at,external_balance_state,"
                    "observed_at) VALUES(:id,:provider,:model,:environment,:heartbeat,true,"
                    ":budget,:last_success,:balance,:now)"
                ),
                {
                    "id": uuid7(),
                    "provider": provider,
                    "model": model,
                    "environment": self._environment,
                    "heartbeat": worker_heartbeat_at,
                    "budget": budget_healthy,
                    "last_success": last_success,
                    "balance": balance,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO ai_runtime_health_v2(id,provider,model,environment,"
                    "worker_heartbeat_at,queue_healthy,budget_healthy,"
                    "last_real_schema_success_at,observed_at) VALUES("
                    ":id,:provider,:model,:environment,:heartbeat,true,:budget,"
                    ":last_success,:now) ON CONFLICT(provider,environment) DO UPDATE SET "
                    "model=EXCLUDED.model,worker_heartbeat_at=EXCLUDED.worker_heartbeat_at,"
                    "queue_healthy=true,budget_healthy=EXCLUDED.budget_healthy,"
                    "observed_at=EXCLUDED.observed_at"
                ),
                {
                    "id": uuid7(),
                    "provider": provider,
                    "model": model,
                    "environment": self._environment,
                    "heartbeat": worker_heartbeat_at,
                    "budget": budget_healthy,
                    "last_success": last_success,
                    "now": now,
                },
            )

    async def record_balance_insufficient(self, *, provider: str, model: str) -> None:
        """Persist a provider balance rejection from a real attempted call."""

        if provider != "deepseek":
            raise RuntimeError("RUNTIME_PROVIDER_MISMATCH")
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            last_success = await connection.scalar(
                text(
                    "SELECT max(succeeded_at) FROM ai_approved_content_success_v2 "
                    "WHERE provider=:provider AND model=:model AND environment=:environment "
                    "AND success_kind='APPROVED_CONTENT'"
                ),
                {"provider": provider, "model": model, "environment": self._environment},
            )
            await connection.execute(
                text(
                    "INSERT INTO ai_runtime_observation_v2("
                    "id,provider,model,environment,worker_heartbeat_at,queue_healthy,"
                    "budget_healthy,last_real_schema_success_at,external_balance_state,"
                    "observed_at) VALUES(:id,:provider,:model,:environment,:now,true,true,"
                    ":last_success,'INSUFFICIENT',:now)"
                ),
                {
                    "id": uuid7(),
                    "provider": provider,
                    "model": model,
                    "environment": self._environment,
                    "last_success": last_success,
                    "now": now,
                },
            )

    async def append_failed_step(
        self,
        run_id: UUID,
        step: AiStep,
        attempt: int,
        kind: str,
        error_code: str,
        input_sha256: str | None,
        billing_response: ModelResponse | None = None,
        prompt_version: str | None = None,
        schema_version: str | None = None,
    ) -> None:
        await self._append_step_row(
            run_id=run_id,
            step=step,
            attempt=attempt,
            kind=kind,
            response=None,
            status="FAILED",
            error_code=error_code,
            input_sha256=input_sha256,
            billing_response=billing_response,
            prompt_version=prompt_version,
            schema_version=schema_version,
        )

    async def _append_step_row(
        self,
        *,
        run_id: UUID,
        step: AiStep,
        attempt: int,
        kind: str,
        response: ModelResponse | None,
        status: str,
        error_code: str | None,
        input_sha256: str | None = None,
        billing_response: ModelResponse | None = None,
        prompt_version: str | None = None,
        schema_version: str | None = None,
    ) -> UUID:
        if response is not None and not await self.authorize_model_call(run_id):
            raise PermissionError("AI_RUNTIME_AUTHORIZATION_DENIED")
        async with self._engine.begin() as connection:
            step_run_id = await self._append_step_row_in_connection(
                connection,
                run_id=run_id,
                step=step,
                attempt=attempt,
                kind=kind,
                response=response,
                status=status,
                error_code=error_code,
                input_sha256=input_sha256,
                billing_response=billing_response,
                prompt_version=prompt_version,
                schema_version=schema_version,
            )
        return step_run_id

    async def _append_step_row_in_connection(
        self,
        connection: Any,
        *,
        run_id: UUID,
        step: AiStep,
        attempt: int,
        kind: str,
        response: ModelResponse | None,
        status: str,
        error_code: str | None,
        input_sha256: str | None,
        billing_response: ModelResponse | None,
        prompt_version: str | None,
        schema_version: str | None,
    ) -> UUID:
        registry = (
            (
                await connection.execute(
                    text(_REGISTRY_SQL),
                    {
                        "prompt_version": prompt_version
                        or (
                            f"pers07-{step.value.lower()}-v1"
                            if step in {AiStep.SUMMARIZE, AiStep.VERIFY}
                            else f"ai01-{step.value.lower()}-v1"
                        ),
                        "schema_version": schema_version
                        or (
                            f"{step.value.lower()}-output-v2"
                            if step in {AiStep.SUMMARIZE, AiStep.VERIFY}
                            else f"{step.value.lower()}-output-v1"
                        ),
                        "model_version": _MODEL_PROFILE_VERSION,
                    },
                )
            )
            .mappings()
            .one()
        )
        input_hash = input_sha256 or await connection.scalar(
            text("SELECT input_sha256 FROM ai_pipeline_run WHERE id=:run_id"),
            {"run_id": run_id},
        )
        usage_source = response or billing_response
        usage = usage_source.usage if usage_source is not None else None
        step_run_id = uuid7()
        await connection.execute(
            text(_INSERT_STEP_SQL),
            {
                "id": step_run_id,
                "run_id": run_id,
                "step": step.value,
                "attempt": attempt,
                "prompt_id": registry["prompt_id"],
                "schema_id": registry["schema_id"],
                "model_id": registry["model_id"],
                "input_hash": input_hash,
                "raw_output": response.raw_output if response else None,
                "validated_output": (
                    json.dumps(response.output, ensure_ascii=False) if response else None
                ),
                "status": status,
                "input_tokens": usage.input_tokens if usage else 0,
                "output_tokens": usage.output_tokens if usage else 0,
                "cache_hit": usage.cache_hit_tokens if usage else 0,
                "cache_miss": usage.cache_miss_tokens if usage else 0,
                "cost": usage_source.cost_microusd if usage_source else 0,
                "latency": usage_source.latency_ms if usage_source else 0,
                "request_id": usage_source.provider_request_id if usage_source else None,
                "finish_reason": usage_source.finish_reason if usage_source else None,
                "kind": kind,
                "error_code": error_code,
            },
        )
        return step_run_id

    async def complete_verified_content(
        self,
        document: PreparationDocument,
        *,
        response: ModelResponse,
        request: ModelRequest,
        attempt: int,
        kind: str,
        provider: str,
        model: str,
    ) -> UUID:
        """Atomically persist VERIFY, evidence excerpt, handoff and projection outbox."""

        if provider != "deepseek" or model != "deepseek-v4-flash":
            raise RuntimeError("RUNTIME_PROVIDER_CONFIG_MISMATCH")
        if not await self.authorize_model_call(
            document.run_id,
            document_version_id=document.document_version_id,
        ):
            raise PermissionError("AI_RUNTIME_AUTHORIZATION_DENIED")
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            pipeline_status = await connection.scalar(
                text(
                    "SELECT status FROM ai_pipeline_run "
                    "WHERE id=:run_id AND document_version_id=:version_id "
                    "FOR UPDATE"
                ),
                {
                    "run_id": document.run_id,
                    "version_id": document.document_version_id,
                },
            )
            if pipeline_status != "VERIFYING":
                raise RuntimeError("VERIFY_HANDOFF_STATE_CONFLICT")
            handoff_status = await connection.scalar(
                text("SELECT lock_source_content_ai_handoff(:run_id,:version_id)"),
                {
                    "run_id": document.run_id,
                    "version_id": document.document_version_id,
                },
            )
            if handoff_status != "WAITING_AI":
                raise RuntimeError("VERIFY_HANDOFF_NOT_CURRENT")
            authority = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT candidate.id AS candidate_id,candidate.event_id,
                              candidate.accepted_claim_set_sha256,
                              candidate.source_excerpt,candidate.claim_ids,
                              candidate.source_excerpt_claim_ids,
                              candidate.evidence_locators,candidate.claim_basis,
                              COALESCE(array_agg(claim.id ORDER BY claim.id)
                                FILTER (WHERE claim.id IS NOT NULL),'{}'::uuid[])
                                AS current_claim_ids
                            FROM ai_pipeline_run run
                            JOIN document_version version
                              ON version.id=run.document_version_id
                             AND version.execution_domain IN ('TRIAL','PRODUCTION')
                            JOIN document document
                              ON document.id=version.document_id
                             AND document.current_version_id=version.id
                            JOIN source source ON source.id=document.source_id
                            JOIN content_preparation_candidate_v2 candidate
                              ON candidate.document_version_id=version.id
                            LEFT JOIN content_preparation_invalidation_v2 invalidation
                              ON invalidation.candidate_id=candidate.id
                            LEFT JOIN claim
                              ON claim.document_version_id=version.id
                             AND claim.verification_status='ACCEPTED'
                             AND (
                               COALESCE(claim.acceptance_method,'HUMAN_REVIEW')
                                 <>'AUTOMATED_EVIDENCE_GATE'
                               OR 'ACTIVE'=(SELECT state.state
                                 FROM automatic_evidence_fact_state_event state
                                 WHERE state.claim_id=claim.id
                                 ORDER BY state.created_at DESC,state.id DESC LIMIT 1)
                             )
                            WHERE run.id=:run_id
                              AND run.document_version_id=:version_id
                              AND invalidation.id IS NULL AND source.desired_enabled
                              AND source.manual_disabled_at IS NULL
                              AND source.runtime_state='RUNNING'
                              AND 'ADMIT'=(SELECT assessment.verdict
                                FROM source_admission_assessment_v2 assessment
                                WHERE assessment.source_id=source.id
                                ORDER BY assessment.assessed_at DESC,assessment.id DESC
                                LIMIT 1)
                            GROUP BY candidate.id
                            ORDER BY candidate.created_at DESC,candidate.id DESC
                            LIMIT 1
                            """
                        ),
                        {
                            "run_id": document.run_id,
                            "version_id": document.document_version_id,
                        },
                    )
                )
                .mappings()
                .one()
            )
            if list(authority["claim_ids"]) != list(authority["current_claim_ids"]):
                raise RuntimeError("VERIFY_ACCEPTED_CLAIM_SET_CHANGED")
            verify_step_run_id = await self._append_step_row_in_connection(
                connection,
                run_id=document.run_id,
                step=AiStep.VERIFY,
                attempt=attempt,
                kind=kind,
                response=response,
                status="SUCCEEDED",
                error_code=None,
                input_sha256=request.input_sha256,
                billing_response=None,
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
            )
            excerpt_id = uuid7()
            await connection.execute(
                text(
                    """
                    INSERT INTO source_excerpt_version_v2(
                      id,event_id,document_version_id,accepted_claim_set_sha256,
                      source_excerpt,accepted_claim_ids,source_excerpt_claim_ids,
                      evidence_locators,claim_basis,created_at
                    ) VALUES(
                      :id,:event_id,:version_id,:claim_hash,:excerpt,:accepted_ids,
                      :excerpt_ids,:locators,:basis,:now
                    ) ON CONFLICT(document_version_id,accepted_claim_set_sha256) DO NOTHING
                    """
                ),
                {
                    "id": excerpt_id,
                    "event_id": authority["event_id"],
                    "version_id": document.document_version_id,
                    "claim_hash": authority["accepted_claim_set_sha256"],
                    "excerpt": authority["source_excerpt"],
                    "accepted_ids": list(authority["claim_ids"]),
                    "excerpt_ids": list(authority["source_excerpt_claim_ids"]),
                    "locators": list(authority["evidence_locators"]),
                    "basis": list(authority["claim_basis"]),
                    "now": now,
                },
            )
            success_id = await connection.scalar(
                text(
                    """
                    INSERT INTO ai_approved_content_success_v2(
                      id,pipeline_run_id,ai_step_run_id,document_version_id,provider,model,
                      environment,model_profile_version,prompt_version,schema_version,
                      success_kind,succeeded_at
                    )
                    SELECT :id,run.id,step.id,run.document_version_id,:provider,:model,
                      :environment,profile.version,prompt.version,schema.version,
                      'APPROVED_CONTENT',:now
                    FROM ai_pipeline_run run
                    JOIN ai_step_run step
                      ON step.id=:step_id AND step.pipeline_run_id=run.id
                    JOIN ai_model_profile profile ON profile.id=step.model_profile_id
                    JOIN ai_prompt_version prompt ON prompt.id=step.prompt_version_id
                    JOIN ai_schema_version schema ON schema.id=step.schema_version_id
                    JOIN source_content_outbox handoff ON handoff.pipeline_run_id=run.id
                    JOIN document_version version ON version.id=run.document_version_id
                    JOIN raw_object raw ON raw.id=version.raw_object_id
                    JOIN document document ON document.id=version.document_id
                    WHERE run.id=:run_id AND step.step='VERIFY'
                      AND step.status='SUCCEEDED' AND handoff.status='WAITING_AI'
                      AND document.current_version_id=version.id
                      AND raw.scan_status='CLEAN'
                      AND EXISTS(SELECT 1 FROM raw_object_security_fact security
                        WHERE security.raw_object_id=raw.id AND security.status='CLEAN')
                      AND NOT EXISTS(SELECT 1 FROM raw_object_security_fact security
                        WHERE security.raw_object_id=raw.id
                          AND security.status IN ('REJECTED','QUARANTINED'))
                    ON CONFLICT(ai_step_run_id) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "id": uuid7(),
                    "run_id": document.run_id,
                    "step_id": verify_step_run_id,
                    "provider": provider,
                    "model": model,
                    "environment": self._environment,
                    "now": now,
                },
            )
            if success_id is None:
                raise RuntimeError("APPROVED_CONTENT_SUCCESS_NOT_AUTHORIZED")
            state_id = uuid7()
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_summary_state_event_v2(
                      id,event_id,document_version_id,pipeline_run_id,candidate_id,status,
                      reason_code,created_at
                    ) VALUES(
                      :id,:event_id,:version_id,:run_id,:candidate_id,'SUCCEEDED',
                      'VERIFY_PASSED_SERVER_GATE',:now
                    )
                    """
                ),
                {
                    "id": state_id,
                    "event_id": authority["event_id"],
                    "version_id": document.document_version_id,
                    "run_id": document.run_id,
                    "candidate_id": authority["candidate_id"],
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_projection_refresh_outbox_v2(
                      id,event_id,document_version_id,summary_state_event_id,status,
                      attempt_count,available_at,last_error_code,created_at,updated_at
                    ) VALUES(
                      :id,:event_id,:version_id,:state_id,'PENDING',0,:now,NULL,:now,:now
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "event_id": authority["event_id"],
                    "version_id": document.document_version_id,
                    "state_id": state_id,
                    "now": now,
                },
            )
            updated = await connection.execute(
                text(
                    "UPDATE ai_pipeline_run SET status='SUCCEEDED',completed_at=:now "
                    "WHERE id=:run_id AND status='VERIFYING'"
                ),
                {"run_id": document.run_id, "now": now},
            )
            if updated.rowcount != 1:
                raise RuntimeError("VERIFY_PIPELINE_STATE_CONFLICT")
            await connection.execute(
                text("SELECT finalize_source_content_ai_run(:run_id,'SUCCEEDED',NULL,:now)"),
                {"run_id": document.run_id, "now": now},
            )
        T06_AI_SUMMARY_STATE_TRANSITIONS.labels(state="SUCCEEDED").inc()
        return cast(UUID, authority["candidate_id"])

    async def materialize(
        self,
        document: PreparationDocument,
        classification: dict[str, Any],
        extraction: dict[str, Any],
    ) -> int:
        primary_type = classification.get("primary_type")
        if primary_type not in {"DIGITAL_TRANSFORMATION", "SAFETY_INTELLIGENCE", "INDUSTRY_UPDATE"}:
            raise RuntimeError("AI01_CLASSIFICATION_OUT_OF_SCOPE")
        item_type, channel = _legacy_storage_class_for_primary_type(str(primary_type))
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"ai01-materialize:{document.document_version_id}"},
            )
            facts = (
                (
                    await connection.execute(
                        text(_MATERIALIZATION_FACTS_SQL),
                        {"version_id": document.document_version_id},
                    )
                )
                .mappings()
                .one()
            )
            item_id = facts["item_id"] or uuid7()
            if facts["item_id"] is None:
                await connection.execute(
                    text(_INSERT_ITEM_SQL),
                    {
                        "id": item_id,
                        "source_id": facts["source_id"],
                        "document_id": facts["document_id"],
                        "version_id": facts["version_id"],
                        "item_type": item_type,
                        "channel": channel,
                        "title": document.title,
                        "url": document.canonical_url,
                        "discovered_at": facts["first_discovered_at"],
                        "actor": _SYSTEM_ACTOR,
                        "now": now,
                    },
                )
                if item_type == "DIGITAL_CASE":
                    await connection.execute(
                        text(_INSERT_DIGITAL_PROFILE_SQL),
                        {"item_id": item_id, "now": now},
                    )
            event_id = await _ensure_personal_event(
                connection,
                item_id=item_id,
                item_type=item_type,
                title=document.title,
                actor_id=_SYSTEM_ACTOR,
                now=now,
            )
            classification_payload = json.dumps(
                classification,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            classification_sha256 = sha256(classification_payload.encode()).hexdigest()
            existing_qualification_hash = await connection.scalar(
                text(
                    "SELECT classification_sha256 FROM qualification_acceptance_v2 "
                    "WHERE document_version_id=:version_id"
                ),
                {"version_id": facts["version_id"]},
            )
            if existing_qualification_hash is None:
                await connection.execute(
                    text(
                        "INSERT INTO qualification_acceptance_v2("
                        "id,event_id,document_version_id,pipeline_run_id,primary_type,"
                        "engineering_objects,specialty_facets,equipment_domains,cross_type_tags,"
                        "classification_sha256,accepted_at) VALUES("
                        ":id,:event_id,:version_id,:run_id,:primary_type,:engineering_objects,"
                        ":specialty_facets,:equipment_domains,:cross_type_tags,:hash,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "event_id": event_id,
                        "version_id": facts["version_id"],
                        "run_id": document.run_id,
                        "primary_type": primary_type,
                        "engineering_objects": classification.get("engineering_objects", []),
                        "specialty_facets": classification.get("specialty_facets", []),
                        "equipment_domains": classification.get("equipment_domains", []),
                        "cross_type_tags": classification.get("cross_type_tags", []),
                        "hash": classification_sha256,
                        "now": now,
                    },
                )
            elif existing_qualification_hash != classification_sha256:
                raise RuntimeError("QUALIFICATION_ACCEPTANCE_CONFLICT")
            step_run_id = await connection.scalar(
                text(
                    "SELECT id FROM ai_step_run WHERE pipeline_run_id=:run_id "
                    "AND step='EXTRACT' AND status='SUCCEEDED' ORDER BY attempt DESC LIMIT 1"
                ),
                {"run_id": document.run_id},
            )
            if not isinstance(step_run_id, UUID):
                raise RuntimeError("EXTRACTION_STEP_MISSING")
            evidence_by_id = {entry["evidence_id"]: entry for entry in extraction["evidence"]}
            prompt_risk = bool(
                await connection.scalar(
                    text(
                        "SELECT detected FROM ai_security_scan "
                        "WHERE document_version_id=:version_id "
                        "ORDER BY created_at DESC,id DESC LIMIT 1"
                    ),
                    {"version_id": facts["version_id"]},
                )
            )
            unresolved_fields = frozenset(
                str(value)
                for value in await connection.scalars(
                    text(
                        "SELECT field_name FROM claim_conflict WHERE event_id=:event_id "
                        "AND status='PENDING_REVIEW'"
                    ),
                    {"event_id": event_id},
                )
            )
            gate = AutomaticEvidenceGate()
            accepted_count = 0
            judgment_count = 0
            for candidate in extraction["claims"]:
                candidate_evidence: dict[UUID, dict[str, Any]] = {}
                for evidence_id in candidate["evidence_ids"]:
                    evidence = evidence_by_id.get(evidence_id)
                    if evidence is None:
                        continue
                    block = (
                        (
                            await connection.execute(
                                text(_BLOCK_FACT_SQL),
                                {"block_id": UUID(evidence["document_block_id"])},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    start = str(block["normalized_text"]).find(evidence["excerpt"])
                    if start < 0:
                        continue
                    persisted_id = uuid7()
                    candidate_evidence[persisted_id] = {
                        "candidate": evidence,
                        "block": block,
                        "start": start,
                    }
                attribution = (
                    document.source_name
                    if candidate.get("claim_status") == "REPORTED_CLAIM"
                    else None
                )
                gate_candidate = AutomaticEvidenceCandidate(
                    candidate_id=str(candidate["claim_id"]),
                    field=str(candidate["field"]),
                    value=candidate["value"],
                    confidence_bps=round(float(candidate["confidence"]) * 10_000),
                    evidence_ids=list(candidate_evidence),
                    attribution=attribution,
                    origin="MODEL",
                )
                gate_context = AutomaticEvidenceContext(
                    document_version_id=facts["version_id"],
                    evidence={
                        evidence_uuid: EvidenceGateEvidence(
                            document_version_id=facts["version_id"],
                            excerpt=row["candidate"]["excerpt"],
                            active=True,
                        )
                        for evidence_uuid, row in candidate_evidence.items()
                    },
                    official_first_party=str(document.source_code).startswith("GOV-"),
                    unresolved_conflict_fields=unresolved_fields,
                    prompt_injection_risk=prompt_risk,
                    evaluated_at=now,
                )
                decision = gate.evaluate(gate_candidate, gate_context)
                if isinstance(decision, AiJudgment):
                    judgment_count += 1
                    judgment_id = uuid7()
                    await connection.execute(
                        text(_INSERT_AI_JUDGMENT_SQL),
                        {
                            "id": judgment_id,
                            "item_id": item_id,
                            "version_id": facts["version_id"],
                            "step_run_id": step_run_id,
                            "candidate_id": candidate["claim_id"],
                            "field": candidate["field"],
                            "value": json.dumps(candidate["value"], ensure_ascii=False),
                            "confidence": gate_candidate.confidence_bps,
                            "attribution": attribution,
                            "reasons": list(decision.reason_codes),
                            "now": now,
                        },
                    )
                    for evidence_uuid, row in candidate_evidence.items():
                        await connection.execute(
                            text(_INSERT_AI_JUDGMENT_EVIDENCE_SQL),
                            {
                                "id": evidence_uuid,
                                "judgment_id": judgment_id,
                                "version_id": facts["version_id"],
                                "block_id": row["block"]["block_id"],
                                "excerpt": row["candidate"]["excerpt"],
                                "hash": sha256(row["candidate"]["excerpt"].encode()).hexdigest(),
                                "locator": row["candidate"]["locator"]["value"],
                                "now": now,
                            },
                        )
                    continue
                if not isinstance(decision, EvidenceFact):
                    raise RuntimeError("AUTOMATIC_EVIDENCE_GATE_INVALID_RESULT")
                claim_id = uuid7()
                result = await connection.execute(
                    text(_INSERT_CLAIM_SQL),
                    {
                        "id": claim_id,
                        "item_id": item_id,
                        "version_id": facts["version_id"],
                        "claim_type": candidate["field"],
                        "subject": attribution or f"model:{candidate['claim_id']}"[:500],
                        "predicate": candidate["field"],
                        "value": json.dumps(candidate["value"], ensure_ascii=False),
                        "now": now,
                    },
                )
                if result.rowcount != 1:
                    continue
                accepted_count += 1
                await connection.execute(
                    text(
                        "INSERT INTO ai_candidate_claim_origin("
                        "claim_id,step_run_id,model_claim_id,created_at) "
                        "VALUES(:claim_id,:step_run_id,:model_id,:now)"
                    ),
                    {
                        "claim_id": claim_id,
                        "step_run_id": step_run_id,
                        "model_id": candidate["claim_id"],
                        "now": now,
                    },
                )
                for evidence_uuid, row in candidate_evidence.items():
                    await connection.execute(
                        text(_INSERT_EVIDENCE_SQL),
                        {
                            "id": evidence_uuid,
                            "claim_id": claim_id,
                            "version_id": facts["version_id"],
                            "evidence_role": (
                                "PRIMARY_OFFICIAL"
                                if str(document.source_code).startswith("GOV-")
                                else "SOURCE_EXCERPT"
                            ),
                            "paragraph_id": str(row["block"]["block_id"]),
                            "start": row["start"],
                            "end": row["start"] + len(row["candidate"]["excerpt"]),
                            "excerpt": row["candidate"]["excerpt"],
                            "excerpt_hash": sha256(
                                row["candidate"]["excerpt"].encode()
                            ).hexdigest(),
                            "url": document.canonical_url,
                            "page": row["block"]["page_number"],
                            "block_id": row["block"]["block_id"],
                            "x0": row["block"]["x0_mpt"],
                            "y0": row["block"]["y0_mpt"],
                            "x1": row["block"]["x1_mpt"],
                            "y1": row["block"]["y1_mpt"],
                            "confidence": row["block"]["confidence_bps"],
                            "now": now,
                        },
                    )
                await connection.execute(
                    text(_INSERT_AUTOMATIC_ACCEPTANCE_SQL),
                    {
                        "claim_id": claim_id,
                        "version_id": facts["version_id"],
                        "hash": decision.evidence_set_sha256,
                        "actor": _SYSTEM_ACTOR,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(_INSERT_AUTOMATIC_FACT_STATE_SQL),
                    {"claim_id": claim_id, "actor": _SYSTEM_ACTOR, "event_id": uuid7(), "now": now},
                )
            await connection.execute(
                text(_INSERT_PERSONAL_CONTENT_OUTBOX_SQL),
                {"id": uuid7(), "item_id": item_id, "version_id": facts["version_id"], "now": now},
            )
            return accepted_count + judgment_count

    async def queue_qualification_review(
        self, document: PreparationDocument, classification: dict[str, Any]
    ) -> UUID:
        """Create a metadata-only Owner case without creating an Event or Item."""

        case_id = uuid7()
        now = datetime.now(UTC)
        reason = str((classification.get("review_reasons") or ["LOW_CONFIDENCE"])[0])[:80]
        safe_metadata = {
            "title": document.title,
            "source_name": document.source_name,
            "original_url": document.canonical_url,
            "direct_relevance": classification.get("direct_relevance"),
        }
        async with self._engine.begin() as connection:
            inserted_case_id = await connection.scalar(
                text(
                    "INSERT INTO owner_review_case_v2(id,event_id,document_version_id,reason,"
                    "risk_tier,safe_metadata,state,version,created_at,updated_at) "
                    "VALUES(:id,NULL,:version_id,:reason,'R3',CAST(:metadata AS jsonb),"
                    "'OPEN',1,:now,:now) ON CONFLICT(document_version_id) DO NOTHING RETURNING id"
                ),
                {
                    "id": case_id,
                    "version_id": document.document_version_id,
                    "reason": reason,
                    "metadata": json.dumps(safe_metadata, ensure_ascii=False),
                    "now": now,
                },
            )
            if inserted_case_id is None:
                existing_case_id = await connection.scalar(
                    text(
                        "SELECT id FROM owner_review_case_v2 WHERE document_version_id=:version_id"
                    ),
                    {"version_id": document.document_version_id},
                )
                if existing_case_id is None:
                    raise RuntimeError("QUALIFICATION_REVIEW_CASE_NOT_PERSISTED")
                case_id = UUID(str(existing_case_id))
            await connection.execute(
                text(
                    "UPDATE ai_pipeline_run SET status='WAITING_CLAIM_REVIEW',"
                    "failure_code='QUALIFICATION_REVIEW_REQUIRED' WHERE id=:run_id"
                ),
                {"run_id": document.run_id},
            )
            await connection.execute(
                text(
                    "SELECT finalize_source_content_ai_run("
                    ":run_id,'WAITING_CLAIM_REVIEW',NULL,:now)"
                ),
                {"run_id": document.run_id, "now": now},
            )
            backlog = await connection.scalar(
                text("SELECT count(*) FROM owner_review_case_v2 WHERE state='OPEN'")
            )
            INTELLIGENCE_QUALIFICATION_REVIEW_BACKLOG.set(int(backlog or 0))
        return case_id

    async def load_judgment_facts(self, document: PreparationDocument) -> list[EvidenceFactInput]:
        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT claim.id AS claim_id,claim.claim_type,claim.literal_value,
                              evidence.id AS evidence_id,evidence.excerpt,
                              CASE WHEN claim.claim_type='claimed_outcome'
                                THEN claim.subject ELSE NULL END AS attribution
                            FROM claim
                            JOIN automatic_evidence_acceptance acceptance
                              ON acceptance.claim_id=claim.id
                             AND acceptance.input_document_version_id=:version_id
                            JOIN claim_evidence evidence ON evidence.claim_id=claim.id
                            WHERE claim.document_version_id=:version_id
                              AND claim.verification_status='ACCEPTED'
                              AND claim.acceptance_method='AUTOMATED_EVIDENCE_GATE'
                              AND 'ACTIVE'=(SELECT state.state
                                FROM automatic_evidence_fact_state_event state
                                WHERE state.claim_id=claim.id
                                ORDER BY state.created_at DESC,state.id DESC LIMIT 1)
                            ORDER BY claim.id,evidence.id
                            """
                        ),
                        {"version_id": document.document_version_id},
                    )
                ).mappings()
            )
        grouped: dict[UUID, EvidenceFactInput] = {}
        evidence_by_claim: dict[UUID, list[EvidenceSnippet]] = {}
        values: dict[UUID, tuple[str, Any]] = {}
        for row in rows:
            claim_id = cast(UUID, row["claim_id"])
            values[claim_id] = (str(row["claim_type"]), row["literal_value"])
            evidence_by_claim.setdefault(claim_id, []).append(
                EvidenceSnippet(
                    evidence_id=cast(UUID, row["evidence_id"]),
                    excerpt=str(row["excerpt"])[:500],
                    attribution=(str(row["attribution"]) if row["attribution"] else None),
                )
            )
        for claim_id, (field_name, value) in values.items():
            grouped[claim_id] = EvidenceFactInput(
                claim_id=claim_id,
                field_name=field_name,
                value=value,
                evidence=evidence_by_claim[claim_id],
            )
        return list(grouped.values())

    async def materialize_judgment(
        self,
        document: PreparationDocument,
        summary: dict[str, Any] | None,
        verification: dict[str, Any] | None,
        result_type: str,
        reason_codes: tuple[str, ...],
    ) -> None:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"pers07-judgment:{document.document_version_id}"},
            )
            facts = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT item.id AS item_id,binding.event_id,
                              COALESCE(jsonb_agg(jsonb_build_object(
                                'claim_id',claim.id,'evidence_hash',acceptance.evidence_set_sha256
                              ) ORDER BY claim.id) FILTER (WHERE claim.id IS NOT NULL),'[]'::jsonb)
                                AS fact_fingerprint
                            FROM intelligence_item item
                            JOIN event_identity_binding binding ON binding.item_id=item.id
                            LEFT JOIN claim ON claim.item_id=item.id
                              AND claim.document_version_id=:version_id
                              AND claim.verification_status='ACCEPTED'
                              AND claim.acceptance_method='AUTOMATED_EVIDENCE_GATE'
                            LEFT JOIN automatic_evidence_acceptance acceptance
                              ON acceptance.claim_id=claim.id
                            WHERE item.current_document_version_id=:version_id
                            GROUP BY item.id,binding.event_id
                            """
                        ),
                        {"version_id": document.document_version_id},
                    )
                )
                .mappings()
                .one()
            )
            fingerprint = sha256(
                json.dumps(
                    facts["fact_fingerprint"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode()
            ).hexdigest()
            step_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id,step,input_tokens,output_tokens,latency_ms,cost_microusd
                            FROM ai_step_run WHERE pipeline_run_id=:run_id
                              AND step IN ('SUMMARIZE','VERIFY') AND status='SUCCEEDED'
                            ORDER BY step,attempt DESC
                            """
                        ),
                        {"run_id": document.run_id},
                    )
                ).mappings()
            )
            latest: dict[str, RowMapping] = {str(row["step"]): row for row in step_rows}
            usage_rows = list(latest.values())
            summarize_step = latest.get("SUMMARIZE")
            verify_step = latest.get("VERIFY")
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_judgment_version(
                      id,event_id,item_id,document_version_id,pipeline_run_id,
                      summarize_step_run_id,verify_step_run_id,evidence_fact_set_sha256,
                      summarize_prompt_version,verify_prompt_version,schema_version,model_version,
                      status,judgment_payload,verification_result,input_tokens,output_tokens,
                      latency_ms,cost_microusd,failure_reason_codes,invalidation_reason,
                      created_at,invalidated_at
                    ) VALUES(
                      :id,:event_id,:item_id,:version_id,:run_id,:summarize_id,:verify_id,:hash,
                      'pers07-summarize-v1','pers07-verify-v1','ai-judgment-v2',
                      'deepseek-v4-flash',:status,CAST(:summary AS jsonb),
                      CAST(:verification AS jsonb),
                      :input_tokens,:output_tokens,:latency,:cost,:reasons,NULL,:now,NULL
                    ) ON CONFLICT(document_version_id,evidence_fact_set_sha256,
                      summarize_prompt_version,verify_prompt_version,schema_version,model_version)
                    DO UPDATE SET status=EXCLUDED.status,judgment_payload=EXCLUDED.judgment_payload,
                      verification_result=EXCLUDED.verification_result,
                      input_tokens=EXCLUDED.input_tokens,output_tokens=EXCLUDED.output_tokens,
                      latency_ms=EXCLUDED.latency_ms,cost_microusd=EXCLUDED.cost_microusd,
                      failure_reason_codes=EXCLUDED.failure_reason_codes,
                      invalidation_reason=NULL,invalidated_at=NULL
                    """
                ),
                {
                    "id": uuid7(),
                    "event_id": facts["event_id"],
                    "item_id": facts["item_id"],
                    "version_id": document.document_version_id,
                    "run_id": document.run_id,
                    "summarize_id": summarize_step["id"] if summarize_step else None,
                    "verify_id": verify_step["id"] if verify_step else None,
                    "hash": fingerprint,
                    "status": result_type,
                    "summary": json.dumps(summary, ensure_ascii=False) if summary else None,
                    "verification": (
                        json.dumps(verification, ensure_ascii=False) if verification else None
                    ),
                    "input_tokens": sum(int(row["input_tokens"]) for row in usage_rows),
                    "output_tokens": sum(int(row["output_tokens"]) for row in usage_rows),
                    "latency": sum(int(row["latency_ms"]) for row in usage_rows),
                    "cost": sum(int(row["cost_microusd"]) for row in usage_rows),
                    "reasons": list(reason_codes),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO personal_content_outbox(
                      id,document_version_id,item_id,action,status,attempt_count,
                      available_at,created_at,processed_at
                    ) VALUES(:id,:version_id,:item_id,'PROJECT','PENDING',0,:now,:now,NULL)
                    ON CONFLICT(document_version_id,action) DO UPDATE SET
                      status='PENDING',attempt_count=0,available_at=EXCLUDED.available_at,
                      processed_at=NULL
                    """
                ),
                {
                    "id": uuid7(),
                    "version_id": document.document_version_id,
                    "item_id": facts["item_id"],
                    "now": now,
                },
            )

    async def _legacy_materialize_local(self, document: PreparationDocument) -> int:
        raise RuntimeError("LEGACY_PREQUALIFICATION_MATERIALIZATION_RETIRED")

        # Kept temporarily only as a migration reference.  The unconditional
        # guard above makes pre-qualification Event/Feed writes impossible.
        """Persist bounded local facts before any provider call."""

        candidates = extract_local_evidence_candidates(
            title=document.title,
            source_name=document.source_name,
            blocks=document.blocks,
        )
        if not candidates:
            return 0
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"pers06-local:{document.document_version_id}"},
            )
            facts = (
                (
                    await connection.execute(
                        text(_MATERIALIZATION_FACTS_SQL),
                        {"version_id": document.document_version_id},
                    )
                )
                .mappings()
                .one()
            )
            item_id = facts["item_id"] or uuid7()
            if facts["item_id"] is None:
                await connection.execute(
                    text(_INSERT_ITEM_SQL),
                    {
                        "id": item_id,
                        "source_id": facts["source_id"],
                        "document_id": facts["document_id"],
                        "version_id": facts["version_id"],
                        "item_type": "DIGITAL_CASE",
                        "channel": "DIGITAL",
                        "title": document.title,
                        "url": document.canonical_url,
                        "discovered_at": facts["first_discovered_at"],
                        "actor": _SYSTEM_ACTOR,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(_INSERT_DIGITAL_PROFILE_SQL),
                    {"item_id": item_id, "now": now},
                )
            await _ensure_personal_event(
                connection,
                item_id=item_id,
                item_type="DIGITAL_CASE",
                title=document.title,
                actor_id=_SYSTEM_ACTOR,
                now=now,
            )
            accepted = 0
            gate = AutomaticEvidenceGate()
            for local in candidates:
                block = (
                    (
                        await connection.execute(
                            text(_BLOCK_FACT_SQL),
                            {"block_id": UUID(local.block_id)},
                        )
                    )
                    .mappings()
                    .one()
                )
                start = str(block["normalized_text"]).find(local.excerpt)
                if start < 0:
                    continue
                evidence_id = uuid7()
                gate_candidate = AutomaticEvidenceCandidate(
                    candidate_id=local.candidate_id,
                    field=local.field,
                    value=local.value,
                    confidence_bps=10_000,
                    evidence_ids=[evidence_id],
                    attribution=local.attribution,
                    origin="LOCAL_RULE",
                )
                decision = gate.evaluate(
                    gate_candidate,
                    AutomaticEvidenceContext(
                        document_version_id=facts["version_id"],
                        evidence={
                            evidence_id: EvidenceGateEvidence(
                                document_version_id=facts["version_id"],
                                excerpt=local.excerpt,
                                active=True,
                            )
                        },
                        official_first_party=str(document.source_code).startswith("GOV-"),
                        unresolved_conflict_fields=frozenset(),
                        prompt_injection_risk=False,
                        evaluated_at=now,
                    ),
                )
                if not isinstance(decision, EvidenceFact):
                    continue
                claim_id = uuid7()
                inserted = await connection.execute(
                    text(_INSERT_CLAIM_SQL),
                    {
                        "id": claim_id,
                        "item_id": item_id,
                        "version_id": facts["version_id"],
                        "claim_type": local.field,
                        "subject": local.attribution or f"local:{local.candidate_id}",
                        "predicate": local.field,
                        "value": json.dumps(local.value, ensure_ascii=False),
                        "now": now,
                    },
                )
                if inserted.rowcount != 1:
                    continue
                await connection.execute(
                    text(_INSERT_EVIDENCE_SQL),
                    {
                        "id": evidence_id,
                        "claim_id": claim_id,
                        "version_id": facts["version_id"],
                        "evidence_role": (
                            "PRIMARY_OFFICIAL"
                            if str(document.source_code).startswith("GOV-")
                            else "SOURCE_EXCERPT"
                        ),
                        "paragraph_id": str(block["block_id"]),
                        "start": start,
                        "end": start + len(local.excerpt),
                        "excerpt": local.excerpt,
                        "excerpt_hash": sha256(local.excerpt.encode()).hexdigest(),
                        "url": document.canonical_url,
                        "page": block["page_number"],
                        "block_id": block["block_id"],
                        "x0": block["x0_mpt"],
                        "y0": block["y0_mpt"],
                        "x1": block["x1_mpt"],
                        "y1": block["y1_mpt"],
                        "confidence": block["confidence_bps"],
                        "now": now,
                    },
                )
                await connection.execute(
                    text(_INSERT_AUTOMATIC_ACCEPTANCE_SQL),
                    {
                        "claim_id": claim_id,
                        "version_id": facts["version_id"],
                        "hash": decision.evidence_set_sha256,
                        "actor": _SYSTEM_ACTOR,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(_INSERT_AUTOMATIC_FACT_STATE_SQL),
                    {"claim_id": claim_id, "actor": _SYSTEM_ACTOR, "event_id": uuid7(), "now": now},
                )
                accepted += 1
            await connection.execute(
                text(_INSERT_PERSONAL_CONTENT_OUTBOX_SQL),
                {"id": uuid7(), "item_id": item_id, "version_id": facts["version_id"], "now": now},
            )
            return accepted

    async def materialize_local(self, document: PreparationDocument) -> int:
        """Build local candidates without creating Item, Event, claim or projection facts."""

        return len(
            extract_local_evidence_candidates(
                title=document.title,
                source_name=document.source_name,
                blocks=document.blocks,
            )
        )

    async def successful_output(self, run_id: UUID, step: AiStep) -> dict[str, Any]:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text(
                    "SELECT validated_output FROM ai_step_run "
                    "WHERE pipeline_run_id=:run_id AND step=:step AND status='SUCCEEDED' "
                    "ORDER BY attempt DESC LIMIT 1"
                ),
                {"run_id": run_id, "step": step.value},
            )
        if not isinstance(value, dict):
            raise RuntimeError(f"{step.value}_STEP_MISSING")
        return cast(dict[str, Any], value)

    async def successful_output_before_attempt(
        self, run_id: UUID, step: AiStep, *, attempt: int
    ) -> dict[str, Any]:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text(
                    "SELECT validated_output FROM ai_step_run "
                    "WHERE pipeline_run_id=:run_id AND step=:step AND attempt<:attempt "
                    "AND status='SUCCEEDED' ORDER BY attempt DESC LIMIT 1"
                ),
                {"run_id": run_id, "step": step.value, "attempt": attempt},
            )
        if not isinstance(value, dict):
            raise RuntimeError(f"{step.value}_ATTEMPT_MISSING")
        return cast(dict[str, Any], value)

    async def fail(self, run_id: UUID, status: str, code: str) -> None:
        if status not in {"FAILED", "DEGRADED"}:
            raise ValueError("failure status is invalid")
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE ai_pipeline_run SET status=:status,failure_code=:code,"
                    "completed_at=:now WHERE id=:run_id AND status NOT IN "
                    "('WAITING_CLAIM_REVIEW','SUCCEEDED')"
                ),
                {
                    "status": status,
                    "code": code[:80],
                    "now": datetime.now(UTC),
                    "run_id": run_id,
                },
            )
            await connection.execute(
                text("SELECT finalize_source_content_ai_run(:run_id,:status,:code,:now)"),
                {
                    "run_id": run_id,
                    "status": status,
                    "code": code[:80],
                    "now": datetime.now(UTC),
                },
            )

    async def _persist_parsed(self, document_version_id: UUID, parsed: ParsedPdfDocument) -> None:
        previews: dict[int, str] = {}
        for page in parsed.pages:
            key = f"previews/{document_version_id}/{page.page_number}-{page.preview_sha256}.png"
            await self._object_store.put_if_absent(key, page.preview_png, "image/png")
            previews[page.page_number] = key
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"ai01-pages:{document_version_id}"},
            )
            exists = await connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM document_page "
                    "WHERE document_version_id=:version_id)"
                ),
                {"version_id": document_version_id},
            )
            if exists:
                return
            for page in parsed.pages:
                page_id = uuid7()
                await connection.execute(
                    text(_INSERT_PAGE_SQL),
                    {
                        "id": page_id,
                        "version_id": document_version_id,
                        "number": page.page_number,
                        "width": page.width_mpt,
                        "height": page.height_mpt,
                        "rotation": page.rotation,
                        "source": page.text_source,
                        "text_hash": page.normalized_text_sha256,
                        "preview_key": previews[page.page_number],
                        "preview_hash": page.preview_sha256,
                        "now": datetime.now(UTC),
                    },
                )
                for block in page.blocks:
                    await connection.execute(
                        text(_INSERT_BLOCK_SQL),
                        {
                            "id": uuid7(),
                            "page_id": page_id,
                            "index": block.block_index,
                            "kind": block.kind,
                            "source": block.text_source,
                            "text": block.text,
                            "normalized": block.normalized_text,
                            "hash": block.text_sha256,
                            "x0": block.bbox_mpt[0],
                            "y0": block.bbox_mpt[1],
                            "x1": block.bbox_mpt[2],
                            "y1": block.bbox_mpt[3],
                            "confidence": block.confidence_bps,
                            "now": datetime.now(UTC),
                        },
                    )

    async def close(self) -> None:
        await self._engine.dispose()


async def _ensure_personal_event(
    connection: Any,
    *,
    item_id: UUID,
    item_type: str,
    title: str,
    actor_id: UUID,
    now: datetime,
) -> UUID:
    existing = await connection.scalar(
        text("SELECT event_id FROM event_identity_binding WHERE item_id=:item_id"),
        {"item_id": item_id},
    )
    if isinstance(existing, UUID):
        return existing
    event_type = {
        "DIGITAL_CASE": "DIGITAL_PROJECT",
        "INDUSTRY_UPDATE": "INDUSTRY_UPDATE",
        "JOURNAL_PAPER": "RESEARCH_RESULT",
        "SAFETY_REGULATION": "REGULATION_CHANGE",
        "SOFTWARE_PRODUCT": "PRODUCT_RELEASE",
        "IOT_PRODUCT": "PRODUCT_RELEASE",
        "LOW_ALTITUDE_EQUIPMENT": "PRODUCT_RELEASE",
        "AI_EQUIPMENT": "PRODUCT_RELEASE",
    }.get(item_type, "DIGITAL_PROJECT")
    event_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO event(id,event_type,title,subject_names,confirmation_status,"
            "confirmed_by,confirmed_at,created_at,updated_at) VALUES("
            ":id,:event_type,:title,'[]'::jsonb,'CONFIRMED',:actor,:now,:now,:now)"
        ),
        {"id": event_id, "event_type": event_type, "title": title, "actor": actor_id, "now": now},
    )
    await connection.execute(
        text(
            "INSERT INTO event_identity_binding(event_id,item_id,binding_kind,created_by,"
            "created_at,rule_version,identity_key) VALUES(:event_id,:item_id,'ROUND14_ONE_TO_ONE',"
            ":actor,:now,'pers06-v1',:identity_key)"
        ),
        {
            "event_id": event_id,
            "item_id": item_id,
            "actor": actor_id,
            "now": now,
            "identity_key": f"pers06:{item_id}",
        },
    )
    return event_id


def _legacy_storage_class_for_primary_type(primary_type: str) -> tuple[str, str]:
    """Keep v2 PrimaryType semantics intact in the shared legacy storage envelope."""

    return {
        "DIGITAL_TRANSFORMATION": ("DIGITAL_CASE", "DIGITAL"),
        "SAFETY_INTELLIGENCE": ("SAFETY_CASE", "SAFETY"),
        "INDUSTRY_UPDATE": ("INDUSTRY_UPDATE", "INDUSTRY"),
    }[primary_type]


async def _load_blocks(connection: Any, version_id: UUID) -> list[DocumentBlock]:
    rows = (
        (await connection.execute(text(_BLOCKS_SQL), {"version_id": version_id})).mappings().all()
    )
    return [
        DocumentBlock(
            block_id=str(row["block_id"]),
            page_number=int(row["page_number"]),
            text=str(row["normalized_text"]),
            locator_value=(
                f"page={row['page_number']}&box={row['x0_mpt']},{row['y0_mpt']},"
                f"{row['x1_mpt']},{row['y1_mpt']}"
            ),
            repeated_header_footer=row["block_kind"] in {"HEADER", "FOOTER"},
        )
        for row in rows
    ]


_SYSTEM_ACTOR = UUID("019b0000-0000-7000-8000-000000009002")
_MODEL_PROFILE_VERSION = "ai01-deepseek-deepseek-v4-flash-v1"

_AUTHORIZE_PERSONAL_SQL = """
WITH candidate AS (
  SELECT run.id,run.mode,run.status
    FROM ai_pipeline_run run
    JOIN document_version version ON version.id=run.document_version_id
    JOIN raw_object raw ON raw.id=version.raw_object_id
    JOIN document doc ON doc.id=version.document_id
    JOIN source src ON src.id=doc.source_id
   WHERE run.id=:run_id
     AND src.desired_enabled=true AND src.manual_disabled_at IS NULL
     AND src.runtime_state='RUNNING'
     AND doc.current_version_id=version.id AND raw.scan_status='CLEAN'
     AND EXISTS(
       SELECT 1 FROM raw_object_security_fact security
       WHERE security.raw_object_id=raw.id AND security.status='CLEAN'
     )
     AND NOT EXISTS(
       SELECT 1 FROM raw_object_security_fact security
       WHERE security.raw_object_id=raw.id
         AND security.status IN ('REJECTED','QUARANTINED')
     )
     AND version.execution_domain IN ('TRIAL','PRODUCTION')
     AND 'ADMIT'=(
       SELECT assessment.verdict FROM source_admission_assessment_v2 assessment
       WHERE assessment.source_id=src.id
       ORDER BY assessment.assessed_at DESC,assessment.id DESC LIMIT 1
     )
     AND EXISTS(
       SELECT 1 FROM ai_budget_policy budget
       LEFT JOIN ai_budget_month month ON month.policy_id=budget.id
         AND month.month_start=date_trunc('month',now())::date
       WHERE budget.provider='deepseek' AND budget.active
         AND COALESCE(month.reserved_points,0)+COALESCE(month.settled_points,0)
             <budget.monthly_points
     )
     AND true=(
       SELECT activation.active AND profile.enabled
         AND profile.provider='deepseek' AND profile.model='deepseek-v4-flash'
       FROM ai_provider_activation activation
       JOIN ai_model_profile profile ON profile.id=activation.model_profile_id
       WHERE activation.provider='deepseek' AND activation.environment=:environment
       ORDER BY activation.created_at DESC,activation.id DESC LIMIT 1
     )
     AND (
       (run.mode='SHADOW' AND run.status IN (
         'QUEUED','PREPARING','CLASSIFYING','EXTRACTING','WAITING_CLAIM_REVIEW'
       )) OR (
         run.mode='LIVE' AND run.status IN (
           'QUEUED','PREPARING','CLASSIFYING','EXTRACTING','EVIDENCE_GATING',
           'SUMMARIZING','VERIFYING','WAITING_CLAIM_REVIEW'
         )
         AND EXISTS(
           SELECT 1 FROM source_content_outbox outbox
            WHERE outbox.pipeline_run_id=run.id AND outbox.status='WAITING_AI'
         )
       )
     )
   FOR UPDATE OF run
)
SELECT id FROM candidate
LIMIT 1
"""

_DOCUMENT_SQL = """
SELECT run.mode AS run_mode,version.id AS document_version_id,version.raw_object_id,
       version.content_hash,version.title,
       raw.object_key,document.canonical_url,source.registry_code,
       source.name AS source_name,COALESCE(raw.detected_mime,raw.declared_mime,'') AS mime_type,
       bundle.policy_version,bundle.global_rule_version,
       bundle.ai_provider,bundle.ai_model,bundle.prompt_version,bundle.schema_version,
       bundle.code_version,bundle.bundle_sha256,bundle.policy_payload,
       bundle.source_stream_policy_version,
       LEAST(COALESCE(stream_policy.max_attempts,3),3) AS technical_retry_max_retries
FROM ai_pipeline_run run
JOIN qualification_policy_bundle_v2 bundle ON bundle.id=run.policy_bundle_id
JOIN document_version version ON version.id=run.document_version_id
JOIN raw_object raw ON raw.id=version.raw_object_id
JOIN document ON document.id=version.document_id
JOIN source ON source.id=document.source_id
LEFT JOIN LATERAL (
  SELECT config.config_sha256,schedule.max_attempts FROM raw_object_capture capture
  JOIN fetch_run fetch_row ON fetch_row.id=capture.fetch_run_id
  JOIN stream_config_version config ON config.id=fetch_row.stream_config_version_id
  LEFT JOIN fetch_schedule schedule ON schedule.source_stream_id=fetch_row.source_stream_id
  WHERE capture.raw_object_id=raw.id ORDER BY capture.captured_at DESC LIMIT 1
) stream_policy ON true
WHERE run.id=:run_id AND run.mode IN ('LIVE','SHADOW')
  AND run.status IN (
    'PREPARING','CLASSIFYING','EXTRACTING','EVIDENCE_GATING',
    'SUMMARIZING','VERIFYING','WAITING_CLAIM_REVIEW'
  )
  AND raw.scan_status='CLEAN' AND document.current_version_id=version.id
"""


def _policy_bundle_from_facts(facts: RowMapping) -> QualificationPolicyBundle:
    source_stream_policy_version = str(facts["source_stream_policy_version"])
    return QualificationPolicyBundle.from_persisted(
        policy_version=str(facts["policy_version"]),
        global_rule_version=str(facts["global_rule_version"]),
        source_stream_policy_version=source_stream_policy_version,
        ai_provider=str(facts["ai_provider"]),
        ai_model=str(facts["ai_model"]),
        prompt_version=str(facts["prompt_version"]),
        schema_version=str(facts["schema_version"]),
        code_version=str(facts["code_version"]),
        bundle_sha256=str(facts["bundle_sha256"]),
        policy_payload=facts["policy_payload"],
    )


_BLOCKS_SQL = """
SELECT block.id AS block_id,page.page_number,block.block_kind,block.normalized_text,
       block.x0_mpt,block.y0_mpt,block.x1_mpt,block.y1_mpt
FROM document_page page JOIN document_text_block block ON block.document_page_id=page.id
WHERE page.document_version_id=:version_id
ORDER BY page.page_number,block.block_index
"""

_REGISTRY_SQL = """
SELECT prompt.id AS prompt_id,schema.id AS schema_id,model.id AS model_id
FROM ai_prompt_version prompt,ai_schema_version schema,ai_model_profile model
WHERE prompt.version=:prompt_version AND schema.version=:schema_version
  AND model.version=:model_version AND model.enabled
"""

_INSERT_STEP_SQL = """
INSERT INTO ai_step_run(
 id,pipeline_run_id,step,attempt,prompt_version_id,schema_version_id,model_profile_id,
 input_sha256,raw_output,validated_output,status,input_tokens,output_tokens,cost_microusd,
 latency_ms,provider_request_id,error_code,created_at,cache_hit_tokens,cache_miss_tokens,
 finish_reason,attempt_kind,pricing_version,provider_cost_microusd,billing_status
) VALUES(
 :id,:run_id,:step,:attempt,:prompt_id,:schema_id,:model_id,:input_hash,
 :raw_output,CAST(:validated_output AS jsonb),CAST(:status AS varchar),
 :input_tokens,:output_tokens,:cost,:latency,
 :request_id,:error_code,now(),:cache_hit,:cache_miss,:finish_reason,:kind,
 'deepseek-v4-flash-2026-07-17',:cost,
 CASE WHEN CAST(:status AS varchar)='SUCCEEDED' THEN 'SETTLED' ELSE 'UNKNOWN' END
)
"""

_MATERIALIZATION_FACTS_SQL = """
SELECT version.id AS version_id,document.id AS document_id,document.source_id,
       document.first_discovered_at,item.id AS item_id,
       (SELECT policy.id FROM source_policy policy WHERE policy.source_id=document.source_id
        AND policy.status='VALID' AND policy.valid_until>now()
        ORDER BY policy.created_at DESC,policy.id DESC LIMIT 1) AS policy_id
FROM document_version version JOIN document ON document.id=version.document_id
LEFT JOIN intelligence_item item ON item.primary_document_id=document.id
WHERE version.id=:version_id AND document.current_version_id=version.id
"""

_INSERT_ITEM_SQL = """
INSERT INTO intelligence_item(
 id,source_id,primary_document_id,current_document_version_id,item_type,channel,risk_level,
 title,original_url,source_published_at,first_discovered_at,activity_at,processing_status,
 review_status,submitted_by,is_demo,publishable,created_at,updated_at
) VALUES(
 :id,:source_id,:document_id,:version_id,:item_type,:channel,'R1',:title,:url,NULL,
 :discovered_at,:now,'READY','PENDING',:actor,false,false,:now,:now
)
"""

_INSERT_DIGITAL_PROFILE_SQL = """
INSERT INTO digital_case_profile(
 item_id,source_nature,maturity_level,deployment_scale,maturity_evidence_ids,applicability,
 replication_conditions,limitations,risks,srbg_relationship,is_sichuan,created_at,updated_at
) VALUES(
 :item_id,'GOVERNMENT_CASE_COLLECTION','UNKNOWN',NULL,ARRAY[]::uuid[],'[]'::jsonb,
 '[]'::jsonb,'[]'::jsonb,'[]'::jsonb,'待人工审核',false,:now,:now
)
"""

_INSERT_CLAIM_SQL = """
INSERT INTO claim(
 id,item_id,document_version_id,claim_type,subject,predicate,literal_value,
 verification_status,critical,created_at,acceptance_method
) VALUES(:id,:item_id,:version_id,:claim_type,:subject,:predicate,CAST(:value AS jsonb),
 'ACCEPTED',true,:now,'AUTOMATED_EVIDENCE_GATE')
ON CONFLICT(item_id,document_version_id,claim_type,subject,predicate) DO NOTHING
"""

_BLOCK_FACT_SQL = """
SELECT block.id AS block_id,block.normalized_text,block.x0_mpt,block.y0_mpt,
       block.x1_mpt,block.y1_mpt,block.confidence_bps,page.page_number
FROM document_text_block block JOIN document_page page ON page.id=block.document_page_id
WHERE block.id=:block_id
"""

_INSERT_EVIDENCE_SQL = """
INSERT INTO claim_evidence(
 id,claim_id,document_version_id,evidence_role,paragraph_id,char_start,char_end,excerpt,
 excerpt_sha256,original_url,created_at,locator_type,page_number,document_text_block_id,
 x0_mpt,y0_mpt,x1_mpt,y1_mpt,confidence_bps
) VALUES(
 :id,:claim_id,:version_id,:evidence_role,:paragraph_id,:start,:end,:excerpt,
 :excerpt_hash,:url,:now,'PDF_TEXT',:page,:block_id,:x0,:y0,:x1,:y1,:confidence
)
"""

_INSERT_AUTOMATIC_ACCEPTANCE_SQL = """
INSERT INTO automatic_evidence_acceptance(
 claim_id,acceptance_method,rule_version,input_document_version_id,evidence_set_sha256,
 system_actor_id,accepted_at
) VALUES(:claim_id,'AUTOMATED_EVIDENCE_GATE','automatic-evidence-gate-v1',:version_id,
 :hash,:actor,:now)
"""

_INSERT_AUTOMATIC_FACT_STATE_SQL = """
INSERT INTO automatic_evidence_fact_state_event(
 id,claim_id,state,reason_code,actor_id,created_at
) VALUES(:event_id,:claim_id,'ACTIVE','GATE_PASSED',:actor,:now)
"""

_INSERT_AI_JUDGMENT_SQL = """
INSERT INTO ai_judgment(
 id,item_id,document_version_id,step_run_id,model_candidate_id,field_name,candidate_value,
 confidence_bps,attribution,origin,rule_version,reason_codes,evidence_set_sha256,status,
 created_at,invalidated_at
) VALUES(:id,:item_id,:version_id,:step_run_id,:candidate_id,:field,CAST(:value AS jsonb),
 :confidence,:attribution,'MODEL','automatic-evidence-gate-v1',:reasons,NULL,'CURRENT',:now,NULL)
ON CONFLICT(document_version_id,model_candidate_id,origin) DO NOTHING
"""

_INSERT_AI_JUDGMENT_EVIDENCE_SQL = """
INSERT INTO ai_judgment_evidence(
 id,judgment_id,document_version_id,document_text_block_id,excerpt,excerpt_sha256,locator,created_at
) VALUES(:id,:judgment_id,:version_id,:block_id,:excerpt,:hash,:locator,:now)
ON CONFLICT(id) DO NOTHING
"""

_INSERT_PERSONAL_CONTENT_OUTBOX_SQL = """
INSERT INTO personal_content_outbox(
 id,document_version_id,item_id,action,status,attempt_count,available_at,created_at,processed_at
) VALUES(:id,:version_id,:item_id,'PROJECT','PENDING',0,:now,:now,NULL)
ON CONFLICT(document_version_id,action) DO NOTHING
"""

_INSERT_PAGE_SQL = """
INSERT INTO document_page(
 id,document_version_id,page_number,width_mpt,height_mpt,rotation,text_source,
 normalized_text_sha256,preview_object_key,preview_sha256,preview_mime,created_at
) VALUES(:id,:version_id,:number,:width,:height,:rotation,:source,:text_hash,
 :preview_key,:preview_hash,'image/png',:now)
"""

_INSERT_BLOCK_SQL = """
INSERT INTO document_text_block(
 id,document_page_id,block_index,block_kind,text_source,text,normalized_text,text_sha256,
 x0_mpt,y0_mpt,x1_mpt,y1_mpt,confidence_bps,created_at
) VALUES(:id,:page_id,:index,:kind,:source,:text,:normalized,:hash,:x0,:y0,:x1,:y1,
 :confidence,:now)
"""
