from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from srbg_api.acquisition.contracts import FetchedAttachment
from srbg_api.document_vault.security import (
    MalwareDetected,
    MalwareScanInconclusive,
    UploadRejected,
)
from srbg_api.document_vault.service import (
    AttachmentAttemptRecord,
    AttachmentQuarantined,
    AttachmentRecord,
    DocumentVaultService,
    FixtureRecord,
    RejectedRawRecord,
    SourceVaultMetrics,
)
from srbg_api.pdf_processing.security import FileSecurityPolicy, SecurityViolation
from srbg_contracts import (
    DocumentDetail,
    DocumentVersionSummary,
    FixtureUploadResponse,
    RawObjectSummary,
    ScanStatus,
)

SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000001")
ACTOR_ID = UUID("019b0000-0000-7000-8000-000000009001")
TRIAL_ID = UUID("019b0000-0000-7000-8000-000000009002")


class CleanScanner:
    async def scan(self, content: bytes) -> None:
        assert content


class RejectOnceScanner:
    def __init__(self) -> None:
        self.calls = 0

    async def scan(self, content: bytes) -> None:
        self.calls += 1
        if self.calls == 1:
            raise MalwareDetected("scanner rejected the immutable bytes")


class InconclusiveOnceScanner:
    def __init__(self) -> None:
        self.calls = 0

    async def scan(self, content: bytes) -> None:
        self.calls += 1
        if self.calls == 1:
            raise MalwareScanInconclusive("scanner temporarily unavailable")


class RejectSecondScan:
    def __init__(self) -> None:
        self.calls = 0

    async def scan(self, content: bytes) -> None:
        self.calls += 1
        if self.calls == 2:
            raise MalwareDetected("archive child contains malware")


class InconclusiveSecondScan:
    def __init__(self) -> None:
        self.calls = 0

    async def scan(self, content: bytes) -> None:
        self.calls += 1
        if self.calls == 2:
            raise MalwareScanInconclusive("archive child scan is unavailable")


class MemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_count = 0

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        assert content_type in {"application/octet-stream", "text/html", "application/pdf"}
        if key not in self.objects:
            self.objects[key] = content
            self.put_count += 1
        return f"etag-{len(content)}"

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        content = self.objects[key]
        if max_bytes is not None and len(content) > max_bytes:
            raise OSError("object exceeds bounded read limit")
        return content


class FailingObjectStore:
    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        raise OSError("object storage unavailable")


class MemoryVaultRepository:
    def __init__(self) -> None:
        self.raw: dict[str, UUID] = {}
        self.documents: dict[str, tuple[UUID, list[FixtureRecord]]] = {}
        self.attachments: list[AttachmentRecord] = []
        self.attachment_attempts: list[AttachmentAttemptRecord] = []
        self.rejected_raw: list[RejectedRawRecord] = []
        self.blocked_raw: set[str] = set()

    async def source_accepts_fixture(
        self, source_id: UUID, canonical_url: str
    ) -> UUID | None:
        if source_id == SOURCE_ID and canonical_url.startswith("https://example.test/"):
            return TRIAL_ID
        return None

    async def raw_object_exists(self, content_hash: str) -> bool:
        return content_hash in self.raw

    async def raw_object_security_blocked(self, content_hash: str) -> bool:
        return content_hash in self.blocked_raw

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

    async def record_attachment(self, record: AttachmentRecord) -> UUID:
        if record.globally_quarantined:
            self.blocked_raw.add(record.content_hash)
        self.attachments.append(record)
        self.raw.setdefault(record.content_hash, record.raw_object_id)
        return record.attachment_id

    async def record_attachment_attempt(self, record: AttachmentAttemptRecord) -> UUID:
        self.attachment_attempts.append(record)
        return record.attempt_id

    async def record_rejected_raw(self, record: RejectedRawRecord) -> UUID:
        self.rejected_raw.append(record)
        if record.globally_quarantined:
            self.blocked_raw.add(record.content_hash)
        self.raw.setdefault(record.content_hash, record.raw_object_id)
        return self.raw[record.content_hash]


