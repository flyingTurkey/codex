"""Scheduled discovery runner for server-admitted MEM HTML connectors."""

import logging
from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.acquisition.http import FetchPolicy, ResilientHttpClient
from srbg_api.acquisition.live import HttpxTransport, SystemClock, SystemResolver
from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.pdf_processing.ocr import TesseractOcrAdapter
from srbg_api.pdf_processing.parser import PdfDocumentParser
from srbg_api.safety_regulations.dispatch import SafetyRegulationDocumentParser
from srbg_api.safety_regulations.parser import MemSafetyRegulationParser
from srbg_api.safety_regulations.pdf_parser import PdfSafetyRegulationParser
from srbg_api.safety_regulations.pipeline import (
    IngestionRunResult,
    SafetyRegulationIngestionService,
    SourceNotAdmitted,
)
from srbg_api.safety_regulations.repository import (
    PostgresIngestionStore,
    SourceRegistryAuthorizer,
)
from srbg_api.safety_regulations.scanner import RuleBasedSemanticScanner
from srbg_api.safety_regulations.source import MemSafetyRegulationAdapter
from srbg_api.source_registry.service import build_default_source_service

SYSTEM_ACTOR_ID = UUID("019b0000-0000-7000-8000-000000009002")


async def run_scheduled_mem_discovery(settings: Settings) -> dict[str, object]:
    engine = create_database_engine(settings)
    source_service = build_default_source_service(settings)
    store = PostgresIngestionStore(engine, preview_object_store=S3ObjectStore(settings))
    logger = logging.getLogger("srbg.worker.safety_regulations")
    results: list[dict[str, object]] = []
    try:
        connectors = await _enabled_mem_connectors(engine)
        for connector in connectors:
            transport = HttpxTransport()
            try:
                policy_document = dict(connector["policy_document"] or {})
                access = policy_document.get("access", {})
                allowed_hosts = tuple(str(value) for value in access.get("allowed_domains", []))
                client = ResilientHttpClient(
                    FetchPolicy(
                        allowed_hosts=allowed_hosts,
                        timeout_seconds=settings.external_io_timeout_seconds,
                        max_attempts=3,
                        base_backoff_seconds=0.5,
                        rate_limit_per_minute=int(access.get("rate_limit_per_minute", 1)),
                        circuit_failure_threshold=3,
                        circuit_reset_seconds=300,
                        max_redirects=3,
                        user_agent=str(access.get("user_agent", "")),
                    ),
                    resolver=SystemResolver(),
                    transport=transport,
                    clock=SystemClock(),
                )
                connector_config = dict(connector["config"] or {})
                service = SafetyRegulationIngestionService(
                    authorizer=SourceRegistryAuthorizer(source_service),
                    store=store,
                    document_vault=source_service.document_vault,
                    parser=SafetyRegulationDocumentParser(
                        html_parser=MemSafetyRegulationParser(),
                        pdf_parser=PdfSafetyRegulationParser(
                            PdfDocumentParser(
                                ocr_adapter=TesseractOcrAdapter(
                                    timeout_seconds=settings.ocr_timeout_seconds
                                ),
                                max_ocr_pages=settings.pdf_max_ocr_pages,
                                max_page_pixels=settings.pdf_max_page_pixels,
                            )
                        ),
                    ),
                    semantic_scanner=RuleBasedSemanticScanner(),
                )
                result = await service.run(
                    source_id=connector["source_id"],
                    connector_id=connector["id"],
                    adapter=MemSafetyRegulationAdapter(
                        client,
                        list_url=str(connector_config["list_url"]),
                    ),
                    actor_id=SYSTEM_ACTOR_ID,
                    request_id=str(uuid7()),
                    trigger="SCHEDULED",
                )
                results.append(_result_document(result))
            except SourceNotAdmitted:
                logger.info(
                    "source_not_effectively_active",
                    extra={"source_id": str(connector["source_id"])},
                )
            except Exception as exc:
                logger.exception(
                    "scheduled_mem_discovery_failed",
                    exc_info=exc,
                    extra={"source_id": str(connector["source_id"])},
                )
            finally:
                await transport.close()
        return {"connector_count": len(connectors), "runs": results}
    finally:
        await source_service.close()
        await store.close()


async def _enabled_mem_connectors(engine: AsyncEngine) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT c.id, c.source_id, c.config, policy.document AS policy_document
                    FROM source_connector c
                    JOIN source s ON s.id = c.source_id
                    LEFT JOIN LATERAL (
                        SELECT p.document
                        FROM source_policy p
                        WHERE p.source_id = s.id
                        ORDER BY p.created_at DESC, p.id DESC LIMIT 1
                    ) policy ON true
                    WHERE c.connector_type = 'MEM_SAFETY_REGULATION_HTML'
                      AND c.enabled = true
                      AND s.state = 'ACTIVE'
                      AND s.enabled = true
                    ORDER BY c.id
                    """
                )
            )
        ).mappings()
        return [dict(row) for row in rows]


def _result_document(result: IngestionRunResult) -> dict[str, object]:
    document = asdict(result)
    document["run_id"] = str(result.run_id)
    return document
