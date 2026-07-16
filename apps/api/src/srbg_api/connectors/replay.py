"""Network-free fixed replay and raw-first evidence contracts."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from uuid import UUID

from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    DocumentVersion,
    ExecutionDomain,
    FetchResult,
    RawObject,
    SourceCheckpoint,
)
from srbg_api.connectors.config import (
    ConnectorConfigRejected,
    ConnectorKind,
    preview_connector_config,
    validate_connector_config,
    validate_runtime_url,
)
from srbg_api.connectors.parsers import CONNECTOR_PARSERS, DeclarativeParseError
from srbg_api.document_vault.security import UploadRejected, inspect_fixture_bytes
from srbg_api.identifiers import uuid7
from srbg_api.pdf_processing.security import (
    FileSecurityPolicy,
    SecurityViolation,
    inspect_pdf_bytes,
    inspect_zip_bytes,
)


class ConnectorParseFailed(ValueError):
    pass


class FixtureProductionDenied(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class FixtureExchange:
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes


class FixedFixtureTransport:
    """Exact URL-to-bytes transport. It has no socket or resolver capability."""

    def __init__(self, exchanges: tuple[FixtureExchange, ...]) -> None:
        self._exchanges = {exchange.url: exchange for exchange in exchanges}
        if len(self._exchanges) != len(exchanges):
            raise ValueError("fixed replay exchange URLs must be unique")
        self.calls: list[str] = []
        self.real_network_calls = 0

    async def fetch(self, url: str, *, fetched_at: datetime) -> FetchResult:
        self.calls.append(url)
        try:
            exchange = self._exchanges[url]
        except KeyError as error:
            raise OSError("fixed replay refused an unregistered URL") from error
        content_type = _header(exchange.headers, "content-type")
        return FetchResult(
            url=url,
            status_code=exchange.status_code,
            content=exchange.content,
            content_type=content_type,
            etag=_header(exchange.headers, "etag"),
            last_modified=_header(exchange.headers, "last-modified"),
            fetched_at=fetched_at,
            request_url=url,
            response_sha256=_response_sha256(
                exchange.status_code,
                exchange.headers,
                exchange.content,
            ),
        )


@dataclass(frozen=True, slots=True)
class ManualImportSubmission:
    import_type: str
    canonical_url: str
    title: str
    filename: str | None = None
    declared_mime: str | None = None
    content: bytes | None = None

    @classmethod
    def for_url(cls, *, url: str, title: str) -> ManualImportSubmission:
        return cls(import_type="URL", canonical_url=url, title=title)

    @classmethod
    def for_file(
        cls,
        *,
        canonical_url: str,
        title: str,
        filename: str,
        declared_mime: str,
        content: bytes,
    ) -> ManualImportSubmission:
        return cls(
            import_type="FILE",
            canonical_url=canonical_url,
            title=title,
            filename=filename,
            declared_mime=declared_mime,
            content=content,
        )


@dataclass(frozen=True, slots=True)
class IngestionOutcome:
    raw_object: RawObject
    document_version: DocumentVersion


@dataclass(frozen=True, slots=True)
class ConnectorReplayResult:
    discovery_records: tuple[DiscoveryRecord, ...]
    fetch_results: tuple[FetchResult, ...]
    raw_objects: tuple[RawObject, ...]
    document_versions: tuple[DocumentVersion, ...]


class InMemoryEvidenceStore:
    """Deterministic test store that enforces domain-scoped idempotency."""

    def __init__(self) -> None:
        self._raw: dict[tuple[ExecutionDomain, str, str, str], RawObject] = {}
        self._raw_content: dict[UUID, bytes] = {}
        self._parse_failures: dict[UUID, str] = {}
        self._versions: dict[tuple[ExecutionDomain, str, str], DocumentVersion] = {}
        self._current: dict[tuple[ExecutionDomain, str], DocumentVersion] = {}
        self.events: list[tuple[str, str]] = []

    async def persist_raw(self, fetched: FetchResult, domain: ExecutionDomain) -> RawObject:
        content = bytes(memoryview(fetched.content or b""))
        content_hash = sha256(content).hexdigest()
        response_hash = fetched.response_sha256 or _response_sha256(
            fetched.status_code,
            {
                "content-type": fetched.content_type or "",
                "etag": fetched.etag or "",
                "last-modified": fetched.last_modified or "",
            },
            content,
        )
        key = (domain, fetched.request_url or fetched.url, fetched.url, response_hash)
        raw = self._raw.get(key)
        if raw is None:
            raw = RawObject(
                id=uuid7(),
                execution_domain=domain,
                request_url=fetched.request_url or fetched.url,
                final_url=fetched.url,
                status_code=fetched.status_code,
                content_type=fetched.content_type,
                content_sha256=content_hash,
                response_sha256=response_hash,
                byte_size=len(content),
                etag=fetched.etag,
                last_modified=fetched.last_modified,
                fetched_at=fetched.fetched_at,
                redirect_chain=fetched.redirect_chain,
            )
            self._raw[key] = raw
            self._raw_content[raw.id] = content
        elif self._raw_content[raw.id] != content or raw.content_sha256 != content_hash:
            raise ValueError("raw object idempotency collision")
        self.events.append(("RAW_PERSISTED", str(raw.id)))
        return raw

    async def persist_ready(
        self,
        raw: RawObject,
        record: DiscoveryRecord,
    ) -> DocumentVersion:
        key = (raw.execution_domain, record.url, raw.content_sha256)
        version = self._versions.get(key)
        if version is None:
            current = self._current.get((raw.execution_domain, record.url))
            version = DocumentVersion(
                id=uuid7(),
                raw_object_id=raw.id,
                execution_domain=raw.execution_domain,
                canonical_url=record.url,
                version_number=1 if current is None else current.version_number + 1,
                status="READY",
                content_sha256=raw.content_sha256,
                discovered_at=record.discovered_at,
                published_at=record.published_at,
                source_modified_at=record.source_modified_at,
            )
            self._versions[key] = version
            self._current[(raw.execution_domain, record.url)] = version
        self.events.append(("DOCUMENT_READY", str(raw.id)))
        return version

    async def record_parse_failure(self, raw: RawObject, reason_code: str) -> None:
        if raw.id not in self._raw_content:
            raise KeyError("raw object is not persisted")
        if not reason_code or len(reason_code) > 100:
            raise ValueError("parse failure reason code is invalid")
        existing = self._parse_failures.setdefault(raw.id, reason_code)
        if existing != reason_code:
            raise ValueError("parse failure reason is immutable")
        self.events.append(("PARSE_FAILED", str(raw.id)))

    async def record_discovery_parsed(self, raw: RawObject) -> None:
        self.events.append(("DISCOVERY_PARSED", str(raw.id)))

    def current_ready(
        self,
        domain: ExecutionDomain,
        canonical_url: str,
    ) -> DocumentVersion | None:
        return self._current.get((domain, canonical_url))

    def read_raw_bytes(self, raw_object_id: UUID) -> bytes:
        """Return the immutable bytes captured for one persisted raw object."""

        try:
            return self._raw_content[raw_object_id]
        except KeyError as error:
            raise KeyError("raw object is not persisted") from error

    def parse_failure_reason(self, raw_object_id: UUID) -> str | None:
        return self._parse_failures.get(raw_object_id)


_FILE_POLICY = FileSecurityPolicy(
    max_file_bytes=50 * 1024 * 1024,
    max_pdf_pages=1000,
    max_ocr_pages=200,
    max_zip_entries=100,
    max_uncompressed_bytes=200 * 1024 * 1024,
    max_compression_ratio=100,
    max_page_pixels=40_000_000,
)


class RawFirstIngestionService:
    def __init__(self, *, store: InMemoryEvidenceStore) -> None:
        self._store = store

    async def persist_discovery_raw(
        self,
        fetched: FetchResult,
        *,
        domain: ExecutionDomain,
    ) -> RawObject:
        return await self._store.persist_raw(fetched, domain)

    async def record_parse_failure(self, raw: RawObject, reason_code: str) -> None:
        await self._store.record_parse_failure(raw, reason_code)

    async def record_discovery_parsed(self, raw: RawObject) -> None:
        await self._store.record_discovery_parsed(raw)

    async def ingest_document(
        self,
        fetched: FetchResult,
        record: DiscoveryRecord,
        *,
        domain: ExecutionDomain,
        filename: str | None = None,
        declared_mime: str | None = None,
    ) -> IngestionOutcome:
        raw = await self._store.persist_raw(fetched, domain)
        try:
            _validate_document_bytes(
                fetched,
                filename=filename,
                declared_mime=declared_mime,
            )
        except (ConnectorParseFailed, SecurityViolation, UploadRejected) as error:
            await self._store.record_parse_failure(raw, _safe_reason(error))
            raise ConnectorParseFailed("document bytes failed bounded parsing") from error
        version = await self._store.persist_ready(raw, record)
        return IngestionOutcome(raw_object=raw, document_version=version)


class DeclarativeSourceAdapter:
    """Canonical SourceAdapter backed only by built-in parsers and an injected transport."""

    def __init__(
        self,
        *,
        kind: ConnectorKind,
        config: dict[str, object],
        allowed_hosts: tuple[str, ...],
        transport: FixedFixtureTransport,
        ingestion: RawFirstIngestionService,
        now: Callable[[], datetime],
        manual_imports: tuple[ManualImportSubmission, ...] = (),
    ) -> None:
        self._kind = kind
        self._config = config
        self._allowed_hosts = allowed_hosts
        self._transport = transport
        self._ingestion = ingestion
        self._now = now
        self._manual_imports = manual_imports
        self._manual_by_url = {item.canonical_url: item for item in manual_imports}
        if len(self._manual_by_url) != len(manual_imports):
            raise ValueError("manual import canonical URLs must be unique")
        self._discovery_fetches: list[FetchResult] = []
        self._discovery_raw: list[RawObject] = []

    @property
    def discovery_fetches(self) -> tuple[FetchResult, ...]:
        return tuple(self._discovery_fetches)

    @property
    def discovery_raw_objects(self) -> tuple[RawObject, ...]:
        return tuple(self._discovery_raw)

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        if self._kind is ConnectorKind.MANUAL_IMPORT:
            manual_records = tuple(self._manual_record(item) for item in self._manual_imports)
            return DiscoveryBatch(
                records=manual_records,
                next_checkpoint=_next_checkpoint(manual_records, checkpoint, None),
            )
        parser = CONNECTOR_PARSERS[self._kind]
        requests = parser.initial_requests(self._config)
        if requests and all(request.role == "DOCUMENT" for request in requests):
            direct_records = tuple(_direct_record(request.url, self._now()) for request in requests)
            return DiscoveryBatch(
                records=direct_records,
                next_checkpoint=_next_checkpoint(direct_records, checkpoint, None),
            )

        records: list[DiscoveryRecord] = []
        last_fetch: FetchResult | None = None
        for request in requests:
            validate_runtime_url(request.url, allowed_hosts=self._allowed_hosts)
            fetched = await self._transport.fetch(request.url, fetched_at=self._now())
            last_fetch = fetched
            self._discovery_fetches.append(fetched)
            raw = await self._ingestion.persist_discovery_raw(
                fetched,
                domain=ExecutionDomain.FIXTURE,
            )
            self._discovery_raw.append(raw)
            try:
                discovered = parser.discover(fetched, self._config)
            except DeclarativeParseError as error:
                await self._ingestion.record_parse_failure(raw, "DISCOVERY_PARSE_FAILED")
                raise ConnectorParseFailed(
                    "discovery response failed declarative parsing"
                ) from error
            try:
                for record in discovered:
                    validate_runtime_url(record.url, allowed_hosts=self._allowed_hosts)
            except ConnectorConfigRejected as error:
                await self._ingestion.record_parse_failure(raw, "DISCOVERY_SECURITY_FAILED")
                raise ConnectorParseFailed(
                    "discovery target failed runtime security validation"
                ) from error
            await self._ingestion.record_discovery_parsed(raw)
            records.extend(discovered)
        return DiscoveryBatch(
            records=tuple(records),
            next_checkpoint=_next_checkpoint(tuple(records), checkpoint, last_fetch),
        )

    async def fetch(
        self,
        record: DiscoveryRecord,
        checkpoint: SourceCheckpoint,
    ) -> FetchResult:
        del checkpoint
        validate_runtime_url(record.url, allowed_hosts=self._allowed_hosts)
        if self._kind is not ConnectorKind.MANUAL_IMPORT:
            return await self._transport.fetch(record.url, fetched_at=self._now())
        try:
            submission = self._manual_by_url[record.url]
        except KeyError as error:
            raise ValueError("manual adapter refused an undiscovered item") from error
        if submission.import_type == "URL":
            return await self._transport.fetch(record.url, fetched_at=self._now())
        return FetchResult(
            url=record.url,
            status_code=200,
            content=submission.content,
            content_type=submission.declared_mime,
            etag=None,
            last_modified=None,
            fetched_at=self._now(),
            request_url=record.url,
        )

    def _manual_record(self, submission: ManualImportSubmission) -> DiscoveryRecord:
        validate_runtime_url(submission.canonical_url, allowed_hosts=self._allowed_hosts)
        if submission.import_type == "URL":
            if self._config.get("url_import_enabled") is not True:
                raise PermissionError("manual URL import is disabled")
        elif submission.import_type == "FILE":
            if self._config.get("file_import_enabled") is not True:
                raise PermissionError("manual file import is disabled")
            _validate_manual_submission(submission, self._config)
        else:
            raise ValueError("manual import type is invalid")
        return DiscoveryRecord(
            external_id=sha256(submission.canonical_url.encode()).hexdigest(),
            url=submission.canonical_url,
            title=submission.title,
            published_at=None,
            discovered_at=self._now(),
        )

    def document_validation_metadata(
        self,
        record: DiscoveryRecord,
    ) -> tuple[str | None, str | None]:
        if self._kind is not ConnectorKind.MANUAL_IMPORT:
            return None, None
        try:
            submission = self._manual_by_url[record.url]
        except KeyError as error:
            raise ValueError("manual adapter refused an undiscovered item") from error
        if submission.import_type != "FILE":
            return None, None
        return submission.filename, submission.declared_mime


class FixedReplayExecutor:
    def __init__(
        self,
        *,
        transport: FixedFixtureTransport,
        store: InMemoryEvidenceStore,
        now: Callable[[], datetime],
    ) -> None:
        self._transport = transport
        self._store = store
        self._now = now
        self._ingestion = RawFirstIngestionService(store=store)

    def preview(
        self,
        kind: ConnectorKind,
        config: object,
        *,
        source_allowed_hosts: tuple[str, ...],
    ) -> dict[str, object]:
        return preview_connector_config(
            kind,
            config,
            source_allowed_hosts=source_allowed_hosts,
        )

    def adapter(
        self,
        kind: ConnectorKind,
        config: object,
        *,
        source_allowed_hosts: tuple[str, ...],
        manual_imports: tuple[ManualImportSubmission, ...] = (),
    ) -> DeclarativeSourceAdapter:
        validated = validate_connector_config(
            kind,
            config,
            source_allowed_hosts=source_allowed_hosts,
        )
        document = validated.document
        return DeclarativeSourceAdapter(
            kind=kind,
            config=document,
            allowed_hosts=tuple(_string_list(document, "allowed_hosts")),
            transport=self._transport,
            ingestion=self._ingestion,
            now=self._now,
            manual_imports=manual_imports,
        )

    async def run(
        self,
        kind: ConnectorKind,
        config: object,
        *,
        source_allowed_hosts: tuple[str, ...],
        domain: ExecutionDomain,
        manual_imports: tuple[ManualImportSubmission, ...] = (),
    ) -> ConnectorReplayResult:
        if domain is not ExecutionDomain.FIXTURE:
            raise FixtureProductionDenied("fixed fixture transport is restricted to FIXTURE")
        adapter = self.adapter(
            kind,
            config,
            source_allowed_hosts=source_allowed_hosts,
            manual_imports=manual_imports,
        )
        batch = await adapter.discover(SourceCheckpoint())
        fetches = list(adapter.discovery_fetches)
        raw_objects = list(adapter.discovery_raw_objects)
        completed_records: list[DiscoveryRecord] = []
        versions: list[DocumentVersion] = []
        for record in batch.records:
            fetched = await adapter.fetch(record, SourceCheckpoint())
            fetches.append(fetched)
            completed_records.append(record)
            filename, declared_mime = adapter.document_validation_metadata(record)
            outcome = await self._ingestion.ingest_document(
                fetched,
                record,
                domain=ExecutionDomain.FIXTURE,
                filename=filename,
                declared_mime=declared_mime,
            )
            raw_objects.append(outcome.raw_object)
            versions.append(outcome.document_version)
        return ConnectorReplayResult(
            discovery_records=tuple(completed_records),
            fetch_results=tuple(fetches),
            raw_objects=tuple(raw_objects),
            document_versions=tuple(versions),
        )


def _validate_document_bytes(
    fetched: FetchResult,
    *,
    filename: str | None = None,
    declared_mime: str | None = None,
) -> None:
    if not 200 <= fetched.status_code < 300 or fetched.content is None or not fetched.content:
        raise ConnectorParseFailed("document bytes are missing")
    supplied_metadata = filename is not None or declared_mime is not None
    if supplied_metadata and (filename is None or declared_mime is None):
        raise SecurityViolation("FILE_METADATA_INCOMPLETE")
    mime = _normalized_mime(declared_mime if supplied_metadata else fetched.content_type)
    effective_filename = (
        _validated_manual_filename(filename)
        if supplied_metadata and filename is not None
        else PurePosixPath(urlsplit(fetched.url).path).name
    )
    if mime in {"text/html", "application/xhtml+xml"}:
        if not supplied_metadata and not effective_filename.casefold().endswith((".html", ".htm")):
            effective_filename = f"{effective_filename or 'document'}.html"
        inspect_fixture_bytes(
            fetched.content,
            effective_filename,
            "text/html",
            max_bytes=_FILE_POLICY.max_file_bytes,
            max_pdf_pages=_FILE_POLICY.max_pdf_pages,
        )
        return
    if mime == "application/pdf":
        if not supplied_metadata and not effective_filename.casefold().endswith(".pdf"):
            effective_filename = f"{effective_filename or 'document'}.pdf"
        inspect_pdf_bytes(
            fetched.content,
            filename=effective_filename,
            declared_mime=mime,
            policy=_FILE_POLICY,
        )
        return
    if mime in {"application/zip", "application/x-zip-compressed"}:
        if not supplied_metadata and not effective_filename.casefold().endswith(".zip"):
            effective_filename = f"{effective_filename or 'document'}.zip"
        inspect_zip_bytes(
            fetched.content,
            filename=effective_filename,
            declared_mime=mime,
            policy=_FILE_POLICY,
        )
        return
    if mime == "application/json":
        try:
            json.loads(fetched.content)
        except (ValueError, RecursionError) as error:
            raise ConnectorParseFailed("document bytes are not valid JSON") from error
        return
    raise ConnectorParseFailed("document bytes have an unsupported MIME type")


def _normalized_mime(value: str | None) -> str:
    if (
        value is None
        or not value
        or len(value) > 200
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise SecurityViolation("MIME_INVALID")
    return value.split(";", maxsplit=1)[0].strip().casefold()


def _validated_manual_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if (
        not normalized
        or len(normalized) > 255
        or any(character in normalized for character in ("/", "\\", ":", "\x00"))
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise SecurityViolation("FILENAME_INVALID")
    return normalized


def _validate_manual_submission(
    submission: ManualImportSubmission,
    config: dict[str, object],
) -> None:
    if (
        submission.filename is None
        or submission.declared_mime is None
        or submission.content is None
    ):
        raise ValueError("manual file import is incomplete")
    allowed_types = _string_list(config, "allowed_file_types")
    mime_type = submission.declared_mime.split(";", maxsplit=1)[0].strip().casefold()
    kind_by_mime = {
        "text/html": "HTML",
        "application/pdf": "PDF",
        "application/zip": "ZIP",
        "application/x-zip-compressed": "ZIP",
    }
    if kind_by_mime.get(mime_type) not in allowed_types:
        raise PermissionError("manual file type is not enabled")


def _string_list(document: dict[str, object], field_name: str) -> list[str]:
    value = document.get(field_name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"connector list field is invalid: {field_name}")
    return [item for item in value if isinstance(item, str)]


def _direct_record(url: str, discovered_at: datetime) -> DiscoveryRecord:
    filename = PurePosixPath(urlsplit(url).path).name or "document"
    return DiscoveryRecord(
        external_id=sha256(url.encode()).hexdigest(),
        url=url,
        title=filename,
        published_at=None,
        discovered_at=discovered_at,
    )


def _next_checkpoint(
    records: tuple[DiscoveryRecord, ...],
    previous: SourceCheckpoint,
    fetched: FetchResult | None,
) -> SourceCheckpoint:
    return SourceCheckpoint(
        cursor=records[-1].external_id if records else previous.cursor,
        etag=fetched.etag if fetched is not None else previous.etag,
        last_modified=(fetched.last_modified if fetched is not None else previous.last_modified),
        consecutive_failures=0,
    )


def _header(headers: dict[str, str], name: str) -> str | None:
    expected = name.casefold()
    return next((value for key, value in headers.items() if key.casefold() == expected), None)


def _response_sha256(status_code: int, headers: dict[str, str], content: bytes) -> str:
    selected = {
        key.casefold(): value
        for key, value in headers.items()
        if key.casefold() in {"content-type", "etag", "last-modified"}
    }
    evidence = (
        f"{status_code}\n".encode()
        + json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
        + content
    )
    return sha256(evidence).hexdigest()


def _safe_reason(error: Exception) -> str:
    code = getattr(error, "code", None)
    return code if isinstance(code, str) and code else type(error).__name__.upper()