class NegativeFactRaceRepository(MemoryVaultRepository):
    async def record_fixture(self, record: FixtureRecord) -> FixtureUploadResponse:
        self.blocked_raw.add(record.content_hash)
        self.raw.setdefault(record.content_hash, uuid_for_test())
        raise RuntimeError("negative fact won the fixture commit race")


def uuid_for_test() -> UUID:
    return UUID("019b0000-0000-7000-8000-000000000499")


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


async def test_negative_fact_commit_race_appends_rejected_trial_attempt() -> None:
    repository = NegativeFactRaceRepository()
    service = DocumentVaultService(
        repository=repository,
        object_store=MemoryObjectStore(),
        malware_scanner=CleanScanner(),
        metrics=SourceVaultMetrics(),
    )

    with pytest.raises(RuntimeError, match="commit race"):
        await _upload(service, b"<!doctype html><html><body>race</body></html>")

    assert [record.reason_code for record in repository.rejected_raw] == [
        "RAW_SECURITY_HISTORY"
    ]
    assert repository.rejected_raw[0].globally_quarantined is False


async def test_fixture_persists_the_validated_nfc_filename() -> None:
    service, repository, _ = _service()

    await service.upload(
        SOURCE_ID,
        content=b"<!doctype html><html><body>nfc</body></html>",
        filename="cafe\u0301.html",
        declared_mime="text/html",
        canonical_url="https://example.test/document/nfc",
        actor_id=ACTOR_ID,
        request_id="fixture-nfc-filename",
        acquired_at=datetime.now(UTC),
    )

    assert repository.documents["https://example.test/document/nfc"][1][0].filename == (
        "café.html"
    )


async def test_fixture_declared_mime_is_bounded_before_object_storage() -> None:
    service, repository, store = _service()

    with pytest.raises(UploadRejected, match="declared MIME"):
        await service.upload(
            SOURCE_ID,
            content=b"<!doctype html><html><body>mime</body></html>",
            filename="fixture.html",
            declared_mime="text/html\r\nX-Evil: yes",
            canonical_url="https://example.test/document/mime",
            actor_id=ACTOR_ID,
            request_id="fixture-invalid-mime",
            acquired_at=datetime.now(UTC),
        )

    assert store.objects == {}
    assert repository.rejected_raw == []


def _pdf_with_escaped_javascript_names() -> bytes:
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R /Open#41ction 4 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] >>",
        b"<< /S /Java#53cript /J#53 (app.alert(1)) >>",
    )
    document = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(document)


@pytest.mark.parametrize(
    "canonical_url",
    [
        "https://example.test:444/document/1",
        "https://example.test/document/1#fragment",
        "https://example.test/document/1?api_key=secret",
        "https://example.test/document/1?X-Amz-Signature=secret",
        "https://user:password@example.test/document/1",
    ],
)
async def test_unsafe_fixture_url_is_rejected_before_object_storage(
    canonical_url: str,
) -> None:
    service, _, store = _service()

    with pytest.raises(UploadRejected, match="invalid canonical document URL"):
        await service.upload(
            SOURCE_ID,
            content=b"<!doctype html><html><body>fixture</body></html>",
            filename="fixture.html",
            declared_mime="text/html",
            canonical_url=canonical_url,
            actor_id=ACTOR_ID,
            request_id="unsafe-url",
            acquired_at=datetime.now(UTC),
        )

    assert store.put_count == 0


async def test_same_bytes_are_stored_once_and_do_not_create_duplicate_version() -> None:
    service, repository, store = _service()
    content = b"<!doctype html><html><title>One</title><body>fixture</body></html>"

    first = await _upload(service, content)
    second = await _upload(service, content)

    stored = repository.documents["https://example.test/document/1"][1][0]
    assert stored.response_sha256 != stored.content_hash
    expected_evidence = (
        b'200\n{"content-type":"text/html","etag":"","last-modified":""}\n'
        + content
    )
    assert stored.response_sha256 == sha256(expected_evidence).hexdigest()

    assert first.raw_object_deduplicated is False
    assert first.version_created is True
    assert second.raw_object_deduplicated is True
    assert second.version_created is False
    assert len(repository.raw) == 1
    assert store.put_count == 1
    assert service.metrics.uploads == 2
    assert service.metrics.deduplications == 1


