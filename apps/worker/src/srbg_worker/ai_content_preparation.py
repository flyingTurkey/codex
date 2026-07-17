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
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.ai_pipeline.content_preparation import (
    AiContentPreparationService,
    PreparationDocument,
)
from srbg_api.ai_pipeline.contracts import AiStep, ModelResponse
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
            enabled = await connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ai_provider_activation activation "
                    "WHERE activation.provider='deepseek' AND activation.environment=:environment "
                    "AND activation.active ORDER BY activation.created_at DESC LIMIT 1)"
                ),
                {"environment": self._environment},
            )
            if not enabled:
                raise RuntimeError("MODEL_DISABLED")
            await connection.execute(
                text(
                    "UPDATE ai_pipeline_run SET status='PREPARING' WHERE id=:run_id "
                    "AND status='QUEUED'"
                ),
                {"run_id": run_id},
            )
            facts = (
                (
                    await connection.execute(text(_DOCUMENT_SQL), {"run_id": run_id})
                )
                .mappings()
                .one()
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
                blocks = await _load_blocks(
                    connection, cast(UUID, facts["document_version_id"])
                )
        return PreparationDocument(
            run_id=run_id,
            document_version_id=str(facts["document_version_id"]),
            source_code=str(facts["registry_code"]),
            canonical_url=str(facts["canonical_url"]),
            title=str(facts["title"] or "交通运输部公开 PDF"),
            source_name=str(facts["source_name"]),
            blocks=tuple(blocks),
        )

    async def record_security(
        self, document: PreparationDocument, detected: bool
    ) -> None:
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
            "WAITING_CLAIM_REVIEW": "EXTRACTING",
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

    async def settle(
        self, reservation: object, response: ModelResponse | None
    ) -> None:
        if not isinstance(reservation, UUID):
            raise ValueError("budget reservation identifier is invalid")
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "SELECT settle_ai_budget(:id,:cost,:status,:now)"
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
                            "prompt_version": f"ai01-{step.value.lower()}-v1",
                            "schema_version": f"{step.value.lower()}-output-v1",
                            "model_version": "ai01-deepseek-deepseek-v4-flash-v1",
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
        if classification.get("item_type") != "DIGITAL_CASE" or classification.get(
            "channel"
        ) != "DIGITAL":
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
            for candidate in extraction["claims"]:
                claim_id = uuid7()
                result = await connection.execute(
                    text(_INSERT_CLAIM_SQL),
                    {
                        "id": claim_id,
                        "item_id": item_id,
                        "version_id": facts["version_id"],
                        "claim_type": candidate["field"],
                        "subject": f"model:{candidate['claim_id']}"[:500],
                        "predicate": candidate["field"],
                        "value": json.dumps(candidate["value"], ensure_ascii=False),
                        "now": now,
                    },
                )
                if result.rowcount != 1:
                    continue
                await connection.execute(
                    text(
                        "INSERT INTO ai_candidate_claim_origin(claim_id,step_run_id,"
                        "model_claim_id,created_at) VALUES(:claim_id,:step_run_id,:model_id,:now)"
                    ),
                    {
                        "claim_id": claim_id,
                        "step_run_id": step_run_id,
                        "model_id": candidate["claim_id"],
                        "now": now,
                    },
                )
                for evidence_id in candidate["evidence_ids"]:
                    evidence = evidence_by_id[evidence_id]
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
                        raise RuntimeError("EVIDENCE_EXCERPT_MISMATCH")
                    await connection.execute(
                        text(_INSERT_EVIDENCE_SQL),
                        {
                            "id": uuid7(),
                            "claim_id": claim_id,
                            "version_id": facts["version_id"],
                            "paragraph_id": str(block["block_id"]),
                            "start": start,
                            "end": start + len(evidence["excerpt"]),
                            "excerpt": evidence["excerpt"],
                            "excerpt_hash": sha256(evidence["excerpt"].encode()).hexdigest(),
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
            candidate_total = await connection.scalar(
                text(
                    "SELECT count(*) FROM ai_candidate_claim_origin origin "
                    "JOIN claim ON claim.id=origin.claim_id "
                    "WHERE origin.step_run_id=:step_run_id AND claim.item_id=:item_id"
                ),
                {"step_run_id": step_run_id, "item_id": item_id},
            )
            total = int(candidate_total or 0)
            if total:
                await connection.execute(
                    text(_INSERT_REVIEW_TASK_SQL),
                    {
                        "id": uuid7(),
                        "item_id": item_id,
                        "version_id": facts["version_id"],
                        "policy_id": facts["policy_id"],
                        "actor": _SYSTEM_ACTOR,
                        "now": now,
                    },
                )
            return total

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

    async def _persist_parsed(
        self, document_version_id: UUID, parsed: ParsedPdfDocument
    ) -> None:
        previews: dict[int, str] = {}
        for page in parsed.pages:
            key = (
                f"previews/{document_version_id}/{page.page_number}-"
                f"{page.preview_sha256}.png"
            )
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


async def _load_blocks(connection: Any, version_id: UUID) -> list[DocumentBlock]:
    rows = (
        (
            await connection.execute(text(_BLOCKS_SQL), {"version_id": version_id})
        )
        .mappings()
        .all()
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
 verification_status,critical,created_at
) VALUES(:id,:item_id,:version_id,:claim_type,:subject,:predicate,CAST(:value AS jsonb),
 'CANDIDATE',true,:now)
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

_INSERT_REVIEW_TASK_SQL = """
INSERT INTO review_task(
 id,item_id,document_version_id,source_policy_id,risk_level,status,submitted_by,
 submitted_at,assigned_to,decided_by,decided_at,decision_reason,created_at,task_type
) VALUES(:id,:item_id,:version_id,:policy_id,'R3','PENDING',:actor,:now,NULL,NULL,NULL,NULL,
 :now,'CLAIM_REVIEW')
ON CONFLICT(item_id,document_version_id) WHERE task_type='CLAIM_REVIEW' DO NOTHING
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
