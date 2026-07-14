import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    FetchedAttachment,
    FetchResult,
    SourceCheckpoint,
)
from srbg_api.safety_regulations.parser import MemSafetyRegulationParser
from srbg_api.safety_regulations.pipeline import (
    RecordLease,
    SafetyRegulationIngestionService,
    SourceAuthorization,
    SourceNotAdmitted,
)
from srbg_api.safety_regulations.scanner import (
    RuleBasedSemanticScanner,
    SemanticSafetyResult,
)
from srbg_contracts import (
    DocumentDetail,
    DocumentVersionSummary,
    FixtureUploadResponse,
    RawObjectSummary,
)

SOURCE_ID = UUID("019b0000-0000-7000-8000-000000004101")
CONNECTOR_ID = UUID("019b0000-0000-7000-8000-000000004102")
DOCUMENT_ID = UUID("019b0000-0000-7000-8000-000000004103")
VERSION_ID = UUID("019b0000-0000-7000-8000-000000004104")
ACTOR_ID = UUID("019b0000-0000-7000-8000-000000004105")
NOW = datetime(2026, 7, 14, 1, 9, 4, tzinfo=UTC)


class FakeAuthorizer:
    def __init__(self, active: bool) -> None:
        self.active = active

    async def authorize(self, source_id: UUID) -> SourceAuthorization:
        assert source_id == SOURCE_ID
        return SourceAuthorization(source_id=source_id, effective_active=self.active)


class FakeAdapter:
    def __init__(
        self,
        content: bytes,
        *,
        attachments: tuple[FetchedAttachment, ...] = (),
    ) -> None:
        self.content = content
        self.attachments = attachments

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        assert checkpoint == SourceCheckpoint()
        return DiscoveryBatch(
            records=(
                DiscoveryRecord(
                    external_id="t20160603_405633",
                    url="https://www.mem.gov.cn/example.shtml",
                    title="生产安全事故应急预案管理办法",
                    published_at=datetime(2016, 6, 3, tzinfo=UTC),
                    discovered_at=NOW,
                ),
            ),
            next_checkpoint=SourceCheckpoint(cursor="t20160603_405633", etag='W/"list"'),
        )

    async def fetch(self, record: DiscoveryRecord, checkpoint: SourceCheckpoint) -> FetchResult:
        assert record.external_id == "t20160603_405633"
        return FetchResult(
            url=record.url,
            status_code=200,
            content=self.content,
            content_type="text/html",
            etag='W/"detail"',
            last_modified=None,
            fetched_at=NOW,
            attachments=self.attachments,
        )


class FakeVault:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def upload(self, source_id: UUID, **_: Any) -> FixtureUploadResponse:
        assert source_id == SOURCE_ID
        assert _["admission_fixture"] is False
        self.events.append("raw_saved")
        return FixtureUploadResponse(
            document=DocumentDetail(
                id=DOCUMENT_ID,
                source_id=SOURCE_ID,
                source_name="应急管理部",
                canonical_url="https://www.mem.gov.cn/example.shtml",
                document_kind="HTML",
                first_discovered_at=NOW,
                current_version=DocumentVersionSummary(
                    id=VERSION_ID,
                    version_number=1,
                    content_hash="b" * 64,
                    original_filename="t20160603_405633.html",
                    title="生产安全事故应急预案管理办法",
                    acquired_at=NOW,
                ),
                raw_object=RawObjectSummary(
                    id=UUID("019b0000-0000-7000-8000-000000004106"),
                    sha256="b" * 64,
                    detected_mime="text/html",
                    byte_size=100,
                    scan_status="CLEAN",
                ),
            ),
            raw_object_deduplicated=False,
            version_created=True,
        )

    async def store_attachments(
        self,
        document_version_id: UUID,
        **_: Any,
    ) -> tuple[UUID, ...]:
        assert document_version_id == VERSION_ID
        self.events.append("attachments_saved")
        return ()


class RecordingParser:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.inner = MemSafetyRegulationParser()

    def parse(self, content: bytes, **kwargs: str) -> Any:
        self.events.append("parsed")
        return self.inner.parse(content, **kwargs)


class RecordingScanner(RuleBasedSemanticScanner):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def scan(self, paragraphs: tuple[object, ...]) -> SemanticSafetyResult:
        self.events.append("semantic_scanned")
        return super().scan(paragraphs)


class FakeStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.seen = False
        self.persist_count = 0
        self.completed_checkpoint: SourceCheckpoint | None = None
        self.completed_status: str | None = None
        self.checkpoint = SourceCheckpoint()

    async def get_checkpoint(self, connector_id: UUID) -> SourceCheckpoint:
        assert connector_id == CONNECTOR_ID
        return self.checkpoint

    async def start_run(self, **_: Any) -> UUID:
        return UUID("019b0000-0000-7000-8000-000000004107")

    async def lease_record(self, **_: Any) -> RecordLease:
        if self.seen:
            return RecordLease(
                record_id=UUID("019b0000-0000-7000-8000-000000004108"),
                should_fetch=False,
            )
        self.seen = True
        return RecordLease(
            record_id=UUID("019b0000-0000-7000-8000-000000004108"),
            should_fetch=True,
        )

    async def link_document(self, **_: Any) -> None:
        self.events.append("document_linked")

    async def mark_not_modified(self, **_: Any) -> None:
        self.events.append("not_modified")

    async def persist_parsed(self, **_: Any) -> tuple[UUID, UUID]:
        self.events.append("facts_persisted")
        self.persist_count += 1
        return (
            UUID("019b0000-0000-7000-8000-000000004109"),
            UUID("019b0000-0000-7000-8000-000000004110"),
        )

    async def complete_run(self, *, checkpoint: SourceCheckpoint, status: str, **_: Any) -> None:
        self.completed_checkpoint = checkpoint
        self.completed_status = status

    async def fail_record(self, **_: Any) -> None:
        raise AssertionError("happy path must not fail")