async def test_fixture_replay_reads_only_hash_verified_bounded_raw_bytes() -> None:
    service, repository, store = _service()
    content = b"<!doctype html><html><body>bounded replay</body></html>"
    await _upload(service, content)
    stored = repository.documents["https://example.test/document/1"][1][0]

    assert await service.read_fixture_object(
        stored.object_key,
        expected_sha256=stored.content_hash,
        expected_size=len(content),
    ) == content

    with pytest.raises(UploadRejected, match="size"):
        await service.read_fixture_object(
            stored.object_key,
            expected_sha256=stored.content_hash,
            expected_size=len(content) + 1,
        )
    store.objects[stored.object_key] = content + b"tampered"
    with pytest.raises(UploadRejected, match=r"size|hash"):
        await service.read_fixture_object(
            stored.object_key,
            expected_sha256=stored.content_hash,
            expected_size=len(content),
        )


async def test_rejected_raw_bytes_cannot_be_promoted_by_a_later_clean_scan() -> None:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    scanner = RejectOnceScanner()
    service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=scanner,
        metrics=SourceVaultMetrics(),
    )
    content = b"<!doctype html><html><body>immutable bytes</body></html>"

    with pytest.raises(MalwareDetected, match="scanner rejected"):
        await _upload(service, content)
    with pytest.raises(UploadRejected, match="immutable rejected security evidence"):
        await _upload(service, content)

    assert scanner.calls == 1
    assert len(repository.rejected_raw) == 2
    assert repository.rejected_raw[1].reason_code == "RAW_SECURITY_HISTORY"
    assert repository.rejected_raw[1].trial_run_id == TRIAL_ID
    assert repository.documents == {}
    assert store.put_count == 1


