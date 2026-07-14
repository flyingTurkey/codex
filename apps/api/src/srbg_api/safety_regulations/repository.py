"""PostgreSQL persistence for the safety-regulation acquisition pipeline."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from srbg_api.acquisition.contracts import DiscoveryRecord, SourceCheckpoint
from srbg_api.identifiers import uuid7
from srbg_api.pdf_processing.change_detection import CriticalFieldValues
from srbg_api.pdf_processing.parser import ParsedPdfDocument
from srbg_api.pdf_processing.versioning import VersionFacts, decide_version_change
from srbg_api.safety_regulations.parser import ParsedClaim, ParsedSafetyRegulation
from srbg_api.safety_regulations.pipeline import RecordLease, SourceAuthorization
from srbg_api.safety_regulations.scanner import SemanticSafetyResult


class SourceDetailLike(Protocol):
    id: UUID
    effective_active: bool


class SourceRegistryLike(Protocol):
    async def get_source(self, source_id: UUID) -> SourceDetailLike: ...


class PreviewObjectStore(Protocol):
    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str: ...


class SourceRegistryAuthorizer:
    """Reads the admission service's computed state instead of trusting connector data."""

    def __init__(self, source_registry: SourceRegistryLike) -> None:
        self._source_registry = source_registry

    async def authorize(self, source_id: UUID) -> SourceAuthorization:
        source = await self._source_registry.get_source(source_id)
        return SourceAuthorization(
            source_id=source.id,
            effective_active=source.effective_active,
        )


