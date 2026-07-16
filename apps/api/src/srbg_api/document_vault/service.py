"""Validated, content-addressed ingestion of immutable fixture documents."""

import json
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from srbg_contracts import FixtureUploadResponse

from srbg_api.acquisition.contracts import FetchedAttachment
from srbg_api.connectors.config import ConnectorConfigRejected, validate_runtime_url
from srbg_api.document_vault.security import (
    MalwareDetected,
    MalwareScanInconclusive,
    UploadRejected,
    inspect_fixture_bytes,
    validate_filename,
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
MAX_ATTACHMENT_BATCH_COUNT = 1_000
MAX_ATTACHMENT_BATCH_BYTES = 512 * 1024 * 1024
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
    trial_run_id: UUID | None
    content_hash: str
    response_sha256: str
    object_key: str
    storage_etag: str | None
    byte_size: int
    declared_mime: str
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
    globally_quarantined: bool = False


@dataclass(frozen=True, slots=True)
class AttachmentAttemptRecord:
    """Append-only private evidence for every stored attachment root attempt."""

    attempt_id: UUID
    document_version_id: UUID
    content_hash: str
    object_key: str
    storage_etag: str | None
    byte_size: int
    declared_mime: str
    detected_mime: str
    filename_sha256: str
    normalized_path_sha256: str
    canonical_url_sha256: str
    outcome: str
    reason_code: str | None
    acquired_at: datetime


@dataclass(frozen=True, slots=True)
class RejectedRawRecord:
    source_id: UUID
    trial_run_id: UUID | None
    raw_object_id: UUID
    content_hash: str
    object_key: str
    storage_etag: str | None
    byte_size: int
    declared_mime: str
    detected_mime: str
    reason_code: str
    canonical_url: str
    actor_id: UUID
    request_id: str
    globally_quarantined: bool
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
    async def source_accepts_fixture(
        self, source_id: UUID, canonical_url: str
    ) -> UUID | bool | None: ...

    async def raw_object_exists(self, content_hash: str) -> bool: ...

    async def raw_object_security_blocked(self, content_hash: str) -> bool: ...

    async def record_fixture(self, record: FixtureRecord) -> FixtureUploadResponse: ...

    async def record_attachment(self, record: AttachmentRecord) -> UUID: ...

    async def record_attachment_attempt(self, record: AttachmentAttemptRecord) -> UUID: ...

    async def record_rejected_raw(self, record: RejectedRawRecord) -> UUID | None: ...


class ObjectStore(Protocol):
    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str: ...

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes: ...


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

    async def read_fixture_object(
        self,
        object_key: str,
        *,
        expected_sha256: str,
        expected_size: int,
    ) -> bytes:
        """Read an immutable fixture for fixed replay with a hard byte/hash boundary."""

        if (
            expected_size < 1
            or expected_size > self._max_fixture_bytes
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256)
            or object_key != f"sha256/{expected_sha256[:2]}/{expected_sha256}"
        ):
            raise UploadRejected("fixture replay object metadata is invalid")
        content = await self._object_store.get_bytes(
            object_key,
            max_bytes=self._max_fixture_bytes,
        )
        if len(content) != expected_size:
            raise UploadRejected("fixture replay object size does not match immutable evidence")
        if sha256(content).hexdigest() != expected_sha256:
            raise UploadRejected("fixture replay object hash does not match immutable evidence")
        return content

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
            _validate_fixture_declared_mime(declared_mime)
            if not content or len(content) > self._max_fixture_bytes:
                raise UploadRejected("fixture exceeds the configured byte budget")
            fixture_authorization = await self._repository.source_accepts_fixture(
                source_id, canonical_url
            )
            if not fixture_authorization:
                raise UploadRejected("source is not eligible for fixture testing")
        except Exception:
            self.metrics.rejections += 1
            raise

        content_hash = sha256(content).hexdigest()
        object_key = f"sha256/{content_hash[:2]}/{content_hash}"
        raw_exists = await self._repository.raw_object_exists(content_hash)
        if raw_exists and await self._repository.raw_object_security_blocked(content_hash):
            self.metrics.rejections += 1
            await self._repository.record_rejected_raw(
                RejectedRawRecord(
                    source_id=source_id,
                    trial_run_id=(
                        fixture_authorization
                        if isinstance(fixture_authorization, UUID)
                        else None
                    ),
                    raw_object_id=uuid7(),
                    content_hash=content_hash,
                    object_key=object_key,
                    storage_etag=None,
                    byte_size=len(content),
                    declared_mime=declared_mime,
                    detected_mime=_detected_attachment_mime(content),
                    reason_code="RAW_SECURITY_HISTORY",
                    canonical_url=canonical_url,
                    actor_id=actor_id,
                    request_id=request_id,
                    globally_quarantined=False,
                    acquired_at=acquired_at,
                )
            )
            raise UploadRejected("raw object has immutable rejected security evidence")
        storage_etag: str | None = None
        if raw_exists:
            self.metrics.deduplications += 1
        else:
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
            safe_filename = validate_filename(filename)
            inspected = inspect_fixture_bytes(
                content,
                safe_filename,
                declared_mime,
                max_bytes=self._max_fixture_bytes,
                max_pdf_pages=self._max_pdf_pages,
            )
            if inspected.detected_mime == "application/pdf":
                inspect_pdf_bytes(
                    content,
                    filename=safe_filename,
                    declared_mime=declared_mime,
                    policy=replace(
                        self._file_security_policy,
                        max_file_bytes=self._max_fixture_bytes,
                        max_pdf_pages=self._max_pdf_pages,
                    ),
                )
        except Exception as error:
            self.metrics.rejections += 1
            await self._repository.record_rejected_raw(
                RejectedRawRecord(
                    source_id=source_id,
                    trial_run_id=(
                        fixture_authorization
                        if isinstance(fixture_authorization, UUID)
                        else None
                    ),
                    raw_object_id=uuid7(),
                    content_hash=content_hash,
                    object_key=object_key,
                    storage_etag=storage_etag,
                    byte_size=len(content),
                    declared_mime=declared_mime,
                    detected_mime=_detected_attachment_mime(content),
                    reason_code=_security_error_code(error),
                    canonical_url=canonical_url,
                    actor_id=actor_id,
                    request_id=request_id,
                    globally_quarantined=_intrinsic_fixture_security_failure(error),
                    acquired_at=acquired_at,
                )
            )
            raise
        try:
            await self._malware_scanner.scan(content)
        except Exception as error:
            self.metrics.rejections += 1
            await self._repository.record_rejected_raw(
                RejectedRawRecord(
                    source_id=source_id,
                    trial_run_id=(
                        fixture_authorization
                        if isinstance(fixture_authorization, UUID)
                        else None
                    ),
                    raw_object_id=uuid7(),
                    content_hash=content_hash,
                    object_key=object_key,
                    storage_etag=storage_etag,
                    byte_size=len(content),
                    declared_mime=declared_mime,
                    detected_mime=_detected_attachment_mime(content),
                    reason_code=_security_error_code(error),
                    canonical_url=canonical_url,
                    actor_id=actor_id,
                    request_id=request_id,
                    globally_quarantined=isinstance(error, MalwareDetected),
                    acquired_at=acquired_at,
                )
            )
            raise

        record = FixtureRecord(
            source_id=source_id,
            trial_run_id=(
                fixture_authorization if isinstance(fixture_authorization, UUID) else None
            ),
            content_hash=content_hash,
            response_sha256=_fixture_response_sha256(
                content,
                detected_mime=inspected.detected_mime,
            ),
            object_key=object_key,
            storage_etag=storage_etag,
            byte_size=inspected.byte_size,
            declared_mime=declared_mime,
            detected_mime=inspected.detected_mime,
            document_kind=inspected.document_kind,
            title=inspected.title,
            filename=safe_filename,
            canonical_url=canonical_url,
            actor_id=actor_id,
            request_id=request_id,
            acquired_at=acquired_at,
            admission_fixture=admission_fixture,
        )
        try:
            result = await self._repository.record_fixture(record)
        except Exception:
            if await self._repository.raw_object_security_blocked(content_hash):
                await self._repository.record_rejected_raw(
                    RejectedRawRecord(
                        source_id=source_id,
                        trial_run_id=(
                            fixture_authorization
                            if isinstance(fixture_authorization, UUID)
                            else None
                        ),
                        raw_object_id=uuid7(),
                        content_hash=content_hash,
                        object_key=object_key,
                        storage_etag=storage_etag,
                        byte_size=len(content),
                        declared_mime=declared_mime,
                        detected_mime=inspected.detected_mime,
                        reason_code="RAW_SECURITY_HISTORY",
                        canonical_url=canonical_url,
                        actor_id=actor_id,
                        request_id=request_id,
                        globally_quarantined=False,
                        acquired_at=acquired_at,
                    )
                )
            raise
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
        normalized_attachments = self._validate_attachment_batch_envelope(attachments)
        stored_roots: list[AttachmentRecord] = []
        for attachment in normalized_attachments:
            stored_roots.append(
                await self._stored_attachment_record(
                    document_version_id=document_version_id,
                    parent_attachment_id=None,
                    filename=attachment.filename,
                    normalized_path=_root_attachment_path(attachment.filename),
                    role="SOURCE_ATTACHMENT",
                    depth=0,
                    declared_mime=attachment.content_type,
                    detected_mime=_detected_attachment_mime(attachment.content),
                    content=attachment.content,
                    acquired_at=acquired_at,
                    canonical_url=attachment.url,
                    record_received_attempt=True,
                )
            )
        try:
            invalid_attachment = self._validate_attachment_batch_budget(
                normalized_attachments
            )
        except AttachmentQuarantined as error:
            await self._record_root_attempts(
                tuple(zip(normalized_attachments, stored_roots, strict=True)),
                outcome="REJECTED_CONTEXTUAL",
                reason_code=error.code,
            )
            raise
        if invalid_attachment is not None:
            invalid_index, reason_code = invalid_attachment
            intrinsic = _intrinsic_attachment_security_failure(reason_code)
            if intrinsic:
                await self._repository.record_attachment(
                    _with_attachment_security(
                        stored_roots[invalid_index],
                        status="QUARANTINED",
                        reason=reason_code,
                        globally_quarantined=True,
                    )
                )
            for index, (attachment, root) in enumerate(
                zip(normalized_attachments, stored_roots, strict=True)
            ):
                await self._record_attachment_attempt(
                    root,
                    canonical_url=attachment.url,
                    outcome=(
                        "QUARANTINED_INTRINSIC"
                        if intrinsic and index == invalid_index
                        else "REJECTED_CONTEXTUAL"
                    ),
                    reason_code=(
                        reason_code
                        if index == invalid_index
                        else "ATTACHMENT_BATCH_REJECTED"
                    ),
                )
            raise AttachmentQuarantined(reason_code)
        roots: list[UUID] = []
        for attachment, stored_root in zip(
            normalized_attachments, stored_roots, strict=True
        ):
            roots.append(
                await self._store_attachment(
                    document_version_id=document_version_id,
                    attachment=attachment,
                    stored_root=stored_root,
                    acquired_at=acquired_at,
                )
            )
        return tuple(roots)

    def _validate_attachment_batch_envelope(
        self,
        attachments: tuple[FetchedAttachment, ...],
    ) -> tuple[FetchedAttachment, ...]:
        policy = self._file_security_policy
        normalized_attachments: list[FetchedAttachment] = []
        for attachment in attachments:
            if not attachment.content or len(attachment.content) > policy.max_file_bytes:
                raise AttachmentQuarantined("ATTACHMENT_FILE_SIZE_LIMIT")
            filename, media_type = _validated_attachment_metadata(
                attachment.filename,
                attachment.content_type,
            )
            try:
                _validate_canonical_url(attachment.url)
            except UploadRejected as error:
                raise AttachmentQuarantined("ATTACHMENT_URL_INVALID") from error
            _root_attachment_path(filename)
            normalized_attachments.append(
                replace(
                    attachment,
                    filename=filename,
                    content_type=media_type,
                )
            )

        if len(attachments) > MAX_ATTACHMENT_BATCH_COUNT:
            raise AttachmentQuarantined("ATTACHMENT_ABSOLUTE_COUNT_LIMIT")
        if sum(len(attachment.content) for attachment in attachments) > (
            MAX_ATTACHMENT_BATCH_BYTES
        ):
            raise AttachmentQuarantined("ATTACHMENT_ABSOLUTE_SIZE_LIMIT")
        return tuple(normalized_attachments)

    def _validate_attachment_batch_budget(
        self,
        attachments: tuple[FetchedAttachment, ...],
    ) -> tuple[int, str] | None:
        policy = self._file_security_policy
        expanded_count = len(attachments)
        expanded_bytes = 0
        if expanded_count > policy.max_zip_entries:
            raise AttachmentQuarantined("ATTACHMENT_COUNT_LIMIT")
        if sum(len(attachment.content) for attachment in attachments) > (
            policy.max_uncompressed_bytes
        ):
            raise AttachmentQuarantined("ATTACHMENT_TOTAL_SIZE_LIMIT")
        for index, attachment in enumerate(attachments):
            filename = attachment.filename
            media_type = attachment.content_type
            try:
                if media_type in {"application/zip", "application/x-zip-compressed"}:
                    inspection = inspect_zip_bytes(
                        attachment.content,
                        filename=filename,
                        declared_mime=media_type,
                        policy=policy,
                    )
                    expanded_count += len(inspection.entries)
                    expanded_bytes += inspection.total_uncompressed_bytes
                elif media_type == "application/pdf":
                    inspect_pdf_bytes(
                        attachment.content,
                        filename=filename,
                        declared_mime=media_type,
                        policy=policy,
                    )
                    expanded_bytes += len(attachment.content)
                else:
                    inspected = inspect_fixture_bytes(
                        attachment.content,
                        filename,
                        media_type,
                        max_bytes=policy.max_file_bytes,
                        max_pdf_pages=policy.max_pdf_pages,
                    )
                    if inspected.detected_mime != "text/html":
                        raise SecurityViolation("ATTACHMENT_MIME_NOT_ALLOWED")
                    expanded_bytes += len(attachment.content)
            except (SecurityViolation, UploadRejected) as error:
                return index, _security_error_code(error)
            if expanded_count > policy.max_zip_entries:
                raise AttachmentQuarantined("ATTACHMENT_COUNT_LIMIT")
            if expanded_bytes > policy.max_uncompressed_bytes:
                raise AttachmentQuarantined("ATTACHMENT_TOTAL_SIZE_LIMIT")
        return None

    async def _store_attachment(
        self,
        *,
        document_version_id: UUID,
        attachment: FetchedAttachment,
        stored_root: AttachmentRecord,
        acquired_at: datetime,
    ) -> UUID:
        filename, media_type = _validated_attachment_metadata(
            attachment.filename,
            attachment.content_type,
        )
        attachment = replace(
            attachment,
            filename=filename,
            content_type=media_type,
        )
        _validate_canonical_url(attachment.url)
        _root_attachment_path(attachment.filename)
        root = stored_root
        try:
            await self._malware_scanner.scan(attachment.content)
            zip_entries = self._inspect_attachment(attachment)
            children = [
                await self._prepare_zip_child(
                    document_version_id=document_version_id,
                    parent_attachment_id=root.attachment_id,
                    entry=entry,
                    canonical_url=attachment.url,
                    acquired_at=acquired_at,
                )
                for entry in zip_entries
            ]
        except MalwareDetected as error:
            await self._repository.record_attachment(
                _with_attachment_security(
                    root,
                    status="QUARANTINED",
                    reason=error.code,
                    globally_quarantined=True,
                )
            )
            await self._record_attachment_attempt(
                root,
                canonical_url=attachment.url,
                outcome="QUARANTINED_INTRINSIC",
                reason_code=error.code,
            )
            raise AttachmentQuarantined(error.code) from error
        except MalwareScanInconclusive as error:
            await self._record_attachment_attempt(
                root,
                canonical_url=attachment.url,
                outcome="INCONCLUSIVE",
                reason_code=error.code,
            )
            raise AttachmentQuarantined(error.code) from error
        except SecurityViolation as error:
            intrinsic = _intrinsic_attachment_security_failure(error.code)
            if intrinsic:
                await self._repository.record_attachment(
                    _with_attachment_security(
                        root,
                        status="QUARANTINED",
                        reason=error.code,
                        globally_quarantined=True,
                    )
                )
            await self._record_attachment_attempt(
                root,
                canonical_url=attachment.url,
                outcome=(
                    "QUARANTINED_INTRINSIC" if intrinsic else "REJECTED_CONTEXTUAL"
                ),
                reason_code=error.code,
            )
            raise AttachmentQuarantined(error.code) from error
        except Exception as error:
            await self._record_attachment_attempt(
                root,
                canonical_url=attachment.url,
                outcome="INCONCLUSIVE",
                reason_code="MALWARE_SCAN_INCONCLUSIVE",
            )
            raise AttachmentQuarantined("MALWARE_SCAN_INCONCLUSIVE") from error

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
            await self._record_attachment_attempt(
                child,
                canonical_url=attachment.url,
                outcome="ACCEPTED",
                reason_code=None,
            )
        await self._record_attachment_attempt(
            root,
            canonical_url=attachment.url,
            outcome="ACCEPTED",
            reason_code=None,
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
        try:
            html_inspection = inspect_fixture_bytes(
                attachment.content,
                attachment.filename,
                attachment.content_type,
                max_bytes=self._file_security_policy.max_file_bytes,
                max_pdf_pages=self._file_security_policy.max_pdf_pages,
            )
        except UploadRejected as error:
            raise SecurityViolation("ATTACHMENT_CONTENT_REJECTED") from error
        if html_inspection.detected_mime != "text/html":
            raise SecurityViolation("ATTACHMENT_MIME_NOT_ALLOWED")
        return ()

    async def _prepare_zip_child(
        self,
        *,
        document_version_id: UUID,
        parent_attachment_id: UUID,
        entry: InspectedZipEntry,
        canonical_url: str,
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
        await self._record_attachment_attempt(
            record,
            canonical_url=canonical_url,
            outcome="RECEIVED",
            reason_code=None,
        )
        try:
            await self._malware_scanner.scan(entry.content)
        except MalwareDetected as error:
            await self._repository.record_attachment(
                _with_attachment_security(
                    replace(record, parent_attachment_id=None),
                    status="QUARANTINED",
                    reason=error.code,
                    globally_quarantined=True,
                )
            )
            await self._record_attachment_attempt(
                record,
                canonical_url=canonical_url,
                outcome="QUARANTINED_INTRINSIC",
                reason_code=error.code,
            )
            raise
        except MalwareScanInconclusive as error:
            await self._record_attachment_attempt(
                record,
                canonical_url=canonical_url,
                outcome="INCONCLUSIVE",
                reason_code=error.code,
            )
            raise
        except Exception as error:
            await self._record_attachment_attempt(
                record,
                canonical_url=canonical_url,
                outcome="INCONCLUSIVE",
                reason_code="MALWARE_SCAN_INCONCLUSIVE",
            )
            raise MalwareScanInconclusive("attachment malware scan was inconclusive") from error
        try:
            if entry.detected_mime == "application/pdf":
                inspect_pdf_bytes(
                    entry.content,
                    filename=entry.normalized_path,
                    declared_mime=entry.detected_mime,
                    policy=self._file_security_policy,
                )
        except SecurityViolation as error:
            intrinsic = _intrinsic_attachment_security_failure(error.code)
            if intrinsic:
                await self._repository.record_attachment(
                    _with_attachment_security(
                        replace(record, parent_attachment_id=None),
                        status="QUARANTINED",
                        reason=error.code,
                        globally_quarantined=True,
                    )
                )
            await self._record_attachment_attempt(
                record,
                canonical_url=canonical_url,
                outcome=(
                    "QUARANTINED_INTRINSIC" if intrinsic else "REJECTED_CONTEXTUAL"
                ),
                reason_code=error.code,
            )
            raise
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
        canonical_url: str | None = None,
        record_received_attempt: bool = False,
    ) -> AttachmentRecord:
        content_hash = sha256(content).hexdigest()
        object_key = f"sha256/{content_hash[:2]}/{content_hash}"
        if (
            await self._repository.raw_object_exists(content_hash)
            and await self._repository.raw_object_security_blocked(content_hash)
        ):
            if record_received_attempt and canonical_url is not None:
                blocked = AttachmentRecord(
                    attachment_id=uuid7(),
                    raw_object_id=uuid7(),
                    document_version_id=document_version_id,
                    parent_attachment_id=parent_attachment_id,
                    content_hash=content_hash,
                    object_key=object_key,
                    storage_etag=None,
                    filename=filename,
                    normalized_path=normalized_path,
                    role=role,
                    depth=depth,
                    declared_mime=declared_mime,
                    detected_mime=detected_mime,
                    byte_size=len(content),
                    security_status="QUARANTINED",
                    reason_code="ATTACHMENT_RAW_SECURITY_HISTORY",
                    acquired_at=acquired_at,
                    globally_quarantined=False,
                )
                await self._record_attachment_attempt(
                    blocked,
                    canonical_url=canonical_url,
                    outcome="REJECTED_SECURITY_HISTORY",
                    reason_code="ATTACHMENT_RAW_SECURITY_HISTORY",
                )
            raise AttachmentQuarantined("ATTACHMENT_RAW_SECURITY_HISTORY")
        storage_etag = await self._object_store.put_if_absent(
            object_key,
            content,
            "application/octet-stream",
        )
        record = AttachmentRecord(
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
        if record_received_attempt and canonical_url is not None:
            await self._record_attachment_attempt(
                record,
                canonical_url=canonical_url,
                outcome="RECEIVED",
                reason_code=None,
            )
        return record

    async def _record_root_attempts(
        self,
        roots: tuple[tuple[FetchedAttachment, AttachmentRecord], ...],
        *,
        outcome: str,
        reason_code: str,
    ) -> None:
        for attachment, root in roots:
            await self._record_attachment_attempt(
                root,
                canonical_url=attachment.url,
                outcome=outcome,
                reason_code=reason_code,
            )

    async def _record_attachment_attempt(
        self,
        record: AttachmentRecord,
        *,
        canonical_url: str,
        outcome: str,
        reason_code: str | None,
    ) -> UUID:
        return await self._repository.record_attachment_attempt(
            AttachmentAttemptRecord(
                attempt_id=uuid7(),
                document_version_id=record.document_version_id,
                content_hash=record.content_hash,
                object_key=record.object_key,
                storage_etag=record.storage_etag,
                byte_size=record.byte_size,
                declared_mime=record.declared_mime,
                detected_mime=record.detected_mime,
                filename_sha256=sha256(record.filename.encode("utf-8")).hexdigest(),
                normalized_path_sha256=sha256(
                    record.normalized_path.encode("utf-8")
                ).hexdigest(),
                canonical_url_sha256=sha256(
                    canonical_url.encode("utf-8")
                ).hexdigest(),
                outcome=outcome,
                reason_code=reason_code,
                acquired_at=record.acquired_at,
            )
        )


def _fixture_response_sha256(content: bytes, *, detected_mime: str) -> str:
    selected_headers = {
        "content-type": detected_mime,
        "etag": "",
        "last-modified": "",
    }
    evidence = (
        b"200\n"
        + json.dumps(selected_headers, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
        + content
    )
    return sha256(evidence).hexdigest()


def _validate_canonical_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if hostname is None:
            raise ConnectorConfigRejected("missing host")
        validate_runtime_url(value, allowed_hosts=(hostname.rstrip(".").casefold(),))
    except (ConnectorConfigRejected, ValueError) as error:
        raise UploadRejected("invalid canonical document URL") from error


def _root_attachment_path(filename: str) -> str:
    portable = filename.replace("\\", "/")
    path = PurePosixPath(portable)
    if len(path.parts) != 1 or path.name in {"", ".", ".."} or ":" in path.name:
        raise AttachmentQuarantined("ATTACHMENT_PATH_INVALID")
    return path.name


def _validated_attachment_metadata(filename: str, content_type: str) -> tuple[str, str]:
    normalized_name = unicodedata.normalize("NFC", filename)
    if (
        not normalized_name
        or len(normalized_name) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized_name)
    ):
        raise AttachmentQuarantined("ATTACHMENT_METADATA_INVALID")
    if (
        not content_type
        or len(content_type) > 200
        or any(ord(character) < 32 or ord(character) == 127 for character in content_type)
    ):
        raise AttachmentQuarantined("ATTACHMENT_METADATA_INVALID")
    media_type = content_type.split(";", 1)[0].strip().casefold()
    if media_type not in {
        "text/html",
        "application/pdf",
        "application/zip",
        "application/x-zip-compressed",
    }:
        raise AttachmentQuarantined("ATTACHMENT_METADATA_INVALID")
    return normalized_name, media_type


def _validate_fixture_declared_mime(declared_mime: str) -> None:
    if (
        declared_mime
        not in {
            "application/atom+xml",
            "application/json",
            "application/pdf",
            "application/rss+xml",
            "application/xml",
            "text/html",
            "text/xml",
        }
        or len(declared_mime) > 100
        or any(ord(character) < 32 or ord(character) == 127 for character in declared_mime)
    ):
        raise UploadRejected("fixture declared MIME is invalid")


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
    globally_quarantined: bool = False,
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
        globally_quarantined=globally_quarantined,
    )


def _security_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code[:100]
    if isinstance(error, UploadRejected):
        return "UPLOAD_SECURITY_REJECTED"
    return "MALWARE_SCAN_FAILED"


def _intrinsic_fixture_security_failure(error: Exception) -> bool:
    """Distinguish byte-intrinsic threats from filename/MIME submission errors."""

    if isinstance(error, SecurityViolation):
        return error.code not in {"MIME_MISMATCH", "FILE_SIZE_LIMIT"}
    message = str(error).casefold()
    return any(
        marker in message
        for marker in (
            "active content",
            "encrypted pdf",
            "too many pages",
            "malformed pdf",
            "compression ratio",
            "embedded file",
        )
    )


def _intrinsic_attachment_security_failure(reason_code: str) -> bool:
    """Only byte-intrinsic threats create irreversible cross-submission facts."""

    return reason_code in {
        "MALWARE_DETECTED",
        "PDF_MALFORMED",
        "PDF_ENCRYPTED",
        "PDF_EMBEDDED_FILE",
        "PDF_EXTERNAL_LAUNCH",
        "PDF_ACTIVE_ACTION",
        "PDF_POLYGLOT",
        "HTML_ACTIVE_CONTENT",
        "ZIP_MALFORMED",
        "ZIP_ENCRYPTED_ENTRY",
        "ZIP_SYMLINK",
        "ZIP_DUPLICATE_PATH",
        "ZIP_DEPTH_LIMIT",
        "ZIP_NESTED_ARCHIVE",
        "ZIP_UNCOMPRESSED_LIMIT",
        "ZIP_COMPRESSION_RATIO",
        "ZIP_EMPTY",
        "ZIP_PATH_INVALID",
        "ZIP_PATH_TRAVERSAL",
        "ZIP_POLYGLOT",
    }