async def test_inconclusive_scan_rejects_attempt_without_poisoning_healthy_retry() -> None:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    scanner = InconclusiveOnceScanner()
    service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=scanner,
        metrics=SourceVaultMetrics(),
    )
    content = b"<!doctype html><html><body>retryable bytes</body></html>"

    with pytest.raises(MalwareScanInconclusive, match="temporarily unavailable"):
        await _upload(service, content)
    recovered = await _upload(service, content)

    assert scanner.calls == 2
    assert len(repository.rejected_raw) == 1
    assert repository.rejected_raw[0].globally_quarantined is False
    assert repository.blocked_raw == set()
    assert recovered.version_created is True


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
    rejection_store = MemoryObjectStore()
    rejection_service = DocumentVaultService(
        repository=repository,
        object_store=rejection_store,
        malware_scanner=CleanScanner(),
        metrics=metrics,
    )
    with pytest.raises(ValueError, match="MIME"):
        await rejection_service.upload(
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
    assert len(repository.rejected_raw) == 1
    assert repository.rejected_raw[0].reason_code == "UPLOAD_SECURITY_REJECTED"
    assert repository.rejected_raw[0].object_key in rejection_store.objects
    assert rejection_store.objects[repository.rejected_raw[0].object_key] == b"not html"
    rendered = metrics.render_prometheus()
    assert "srbg_source_fixture_uploads_total 2" in rendered
    assert "srbg_source_fixture_rejections_total 1" in rendered
    assert "srbg_raw_object_storage_errors_total 1" in rendered


async def test_untrusted_bytes_are_privately_stored_before_malware_scan() -> None:
    events: list[str] = []

    class RecordingStore(MemoryObjectStore):
        async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
            events.append("raw_stored")
            return await super().put_if_absent(key, content, content_type)

    class RecordingScanner:
        async def scan(self, content: bytes) -> None:
            events.append("malware_scanned")

    service = DocumentVaultService(
        repository=MemoryVaultRepository(),
        object_store=RecordingStore(),
        malware_scanner=RecordingScanner(),
        metrics=SourceVaultMetrics(),
    )

    await _upload(service, b"<!doctype html><html><body>valid</body></html>")

    assert events == ["raw_stored", "malware_scanned"]


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


async def test_fetched_zip_attachment_is_persisted_as_a_clean_one_level_tree() -> None:
    service, repository, store = _service()
    uploaded = await _upload(
        service,
        b"<!doctype html><html><body>main regulation</body></html>",
    )
    archive = _zip_bytes(
        {
            "annex/one.html": b"<!doctype html><html><body>annex one</body></html>",
            "two.html": b"<!doctype html><html><body>annex two</body></html>",
        }
    )

    roots = await service.store_attachments(
        uploaded.document.current_version.id,
        attachments=(
            FetchedAttachment(
                url="https://example.test/document/1/annexes.zip",
                filename="annexes.zip",
                content=archive,
                content_type="application/zip",
            ),
        ),
        acquired_at=datetime.now(UTC),
    )

    assert len(roots) == 1
    assert len(repository.attachments) == 3
    root = repository.attachments[0]
    children = repository.attachments[1:]
    assert root.attachment_id == roots[0]
    assert root.parent_attachment_id is None
    assert root.depth == 0
    assert root.security_status == "CLEAN"
    assert {child.parent_attachment_id for child in children} == {root.attachment_id}
    assert {child.depth for child in children} == {1}
    assert {child.normalized_path for child in children} == {"annex/one.html", "two.html"}
    assert all(child.security_status == "CLEAN" for child in children)
    assert len(store.objects) == 4  # main document, ZIP root, and two extracted children


async def test_attachment_with_rejected_raw_history_cannot_be_promoted_clean() -> None:
    service, repository, store = _service()
    content = b"<!doctype html><html><body>blocked attachment</body></html>"
    content_hash = sha256(content).hexdigest()
    repository.raw[content_hash] = UUID("019b0000-0000-7000-8000-000000000399")
    repository.blocked_raw.add(content_hash)

    with pytest.raises(AttachmentQuarantined) as captured:
        await service.store_attachments(
            UUID("019b0000-0000-7000-8000-000000000301"),
            attachments=(
                FetchedAttachment(
                    url="https://example.test/document/1/blocked.html",
                    filename="blocked.html",
                    content=content,
                    content_type="text/html",
                ),
            ),
            acquired_at=datetime.now(UTC),
        )

    assert captured.value.code == "ATTACHMENT_RAW_SECURITY_HISTORY"
    assert repository.attachments == []
    assert store.put_count == 0
    assert [attempt.outcome for attempt in repository.attachment_attempts] == [
        "REJECTED_SECURITY_HISTORY"
    ]


async def test_clean_attachment_then_quarantine_is_retained_and_blocks_repromotion() -> None:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    clean_service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=CleanScanner(),
        metrics=SourceVaultMetrics(),
    )
    reject_scanner = RejectOnceScanner()
    rejecting_service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=reject_scanner,
        metrics=SourceVaultMetrics(),
    )
    content = b"<!doctype html><html><body>security changes</body></html>"
    attachment = FetchedAttachment(
        url="https://example.test/document/1/security.html",
        filename="security.html",
        content=content,
        content_type="text/html",
    )
    version_id = UUID("019b0000-0000-7000-8000-000000000301")

    await clean_service.store_attachments(
        version_id, attachments=(attachment,), acquired_at=datetime.now(UTC)
    )
    with pytest.raises(AttachmentQuarantined, match="MALWARE_DETECTED"):
        await rejecting_service.store_attachments(
            version_id, attachments=(attachment,), acquired_at=datetime.now(UTC)
        )
    with pytest.raises(AttachmentQuarantined) as captured:
        await clean_service.store_attachments(
            version_id, attachments=(attachment,), acquired_at=datetime.now(UTC)
        )

    assert captured.value.code == "ATTACHMENT_RAW_SECURITY_HISTORY"
    assert [item.security_status for item in repository.attachments] == [
        "CLEAN",
        "QUARANTINED",
    ]