class PostgresIngestionStore:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        preview_object_store: PreviewObjectStore | None = None,
    ) -> None:
        self._engine = engine
        self._preview_object_store = preview_object_store

    async def close(self) -> None:
        await self._engine.dispose()

    async def get_checkpoint(self, connector_id: UUID) -> SourceCheckpoint:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT cursor, etag, last_modified,
                                   consecutive_failures, circuit_open_until
                            FROM source_checkpoint
                            WHERE source_connector_id = :connector_id
                            """
                        ),
                        {"connector_id": connector_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return SourceCheckpoint()
        cursor_document = row["cursor"] or {}
        return SourceCheckpoint(
            cursor=cursor_document.get("value"),
            etag=row["etag"],
            last_modified=row["last_modified"],
            consecutive_failures=row["consecutive_failures"],
            circuit_open_until=row["circuit_open_until"],
        )

    async def start_run(
        self,
        *,
        connector_id: UUID,
        trigger: str,
        request_id: str,
    ) -> UUID:
        run_id = uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO fetch_run (
                        id, source_connector_id, trigger, status, started_at,
                        discovered_count, fetched_count, failed_count, request_id
                    ) VALUES (
                        :id, :connector_id, :trigger, 'RUNNING', :now, 0, 0, 0, :request_id
                    )
                    """
                ),
                {
                    "id": run_id,
                    "connector_id": connector_id,
                    "trigger": trigger,
                    "request_id": request_id,
                    "now": datetime.now(UTC),
                },
            )
        return run_id

    async def lease_record(
        self,
        *,
        run_id: UUID,
        connector_id: UUID,
        record: object,
    ) -> RecordLease:
        discovered = cast(DiscoveryRecord, record)
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id, etag, last_modified, document_version_id
                            FROM fetch_record
                            WHERE source_connector_id = :connector_id
                              AND external_id = :external_id
                            FOR UPDATE
                            """
                        ),
                        {
                            "connector_id": connector_id,
                            "external_id": discovered.external_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if existing is None:
                record_id = uuid7()
                await connection.execute(
                    text(
                        """
                        INSERT INTO fetch_record (
                            id, fetch_run_id, source_connector_id, external_id,
                            canonical_url, discovered_title, discovered_at, status,
                            attempt_count, created_at, updated_at
                        ) VALUES (
                            :id, :run_id, :connector_id, :external_id, :url, :title,
                            :discovered_at, 'DISCOVERED', 1, :now, :now
                        )
                        """
                    ),
                    {
                        "id": record_id,
                        "run_id": run_id,
                        "connector_id": connector_id,
                        "external_id": discovered.external_id,
                        "url": discovered.url,
                        "title": discovered.title,
                        "discovered_at": discovered.discovered_at,
                        "now": datetime.now(UTC),
                    },
                )
                return RecordLease(record_id=record_id, should_fetch=True)

            record_id = existing["id"]
            await connection.execute(
                text(
                    """
                    UPDATE fetch_record
                    SET fetch_run_id = :run_id, canonical_url = :url,
                        discovered_title = :title, discovered_at = :discovered_at,
                        status = 'DISCOVERED', attempt_count = attempt_count + 1,
                        updated_at = :now
                    WHERE id = :id
                    """
                ),
                {
                    "id": record_id,
                    "run_id": run_id,
                    "url": discovered.url,
                    "title": discovered.title,
                    "discovered_at": discovered.discovered_at,
                    "now": datetime.now(UTC),
                },
            )
            return RecordLease(
                record_id=record_id,
                should_fetch=True,
                checkpoint=SourceCheckpoint(
                    etag=existing["etag"],
                    last_modified=existing["last_modified"],
                ),
            )

    async def mark_not_modified(self, *, record_id: UUID) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE fetch_record
                    SET status = 'NOT_MODIFIED', http_status = 304, updated_at = :now
                    WHERE id = :id
                    """
                ),
                {"id": record_id, "now": datetime.now(UTC)},
            )

    async def link_document(
        self,
        *,
        record_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE fetch_record
                    SET status = 'FETCHED', http_status = 200, document_id = :document_id,
                        document_version_id = :version_id, etag = :etag,
                        last_modified = :last_modified, error_code = NULL, updated_at = :now
                    WHERE id = :id
                    """
                ),
                {
                    "id": record_id,
                    "document_id": document_id,
                    "version_id": document_version_id,
                    "etag": etag,
                    "last_modified": last_modified,
                    "now": datetime.now(UTC),
                },
            )

    async def persist_parsed(
        self,
        *,
        record_id: UUID,
        source_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
        parsed: ParsedSafetyRegulation,
        semantic_scan: SemanticSafetyResult,
        submitted_by: UUID,
    ) -> tuple[UUID, UUID]:
        now = datetime.now(UTC)
        preview_keys = await self._store_pdf_previews(document_version_id, parsed.pdf_document)
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT i.id AS item_id,
                                   COALESCE(
                                       r.id,
                                       (SELECT prior.id FROM review_task prior
                                        WHERE prior.item_id = i.id
                                        ORDER BY prior.submitted_at DESC, prior.id DESC LIMIT 1)
                                   ) AS review_task_id
                            FROM intelligence_item i
                            LEFT JOIN review_task r
                              ON r.item_id = i.id
                             AND r.document_version_id = :version_id
                            WHERE i.primary_document_id = :document_id
                              AND i.current_document_version_id = :version_id
                            """
                        ),
                        {"document_id": document_id, "version_id": document_version_id},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return existing["item_id"], existing["review_task_id"]

            processing_id = uuid7()
            await connection.execute(
                text(
                    """
                    INSERT INTO processing_run (
                        id, fetch_record_id, document_version_id, parser_name,
                        parser_version, status, started_at, completed_at, paragraphs,
                        semantic_safety_scan_pass, prompt_injection_detected,
                        security_resolution_status, security_scanner_version,
                        normalized_text_sha256, semantic_body_sha256, metadata_sha256,
                        page_count, ocr_page_count, ocr_usable_page_count,
                        low_confidence_critical_count
                    ) VALUES (
                        :id, :record_id, :version_id, :parser_name,
                        :parser_version, 'SUCCEEDED', :now, :now, CAST(:paragraphs AS jsonb),
                        :scan_pass, :injection, :resolution, :scanner_version,
                        :normalized_hash, :semantic_hash, :metadata_hash,
                        :page_count, :ocr_page_count, :ocr_usable_count,
                        :low_confidence_count
                    )
                    """
                ),
                {
                    "id": processing_id,
                    "record_id": record_id,
                    "version_id": document_version_id,
                    "parser_name": parsed.parser_name,
                    "parser_version": parsed.parser_version,
                    "now": now,
                    "paragraphs": _json(
                        [
                            {"paragraph_id": paragraph.paragraph_id, "text": paragraph.text}
                            for paragraph in parsed.paragraphs
                        ]
                    ),
                    "scan_pass": semantic_scan.passed,
                    "injection": semantic_scan.prompt_injection_detected,
                    "resolution": semantic_scan.resolution_status,
                    "scanner_version": semantic_scan.scanner_version,
                    "normalized_hash": (
                        parsed.pdf_document.normalized_text_sha256
                        if parsed.pdf_document is not None
                        else None
                    ),
                    "semantic_hash": (
                        parsed.pdf_document.semantic_body_sha256
                        if parsed.pdf_document is not None
                        else None
                    ),
                    "metadata_hash": (
                        parsed.pdf_document.metadata_sha256
                        if parsed.pdf_document is not None
                        else None
                    ),
                    "page_count": (
                        len(parsed.pdf_document.pages) if parsed.pdf_document is not None else None
                    ),
                    "ocr_page_count": (
                        parsed.pdf_document.ocr_page_count
                        if parsed.pdf_document is not None
                        else None
                    ),
                    "ocr_usable_count": (
                        parsed.pdf_document.ocr_usable_page_count
                        if parsed.pdf_document is not None
                        else None
                    ),
                    "low_confidence_count": (
                        parsed.pdf_document.low_confidence_critical_count
                        if parsed.pdf_document is not None
                        else None
                    ),
                },
            )
            block_ids = await _persist_pdf_pages(
                connection,
                document_version_id=document_version_id,
                document=parsed.pdf_document,
                preview_keys=preview_keys,
                now=now,
            )
            policy_id = await connection.scalar(
                text(
                    """
                    SELECT id FROM source_policy
                    WHERE source_id = :source_id AND status = 'VALID'
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """
                ),
                {"source_id": source_id},
            )
            if not isinstance(policy_id, UUID):
                raise RuntimeError("current source policy is missing")

            current_item = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id, current_document_version_id, review_status
                            FROM intelligence_item
                            WHERE primary_document_id = :document_id
                            FOR UPDATE
                            """
                        ),
                        {"document_id": document_id},
                    )
                )
                .mappings()
                .first()
            )
            previous_version_id = (
                current_item["current_document_version_id"] if current_item is not None else None
            )
            previous_facts = await _load_version_facts(
                connection,
                document_version_id=previous_version_id,
            )
            current_facts = await _current_version_facts(
                connection,
                document_version_id=document_version_id,
                parsed=parsed,
            )
            version_decision = decide_version_change(previous_facts, current_facts)
            if (
                version_decision.change_type == "METADATA_ONLY"
                and current_item is not None
                and not await _metadata_reanchor_possible(
                    connection,
                    item_id=current_item["id"],
                    parsed=parsed,
                )
            ):
                version_decision = replace(
                    version_decision,
                    change_type="CONTENT_UPDATE",
                    material=True,
                    review_state="RE_REVIEW_PENDING",
                )
            change_id = uuid7()
            await connection.execute(
                text(
                    """
                    INSERT INTO version_change (
                        id, document_id, from_document_version_id, to_document_version_id,
                        change_type, material, review_state, raw_sha256,
                        normalized_text_sha256, semantic_body_sha256, metadata_sha256,
                        changed_token_count, changed_token_ratio_bps, page_diffs,
                        critical_field_diffs, classifier_version, created_at
                    ) VALUES (
                        :id, :document_id, :from_version_id, :to_version_id,
                        :change_type, :material, :review_state, :raw_hash,
                        :normalized_hash, :semantic_hash, :metadata_hash,
                        :changed_count, :changed_ratio, '[]'::jsonb,
                        CAST(:critical_diffs AS jsonb), 'srbg-version-change-1.0.0', :now
                    )
                    """
                ),
                {
                    "id": change_id,
                    "document_id": document_id,
                    "from_version_id": previous_version_id,
                    "to_version_id": document_version_id,
                    "change_type": version_decision.change_type,
                    "material": version_decision.material,
                    "review_state": version_decision.review_state,
                    "raw_hash": current_facts.raw_sha256,
                    "normalized_hash": current_facts.normalized_text_sha256,
                    "semantic_hash": current_facts.semantic_body_sha256,
                    "metadata_hash": current_facts.metadata_sha256,
                    "changed_count": version_decision.changed_token_count,
                    "changed_ratio": version_decision.changed_token_ratio_bps,
                    "critical_diffs": _json(
                        [
                            {
                                "field": change.field,
                                "before": change.before,
                                "after": change.after,
                            }
                            for change in version_decision.critical_fields
                        ]
                    ),
                    "now": now,
                },
            )
            await _append_version_change_state_events(
                connection,
                version_change_id=change_id,
                change_type=version_decision.change_type,
                material=version_decision.material,
                review_state=version_decision.review_state,
                now=now,
            )
            if current_item is None:
                item_id = uuid7()
                await connection.execute(
                    text(
                        """
                        INSERT INTO intelligence_item (
                            id, source_id, primary_document_id, current_document_version_id,
                            item_type, channel, risk_level, title, original_url,
                            source_published_at, first_discovered_at, activity_at,
                            processing_status, review_status, submitted_by, is_demo,
                            publishable, created_at, updated_at
                        ) VALUES (
                            :id, :source_id, :document_id, :version_id,
                            'SAFETY_REGULATION', 'SAFETY', 'R3', :title, :original_url,
                            :published_at, :now, :now, 'READY_FOR_REVIEW',
                            'PENDING', :submitted_by, false, true, :now, :now
                        )
                        """
                    ),
                    {
                        "id": item_id,
                        "source_id": source_id,
                        "document_id": document_id,
                        "version_id": document_version_id,
                        "title": parsed.title,
                        "original_url": parsed.canonical_url,
                        "published_at": parsed.published_at,
                        "submitted_by": submitted_by,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO safety_regulation_profile (
                            item_id, classification, document_number, issuing_authority,
                            published_at, effective_at, regulation_status, created_at
                        ) VALUES (
                            :item_id, :classification, :number, :authority,
                            :published_at, :effective_at, :status, :now
                        )
                        """
                    ),
                    {
                        "item_id": item_id,
                        "classification": parsed.classification,
                        "number": parsed.document_number,
                        "authority": parsed.issuing_authority,
                        "published_at": parsed.published_at,
                        "effective_at": parsed.effective_at,
                        "status": parsed.regulation_status,
                        "now": now,
                    },
                )
            else:
                item_id = current_item["id"]
                await connection.execute(
                    text(
                        """
                        UPDATE intelligence_item
                        SET current_document_version_id = :version_id,
                            title = :title, source_published_at = :published_at,
                            activity_at = CASE
                                WHEN :material THEN :now
                                ELSE activity_at
                            END,
                            updated_at = :now,
                            processing_status = :processing_status,
                            review_status = :review_status
                        WHERE id = :item_id
                        """
                    ),
                    {
                        "version_id": document_version_id,
                        "title": parsed.title,
                        "published_at": parsed.published_at,
                        "now": now,
                        "material": version_decision.material,
                        "processing_status": (
                            "READY_FOR_REVIEW" if version_decision.material else "READY"
                        ),
                        "review_status": (
                            "PENDING"
                            if version_decision.material
                            else current_item["review_status"]
                        ),
                        "item_id": item_id,
                    },
                )
                await connection.execute(
                    text(
                        """
                        UPDATE safety_regulation_profile
                        SET classification = :classification, document_number = :number,
                            issuing_authority = :authority, published_at = :published_at,
                            effective_at = :effective_at
                        WHERE item_id = :item_id
                        """
                    ),
                    {
                        "classification": parsed.classification,
                        "number": parsed.document_number,
                        "authority": parsed.issuing_authority,
                        "published_at": parsed.published_at,
                        "effective_at": parsed.effective_at,
                        "item_id": item_id,
                    },
                )
            for parsed_claim in parsed.claims:
                claim_id = uuid7()
                derived_claim_id, derived_evidence_ids = await _metadata_reanchor_sources(
                    connection,
                    previous_document_version_id=previous_version_id,
                    parsed_claim=parsed_claim,
                    enabled=version_decision.change_type == "METADATA_ONLY",
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO claim (
                            id, item_id, document_version_id, claim_type, subject,
                            predicate, literal_value, verification_status, critical,
                            confidence_bps, derived_from_claim_id, created_at
                        ) VALUES (
                            :id, :item_id, :version_id, :claim_type, :subject,
                            :predicate, CAST(:literal_value AS jsonb), 'ACCEPTED', true,
                            :confidence_bps, :derived_claim_id, :now
                        )
                        """
                    ),
                    {
                        "id": claim_id,
                        "item_id": item_id,
                        "version_id": document_version_id,
                        "claim_type": parsed_claim.claim_type,
                        "subject": parsed_claim.subject,
                        "predicate": parsed_claim.predicate,
                        "literal_value": _json(parsed_claim.literal_value),
                        "confidence_bps": parsed_claim.confidence_bps,
                        "derived_claim_id": derived_claim_id,
                        "now": now,
                    },
                )
                for parsed_evidence in parsed_claim.evidence:
                    await connection.execute(
                        text(
                            """
                            INSERT INTO claim_evidence (
                                id, claim_id, document_version_id, evidence_role,
                                derived_from_evidence_id, paragraph_id,
                                char_start, char_end, excerpt,
                                excerpt_sha256, original_url, locator_type, page_number,
                                document_text_block_id, document_table_cell_id,
                                x0_mpt, y0_mpt, x1_mpt, y1_mpt, confidence_bps, created_at
                            ) VALUES (
                                :id, :claim_id, :version_id, 'SUPPORTS',
                                :derived_evidence_id, :paragraph_id,
                                :char_start, :char_end, :excerpt, :excerpt_sha256,
                                :original_url, :locator_type, :page_number,
                                :text_block_id, NULL, :x0, :y0, :x1, :y1,
                                :confidence_bps, :now
                            )
                            """
                        ),
                        {
                            "id": uuid7(),
                            "claim_id": claim_id,
                            "version_id": document_version_id,
                            "derived_evidence_id": derived_evidence_ids.get(
                                parsed_evidence.excerpt_sha256
                            ),
                            "paragraph_id": parsed_evidence.paragraph_id,
                            "char_start": parsed_evidence.char_start,
                            "char_end": parsed_evidence.char_end,
                            "excerpt": parsed_evidence.excerpt,
                            "excerpt_sha256": parsed_evidence.excerpt_sha256,
                            "original_url": parsed_evidence.original_url,
                            "locator_type": parsed_evidence.locator_type,
                            "page_number": parsed_evidence.page_number,
                            "text_block_id": block_ids.get(
                                (
                                    parsed_evidence.page_number,
                                    parsed_evidence.block_index,
                                )
                            ),
                            "x0": (
                                parsed_evidence.bbox_mpt[0]
                                if parsed_evidence.bbox_mpt is not None
                                else None
                            ),
                            "y0": (
                                parsed_evidence.bbox_mpt[1]
                                if parsed_evidence.bbox_mpt is not None
                                else None
                            ),
                            "x1": (
                                parsed_evidence.bbox_mpt[2]
                                if parsed_evidence.bbox_mpt is not None
                                else None
                            ),
                            "y1": (
                                parsed_evidence.bbox_mpt[3]
                                if parsed_evidence.bbox_mpt is not None
                                else None
                            ),
                            "confidence_bps": parsed_evidence.confidence_bps,
                            "now": now,
                        },
                    )
            if version_decision.review_state == "RE_REVIEW_PENDING":
                review_task_id = uuid7()
                await connection.execute(
                    text(
                        """
                        INSERT INTO review_task (
                            id, item_id, document_version_id, source_policy_id, risk_level,
                            status, submitted_by, submitted_at, created_at
                        ) VALUES (
                            :id, :item_id, :version_id, :policy_id, 'R3',
                            'PENDING', :submitted_by, :now, :now
                        )
                        """
                    ),
                    {
                        "id": review_task_id,
                        "item_id": item_id,
                        "version_id": document_version_id,
                        "policy_id": policy_id,
                        "submitted_by": submitted_by,
                        "now": now,
                    },
                )
                await _append_audit(
                    connection,
                    event_type="R3_REVIEW_QUEUED",
                    actor_id=submitted_by,
                    target_type="review_task",
                    target_id=review_task_id,
                    after_state={"item_id": str(item_id), "status": "PENDING"},
                    reason="Safety regulation requires separated human review",
                    request_id=str(record_id),
                    now=now,
                )
            else:
                previous_task_id = await connection.scalar(
                    text(
                        """
                        SELECT id FROM review_task
                        WHERE item_id = :item_id
                        ORDER BY submitted_at DESC, id DESC LIMIT 1
                        """
                    ),
                    {"item_id": item_id},
                )
                if not isinstance(previous_task_id, UUID):
                    raise RuntimeError("metadata-only version has no prior review")
                review_task_id = previous_task_id
            await _append_version_state_events(
                connection,
                document_version_id=document_version_id,
                has_ocr=bool(parsed.pdf_document and parsed.pdf_document.ocr_page_count),
                now=now,
            )
            if version_decision.change_type != "INITIAL":
                event_type = (
                    "DOCUMENT_METADATA_REVISION_READY"
                    if version_decision.review_state == "NO_REVIEW_REQUIRED"
                    else "DOCUMENT_VERSION_UPDATE_DETECTED"
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO outbox_event (
                            id, event_type, aggregate_type, aggregate_id, payload,
                            status, attempt_count, available_at, created_at
                        ) VALUES (
                            :id, :event_type, 'intelligence_item', :item_id,
                            CAST(:payload AS jsonb), 'PENDING', 0, :now, :now
                        )
                        """
                    ),
                    {
                        "id": uuid7(),
                        "event_type": event_type,
                        "item_id": item_id,
                        "payload": _json(
                            {
                                "item_id": str(item_id),
                                "version_change_id": str(change_id),
                                "document_version_id": str(document_version_id),
                                "review_task_id": str(review_task_id),
                            }
                        ),
                        "now": now,
                    },
                )
            await connection.execute(
                text(
                    """
                    UPDATE document
                    SET current_version_id = :version_id
                    WHERE id = :document_id
                    """
                ),
                {"document_id": document_id, "version_id": document_version_id},
            )
            return item_id, review_task_id

    async def _store_pdf_previews(
        self,
        document_version_id: UUID,
        document: ParsedPdfDocument | None,
    ) -> dict[int, str]:
        if document is None:
            return {}
        if self._preview_object_store is None:
            raise RuntimeError("PDF preview object store is required")
        keys: dict[int, str] = {}
        for page in document.pages:
            key = (
                f"pdf-previews/{document_version_id}/"
                f"{page.page_number:04d}-{page.preview_sha256}.png"
            )
            await self._preview_object_store.put_if_absent(key, page.preview_png, "image/png")
            keys[page.page_number] = key
        return keys

    async def fail_record(self, *, record_id: UUID, error_code: str) -> None:
        now = datetime.now(UTC)
        terminal_state = _failed_version_state(error_code)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE fetch_record
                    SET status = 'FAILED', error_code = :error_code, updated_at = :now
                    WHERE id = :id
                    """
                ),
                {"id": record_id, "error_code": error_code[:100], "now": now},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO document_version_state_event (
                        id, document_version_id, state, reason_code, actor_type, created_at
                    )
                    SELECT :event_id, record.document_version_id, :state,
                           :reason_code, 'WORKER',
                           GREATEST(
                               CAST(:now AS timestamptz),
                               COALESCE(
                                   (
                                       SELECT max(existing.created_at) + interval '1 microsecond'
                                       FROM document_version_state_event existing
                                       WHERE existing.document_version_id =
                                             record.document_version_id
                                   ),
                                   CAST(:now AS timestamptz)
                               )
                           )
                    FROM fetch_record record
                    WHERE record.id = :record_id
                      AND record.document_version_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM document_version_state_event existing
                          WHERE existing.document_version_id = record.document_version_id
                            AND existing.state IN ('READY','QUARANTINED','FAILED')
                      )
                    """
                ),
                {
                    "event_id": uuid7(),
                    "record_id": record_id,
                    "state": terminal_state,
                    "reason_code": error_code[:100],
                    "now": now,
                },
            )

    async def complete_run(
        self,
        *,
        run_id: UUID,
        checkpoint: SourceCheckpoint,
        status: str,
        discovered_count: int,
        fetched_count: int,
        failed_count: int,
    ) -> None:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            connector_id = await connection.scalar(
                text("SELECT source_connector_id FROM fetch_run WHERE id = :id FOR UPDATE"),
                {"id": run_id},
            )
            if not isinstance(connector_id, UUID):
                raise RuntimeError("fetch run does not exist")
            previous = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT last_success_at, consecutive_failures, circuit_open_until
                            FROM source_checkpoint
                            WHERE source_connector_id = :connector_id
                            FOR UPDATE
                            """
                        ),
                        {"connector_id": connector_id},
                    )
                )
                .mappings()
                .first()
            )
            previous_failures = int(previous["consecutive_failures"]) if previous else 0
            previous_success = previous["last_success_at"] if previous else None
            previous_open_until = previous["circuit_open_until"] if previous else None
            last_success_at: datetime | None
            circuit_open_until: datetime | None
            if status == "SUCCEEDED":
                failures = 0
                circuit_open_until = None
                last_success_at = now
            elif status == "CIRCUIT_OPEN":
                failures = previous_failures
                circuit_open_until = previous_open_until
                last_success_at = previous_success
            else:
                failures = previous_failures + 1
                circuit_open_until = (
                    now + timedelta(minutes=5) if failures >= 3 else previous_open_until
                )
                last_success_at = previous_success
            await connection.execute(
                text(
                    """
                    UPDATE fetch_run
                    SET status = :status, completed_at = :now,
                        discovered_count = :discovered, fetched_count = :fetched,
                        failed_count = :failed
                    WHERE id = :id
                    """
                ),
                {
                    "id": run_id,
                    "status": status,
                    "now": now,
                    "discovered": discovered_count,
                    "fetched": fetched_count,
                    "failed": failed_count,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO source_checkpoint (
                        id, source_connector_id, cursor, etag, last_modified,
                        last_success_at, consecutive_failures, circuit_open_until, updated_at
                    ) VALUES (
                        :id, :connector_id, CAST(:cursor AS jsonb), :etag, :last_modified,
                        :last_success_at, :failures, :circuit_open_until, :now
                    )
                    ON CONFLICT (source_connector_id) DO UPDATE SET
                        cursor = EXCLUDED.cursor, etag = EXCLUDED.etag,
                        last_modified = EXCLUDED.last_modified,
                        last_success_at = EXCLUDED.last_success_at,
                        consecutive_failures = EXCLUDED.consecutive_failures,
                        circuit_open_until = EXCLUDED.circuit_open_until,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": uuid7(),
                    "connector_id": connector_id,
                    "cursor": _json({"value": checkpoint.cursor}),
                    "etag": checkpoint.etag,
                    "last_modified": checkpoint.last_modified,
                    "last_success_at": last_success_at,
                    "failures": failures,
                    "circuit_open_until": circuit_open_until,
                    "now": now,
                },
            )
            await _append_audit(
                connection,
                event_type="FETCH_RUN_COMPLETED",
                actor_id=UUID("019b0000-0000-7000-8000-000000009002"),
                target_type="fetch_run",
                target_id=run_id,
                after_state={
                    "status": status,
                    "discovered_count": discovered_count,
                    "fetched_count": fetched_count,
                    "failed_count": failed_count,
                },
                reason="Scheduled source acquisition completed",
                request_id=str(run_id),
                now=now,
            )


async def _persist_pdf_pages(
    connection: AsyncConnection,
    *,
    document_version_id: UUID,
    document: ParsedPdfDocument | None,
    preview_keys: dict[int, str],
    now: datetime,
) -> dict[tuple[int | None, int | None], UUID]:
    if document is None:
        return {}
    block_ids: dict[tuple[int | None, int | None], UUID] = {}
    for page in document.pages:
        page_id = uuid7()
        await connection.execute(
            text(
                """
                INSERT INTO document_page (
                    id, document_version_id, page_number, width_mpt, height_mpt,
                    rotation, text_source, normalized_text_sha256,
                    preview_object_key, preview_sha256, preview_mime, created_at
                ) VALUES (
                    :id, :version_id, :page_number, :width, :height,
                    :rotation, :source, :text_hash, :preview_key, :preview_hash,
                    'image/png', :now
                )
                """
            ),
            {
                "id": page_id,
                "version_id": document_version_id,
                "page_number": page.page_number,
                "width": page.width_mpt,
                "height": page.height_mpt,
                "rotation": page.rotation,
                "source": page.text_source,
                "text_hash": page.normalized_text_sha256,
                "preview_key": preview_keys[page.page_number],
                "preview_hash": page.preview_sha256,
                "now": now,
            },
        )
        for block in page.blocks:
            block_id = uuid7()
            x0, y0, x1, y1 = block.bbox_mpt
            await connection.execute(
                text(
                    """
                    INSERT INTO document_text_block (
                        id, document_page_id, block_index, block_kind, text_source,
                        text, normalized_text, text_sha256, x0_mpt, y0_mpt,
                        x1_mpt, y1_mpt, confidence_bps, created_at
                    ) VALUES (
                        :id, :page_id, :block_index, :kind, :source,
                        :text, :normalized, :text_hash, :x0, :y0, :x1, :y1,
                        :confidence, :now
                    )
                    """
                ),
                {
                    "id": block_id,
                    "page_id": page_id,
                    "block_index": block.block_index,
                    "kind": block.kind,
                    "source": block.text_source,
                    "text": block.text,
                    "normalized": block.normalized_text,
                    "text_hash": block.text_sha256,
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "confidence": block.confidence_bps,
                    "now": now,
                },
            )
            block_ids[(page.page_number, block.block_index)] = block_id
        for cell in page.table_cells:
            x0, y0, x1, y1 = cell.bbox_mpt
            await connection.execute(
                text(
                    """
                    INSERT INTO document_table_cell (
                        id, document_page_id, table_index, row_index, column_index,
                        row_span, column_span, text, text_sha256, x0_mpt, y0_mpt,
                        x1_mpt, y1_mpt, confidence_bps, created_at
                    ) VALUES (
                        :id, :page_id, :table_index, :row_index, :column_index,
                        1, 1, :text, :text_hash, :x0, :y0, :x1, :y1,
                        :confidence, :now
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "page_id": page_id,
                    "table_index": cell.table_index,
                    "row_index": cell.row_index,
                    "column_index": cell.column_index,
                    "text": cell.text,
                    "text_hash": cell.text_sha256,
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "confidence": cell.confidence_bps,
                    "now": now,
                },
            )
    return block_ids


