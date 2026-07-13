from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.document_vault.service import (
    DocumentVaultService,
    FixtureRecord,
    SourceVaultMetrics,
)
from srbg_contracts import (
    DocumentDetail,
    DocumentVersionSummary,
    FixtureUploadResponse,
    RawObjectSummary,
    ScanStatus,
)

SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000001")
ACTOR_ID = UUID("019b0000-0000-7000-8000-000000009001")


class CleanScanner:
    async def scan(self, content: bytes) -> None:
        assert content


class MemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_count = 0

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        assert content_type in {"text/html", "application/pdf"}
        if key not in self.objects:
            self.objects[key] = content
            self.put_count += 1
        return f"etag-{len(content)}"


class FailingObjectStore:
    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        raise OSError("object storage unavailable")


class MemoryVaultRepository:
    def __init__(self) -> None:
        self.raw: dict[str, UUID] = {}
        self.documents: dict[str, tuple[UUID, list[FixtureRecord]]] = {}

    async def source_accepts_fixture(self, source_id: UUID, canonical_url: str) -> bool:
        return source_id == SOURCE_ID and canonical_url.startswith("https://example.test/")

    async def raw_object_exists(self, content_hash: str) -> bool:
        return content_hash in self.raw

    async def record_fixture(self, record: FixtureRecord) -> FixtureUploadResponse:
        raw_deduplicated = record.content_hash in self.raw
        raw_id = self.raw.setdefault(
            record.content_hash,
            UUID(f"019b0000-0000-7000-8000-{len(self.raw) + 100:012d}"),
        )
        document_id, versions = self.documents.setdefault(
            record.canonical_url,
            (UUID(f"019b0000-0000-7000-8000-{len(self.documents) + 200:012d}"), []),
        )
        previous = next(
            (version for version in versions if version.content_hash == record.content_hash),
            None,
        )
        version_created = previous is None
        if version_created:
            versions.append(record)
        current = versions[-1]
        version_id = UUID(f"019b0000-0000-7000-8000-{len(versions) + 300:012d}")
        document = DocumentDetail(
            id=document_id,
            source_id=SOURCE_ID,
            source_name="测试来源",
            canonical_url=record.canonical_url,
            document_kind=record.document_kind,
            first_discovered_at=record.acquired_at,
            current_version=DocumentVersionSummary(
                id=version_id,
                version_number=len(versions),
                content_hash=current.content_hash,
                original_filename=current.filename,
                title=current.title,
                acquired_at=current.acquired_at,
            ),
            raw_object=RawObjectSummary(
                id=raw_id,
                sha256=current.content_hash,
                detected_mime=current.detected_mime,
                byte_size=current.byte_size,
                scan_status=ScanStatus.CLEAN,
            ),
        )
        return FixtureUploadResponse(
            document=document,
            raw_object_deduplicated=raw_deduplicated,
            version_created=version_created,
        )


def _service() -> tuple[DocumentVaultService, MemoryVaultRepository, MemoryObjectStore]:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=CleanScanner(),
        metrics=SourceVaultMetrics(),
    )
    return service, repository, store


async def _upload(service: DocumentVaultService, content: bytes) -> FixtureUploadResponse:
    return await service.upload(
        SOURCE_ID,
        content=content,
        filename="fixture.html",
        declared_mime="text/html",
        canonical_url="https://example.test/document/1",
        actor_id=ACTOR_ID,
        request_id="request-1",
        acquired_at=datetime.now(UTC),
    )


async def test_same_bytes_are_stored_once_and_do_not_create_duplicate_version() -> None:
    service, repository, store = _service()
    content = b"<!doctype html><html><title>One</title><body>fixture</body></html>"

    first = await _upload(service, content)
    second = await _upload(service, content)

    assert first.raw_object_deduplicated is False
    assert first.version_created is True
    assert second.raw_object_deduplicated is True
    assert second.version_created is False
    assert len(repository.raw) == 1
    assert store.put_count == 1
    assert service.metrics.uploads == 2
    assert service.metrics.deduplications == 1


async def test_same_url_with_changed_content_creates_new_document_version() -> None:
    service, repository, store = _service()

    first = await _upload(service, b"<!doctype html><html><body>version one</body></html>")
    second = await _upload(service, b"<!doctype html><html><body>version two</body></html>")

    assert first.document.id == second.document.id
    assert second.document.current_version.version_number == 2
    assert len(repository.raw) == 2
    assert store.put_count == 2


async def test_storage_failures_and_rejections_are_counted() -> None:
    repository = MemoryVaultRepository()
    metrics = SourceVaultMetrics()
    service = DocumentVaultService(
        repository=repository,
        object_store=FailingObjectStore(),
        malware_scanner=CleanScanner(),
        metrics=metrics,
    )

    with pytest.raises(OSError, match="object storage unavailable"):
        await _upload(service, b"<!doctype html><html><body>valid</body></html>")
    with pytest.raises(ValueError, match="MIME"):
        await service.upload(
            SOURCE_ID,
            content=b"not html",
            filename="fixture.html",
            declared_mime="text/html",
            canonical_url="https://example.test/document/2",
            actor_id=ACTOR_ID,
            request_id="request-2",
            acquired_at=datetime.now(UTC),
        )

    assert metrics.uploads == 2
    assert metrics.object_storage_errors == 1
    assert metrics.rejections == 1
    rendered = metrics.render_prometheus()
    assert "srbg_source_fixture_uploads_total 2" in rendered
    assert "srbg_source_fixture_rejections_total 1" in rendered
    assert "srbg_raw_object_storage_errors_total 1" in rendered