async def test_inconclusive_attachment_scan_does_not_poison_a_healthy_retry() -> None:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    scanner = InconclusiveOnceScanner()
    service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=scanner,
        metrics=SourceVaultMetrics(),
    )
    attachment = FetchedAttachment(
        url="https://example.test/document/1/retry.html",
        filename="retry.html",
        content=b"<!doctype html><html><body>retry</body></html>",
        content_type="text/html",
    )
    version_id = UUID("019b0000-0000-7000-8000-000000000301")

    with pytest.raises(AttachmentQuarantined, match="MALWARE_SCAN_INCONCLUSIVE"):
        await service.store_attachments(
            version_id,
            attachments=(attachment,),
            acquired_at=datetime.now(UTC),
        )

    roots = await service.store_attachments(
        version_id,
        attachments=(attachment,),
        acquired_at=datetime.now(UTC),
    )

    assert len(roots) == 1
    assert [item.security_status for item in repository.attachments] == ["CLEAN"]
    assert repository.blocked_raw == set()
    assert store.put_count == 1
    assert [attempt.outcome for attempt in repository.attachment_attempts] == [
        "RECEIVED",
        "INCONCLUSIVE",
        "RECEIVED",
        "ACCEPTED",
    ]


async def test_contextual_attachment_mime_rejection_does_not_poison_same_bytes() -> None:
    service, repository, _ = _service()
    content = b"<!doctype html><html><body>contextual metadata</body></html>"
    version_id = UUID("019b0000-0000-7000-8000-000000000301")

    with pytest.raises(AttachmentQuarantined, match="MIME_MISMATCH"):
        await service.store_attachments(
            version_id,
            attachments=(
                FetchedAttachment(
                    url="https://example.test/document/1/context.pdf",
                    filename="context.pdf",
                    content=content,
                    content_type="application/pdf",
                ),
            ),
            acquired_at=datetime.now(UTC),
        )

    roots = await service.store_attachments(
        version_id,
        attachments=(
            FetchedAttachment(
                url="https://example.test/document/1/context.html",
                filename="context.html",
                content=content,
                content_type="text/html",
            ),
        ),
        acquired_at=datetime.now(UTC),
    )

    assert len(roots) == 1
    assert repository.blocked_raw == set()
    assert [attempt.outcome for attempt in repository.attachment_attempts] == [
        "RECEIVED",
        "REJECTED_CONTEXTUAL",
        "RECEIVED",
        "ACCEPTED",
    ]


async def test_malware_found_in_zip_child_blocks_that_child_hash_from_repromotion() -> None:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    scanner = RejectSecondScan()
    service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=scanner,
        metrics=SourceVaultMetrics(),
    )
    child_content = b"<!doctype html><html><body>infected child</body></html>"
    archive = _zip_bytes({"child.html": child_content})
    version_id = UUID("019b0000-0000-7000-8000-000000000301")

    with pytest.raises(AttachmentQuarantined, match="MALWARE_DETECTED"):
        await service.store_attachments(
            version_id,
            attachments=(
                FetchedAttachment(
                    url="https://example.test/document/1/archive.zip",
                    filename="archive.zip",
                    content=archive,
                    content_type="application/zip",
                ),
            ),
            acquired_at=datetime.now(UTC),
        )

    child_hash = sha256(child_content).hexdigest()
    assert child_hash in repository.blocked_raw
    assert any(
        item.content_hash == child_hash and item.security_status == "QUARANTINED"
        for item in repository.attachments
    )
    with pytest.raises(AttachmentQuarantined, match="ATTACHMENT_RAW_SECURITY_HISTORY"):
        await DocumentVaultService(
            repository=repository,
            object_store=store,
            malware_scanner=CleanScanner(),
            metrics=SourceVaultMetrics(),
        ).store_attachments(
            version_id,
            attachments=(
                FetchedAttachment(
                    url="https://example.test/document/1/child.html",
                    filename="child.html",
                    content=child_content,
                    content_type="text/html",
                ),
            ),
            acquired_at=datetime.now(UTC),
        )