async def _load_version_facts(
    connection: AsyncConnection,
    *,
    document_version_id: UUID | None,
) -> VersionFacts | None:
    if document_version_id is None:
        return None
    row = (
        (
            await connection.execute(
                text(
                    """
                    SELECT v.content_hash, p.normalized_text_sha256,
                           p.semantic_body_sha256, p.metadata_sha256, p.paragraphs,
                           profile.document_number, profile.published_at,
                           profile.effective_at, profile.regulation_status,
                           COALESCE((
                               SELECT string_agg(b.normalized_text, E'\\n'
                                                 ORDER BY page.page_number, b.block_index)
                               FROM document_page page
                               JOIN document_text_block b ON b.document_page_id = page.id
                               WHERE page.document_version_id = v.id
                                 AND b.block_kind NOT IN ('HEADER','FOOTER')
                           ), '') AS semantic_body
                    FROM document_version v
                    LEFT JOIN processing_run p ON p.document_version_id = v.id
                    LEFT JOIN intelligence_item i ON i.current_document_version_id = v.id
                    LEFT JOIN safety_regulation_profile profile ON profile.item_id = i.id
                    WHERE v.id = :version_id
                    ORDER BY p.completed_at DESC NULLS LAST LIMIT 1
                    """
                ),
                {"version_id": document_version_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    paragraphs = row["paragraphs"] or []
    fallback_body = "\n".join(
        str(value.get("text", "")) for value in paragraphs if isinstance(value, dict)
    )
    semantic_body = str(row["semantic_body"] or fallback_body)
    semantic_hash = row["semantic_body_sha256"] or sha256(semantic_body.encode("utf-8")).hexdigest()
    normalized_hash = row["normalized_text_sha256"] or semantic_hash
    metadata_hash = row["metadata_sha256"] or sha256(b"{}").hexdigest()
    return VersionFacts(
        raw_sha256=str(row["content_hash"]),
        normalized_text_sha256=str(normalized_hash),
        semantic_body_sha256=str(semantic_hash),
        metadata_sha256=str(metadata_hash),
        normalized_body=semantic_body,
        critical_fields=CriticalFieldValues(
            document_number=row["document_number"],
            published_at=_date_value(row["published_at"]),
            effective_at=_date_value(row["effective_at"]),
            legal_effect=row["regulation_status"],
        ),
    )


async def _current_version_facts(
    connection: AsyncConnection,
    *,
    document_version_id: UUID,
    parsed: ParsedSafetyRegulation,
) -> VersionFacts:
    raw_hash = await connection.scalar(
        text("SELECT content_hash FROM document_version WHERE id = :id"),
        {"id": document_version_id},
    )
    if not isinstance(raw_hash, str):
        raise RuntimeError("document version content hash is missing")
    if parsed.pdf_document is not None:
        normalized_hash = parsed.pdf_document.normalized_text_sha256
        semantic_hash = parsed.pdf_document.semantic_body_sha256
        metadata_hash = parsed.pdf_document.metadata_sha256
        normalized_body = parsed.pdf_document.semantic_body
    else:
        normalized_body = "\n".join(paragraph.text for paragraph in parsed.paragraphs)
        semantic_hash = sha256(normalized_body.encode("utf-8")).hexdigest()
        normalized_hash = semantic_hash
        metadata_hash = sha256(b"{}").hexdigest()
    return VersionFacts(
        raw_sha256=raw_hash,
        normalized_text_sha256=normalized_hash,
        semantic_body_sha256=semantic_hash,
        metadata_sha256=metadata_hash,
        normalized_body=normalized_body,
        critical_fields=CriticalFieldValues(
            document_number=parsed.document_number,
            published_at=_date_value(parsed.published_at),
            effective_at=_date_value(parsed.effective_at),
            legal_effect=parsed.regulation_status,
        ),
    )


async def _metadata_reanchor_possible(
    connection: AsyncConnection,
    *,
    item_id: UUID,
    parsed: ParsedSafetyRegulation,
) -> bool:
    old_rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT c.claim_type, e.excerpt_sha256, e.locator_type, e.page_number,
                           e.x0_mpt, e.y0_mpt, e.x1_mpt, e.y1_mpt
                    FROM intelligence_item i
                    JOIN claim c
                      ON c.item_id = i.id
                     AND c.document_version_id = i.current_document_version_id
                    JOIN claim_evidence e ON e.claim_id = c.id
                    WHERE i.id = :item_id AND c.verification_status = 'ACCEPTED'
                    ORDER BY c.claim_type, e.id
                    """
                ),
                {"item_id": item_id},
            )
        ).mappings()
    )
    new_by_hash: dict[str, list[tuple[str, object]]] = {}
    for claim in parsed.claims:
        for evidence in claim.evidence:
            new_by_hash.setdefault(evidence.excerpt_sha256, []).append(
                (
                    claim.claim_type,
                    (
                        evidence.locator_type,
                        evidence.page_number,
                        evidence.bbox_mpt,
                    ),
                )
            )
    for row in old_rows:
        matches = new_by_hash.get(str(row["excerpt_sha256"]), [])
        if len(matches) != 1 or matches[0][0] != row["claim_type"]:
            return False
        if row["locator_type"] in {"PDF_TEXT", "PDF_OCR", "PDF_TABLE_CELL"}:
            old_locator = (
                row["locator_type"],
                row["page_number"],
                (row["x0_mpt"], row["y0_mpt"], row["x1_mpt"], row["y1_mpt"]),
            )
            if matches[0][1] != old_locator:
                return False
    return bool(old_rows)


async def _metadata_reanchor_sources(
    connection: AsyncConnection,
    *,
    previous_document_version_id: UUID | None,
    parsed_claim: ParsedClaim,
    enabled: bool,
) -> tuple[UUID | None, dict[str, UUID]]:
    if not enabled or previous_document_version_id is None:
        return None, {}
    hashes = [evidence.excerpt_sha256 for evidence in parsed_claim.evidence]
    rows = list(
        (
            await connection.execute(
                text(
                    """
                    SELECT claim.id AS claim_id, evidence.id AS evidence_id,
                           evidence.excerpt_sha256
                    FROM claim claim
                    JOIN claim_evidence evidence ON evidence.claim_id = claim.id
                    WHERE claim.document_version_id = :version_id
                      AND claim.claim_type = :claim_type
                      AND evidence.excerpt_sha256 = ANY(:hashes)
                    ORDER BY claim.id, evidence.id
                    """
                ),
                {
                    "version_id": previous_document_version_id,
                    "claim_type": parsed_claim.claim_type,
                    "hashes": hashes,
                },
            )
        ).mappings()
    )
    claim_ids = {cast(UUID, row["claim_id"]) for row in rows}
    evidence_by_hash: dict[str, list[UUID]] = {}
    for row in rows:
        evidence_by_hash.setdefault(str(row["excerpt_sha256"]), []).append(
            cast(UUID, row["evidence_id"])
        )
    if len(claim_ids) != 1 or any(len(evidence_by_hash.get(digest, [])) != 1 for digest in hashes):
        raise RuntimeError("metadata re-anchor sources became ambiguous")
    return next(iter(claim_ids)), {digest: values[0] for digest, values in evidence_by_hash.items()}


async def _append_version_state_events(
    connection: AsyncConnection,
    *,
    document_version_id: UUID,
    has_ocr: bool,
    now: datetime,
) -> None:
    existing_events = list(
        (
            await connection.execute(
                text(
                    """
                SELECT state, created_at FROM document_version_state_event
                WHERE document_version_id = :version_id
                """
                ),
                {"version_id": document_version_id},
            )
        ).mappings()
    )
    existing_states = {event["state"] for event in existing_events}
    latest_existing_at = max((event["created_at"] for event in existing_events), default=now)
    next_created_at = max(now, latest_existing_at + timedelta(microseconds=1))
    states = ["RECEIVED", "SECURITY_PASSED", "PARSING"]
    if has_ocr:
        states.extend(("OCR_PENDING", "OCR_COMPLETE"))
    states.append("READY")
    missing_states = [state for state in states if state not in existing_states]
    for offset, state in enumerate(missing_states, start=len(existing_states)):
        await connection.execute(
            text(
                """
                INSERT INTO document_version_state_event (
                    id, document_version_id, state, reason_code, actor_type, created_at
                ) VALUES (
                    :id, :version_id, :state, NULL, 'WORKER', :created_at
                )
                """
            ),
            {
                "id": uuid7(),
                "version_id": document_version_id,
                "state": state,
                "created_at": next_created_at + timedelta(microseconds=offset),
            },
        )


def _failed_version_state(error_code: str) -> str:
    quarantine_prefixes = ("ATTACHMENT_", "MALWARE_", "MIME_", "PDF_", "ZIP_")
    return "QUARANTINED" if error_code.startswith(quarantine_prefixes) else "FAILED"


async def _append_version_change_state_events(
    connection: AsyncConnection,
    *,
    version_change_id: UUID,
    change_type: str,
    material: bool,
    review_state: str,
    now: datetime,
) -> None:
    states = ("DETECTED",) if review_state == "DETECTED" else ("DETECTED", review_state)
    for state_index, state in enumerate(states):
        await connection.execute(
            text(
                """
                INSERT INTO version_change_state_event (
                    id, version_change_id, state, change_type, material, resolved_change_type,
                    reviewer_id, reason, created_at
                ) VALUES (
                    :id, :change_id, :state, :change_type, :material, NULL, NULL,
                    :reason, :now
                )
                """
            ),
            {
                "id": uuid7(),
                "change_id": version_change_id,
                "state": state,
                "change_type": change_type,
                "material": material,
                "reason": (
                    "Version change detected by deterministic classifier"
                    if state == "DETECTED"
                    else "Deterministic change policy selected the review route"
                ),
                "now": now + timedelta(microseconds=state_index),
            },
        )


def _date_value(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value) if value is not None else None


async def _append_audit(
    connection: AsyncConnection,
    *,
    event_type: str,
    actor_id: UUID,
    target_type: str,
    target_id: UUID,
    after_state: dict[str, Any],
    reason: str,
    request_id: str,
    now: datetime,
) -> None:
    await connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('audit_log'))"))
    previous_hash = await connection.scalar(
        text("SELECT entry_hash FROM audit_log ORDER BY created_at DESC, id DESC LIMIT 1")
    )
    audit_id = uuid7()
    canonical = {
        "id": str(audit_id),
        "event_type": event_type,
        "actor_id": str(actor_id),
        "target_type": target_type,
        "target_id": str(target_id),
        "before_state": None,
        "after_state": after_state,
        "reason": reason,
        "request_id": request_id,
        "previous_hash": previous_hash,
        "created_at": now.isoformat(),
    }
    entry_hash = sha256(_json(canonical).encode()).hexdigest()
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                id, event_type, actor_id, target_type, target_id, before_state,
                after_state, reason, request_id, previous_hash, entry_hash, created_at
            ) VALUES (
                :id, :event_type, :actor_id, :target_type, :target_id, NULL,
                CAST(:after_state AS jsonb), :reason, :request_id,
                :previous_hash, :entry_hash, :created_at
            )
            """
        ),
        {
            "id": audit_id,
            "event_type": event_type,
            "actor_id": actor_id,
            "target_type": target_type,
            "target_id": target_id,
            "after_state": _json(after_state),
            "reason": reason,
            "request_id": request_id,
            "previous_hash": previous_hash,
            "entry_hash": entry_hash,
            "created_at": now,
        },
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
