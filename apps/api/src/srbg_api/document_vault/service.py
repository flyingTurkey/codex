"""Validated, content-addressed ingestion of immutable fixture documents."""

from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from srbg_contracts import FixtureUploadResponse

from srbg_api.acquisition.contracts import FetchedAttachment
from srbg_api.document_vault.security import (
    UploadRejected,
    inspect_fixture_bytes,
)
from srbg_api.identifiers import uuid7
from srbg_api.pdf_processing.security import (
    FileSecurityPolicy,
    InspectedZipEntry,
    SecurityViolation,
    inspect_pdf_bytes,
    inspect_zip_bytes,
)

MAX_FIXTURE_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 1000
DEFAULT_FILE_SECURITY_POLICY = FileSecurityPolicy(
    max_file_bytes=MAX_FIXTURE_BYTES,
    max_pdf_pages=MAX_PDF_PAGES,
    max_ocr_pages=200,
    max_zip_entries=100,
    max_uncompressed_bytes=200 * 1024 * 1024,
    max_compression_ratio=100,
    max_page_pixels=40_000_000,
)


class AttachmentQuarantined(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class FixtureRecord:
    source_id: UUID
    content_hash: str
    object_key: str
    storage_etag: str | None
    byte_size: int
    detected_mime: str
    document_kind: str
    title: str | None
    filename: str
    canonical_url: str
    actor_id: UUID
    request_id: str
    acquired_at: datetime
    admission_fixture: bool = True


@dataclass(frozen=True, slots=True)
class AttachmentRecord:
    attachment_id: UUID
    raw_object_id: UUID
    document_version_id: UUID
    parent_attachment_id: UUID | None
    content_hash: str
    object_key: str
    storage_etag: str | None
    filename: str
    normalized_path: str
    role: str
    depth: int
    declared_mime: str
    detected_mime: str
    byte_size: int
    security_status: str
    reason_code: str | None
    acquired_at: datetime


@dataclass(frozen=True, slots=True)
class RejectedRawRecord:
    raw_object_id: UUID
    content_hash: str
    object_key: str
    storage_etag: str | None
    byte_size: int
    declared_mime: str
    detected_mime: str
    reason_code: str
    acquired_at: datetime


@dataclass(slots=True)
class SourceVaultMetrics:
    uploads: int = 0
    rejections: int = 0
    deduplications: int = 0
    object_storage_errors: int = 0

    def render_prometheus(self) -> str:
        values = (
            ("srbg_source_fixture_uploads_total", self.uploads),
            ("srbg_source_fixture_rejections_total", self.rejections),
            ("srbg_raw_object_deduplications_total", self.deduplications),
            ("srbg_raw_object_storage_errors_total", self.object_storage_errors),
        )
        return "".join(f"# TYPE {name} counter\n{name} {value}\n" for name, value in values)


class VaultRepository(Protocol):
    async def source_accepts_fixture(self, source_id: UUID, canonical_url: str) -> bool: ...

    async def raw_object_exists(self, content_hash: str) -> bool: ...

    async def record_fixture(self, record: FixtureRecord) -> FixtureUploadResponse: ...

    async def record_attachment(self, record: AttachmentRecord) -> UUID: ...

    async def record_rejected_raw(self, record: RejectedRawRecord) -> UUID: ...


class ObjectStore(Protocol):
    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str: ...


class MalwareScanner(Protocol):
    async def scan(self, content: bytes) -> None: ...


class DocumentVaultService:
    def __init__(
        self,
        *,
        repository: VaultRepository,
        object_store: ObjectStore,
        malware_scanner: MalwareScanner,
        metrics: SourceVaultMetrics,
        max_fixture_bytes: int = MAX_FIXTURE_BYTES,
        max_pdf_pages: int = MAX_PDF_PAGES,
        file_security_policy: FileSecurityPolicy = DEFAULT_FILE_SECURITY_POLICY,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._malware_scanner = malware_scanner
        self.metrics = metrics
        self._max_fixture_bytes = max_fixture_bytes
        self._max_pdf_pages = max_pdf_pages
        self._file_security_policy = file_security_policy

    async def upload(
        self,
        source_id: UUID,
        *,
        content: bytes,
        filename: str,
        declared_mime: str,
        canonical_url: str,
        actor_id: UUID,
        request_id: str,
        acquired_at: datetime,
        admission_fixture: bool = True,
    ) -> FixtureUploadResponse:
        self.metrics.uploads += 1
        try:
            _validate_canonical_url(canonical_url)
            if not content or len(content) > self._max_fixture_bytes:
                raise UploadRejected("fixture exceeds the configured byte budget")
            if not await self._repository.source_accepts_fixture(source_id, canonical_url):
                raise UploadRejected("source is not eligible for fixture testing")
        except Exception:
            self.metrics.rejections += 1
            raise

        content_hash = sha256(content).hexdigest()
        raw_exists = await self._repository.raw_object_exists(content_hash)
        storage_etag: str | None = None
        if raw_exists:
            self.metrics.deduplications += 1
        else:
            object_key = f"sha256/{content_hash[:2]}/{content_hash}"
            try:
                storage_etag = await self._object_store.put_if_absent(
                    object_key,
                    content,
                    "application/octet-stream",
                )
            except Exception:
                self.metrics.object_storage_errors += 1
                raise

        try:
            inspected = inspect_fixture_bytes(
                content,
                filename,
                declared_mime,
                max_bytes=self._max_fixture_bytes,
                max_pdf_pages=self._max_pdf_pages,
            )
            await self._malware_scanner.scan(content)
        except Exception as error:
            self.metrics.rejections += 1
            await self._repository.record_rejected_raw(
                RejectedRawRecord(
                    raw_object_id=uuid7(),
                    content_hash=content_hash,
                    object_key=f"sha256/{content_hash[:2]}/{content_hash}",
                    storage_etag=storage_etag,
                    byte_size=len(content),
                    declared_mime=declared_mime,
                    detected_mime=_detected_attachment_mime(content),
                    reason_code=_security_error_code(error),
                    acquired_at=acquired_at,
                )
            )
            raise

        record = FixtureRecord(
            source_id=source_id,
            content_hash=content_hash,
            object_key=f"sha256/{content_hash[:2]}/{content_hash}",
            storage_etag=storage_etag,
            byte_size=inspected.byte_size,
            detected_mime=inspected.detected_mime,
            document_kind=inspected.document_kind,
            title=inspected.title,
            filename=filename,
            canonical_url=canonical_url,
            actor_id=actor_id,
            request_id=request_id,
            acquired_at=acquired_at,
            admission_fixture=admission_fixture,
        )
        result = await self._repository.record_fixture(record)
        if result.raw_object_deduplicated and not raw_exists:
            self.metrics.deduplications += 1
        return result

    async def store_attachments(
        self,
        document_version_id: UUID,
        *,
        attachments: tuple[FetchedAttachment, ...],
        acquired_at: datetime,
    ) -> tuple[UUID, ...]:
        roots: list[UUID] = []
        for attachment in attachments:
            roots.append(
                await self._store_attachment(
                    document_version_id=document_version_id,
                    attachment=attachment,
                    acquired_at=acquired_at,
                )
            )
        return tuple(roots)

    async def _store_attachment(
        self,
        *,
        document_version_id: UUID,
        attachment: FetchedAttachment,
        acquired_at: datetime,
    ) -> UUID:
        attachment = replace(
            attachment,
            content_type=attachment.content_type.split(";", 1)[0].strip().casefold(),
        )
        _validate_canonical_url(attachment.url)
        normalized_path = _root_attachment_path(attachment.filename)
        root = await self._stored_attachment_record(
            document_version_id=document_version_id,
            parent_attachment_id=None,
            filename=attachment.filename,
            normalized_path=normalized_path,
            role="SOURCE_ATTACHMENT",
            depth=0,
            declared_mime=attachment.content_type,
            detected_mime=_detected_attachment_mime(attachment.content),
            content=attachment.content,
            acquired_at=acquired_at,
        )
        try:
            await self._malware_scanner.scan(attachment.content)
            zip_entries = self._inspect_attachment(attachment)
            children = [
                await self._prepare_zip_child(
                    document_version_id=document_version_id,
                    parent_attachment_id=root.attachment_id,
                    entry=entry,
                    acquired_at=acquired_at,
                )
                for entry in zip_entries
            ]
        except SecurityViolation as error:
            await self._repository.record_attachment(
                _with_attachment_security(root, status="QUARANTINED", reason=error.code)
            )
            raise AttachmentQuarantined(error.code) from error
        except Exception as error:
            await self._repository.record_attachment(
                _with_attachment_security(
                    root,
                    status="QUARANTINED",
                    reason="MALWARE_SCAN_FAILED",
                )
            )
            raise AttachmentQuarantined("MALWARE_SCAN_FAILED") from error

        persisted_root_id = await self._repository.record_attachment(
            _with_attachment_security(root, status="CLEAN", reason=None)
        )
        for child in children:
            await self._repository.record_attachment(
                _with_attachment_security(
                    replace(child, parent_attachment_id=persisted_root_id),
                    status="CLEAN",
                    reason=None,
                )
            )
        return persisted_root_id

    def _inspect_attachment(
        self,
        attachment: FetchedAttachment,
    ) -> tuple[InspectedZipEntry, ...]:
        if attachment.content_type in {"application/zip", "application/x-zip-compressed"}:
            inspected = inspect_zip_bytes(
                attachment.content,
                filename=attachment.filename,
                declared_mime=attachment.content_type,
                policy=self._file_security_policy,
            )
            return inspected.entries
        if attachment.content_type == "application/pdf":
            inspect_pdf_bytes(
                attachment.content,
                filename=attachment.filename,
                declared_mime=attachment.content_type,
                policy=self._file_security_policy,
            )
            return ()
        html_inspection = inspect_fixture_bytes(
            attachment.content,
            attachment.filename,
            attachment.content_type,
            max_bytes=self._file_security_policy.max_file_bytes,
            max_pdf_pages=self._file_security_policy.max_pdf_pages,
        )
        if html_inspection.detected_mime != "text/html":
            raise SecurityViolation("ATTACHMENT_MIME_NOT_ALLOWED")
        return ()

    async def _prepare_zip_child(
        self,
        *,
        document_version_id: UUID,
        parent_attachment_id: UUID,
        entry: InspectedZipEntry,
        acquired_at: datetime,
    ) -> AttachmentRecord:
        record = await self._stored_attachment_record(
            document_version_id=document_version_id,
            parent_attachment_id=parent_attachment_id,
            filename=PurePosixPath(entry.normalized_path).name,
            normalized_path=entry.normalized_path,
            role="ARCHIVE_ENTRY",
            depth=1,
            declared_mime=entry.detected_mime,
            detected_mime=entry.detected_mime,
            content=entry.content,
            acquired_at=acquired_at,
        )
        await self._malware_scanner.scan(entry.content)
        if entry.detected_mime == "application/pdf":
            inspect_pdf_bytes(
                entry.content,
                filename=entry.normalized_path,
                declared_mime=entry.detected_mime,
                policy=self._file_security_policy,
            )
        return record

    async def _stored_attachment_record(
        self,
        *,
        document_version_id: UUID,
        parent_attachment_id: UUID | None,
        filename: str,
        normalized_path: str,
        role: str,
        depth: int,
        declared_mime: str,
        detected_mime: str,
        content: bytes,
        acquired_at: datetime,
    ) -> AttachmentRecord:
        content_hash = sha256(content).hexdigest()
        object_key = f"sha256/{content_hash[:2]}/{content_hash}"
        storage_etag = await self._object_store.put_if_absent(
            object_key,
            content,
            "application/octet-stream",
        )
        return AttachmentRecord(
            attachment_id=uuid7(),
            raw_object_id=uuid7(),
            document_version_id=document_version_id,
            parent_attachment_id=parent_attachment_id,
            content_hash=content_hash,
            object_key=object_key,
            storage_etag=storage_etag,
            filename=filename,
            normalized_path=normalized_path,
            role=role,
            depth=depth,
            declared_mime=declared_mime,
            detected_mime=detected_mime,
            byte_size=len(content),
            security_status="CLEAN",
            reason_code=None,
            acquired_at=acquired_at,
        )


def _validate_canonical_url(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or len(value) > 2048
    ):
        raise UploadRejected("invalid canonical document URL")


def _root_attachment_path(filename: str) -> str:
    portable = filename.replace("\\", "/")
    path = PurePosixPath(portable)
    if len(path.parts) != 1 or path.name in {"", ".", ".."} or ":" in path.name:
        raise AttachmentQuarantined("ATTACHMENT_PATH_INVALID")
    return path.name


def _detected_attachment_mime(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"PK"):
        return "application/zip"
    html_prefix = content[:512].lstrip().lower()
    if html_prefix.startswith(b"<!doctype html") or b"<html" in html_prefix:
        return "text/html"
    return "application/octet-stream"


def _with_attachment_security(
    record: AttachmentRecord,
    *,
    status: str,
    reason: str | None,
) -> AttachmentRecord:
    return AttachmentRecord(
        attachment_id=record.attachment_id,
        raw_object_id=record.raw_object_id,
        document_version_id=record.document_version_id,
        parent_attachment_id=record.parent_attachment_id,
        content_hash=record.content_hash,
        object_key=record.object_key,
        storage_etag=record.storage_etag,
        filename=record.filename,
        normalized_path=record.normalized_path,
        role=record.role,
        depth=record.depth,
        declared_mime=record.declared_mime,
        detected_mime=record.detected_mime,
        byte_size=record.byte_size,
        security_status=status,
        reason_code=reason,
        acquired_at=record.acquired_at,
    )


def _security_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code[:100]
    if isinstance(error, UploadRejected):
        return "UPLOAD_SECURITY_REJECTED"
    return "MALWARE_SCAN_FAILED"