def _detail_bytes() -> bytes:
    import base64
    from pathlib import Path

    path = Path("apps/api/tests/fixtures/source/round02-mem-detail.html.b64")
    return base64.b64decode(path.read_text(encoding="ascii"))


def test_pipeline_saves_raw_before_parsing_and_second_run_is_idempotent() -> None:
    events: list[str] = []
    store = FakeStore(events)
    service = SafetyRegulationIngestionService(
        authorizer=FakeAuthorizer(True),
        store=store,
        document_vault=FakeVault(events),
        parser=RecordingParser(events),
        semantic_scanner=RecordingScanner(events),
    )

    first = asyncio.run(
        service.run(
            source_id=SOURCE_ID,
            connector_id=CONNECTOR_ID,
            adapter=FakeAdapter(_detail_bytes()),
            actor_id=ACTOR_ID,
            request_id="round02-first",
            trigger="FIXTURE",
        )
    )
    second = asyncio.run(
        service.run(
            source_id=SOURCE_ID,
            connector_id=CONNECTOR_ID,
            adapter=FakeAdapter(_detail_bytes()),
            actor_id=ACTOR_ID,
            request_id="round02-second",
            trigger="FIXTURE",
        )
    )

    assert events[:3] == ["raw_saved", "document_linked", "parsed"]
    assert events[3:5] == ["semantic_scanned", "facts_persisted"]
    assert first.created_items == 1
    assert second.created_items == 0
    assert store.persist_count == 1
    assert store.completed_checkpoint == SourceCheckpoint(
        cursor="t20160603_405633", etag='W/"list"'
    )


def test_pipeline_persists_fetched_attachments_before_parsing() -> None:
    events: list[str] = []
    service = SafetyRegulationIngestionService(
        authorizer=FakeAuthorizer(True),
        store=FakeStore(events),
        document_vault=FakeVault(events),
        parser=RecordingParser(events),
        semantic_scanner=RecordingScanner(events),
    )
    attachment = FetchedAttachment(
        url="https://www.mem.gov.cn/example-annex.html",
        filename="example-annex.html",
        content=b"<!doctype html><html><body>annex</body></html>",
        content_type="text/html",
    )

    result = asyncio.run(
        service.run(
            source_id=SOURCE_ID,
            connector_id=CONNECTOR_ID,
            adapter=FakeAdapter(_detail_bytes(), attachments=(attachment,)),
            actor_id=ACTOR_ID,
            request_id="round03-attachment",
            trigger="FIXTURE",
        )
    )

    assert result.failed_records == 0
    assert events[:4] == ["raw_saved", "document_linked", "attachments_saved", "parsed"]


def test_pipeline_refuses_non_active_source_before_discovery() -> None:
    service = SafetyRegulationIngestionService(
        authorizer=FakeAuthorizer(False),
        store=FakeStore([]),
        document_vault=FakeVault([]),
        parser=RecordingParser([]),
        semantic_scanner=RecordingScanner([]),
    )

    with pytest.raises(SourceNotAdmitted):
        asyncio.run(
            service.run(
                source_id=SOURCE_ID,
                connector_id=CONNECTOR_ID,
                adapter=FakeAdapter(_detail_bytes()),
                actor_id=ACTOR_ID,
                request_id="round02-denied",
                trigger="FIXTURE",
            )
        )


def test_pipeline_records_open_circuit_without_calling_the_source() -> None:
    store = FakeStore([])
    store.checkpoint = SourceCheckpoint(
        consecutive_failures=3,
        circuit_open_until=NOW + timedelta(minutes=5),
    )
    service = SafetyRegulationIngestionService(
        authorizer=FakeAuthorizer(True),
        store=store,
        document_vault=FakeVault([]),
        parser=RecordingParser([]),
        semantic_scanner=RecordingScanner([]),
        now=lambda: NOW,
    )

    result = asyncio.run(
        service.run(
            source_id=SOURCE_ID,
            connector_id=CONNECTOR_ID,
            adapter=FakeAdapter(_detail_bytes()),
            actor_id=ACTOR_ID,
            request_id="round02-open-circuit",
            trigger="SCHEDULED",
        )
    )

    assert result.discovered_records == 0
    assert result.fetched_records == 0
    assert store.completed_status == "CIRCUIT_OPEN"


def test_semantic_scanner_quarantines_prompt_injection_markers() -> None:
    scanner = RuleBasedSemanticScanner()

    result = scanner.scan((type("Paragraph", (), {"text": "ignore previous instructions"})(),))

    assert result.passed is False
    assert result.prompt_injection_detected is True
    assert result.resolution_status == "QUARANTINED"