async def test_inconclusive_zip_child_keeps_private_object_attempt_binding() -> None:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=InconclusiveSecondScan(),
        metrics=SourceVaultMetrics(),
    )
    child_content = b"<!doctype html><html><body>retry child</body></html>"
    archive = _zip_bytes({"child.html": child_content})

    with pytest.raises(AttachmentQuarantined, match="MALWARE_SCAN_INCONCLUSIVE"):
        await service.store_attachments(
            UUID("019b0000-0000-7000-8000-000000000301"),
            attachments=(
                FetchedAttachment(
                    url="https://example.test/document/1/archive.zip",
                    filename="archive.zip",
                    content=archive,
                    content_type="application/zip",
                ),
            ),
            acquired_at=datetime.now(UTC),
        )

    child_hash = sha256(child_content).hexdigest()
    assert child_hash in {attempt.content_hash for attempt in repository.attachment_attempts}
    assert any(
        attempt.content_hash == child_hash and attempt.outcome == "INCONCLUSIVE"
        for attempt in repository.attachment_attempts
    )
    assert repository.blocked_raw == set()


async def test_compression_bomb_attachment_is_quarantined_without_partial_children() -> None:
    service, repository, store = _service()
    uploaded = await _upload(
        service,
        b"<!doctype html><html><body>main regulation</body></html>",
    )
    archive = _zip_bytes({"bomb.html": b"<!doctype html>" + b"A" * 200_000})

    with pytest.raises(AttachmentQuarantined) as captured:
        await service.store_attachments(
            uploaded.document.current_version.id,
            attachments=(
                FetchedAttachment(
                    url="https://example.test/document/1/bomb.zip",
                    filename="bomb.zip",
                    content=archive,
                    content_type="application/zip",
                ),
            ),
            acquired_at=datetime.now(UTC),
        )

    assert captured.value.code == "ZIP_COMPRESSION_RATIO"
    assert len(repository.attachments) == 1
    root = repository.attachments[0]
    assert root.parent_attachment_id is None
    assert root.security_status == "QUARANTINED"
    assert root.reason_code == "ZIP_COMPRESSION_RATIO"
    assert any(value == archive for value in store.objects.values())


@pytest.mark.parametrize(
    ("max_entries", "max_total_bytes", "expected_code"),
    [
        (1, 100, "ATTACHMENT_COUNT_LIMIT"),
        (10, 10, "ATTACHMENT_TOTAL_SIZE_LIMIT"),
    ],
)
async def test_attachment_batch_budget_retains_roots_as_contextual_attempt_evidence(
    max_entries: int,
    max_total_bytes: int,
    expected_code: str,
) -> None:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=CleanScanner(),
        metrics=SourceVaultMetrics(),
        file_security_policy=FileSecurityPolicy(
            max_file_bytes=100,
            max_pdf_pages=10,
            max_ocr_pages=10,
            max_zip_entries=max_entries,
            max_uncompressed_bytes=max_total_bytes,
            max_compression_ratio=10,
            max_page_pixels=1_000_000,
        ),
    )
    attachments = tuple(
        FetchedAttachment(
            url=f"https://example.test/attachment/{index}",
            filename=f"attachment-{index}.html",
            content=b"<html></html>",
            content_type="text/html",
        )
        for index in range(2)
    )

    with pytest.raises(AttachmentQuarantined) as captured:
        await service.store_attachments(
            UUID("019b0000-0000-7000-8000-000000000301"),
            attachments=attachments,
            acquired_at=datetime.now(UTC),
        )

    assert captured.value.code == expected_code
    assert set(store.objects.values()) == {attachment.content for attachment in attachments}
    assert repository.attachments == []
    assert [attempt.outcome for attempt in repository.attachment_attempts] == [
        "RECEIVED",
        "RECEIVED",
        "REJECTED_CONTEXTUAL",
        "REJECTED_CONTEXTUAL",
    ]
    assert repository.blocked_raw == set()


