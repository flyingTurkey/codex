"""PostgreSQL/object-store boundary for the R-AI01 preparation service."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.ai_pipeline.ai_judgments import EvidenceFactInput, EvidenceSnippet
from srbg_api.ai_pipeline.content_preparation import (
    AiContentPreparationService,
    PreparationDocument,
)
from srbg_api.ai_pipeline.contracts import AiStep, ModelResponse
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
from srbg_api.pdf_processing.parser import ParsedPdfDocument, PdfDocumentParser

logger = logging.getLogger("srbg.worker.ai_content_preparation")


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
                text(_PROMOTE_PILOT_SQL),
                {
                    "run_id": run_id,
                    "pilot_source": AiContentPreparationService.PILOT_SOURCE,
                    "pilot_url": AiContentPreparationService.PILOT_URL,
                },
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
            parsed = await asyncio.to_thread(self._parser.parse, content)
            await self._persist_parsed(cast(UUID, facts["document_version_id"]), parsed)
            async with self._engine.connect() as connection:
                blocks = await _load_blocks(connection, cast(UUID, facts["document_version_id"]))
        return PreparationDocument(
            run_id=run_id,
            document_version_id=str(facts["document_version_id"]),
            source_code=str(facts["registry_code"]),
            canonical_url=str(facts["canonical_url"]),
            title=str(facts["title"] or "交通运输部公开 PDF"),
            source_name=str(facts["source_name"]),
            blocks=tuple(blocks),
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
                    "version_id": UUID(document.document_version_id),
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
            "SUCCEEDED": "VERIFYING",
        }
        previous = allowed_previous.get(status)
        if previous is None:
            raise ValueError("pipeline transition is invalid")
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    "UPDATE ai_pipeline_run SET status=:status WHERE id=:run_id "
                    "AND status=:previous"
                ),
                {"status": status, "run_id": run_id, "previous": previous},
            )
            if result.rowcount != 1:
                current = await connection.scalar(
                    text("SELECT status FROM ai_pipeline_run WHERE id=:run_id"),
                    {"run_id": run_id},
                )
                if current != status:
                    raise RuntimeError("AI_PIPELINE_STATE_CONFLICT")

    async def reserve(self, run_id: UUID, step: AiStep, attempt: int) -> object:
        reservation_id = uuid7()
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT reservation_id,alert_crossed FROM reserve_ai_budget("
                            ":id,:run_id,:step,:attempt,12,:now)"
                        ),
                        {
                            "id": reservation_id,
                            "run_id": run_id,
                            "step": step.value,
                            "attempt": attempt,
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
            await connection.execute(
                text("SELECT settle_ai_budget(:id,:cost,:status,:now)"),
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
            await connection.execute(
                text("SELECT release_ai_budget(:id,:now)"),
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
    ) -> None:
        await self._append_step_row(
            run_id=run_id,
            step=step,
            attempt=attempt,
            kind=kind,
            response=response,
            status="SUCCEEDED",
            error_code=None,
            input_sha256=input_sha256,
        )

    async def append_failed_step(
        self,
        run_id: UUID,
        step: AiStep,
        attempt: int,
        kind: str,
        error_code: str,
        input_sha256: str,
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
    ) -> None:
        async with self._engine.begin() as connection:
            registry = (
                (
                    await connection.execute(
                        text(_REGISTRY_SQL),
                        {
                            "prompt_version": (
                                f"pers07-{step.value.lower()}-v1"
                                if step in {AiStep.SUMMARIZE, AiStep.VERIFY}
                                else f"ai01-{step.value.lower()}-v1"
                            ),
                            "schema_version": (
                                f"{step.value.lower()}-output-v2"
                                if step in {AiStep.SUMMARIZE, AiStep.VERIFY}
                                else f"{step.value.lower()}-output-v1"
                            ),
                            "model_version": "pers07-deepseek-v4-flash-v1",
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
            usage = response.usage if response is not None else None
            await connection.execute(
                text(_INSERT_STEP_SQL),
                {
                    "id": uuid7(),
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
                    "cost": response.cost_microusd if response else 0,
                    "latency": response.latency_ms if response else 0,
                    "request_id": response.provider_request_id if response else None,
                    "finish_reason": response.finish_reason if response else None,
                    "kind": kind,
                    "error_code": error_code,
                },
            )

    async def materialize(
        self,
        document: PreparationDocument,
        classification: dict[str, Any],
        extraction: dict[str, Any],
    ) -> int:
        if (
            classification.get("item_type") != "DIGITAL_CASE"
            or classification.get("channel") != "DIGITAL"
        ):
            raise RuntimeError("AI01_CLASSIFICATION_OUT_OF_SCOPE")
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
                        {"version_id": UUID(document.document_version_id)},
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
                        "item_type": classification["item_type"],
                        "channel": classification["channel"],
                        "title": document.title,
                        "url": document.canonical_url,
                        "discovered_at": facts["first_discovered_at"],
                        "actor": _SYSTEM_ACTOR,
                        "now": now,
                    },
                )
                if classification["item_type"] == "DIGITAL_CASE":
                    await connection.execute(
                        text(_INSERT_DIGITAL_PROFILE_SQL),
                        {"item_id": item_id, "now": now},
                    )
            await _ensure_personal_event(
                connection,
                item_id=item_id,
                item_type=str(classification["item_type"]),
                title=document.title,
                actor_id=_SYSTEM_ACTOR,
                now=now,
            )
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
                        "SELECT field_name FROM claim_conflict WHERE source_item_id=:item_id "
                        "AND status='PENDING_REVIEW'"
                    ),
                    {"item_id": item_id},
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
                        {"version_id": UUID(document.document_version_id)},
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
                        {"version_id": UUID(document.document_version_id)},
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
                    "version_id": UUID(document.document_version_id),
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
                    "version_id": UUID(document.document_version_id),
                    "item_id": facts["item_id"],
                    "now": now,
                },
            )

    async def materialize_local(self, document: PreparationDocument) -> int:
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
                        {"version_id": UUID(document.document_version_id)},
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

_PROMOTE_PILOT_SQL = """
WITH candidate AS (
  SELECT run.id,run.mode,run.status
    FROM ai_pipeline_run run
    JOIN document_version version ON version.id=run.document_version_id
    JOIN document doc ON doc.id=version.document_id
    JOIN source src ON src.id=doc.source_id
   WHERE run.id=:run_id AND src.registry_code=:pilot_source
     AND doc.canonical_url=:pilot_url
     AND (
       (run.mode='SHADOW' AND run.status IN (
         'QUEUED','PREPARING','CLASSIFYING','EXTRACTING','WAITING_CLAIM_REVIEW'
       )) OR (
         run.mode='LIVE' AND run.status='QUEUED'
         AND EXISTS(
           SELECT 1 FROM source_content_outbox outbox
            WHERE outbox.pipeline_run_id=run.id AND outbox.status='WAITING_AI'
         )
       )
     )
   FOR UPDATE OF run
), promoted AS (
  UPDATE ai_pipeline_run run SET mode='SHADOW'
    FROM candidate
   WHERE run.id=candidate.id AND candidate.mode='LIVE'
  RETURNING run.id
)
SELECT id FROM promoted
UNION ALL
SELECT id FROM candidate WHERE mode='SHADOW'
LIMIT 1
"""

_DOCUMENT_SQL = """
SELECT version.id AS document_version_id,version.content_hash,version.title,
       raw.object_key,document.canonical_url,source.registry_code,
       source.name AS source_name
FROM ai_pipeline_run run
JOIN document_version version ON version.id=run.document_version_id
JOIN raw_object raw ON raw.id=version.raw_object_id
JOIN document ON document.id=version.document_id
JOIN source ON source.id=document.source_id
WHERE run.id=:run_id AND run.mode='SHADOW'
  AND run.status IN ('PREPARING','CLASSIFYING','EXTRACTING')
  AND raw.scan_status='CLEAN' AND document.current_version_id=version.id
"""

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
 :id,:run_id,:step,:attempt,:prompt_id,:schema_id,:model_id,:input_hash,:raw_output,
 CAST(:validated_output AS jsonb),:status,:input_tokens,:output_tokens,:cost,:latency,
 :request_id,:error_code,now(),:cache_hit,:cache_miss,:finish_reason,:kind,
 'deepseek-v4-flash-2026-07-17',:cost,
 CASE WHEN :status='SUCCEEDED' THEN 'SETTLED' ELSE 'UNKNOWN' END
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
 :id,:source_id,:document_id,:version_id,:item_type,:channel,'R3',:title,:url,NULL,
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
 :id,:claim_id,:version_id,'PRIMARY_OFFICIAL',:paragraph_id,:start,:end,:excerpt,
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
