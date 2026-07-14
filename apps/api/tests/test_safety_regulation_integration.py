import asyncio
import base64
import json
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    FetchedAttachment,
    FetchResult,
    SourceCheckpoint,
)
from srbg_api.config import get_settings
from srbg_api.database import create_database_engine, create_publication_engine
from srbg_api.document_vault.service import DocumentVaultService, SourceVaultMetrics
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.pdf_processing.ocr import OcrPageResult
from srbg_api.pdf_processing.parser import PdfDocumentParser
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationDenied, PublicationService
from srbg_api.safety_regulations.parser import MemSafetyRegulationParser
from srbg_api.safety_regulations.pdf_parser import PdfSafetyRegulationParser
from srbg_api.safety_regulations.pipeline import SafetyRegulationIngestionService
from srbg_api.safety_regulations.query import PostgresIntelligenceQueryService
from srbg_api.safety_regulations.repository import (
    PostgresIngestionStore,
    SourceRegistryAuthorizer,
)
from srbg_api.safety_regulations.scanner import RuleBasedSemanticScanner
from srbg_api.safety_regulations.source import FixedMemFixtureAdapter
from srbg_api.source_registry.admission import REQUIRED_ONBOARDING_CHECKS
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_api.source_registry.service import SourceRegistryService
from srbg_contracts import (
    CreateSourceRequest,
    OnboardingCheckEvidence,
    SourceOnboardingSubmission,
    SourcePolicySubmission,
    SourceTransitionRequest,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("SRBG_RUN_SAFETY_INTEGRATION") != "1",
    reason="run through make safety-regulation-test",
)

FIXTURES = Path(__file__).parent / "fixtures" / "source"
DETAIL_URL = "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/201606/t20160603_405633.shtml"
SUBMITTER = UUID("019b0000-0000-7000-8000-000000009101")
REVIEWER = UUID("019b0000-0000-7000-8000-000000009102")


class CleanScanner:
    async def scan(self, content: bytes) -> None:
        assert content


def test_safety_regulation_fixture_to_publication_vertical_slice() -> None:
    asyncio.run(_vertical_slice())


def test_pdf_regulation_fixture_to_v3_publication_with_page_evidence() -> None:
    asyncio.run(_pdf_vertical_slice())


class PdfFixtureAdapter:
    def __init__(
        self,
        content: bytes,
        fetched_at: datetime,
        *,
        external_id: str = "v1",
        url: str = "https://www.mem.gov.cn/test-only/round03-safety-regulation.pdf",
        attachments: tuple[FetchedAttachment, ...] = (),
    ) -> None:
        self._content = content
        self._fetched_at = fetched_at
        self._external_id = f"round03-{external_id}-{uuid4().hex}"
        self.url = url
        self._attachments = attachments

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        return DiscoveryBatch(
            records=(
                DiscoveryRecord(
                    external_id=self._external_id,
                    url=self.url,
                    title="Test-only Bridge Safety Regulation",
                    published_at=self._fetched_at,
                    discovered_at=self._fetched_at,
                ),
            ),
            next_checkpoint=SourceCheckpoint(cursor="round03-pdf", etag='"round03-pdf"'),
        )

    async def fetch(self, record: DiscoveryRecord, checkpoint: SourceCheckpoint) -> FetchResult:
        return FetchResult(
            url=record.url,
            status_code=200,
            content=self._content,
            content_type="application/pdf",
            etag=f'"{sha256(self._content).hexdigest()}"',
            last_modified=None,
            fetched_at=self._fetched_at,
            attachments=self._attachments,
        )


class OcrMustNotRun:
    def recognize(self, png_bytes: bytes, *, page_number: int) -> OcrPageResult:
        raise AssertionError("native-text fixture must not invoke OCR")


def _round03_pdf(
    *,
    header: str = "TEST ONLY - controlled copy v1",
    document_number: str = "TEST-ONLY-2026-03",
    effective_at: str = "2026-08-01",
    body: str = "Bridge construction units shall inspect temporary structures before use.",
    producer: str = "srbg-round03-v1",
) -> bytes:
    document = pymupdf.open()
    document.set_metadata({"producer": producer, "title": "Test-only fixture"})
    for page_number in range(1, 4):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 32), header, fontsize=9)
        lines = (
            "Test-only Bridge Safety Regulation",
            "Issuing authority: Emergency Management Department",
            f"Document number: {document_number}",
            "Published: 2026-07-01",
            f"Effective: {effective_at}",
            body,
            f"Test-only section {page_number}",
        )
        for index, value in enumerate(lines):
            page.insert_text((72, 100 + index * 42), value, fontsize=12)
        page.insert_text((260, 810), f"Page {page_number}", fontsize=9)
    content = bytes(document.tobytes(garbage=4, deflate=True))
    document.close()
    return content