async def test_multiple_zip_attachments_share_one_expanded_batch_budget() -> None:
    repository = MemoryVaultRepository()
    store = MemoryObjectStore()
    service = DocumentVaultService(
        repository=repository,
        object_store=store,
        malware_scanner=CleanScanner(),
        metrics=SourceVaultMetrics(),
        file_security_policy=FileSecurityPolicy(
            max_file_bytes=1_000,
            max_pdf_pages=10,
            max_ocr_pages=10,
            max_zip_entries=10,
            max_uncompressed_bytes=1_000,
            max_compression_ratio=1_000,
            max_page_pixels=1_000_000,
        ),
    )
    archives = tuple(
        FetchedAttachment(
            url=f"https://example.test/attachment/{index}.zip",
            filename=f"attachment-{index}.zip",
            content=_zip_bytes(
                {
                    f"attachment-{index}.html": (
                        b"<!doctype html><html><body>" + b"A" * 570 + b"</body></html>"
                    )
                }
            ),
            content_type="application/zip",
        )
        for index in range(2)
    )

    with pytest.raises(AttachmentQuarantined) as captured:
        await service.store_attachments(
            UUID("019b0000-0000-7000-8000-000000000301"),
            attachments=archives,
            acquired_at=datetime.now(UTC),
        )

    assert captured.value.code == "ATTACHMENT_TOTAL_SIZE_LIMIT"
    assert len(store.objects) == 2
    assert set(store.objects.values()) == {attachment.content for attachment in archives}
    assert repository.attachments == []
    assert [attempt.outcome for attempt in repository.attachment_attempts] == [
        "RECEIVED",
        "RECEIVED",
        "REJECTED_CONTEXTUAL",
        "REJECTED_CONTEXTUAL",
    ]
    assert repository.blocked_raw == set()


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("a" * 251 + ".html", "text/html"),
        ("bad\x1fname.html", "text/html"),
        ("safe.html", "text/html\x00application/pdf"),
    ],
)
async def test_attachment_metadata_is_bounded_before_object_storage(
    filename: str,
    content_type: str,
) -> None:
    service, repository, store = _service()

    with pytest.raises(AttachmentQuarantined, match="ATTACHMENT_METADATA_INVALID"):
        await service.store_attachments(
            UUID("019b0000-0000-7000-8000-000000000301"),
            attachments=(
                FetchedAttachment(
                    url="https://example.test/document/1/attachment",
                    filename=filename,
                    content=b"<!doctype html><html></html>",
                    content_type=content_type,
                ),
            ),
            acquired_at=datetime.now(UTC),
        )

    assert store.objects == {}
    assert repository.attachments == []


async def test_entire_attachment_batch_metadata_is_checked_before_first_object() -> None:
    service, repository, store = _service()
    attachments = (
        FetchedAttachment(
            url="https://example.test/document/1/valid.html",
            filename="valid.html",
            content=b"<!doctype html><html></html>",
            content_type="text/html",
        ),
        FetchedAttachment(
            url="https://example.test/document/1/invalid.html",
            filename="a" * 251 + ".html",
            content=b"<!doctype html><html></html>",
            content_type="text/html",
        ),
    )

    with pytest.raises(AttachmentQuarantined, match="ATTACHMENT_METADATA_INVALID"):
        await service.store_attachments(
            UUID("019b0000-0000-7000-8000-000000000301"),
            attachments=attachments,
            acquired_at=datetime.now(UTC),
        )

    assert store.objects == {}
    assert repository.attachments == []


async def test_fixture_pdf_uses_structural_active_content_inspection_after_raw_storage() -> None:
    service, repository, store = _service()
    malicious = _pdf_with_escaped_javascript_names()

    with pytest.raises(SecurityViolation, match="PDF_ACTIVE_ACTION"):
        await service.upload(
            SOURCE_ID,
            content=malicious,
            filename="fixture.pdf",
            declared_mime="application/pdf",
            canonical_url="https://example.test/document/escaped-action",
            actor_id=ACTOR_ID,
            request_id="request-escaped-pdf",
            acquired_at=datetime.now(UTC),
        )

    assert any(value == malicious for value in store.objects.values())
    assert repository.rejected_raw[-1].reason_code == "PDF_ACTIVE_ACTION"
