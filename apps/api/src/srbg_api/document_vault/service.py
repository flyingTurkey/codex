"""Validated, content-addressed ingestion of immutable fixture documents."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from srbg_contracts import FixtureUploadResponse

from srbg_api.document_vault.security import (
    UploadRejected,
    inspect_fixture_bytes,
)

MAX_FIXTURE_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 1000


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
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._malware_scanner = malware_scanner
        self.metrics = metrics
        self._max_fixture_bytes = max_fixture_bytes
        self._max_pdf_pages = max_pdf_pages

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
    ) -> FixtureUploadResponse:
        self.metrics.uploads += 1
        try:
            _validate_canonical_url(canonical_url)
            inspected = inspect_fixture_bytes(
                content,
                filename,
                declared_mime,
                max_bytes=self._max_fixture_bytes,
                max_pdf_pages=self._max_pdf_pages,
            )
            if not await self._repository.source_accepts_fixture(source_id, canonical_url):
                raise UploadRejected("source is not eligible for fixture testing")
            await self._malware_scanner.scan(content)
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
                    inspected.detected_mime,
                )
            except Exception:
                self.metrics.object_storage_errors += 1
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
        )
        result = await self._repository.record_fixture(record)
        if result.raw_object_deduplicated and not raw_exists:
            self.metrics.deduplications += 1
        return result


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