def _round03_attachment_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "annex/test-only-annex.html",
            "<!doctype html><html><body>Test-only safety annex.</body></html>",
        )
    return buffer.getvalue()


def _round03_bomb_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "bomb.html",
            b"<!doctype html><html><body>" + b"A" * 200_000 + b"</body></html>",
        )
    return buffer.getvalue()


async def _process_item_outbox(
    runtime_engine: AsyncEngine,
    publication_service: PublicationService,
    *,
    item_id: UUID,
    event_type: str,
) -> None:
    for _ in range(20):
        async with runtime_engine.connect() as connection:
            status = await connection.scalar(
                text(
                    """
                    SELECT status FROM outbox_event
                    WHERE aggregate_id = :item_id AND event_type = :event_type
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """
                ),
                {"item_id": item_id, "event_type": event_type},
            )
        if status == "PROCESSED":
            return
        if status == "DEAD_LETTER":
            raise AssertionError(f"outbox event {event_type} reached the dead letter state")
        if not await publication_service.process_outbox_once():
            break
    raise AssertionError(f"outbox event {event_type} was not processed; last status={status}")


async def _pdf_vertical_slice() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    runtime_engine = create_database_engine(settings)
    object_store = S3ObjectStore(settings)
    repository = SourceVaultRepository(runtime_engine)
    source_service = SourceRegistryService(
        repository,
        DocumentVaultService(
            repository=repository,
            object_store=object_store,
            malware_scanner=CleanScanner(),
            metrics=SourceVaultMetrics(),
        ),
    )
    query_service = PostgresIntelligenceQueryService(
        create_database_engine(settings),
        preview_object_reader=object_store,
    )
    publication_service = PublicationService(
        repository=PostgresPublicationRepository(create_publication_engine(settings)),
        gate=PublicationGate.from_files(
            Path("docs/codex-kit/assets/validation/publication_gate_v3.json"),
            Path("docs/codex-kit/assets/validation/publication_evaluation_v3.schema.json"),
        ),
    )
    try:
        source_id = await _admit_fixture_source(source_service)
        connector_id = uuid7()
        async with runtime_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO source_connector (
                        id, source_id, connector_type, config, enabled, created_at
                    ) VALUES (
                        :id, :source_id, 'ROUND03_PDF_FIXTURE', '{}'::jsonb, true, :now
                    )
                    """
                ),
                {"id": connector_id, "source_id": source_id, "now": datetime.now(UTC)},
            )
        acquired_at = datetime.now(UTC)
        lifecycle_url = (
            f"https://www.mem.gov.cn/test-only/round03-safety-regulation.pdf?fixture={uuid4().hex}"
        )
        adapter = PdfFixtureAdapter(
            _round03_pdf(),
            acquired_at,
            external_id="v1",
            url=lifecycle_url,
            attachments=(
                FetchedAttachment(
                    url=f"{lifecycle_url}&attachment=annexes.zip",
                    filename="annexes.zip",
                    content=_round03_attachment_zip(),
                    content_type="application/zip",
                ),
            ),
        )
        ingestion = SafetyRegulationIngestionService(
            authorizer=SourceRegistryAuthorizer(source_service),
            store=PostgresIngestionStore(
                runtime_engine,
                preview_object_store=object_store,
            ),
            document_vault=source_service.document_vault,
            parser=PdfSafetyRegulationParser(PdfDocumentParser(ocr_adapter=OcrMustNotRun())),
            semantic_scanner=RuleBasedSemanticScanner(),
        )
        result = await ingestion.run(
            source_id=source_id,
            connector_id=connector_id,
            adapter=adapter,
            actor_id=SUBMITTER,
            request_id=f"round03-pdf-{uuid4().hex}",
            trigger="FIXTURE",
        )
        assert result.failed_records == 0
        feed = await query_service.get_feed(
            mode="all",
            domain="safety",
            content_type=None,
            sort="latest",
            cursor=None,
            limit=100,
        )
        item = next(value for value in feed.items if value.original_url == adapter.url)
        async with runtime_engine.connect() as connection:
            initial_times = (
                (
                    await connection.execute(
                        text(
                            "SELECT activity_at, updated_at "
                            "FROM intelligence_item WHERE id = :item_id"
                        ),
                        {"item_id": item.id},
                    )
                )
                .mappings()
                .one()
            )
        initial_activity_at = initial_times["activity_at"]
        assert isinstance(initial_activity_at, datetime)
        task = next(
            value for value in await query_service.list_review_tasks() if value.item_id == item.id
        )
        decision = await publication_service.decide_review(
            task.id,
            action="APPROVE",
            reason="Test-only PDF critical fields and page locators match official evidence",
            reviewer_id=REVIEWER,
        )
        assert decision.publication_revision_id is not None
        detail = await query_service.get_item(item.id)
        assert detail.evidence
        assert all(value.locator is not None for value in detail.evidence)
        timeline = await query_service.get_versions(item.id, include_restricted=True)
        assert timeline.versions[0].processing_state == "READY"
        page = await query_service.get_document_page(
            timeline.versions[0].version_id,
            1,
            include_restricted=True,
        )
        preview, _ = await query_service.get_page_preview(
            timeline.versions[0].version_id,
            1,
            include_restricted=True,
        )
        assert page.page_count == 3
        assert preview.startswith(b"\x89PNG")
        async with runtime_engine.connect() as connection:
            attachment_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT parent_attachment_id, depth, normalized_path, security_status
                            FROM document_attachment
                            WHERE document_version_id = :version_id
                            ORDER BY depth, normalized_path
                            """
                        ),
                        {"version_id": timeline.versions[0].version_id},
                    )
                ).mappings()
            )
        assert len(attachment_rows) == 2
        assert attachment_rows[0]["parent_attachment_id"] is None
        assert attachment_rows[0]["security_status"] == "CLEAN"
        assert attachment_rows[1]["parent_attachment_id"] is not None
        assert attachment_rows[1]["depth"] == 1
        assert attachment_rows[1]["normalized_path"] == "annex/test-only-annex.html"

        v2 = PdfFixtureAdapter(
            _round03_pdf(
                header="TEST ONLY - controlled copy v2",
                producer="srbg-round03-v2-metadata-only",
            ),
            acquired_at + timedelta(days=1),
            external_id="v2",
            url=lifecycle_url,
        )
        v2_result = await ingestion.run(
            source_id=source_id,
            connector_id=connector_id,
            adapter=v2,
            actor_id=SUBMITTER,
            request_id=f"round03-pdf-v2-{uuid4().hex}",
            trigger="FIXTURE",
        )
        assert v2_result.failed_records == 0
        async with runtime_engine.connect() as connection:
            metadata_times = (
                (
                    await connection.execute(
                        text(
                            "SELECT activity_at, updated_at "
                            "FROM intelligence_item WHERE id = :item_id"
                        ),
                        {"item_id": item.id},
                    )
                )
                .mappings()
                .one()
            )
        assert metadata_times["activity_at"] == initial_activity_at
        assert metadata_times["updated_at"] > metadata_times["activity_at"]
        await _process_item_outbox(
            runtime_engine,
            publication_service,
            item_id=item.id,
            event_type="DOCUMENT_METADATA_REVISION_READY",
        )
        v2_timeline = await query_service.get_versions(item.id, include_restricted=True)
        assert [entry.change_type for entry in v2_timeline.versions] == [
            "INITIAL",
            "METADATA_ONLY",
        ]
        assert v2_timeline.versions[-1].review_state == "NO_REVIEW_REQUIRED"
        async with runtime_engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM claim
                        WHERE item_id = :item_id AND document_version_id = :version_id
                          AND derived_from_claim_id IS NOT NULL
                        """
                    ),
                    {
                        "item_id": item.id,
                        "version_id": v2_timeline.versions[-1].version_id,
                    },
                )
                >= 4
            )
            assert (
                await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM publication_revision revision
                        JOIN publication publication
                          ON publication.id = revision.publication_id
                        WHERE publication.item_id = :item_id
                        """
                    ),
                    {"item_id": item.id},
                )
                == 2
            )

        v3 = PdfFixtureAdapter(
            _round03_pdf(
                header="TEST ONLY - controlled copy v3",
                document_number="TEST-ONLY-2026-04",
                effective_at="2026-09-01",
                body=(
                    "Bridge construction units must inspect temporary structures before every "
                    "shift and shall record ten independent safety verification fields."
                ),
                producer="srbg-round03-v3-material",
            ),
            acquired_at + timedelta(days=2),
            external_id="v3",
            url=lifecycle_url,
        )
        v3_result = await ingestion.run(
            source_id=source_id,
            connector_id=connector_id,
            adapter=v3,
            actor_id=SUBMITTER,
            request_id=f"round03-pdf-v3-{uuid4().hex}",
            trigger="FIXTURE",
        )
        assert v3_result.failed_records == 0
        async with runtime_engine.connect() as connection:
            material_times = (
                (
                    await connection.execute(
                        text(
                            "SELECT activity_at, updated_at "
                            "FROM intelligence_item WHERE id = :item_id"
                        ),
                        {"item_id": item.id},
                    )
                )
                .mappings()
                .one()
            )
        material_activity_at = material_times["activity_at"]
        assert isinstance(material_activity_at, datetime)
        assert material_activity_at > initial_activity_at
        assert material_activity_at == material_times["updated_at"]
        pending_v3 = await query_service.get_item(item.id)
        assert pending_v3.claims is None
        assert pending_v3.evidence is None
        assert pending_v3.item.document_states
        assert "RE_REVIEW_PENDING" in pending_v3.item.document_states
        await _process_item_outbox(
            runtime_engine,
            publication_service,
            item_id=item.id,
            event_type="DOCUMENT_VERSION_UPDATE_DETECTED",
        )
        async with runtime_engine.connect() as connection:
            lifecycle_states = set(
                await connection.scalars(
                    text(
                        """
                        SELECT state FROM content_lifecycle_event
                        WHERE item_id = :item_id
                        """
                    ),
                    {"item_id": item.id},
                )
            )
            assert {"UPDATE_DETECTED", "RE_REVIEW_PENDING"} <= lifecycle_states

        v3_task = next(
            value
            for value in await query_service.list_review_tasks()
            if value.item_id == item.id and value.status == "PENDING"
        )
        v3_decision = await publication_service.decide_review(
            v3_task.id,
            action="APPROVE",
            reason="Test-only v3 document number, effective date and body changes are accepted",
            reviewer_id=REVIEWER,
        )
        assert v3_decision.publication_revision_id is not None
        approved_timeline = await query_service.get_versions(item.id, include_restricted=True)
        assert approved_timeline.versions[-1].change_type == "CONTENT_UPDATE"
        assert approved_timeline.versions[-1].review_state == "APPROVED"
        approved_detail = await query_service.get_item(item.id)
        assert approved_detail.evidence

        async with runtime_engine.connect() as connection:
            publication_id = await connection.scalar(
                text("SELECT id FROM publication WHERE item_id = :item_id"),
                {"item_id": item.id},
            )
            assert isinstance(publication_id, UUID)
            assert (
                await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM derived_summary
                        WHERE item_id = :item_id
                        """
                    ),
                    {"item_id": item.id},
                )
                == 3
            )
        await publication_service.withdraw(
            publication_id,
            reason="Test-only explicit official withdrawal notice accepted by reviewer",
            actor_id=REVIEWER,
            evidence_id=approved_detail.evidence[0].id,
        )
        withdrawn = await query_service.get_item(item.id)
        assert withdrawn.item.publication_revision_id is None
        assert withdrawn.item.document_states
        assert "WITHDRAWN" in withdrawn.item.document_states
        assert withdrawn.claims is None
        assert withdrawn.evidence is None
        history = await query_service.get_versions(item.id, include_restricted=True)
        assert len(history.versions) == 3
        safe_current_version_id = history.versions[-1].version_id

        malicious_attachment = PdfFixtureAdapter(
            _round03_pdf(
                body="Test-only rejected candidate with a quarantined archive attachment.",
                producer="srbg-round03-quarantined-attachment",
            ),
            acquired_at + timedelta(days=3),
            external_id="quarantined-attachment",
            url=lifecycle_url,
            attachments=(
                FetchedAttachment(
                    url=f"{lifecycle_url}&attachment=bomb.zip",
                    filename="bomb.zip",
                    content=_round03_bomb_zip(),
                    content_type="application/zip",
                ),
            ),
        )
        rejected = await ingestion.run(
            source_id=source_id,
            connector_id=connector_id,
            adapter=malicious_attachment,
            actor_id=SUBMITTER,
            request_id=f"round03-pdf-quarantine-{uuid4().hex}",
            trigger="FIXTURE",
        )
        assert rejected.failed_records == 1
        async with runtime_engine.connect() as connection:
            current_version_id = await connection.scalar(
                text(
                    """
                    SELECT document.current_version_id
                    FROM intelligence_item item
                    JOIN document ON document.id = item.primary_document_id
                    WHERE item.id = :item_id
                    """
                ),
                {"item_id": item.id},
            )
            rejected_state = await connection.scalar(
                text(
                    """
                    SELECT state.state
                    FROM document_version version
                    JOIN document ON document.id = version.document_id
                    JOIN intelligence_item item ON item.primary_document_id = document.id
                    JOIN LATERAL (
                        SELECT event.state
                        FROM document_version_state_event event
                        WHERE event.document_version_id = version.id
                        ORDER BY event.created_at DESC, event.id DESC LIMIT 1
                    ) state ON true
                    WHERE item.id = :item_id
                    ORDER BY version.version_number DESC LIMIT 1
                    """
                ),
                {"item_id": item.id},
            )
        assert current_version_id == safe_current_version_id
        assert rejected_state == "QUARANTINED"
    finally:
        await publication_service.close()
        await query_service.close()
        await source_service.close()


async def _vertical_slice() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    runtime_engine = create_database_engine(settings)
    repository = SourceVaultRepository(runtime_engine)
    source_service = SourceRegistryService(
        repository,
        DocumentVaultService(
            repository=repository,
            object_store=S3ObjectStore(settings),
            malware_scanner=CleanScanner(),
            metrics=SourceVaultMetrics(),
        ),
    )
    query_service = PostgresIntelligenceQueryService(create_database_engine(settings))
    publication_service = PublicationService(
        repository=PostgresPublicationRepository(create_publication_engine(settings)),
        gate=PublicationGate.from_files(
            Path("docs/codex-kit/assets/validation/publication_gate.json"),
            Path("docs/codex-kit/assets/validation/publication_evaluation.schema.json"),
        ),
    )
    try:
        source_id = await _admit_fixture_source(source_service)
        connector_id = uuid7()
        async with runtime_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO source_connector (
                        id, source_id, connector_type, config, enabled, created_at
                    ) VALUES (
                        :id, :source_id, 'MEM_SAFETY_REGULATION_FIXTURE',
                        CAST(:config AS jsonb), true, :now
                    )
                    """
                ),
                {
                    "id": connector_id,
                    "source_id": source_id,
                    "config": json.dumps(
                        {
                            "list_url": (
                                "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/index_1.shtml"
                            ),
                            "allowed_hosts": ["www.mem.gov.cn"],
                        }
                    ),
                    "now": datetime.now(UTC),
                },
            )

        adapter = _fixture_adapter()
        ingestion = SafetyRegulationIngestionService(
            authorizer=SourceRegistryAuthorizer(source_service),
            store=PostgresIngestionStore(runtime_engine),
            document_vault=source_service.document_vault,
            parser=MemSafetyRegulationParser(),
            semantic_scanner=RuleBasedSemanticScanner(),
        )
        first_run = await ingestion.run(
            source_id=source_id,
            connector_id=connector_id,
            adapter=adapter,
            actor_id=SUBMITTER,
            request_id=f"round02-{uuid4().hex}",
            trigger="FIXTURE",
        )
        assert first_run.discovered_records == 1
        assert first_run.created_items == 1
        assert first_run.failed_records == 0

        async with runtime_engine.connect() as connection:
            activity_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT source_published_at, first_discovered_at, activity_at
                            FROM intelligence_item
                            WHERE original_url = :url AND source_id = :source_id
                            ORDER BY created_at DESC, id DESC
                            LIMIT 1
                            """
                        ),
                        {"url": DETAIL_URL, "source_id": source_id},
                    )
                )
                .mappings()
                .one()
            )
        assert activity_row["source_published_at"] == datetime(
            2016, 6, 3, 10, 28, tzinfo=UTC
        )
        assert activity_row["activity_at"] == activity_row["first_discovered_at"]

        pending_feed = await query_service.get_feed(
            mode="all",
            domain="safety",
            content_type=None,
            sort="latest",
            cursor=None,
            limit=20,
        )
        pending = next(item for item in pending_feed.items if item.original_url == DETAIL_URL)
        pending_projection = pending.model_dump(exclude_unset=True)
        assert pending.publication_revision_id is None
        assert set(pending_projection) == {
            "id",
            "publication_revision_id",
            "domain",
            "content_type",
            "title",
            "source_name",
            "source_published_at",
            "first_discovered_at",
            "activity_at",
            "original_url",
            "review_status",
        }
        pending_detail = await query_service.get_item(pending.id)
        assert pending_detail.claims is None
        assert pending_detail.evidence is None
        await _assert_feed_keyset_cursor_is_stable_for_equal_activity_times(
            runtime_engine,
            query_service,
            source_id=source_id,
            anchor_item_id=pending.id,
        )

        tasks = await query_service.list_review_tasks()
        task = next(task for task in tasks if task.item_id == pending.id)
        with pytest.raises(PublicationDenied, match="DUTIES_NOT_SEPARATED"):
            await publication_service.decide_review(
                task.id,
                action="APPROVE",
                reason="提交人不得审核自己的 R3 内容",
                reviewer_id=SUBMITTER,
            )

        decision = await publication_service.decide_review(
            task.id,
            action="APPROVE",
            reason="标题、发布机关、文号和日期均与编号段落证据一致",
            reviewer_id=REVIEWER,
        )
        assert decision.publication_revision_id is not None
        assert decision.publication_revision_id.version == 7

        published_feed = await query_service.get_feed(
            mode="all",
            domain="safety",
            content_type=None,
            sort="latest",
            cursor=None,
            limit=20,
        )
        published = next(item for item in published_feed.items if item.id == pending.id)
        assert published.publication_revision_id == decision.publication_revision_id
        assert published.type_summary is not None
        assert published.type_summary.regulation_status == "UNKNOWN"
        assert not hasattr(published, "scores")
        published_detail = await query_service.get_item(pending.id)
        assert len(published_detail.claims or []) == 4
        assert len(published_detail.evidence or []) == 4

        selected = await query_service.get_feed(
            mode="selected",
            domain="safety",
            content_type=None,
            sort="latest",
            cursor=None,
            limit=20,
        )
        assert selected.items == []

        second_run = await ingestion.run(
            source_id=source_id,
            connector_id=connector_id,
            adapter=adapter,
            actor_id=SUBMITTER,
            request_id=f"round02-repeat-{uuid4().hex}",
            trigger="FIXTURE",
        )
        assert second_run.discovered_records == 0
        assert second_run.created_items == 0
        async with runtime_engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM intelligence_item
                        WHERE original_url = :url AND source_id = :source_id
                        """
                    ),
                    {"url": DETAIL_URL, "source_id": source_id},
                )
                == 1
            )
            audit_events = set(
                await connection.scalars(
                    text(
                        """
                        SELECT event_type FROM audit_log
                        WHERE target_id IN (:task_id, :run_id)
                        """
                    ),
                    {"task_id": task.id, "run_id": first_run.run_id},
                )
            )
            assert "R3_REVIEW_QUEUED" in audit_events
            assert "FETCH_RUN_COMPLETED" in audit_events
    finally:
        await publication_service.close()
        await query_service.close()
        await source_service.close()


async def _assert_feed_keyset_cursor_is_stable_for_equal_activity_times(
    runtime_engine: AsyncEngine,
    query_service: PostgresIntelligenceQueryService,
    *,
    source_id: UUID,
    anchor_item_id: UUID,
) -> None:
    tied_at = datetime.now(UTC) + timedelta(minutes=1)
    peer_ids = (uuid7(), uuid7())
    original_activity_at: datetime | None = None
    original_updated_at: datetime | None = None
    try:
        async with runtime_engine.begin() as connection:
            original_times = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT activity_at, updated_at
                            FROM intelligence_item
                            WHERE id = :anchor_item_id
                            """
                        ),
                        {"anchor_item_id": anchor_item_id},
                    )
                )
                .mappings()
                .one()
            )
            original_activity_at = original_times["activity_at"]
            original_updated_at = original_times["updated_at"]
            assert isinstance(original_activity_at, datetime)
            assert isinstance(original_updated_at, datetime)
            documents = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT document.id, document.current_version_id
                            FROM document
                            WHERE document.source_id = :source_id
                              AND document.admission_fixture = true
                              AND document.current_version_id IS NOT NULL
                              AND document.id <>
                                  (SELECT primary_document_id FROM intelligence_item
                                   WHERE id = :anchor_item_id)
                            ORDER BY document.id
                            LIMIT 2
                            """
                        ),
                        {"source_id": source_id, "anchor_item_id": anchor_item_id},
                    )
                ).mappings()
            )
            assert len(documents) == 2
            await connection.execute(
                text(
                    """
                    UPDATE intelligence_item
                    SET activity_at = :tied_at, updated_at = :tied_at
                    WHERE id = :anchor_item_id
                    """
                ),
                {"tied_at": tied_at, "anchor_item_id": anchor_item_id},
            )
            for index, (peer_id, document) in enumerate(
                zip(peer_ids, documents, strict=True)
            ):
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
                            :published_at, :tied_at, :tied_at,
                            'READY_FOR_REVIEW', 'PENDING', :submitted_by, false,
                            true, :tied_at, :tied_at
                        )
                        """
                    ),
                    {
                        "id": peer_id,
                        "source_id": source_id,
                        "document_id": document["id"],
                        "version_id": document["current_version_id"],
                        "title": f"Cursor stability fixture {index}",
                        "original_url": f"https://www.mem.gov.cn/test-only/cursor-{peer_id}",
                        "published_at": tied_at - timedelta(days=1),
                        "tied_at": tied_at,
                        "submitted_by": SUBMITTER,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO safety_regulation_profile (
                            item_id, classification, document_number, issuing_authority,
                            published_at, effective_at, regulation_status, created_at
                        ) VALUES (
                            :item_id, 'DEPARTMENT_RULE', :document_number,
                            'Test-only authority', :published_at, NULL, 'UNKNOWN', :created_at
                        )
                        """
                    ),
                    {
                        "item_id": peer_id,
                        "document_number": f"CURSOR-{index}",
                        "published_at": tied_at - timedelta(days=1),
                        "created_at": tied_at,
                    },
                )

        expected = sorted((anchor_item_id, *peer_ids), reverse=True)
        seen: list[UUID] = []
        cursor: str | None = None
        for _ in expected:
            page = await query_service.get_feed(
                mode="all",
                domain="safety",
                content_type=None,
                sort="latest",
                cursor=cursor,
                limit=1,
            )
            assert len(page.items) == 1
            seen.append(page.items[0].id)
            cursor = page.next_cursor
        assert seen == expected
        assert len(seen) == len(set(seen))
    finally:
        async with runtime_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    DELETE FROM safety_regulation_profile
                    WHERE item_id IN (:peer_one, :peer_two)
                    """
                ),
                {"peer_one": peer_ids[0], "peer_two": peer_ids[1]},
            )
            await connection.execute(
                text(
                    """
                    DELETE FROM intelligence_item
                    WHERE id IN (:peer_one, :peer_two)
                    """
                ),
                {"peer_one": peer_ids[0], "peer_two": peer_ids[1]},
            )
            if original_activity_at is not None and original_updated_at is not None:
                await connection.execute(
                    text(
                        """
                        UPDATE intelligence_item
                        SET activity_at = :activity_at, updated_at = :updated_at
                        WHERE id = :anchor_item_id
                        """
                    ),
                    {
                        "activity_at": original_activity_at,
                        "updated_at": original_updated_at,
                        "anchor_item_id": anchor_item_id,
                    },
                )


async def _admit_fixture_source(service: SourceRegistryService) -> UUID:
    unique = uuid4().hex
    source = await service.create_source(
        CreateSourceRequest(
            name=f"应急管理部固定测试来源-{unique}",
            base_url="https://www.mem.gov.cn/",
            channel="SAFETY",
            source_type="government",
            authority_level="A1",
            priority="P0",
            collection_method="fixture_html",
            poll_interval_minutes=15,
            owner="round02-tests",
        ),
        actor_id=SUBMITTER,
        request_id=f"source-{unique}",
    )
    await service.transition(
        source.id,
        SourceTransitionRequest(
            target_state="COMPLIANCE_REVIEW",
            reason="开始固定来源合规审查",
        ),
        actor_id=SUBMITTER,
        request_id=f"compliance-{unique}",
    )
    now = datetime.now(UTC)
    await service.save_policy(
        source.id,
        SourcePolicySubmission.model_validate(
            {
                "policy_version": f"round02-{unique}",
                "status": "VALID",
                "robots_review": {
                    "result": "ALLOWED",
                    "evidence_url": "https://www.mem.gov.cn/robots.txt",
                    "checked_at": now.isoformat(),
                },
                "terms_review": {
                    "result": "NOT_PRESENT",
                    "evidence_url": "https://www.mem.gov.cn/terms-review",
                    "checked_at": now.isoformat(),
                },
                "copyright": {
                    "storage_policy": "RAW_EVIDENCE_ALLOWED",
                    "display_policy": "METADATA_EXCERPT_LINK",
                    "fulltext_allowed": False,
                    "image_allowed": False,
                    "excerpt_max_chars": 300,
                    "attribution_template": "来源: {source_name}",
                },
                "access": {
                    "allowed_domains": ["www.mem.gov.cn"],
                    "requires_auth": False,
                    "rate_limit_per_minute": 10,
                    "user_agent": "SRBGSourceAdapter/1.0",
                },
                "review": {
                    "valid_until": (now + timedelta(days=30)).isoformat(),
                    "approval_id": f"round02-{unique}",
                },
            }
        ),
        actor_id=SUBMITTER,
        request_id=f"policy-{unique}",
    )
    await service.transition(
        source.id,
        SourceTransitionRequest(target_state="FIXTURE_TEST", reason="合规策略有效"),
        actor_id=SUBMITTER,
        request_id=f"fixture-state-{unique}",
    )
    for index in range(30):
        fixture = (
            "<!doctype html><html><head><title>Admission fixture "
            f"{index}</title></head><body>round02-{unique}-{index}</body></html>"
        ).encode()
        await service.upload_fixture(
            source.id,
            content=fixture,
            filename=f"admission-{index}.html",
            declared_mime="text/html",
            canonical_url=f"https://www.mem.gov.cn/round02-fixtures/{unique}/{index}.shtml",
            actor_id=SUBMITTER,
            request_id=f"fixture-{unique}-{index}",
        )
    await service.save_onboarding(
        source.id,
        SourceOnboardingSubmission(
            checks=[
                OnboardingCheckEvidence(
                    code=code,
                    evidence_ref=f"https://www.mem.gov.cn/round02-evidence/{code}",
                )
                for code in sorted(REQUIRED_ONBOARDING_CHECKS)
            ],
            valid_until=now + timedelta(days=30),
        ),
        actor_id=SUBMITTER,
        request_id=f"onboarding-{unique}",
    )
    await service.transition(
        source.id,
        SourceTransitionRequest(target_state="APPROVED", reason="30 个样本全部通过"),
        actor_id=SUBMITTER,
        request_id=f"approved-{unique}",
    )
    active = await service.set_enabled(
        source.id,
        True,
        "启用固定样本来源",
        actor_id=SUBMITTER,
        request_id=f"active-{unique}",
    )
    assert active.effective_active is True
    return source.id


def _fixture_adapter() -> FixedMemFixtureAdapter:
    manifest = json.loads(
        (FIXTURES / "round02-mem-fixture-manifest.json").read_text(encoding="utf-8")
    )
    responses = {item["kind"]: item for item in manifest["responses"]}
    return FixedMemFixtureAdapter(
        list_content=base64.b64decode(
            (FIXTURES / responses["LIST"]["file"]).read_text(encoding="ascii")
        ),
        detail_content=base64.b64decode(
            (FIXTURES / responses["DETAIL"]["file"]).read_text(encoding="ascii")
        ),
        list_etag=responses["LIST"]["etag"],
        detail_etag=responses["DETAIL"]["etag"],
        detail_url=DETAIL_URL,
        fetched_at=datetime.fromisoformat(manifest["captured_at"].replace("Z", "+00:00")),
    )
