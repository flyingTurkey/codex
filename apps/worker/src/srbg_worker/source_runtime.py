"""Authoritative scheduled execution for versioned declarative source connectors.

The executor is deliberately dependency-injected.  Unit tests use a socket-free
transport and an in-memory gateway; the Celery task uses the PostgreSQL, S3,
ClamAV, DNS-pinned HTTP implementations below.  Fixture, replay, backfill and
drill runs are rejected before a transport is constructed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import ssl
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID
from xml.etree import ElementTree

from defusedxml import ElementTree as DefusedElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    ExecutionDomain,
    FetchResult,
    SourceAdapter,
    SourceCheckpoint,
)
from srbg_api.acquisition.http import FetchPolicy, HttpStatusError, ResilientHttpClient
from srbg_api.acquisition.live import HttpxTransport, SystemClock, SystemResolver
from srbg_api.config import Settings
from srbg_api.connectors.config import (
    ConnectorConfigRejected,
    ConnectorKind,
    validate_connector_config,
    validate_runtime_url,
)
from srbg_api.connectors.parsers import (
    CONNECTOR_PARSERS,
    ConnectorRequest,
    DeclarativeParseError,
    DeclarativeParser,
    EmptyDiscoveryError,
    RequiredFieldMissingError,
)
from srbg_api.database import create_database_engine
from srbg_api.document_vault.scanner import ClamAVScanner
from srbg_api.document_vault.security import MalwareDetected, MalwareScanInconclusive
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.pdf_processing.security import FileSecurityPolicy, inspect_pdf_bytes
from srbg_api.scheduling.domain import FetchFailure, HealthObservation
from srbg_api.scheduling.service import PostgresSchedulingService

logger = logging.getLogger("srbg.worker.source_runtime")

MAX_HTML_TAGS = 100_000
MAX_TITLE_LENGTH = 300
MAX_STRUCTURED_NODES = 20_000
MAX_STRUCTURED_DEPTH = 64
DEFAULT_RUNTIME_FILE_POLICY = FileSecurityPolicy(
    max_file_bytes=50 * 1024 * 1024,
    max_pdf_pages=1000,
    max_ocr_pages=200,
    max_zip_entries=100,
    max_uncompressed_bytes=200 * 1024 * 1024,
    max_compression_ratio=100,
    max_page_pixels=40_000_000,
)


class RunOrigin(StrEnum):
    SCHEDULED = "SCHEDULED"
    REPLAY = "REPLAY"
    BACKFILL = "BACKFILL"
    DRILL = "DRILL"


@dataclass(frozen=True, slots=True)
class RuntimeBinding:
    source_id: UUID
    run_id: UUID
    origin: RunOrigin
    execution_domain: ExecutionDomain
    connector_kind: ConnectorKind
    connector_config: dict[str, object]
    allowed_hosts: tuple[str, ...]
    policy_version_id: UUID | None
    connector_config_version_id: UUID | None
    checkpoint: SourceCheckpoint
    freshness_slo_seconds: int
    fetch_policy: FetchPolicy | None = None
    authority_mode: str = "PERSONAL_STREAM"
    source_stream_id: UUID | None = None
    stream_config_version_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RawCapture:
    raw_object_id: UUID
    capture_id: UUID
    content_sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class RuntimeDocument:
    canonical_url: str
    document_kind: str
    detected_mime: str
    filename: str
    title: str | None
    acquired_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeRunResult:
    acquired: bool
    cancelled: bool
    discovered_count: int
    fetched_count: int
    failed_count: int
    request_count: int
    response_bytes: int
    discovery_body_bytes: int = 0
    discovery_structure_sha256: str | None = None
    latest_published_at: datetime | None = None
    duplicate_ratio: float = 0.0
    required_fields_missing: bool = False


class RuntimeGateway(Protocol):
    async def acquire_execution(self, source_id: UUID, run_id: UUID) -> bool: ...

    async def cancel_ineligible(self, source_id: UUID, run_id: UUID) -> bool: ...

    async def revalidate_binding(self, source_id: UUID, run_id: UUID) -> RuntimeBinding | None: ...

    async def authorize_request(self, binding: RuntimeBinding, *, url: str) -> bool: ...

    async def reserve_request(self, binding: RuntimeBinding, *, url: str) -> None: ...

    async def record_response_bytes(
        self,
        binding: RuntimeBinding,
        *,
        url: str,
        response_bytes: int,
    ) -> None: ...

    async def persist_raw(
        self,
        binding: RuntimeBinding,
        *,
        fetched: FetchResult,
        purpose: str,
    ) -> RawCapture: ...

    async def mark_discovery_parsed(self, capture: RawCapture) -> None: ...

    async def record_parse_failure(self, capture: RawCapture, reason_code: str) -> None: ...

    async def persist_document(
        self,
        binding: RuntimeBinding,
        *,
        capture: RawCapture,
        record: DiscoveryRecord,
        document: RuntimeDocument,
    ) -> UUID: ...

    async def record_outcome(
        self,
        source_id: UUID,
        run_id: UUID,
        binding: RuntimeBinding | None,
        *,
        result: RuntimeRunResult,
        failure_kind: str | None,
        next_checkpoint: SourceCheckpoint | None = None,
    ) -> str: ...

    async def close(self) -> None: ...


class RuntimeTransport(Protocol):
    async def fetch(
        self,
        url: str,
        *,
        checkpoint: SourceCheckpoint,
        accept: str,
        exact_redirect_host: str,
    ) -> FetchResult: ...

    async def close(self) -> None: ...


class RuntimeExecutionError(RuntimeError):
    def __init__(self, failure_kind: str, reason_code: str) -> None:
        self.failure_kind = failure_kind
        self.reason_code = reason_code
        super().__init__(reason_code)


class RawRegistrationError(OSError):
    """S3 bytes exist, but authoritative raw metadata registration failed."""


class ScheduledDeclarativeSourceAdapter(SourceAdapter):
    """Canonical ``SourceAdapter`` for an authorized scheduled production run.

    The adapter owns discovery/fetch semantics and the raw-first boundary.  The
    executor only acquires authority, invokes this contract and promotes the
    returned document bytes, so live collection cannot grow a second connector
    entry point beside ``SourceAdapter``.
    """

    def __init__(
        self,
        *,
        binding: RuntimeBinding,
        parser: DeclarativeParser,
        config: dict[str, object],
        transport: RuntimeTransport,
        gateway: RuntimeGateway,
        authority_heartbeat_seconds: float,
    ) -> None:
        self._binding = binding
        self._parser = parser
        self._config = config
        self._transport = transport
        self._gateway = gateway
        self._authority_heartbeat_seconds = authority_heartbeat_seconds
        self._captures: dict[int, RawCapture] = {}
        self._prefetched: dict[str, list[FetchResult]] = {}
        self._response_bytes = 0
        self._fallback_request_count = 0
        self._initial_not_modified = False
        self._required_fields_missing = False
        self._discovery_body_bytes = 0
        self._discovery_structure_hashes: list[str] = []

    @property
    def response_bytes(self) -> int:
        return self._response_bytes

    @property
    def request_count(self) -> int:
        physical_count = _transport_request_count(self._transport)
        return self._fallback_request_count if physical_count is None else physical_count

    @property
    def initial_not_modified(self) -> bool:
        return self._initial_not_modified

    @property
    def discovery_body_bytes(self) -> int:
        return self._discovery_body_bytes

    @property
    def discovery_structure_sha256(self) -> str | None:
        if not self._discovery_structure_hashes:
            return None
        material = "\n".join(sorted(self._discovery_structure_hashes)).encode()
        return sha256(material).hexdigest()

    @property
    def required_fields_missing(self) -> bool:
        return self._required_fields_missing

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        records: list[DiscoveryRecord] = []
        last_fetch: FetchResult | None = None
        for request in self._parser.initial_requests(self._config):
            fetched, capture = await self._fetch_raw_first(
                request=request,
                checkpoint=checkpoint,
                purpose=request.role,
            )
            last_fetch = fetched
            if request.role != "DOCUMENT" and fetched.content is not None:
                self._discovery_body_bytes += len(fetched.content)
                self._discovery_structure_hashes.append(
                    discovery_structure_sha256(fetched.content, fetched.content_type)
                )
            if fetched.not_modified:
                self._initial_not_modified = True
                await self._gateway.mark_discovery_parsed(capture)
                self._captures.pop(id(fetched), None)
                continue
            try:
                if request.role == "DOCUMENT":
                    record = self._parser.direct_record(request, fetched)
                    records.append(record)
                    self._prefetched.setdefault(record.url, []).append(fetched)
                    continue
                discovered = self._parser.discover(fetched, self._config)
                for record in discovered:
                    validate_runtime_url(
                        record.url,
                        allowed_hosts=self._binding.allowed_hosts,
                    )
                records.extend(discovered)
                await self._gateway.mark_discovery_parsed(capture)
                self._captures.pop(id(fetched), None)
            except RuntimeExecutionError:
                raise
            except EmptyDiscoveryError:
                await self._gateway.mark_discovery_parsed(capture)
                self._captures.pop(id(fetched), None)
                continue
            except RequiredFieldMissingError as error:
                self._required_fields_missing = True
                await self._gateway.record_parse_failure(capture, "REQUIRED_FIELDS_MISSING")
                self._captures.pop(id(fetched), None)
                raise RuntimeExecutionError("PARSE", "REQUIRED_FIELDS_MISSING") from error
            except (ConnectorConfigRejected, DeclarativeParseError, ValueError) as error:
                await self._gateway.record_parse_failure(
                    capture,
                    _safe_reason_code(error, default="DISCOVERY_PARSE_FAILED"),
                )
                self._captures.pop(id(fetched), None)
                raise RuntimeExecutionError("PARSE", "DISCOVERY_PARSE_FAILED") from error
        return DiscoveryBatch(
            records=tuple(records),
            next_checkpoint=_next_runtime_checkpoint(checkpoint, last_fetch),
        )

    async def fetch(
        self,
        record: DiscoveryRecord,
        checkpoint: SourceCheckpoint,
    ) -> FetchResult:
        del checkpoint  # List/feed validators are not valid for a distinct detail URL.
        prefetched = self._prefetched.get(record.url)
        if prefetched:
            fetched = prefetched.pop(0)
            if not prefetched:
                self._prefetched.pop(record.url, None)
            return fetched
        fetched, _capture = await self._fetch_raw_first(
            request=ConnectorRequest(record.url, "DOCUMENT", "*/*"),
            checkpoint=SourceCheckpoint(),
            purpose="DOCUMENT",
        )
        return fetched

    def take_capture(self, fetched: FetchResult) -> RawCapture:
        try:
            return self._captures.pop(id(fetched))
        except KeyError as error:
            raise RuntimeExecutionError("DATABASE", "RAW_CAPTURE_MISSING") from error

    async def _fetch_raw_first(
        self,
        *,
        request: ConnectorRequest,
        checkpoint: SourceCheckpoint,
        purpose: str,
    ) -> tuple[FetchResult, RawCapture]:
        validate_runtime_url(request.url, allowed_hosts=self._binding.allowed_hosts)
        if not await self._gateway.authorize_request(self._binding, url=request.url):
            raise RuntimeExecutionError("AUTHORIZATION", "AUTHORIZATION_REVOKED")
        exact_host = _hostname(request.url)
        fetched = await self._fetch_with_authority_heartbeat(
            request=request,
            checkpoint=checkpoint,
            exact_host=exact_host,
        )
        self._response_bytes += len(fetched.content or b"")
        try:
            capture = await self._gateway.persist_raw(
                self._binding,
                fetched=fetched,
                purpose=purpose,
            )
        except RawRegistrationError as error:
            raise RuntimeExecutionError("DATABASE", "RAW_REGISTRATION_FAILED") from error
        except OSError as error:
            raise RuntimeExecutionError("OBJECT_STORAGE", "RAW_PERSISTENCE_FAILED") from error
        self._captures[id(fetched)] = capture
        try:
            _validate_fetch_identity(request.url, fetched, self._binding.allowed_hosts)
            _reject_runtime_access_barriers(fetched.content or b"", fetched.content_type)
        except RuntimeExecutionError as error:
            await self._gateway.record_parse_failure(capture, error.reason_code)
            self._captures.pop(id(fetched), None)
            raise
        return fetched, capture

    async def _fetch_with_authority_heartbeat(
        self,
        *,
        request: ConnectorRequest,
        checkpoint: SourceCheckpoint,
        exact_host: str,
    ) -> FetchResult:
        if _transport_request_count(self._transport) is None:
            self._fallback_request_count += 1
        fetch_task = asyncio.create_task(
            self._transport.fetch(
                request.url,
                checkpoint=checkpoint,
                accept=request.accept,
                exact_redirect_host=exact_host,
            )
        )
        try:
            while True:
                done, _pending = await asyncio.wait(
                    (fetch_task,),
                    timeout=self._authority_heartbeat_seconds,
                )
                if fetch_task in done:
                    return await fetch_task
                if not await self._gateway.authorize_request(
                    self._binding,
                    url=request.url,
                ):
                    raise RuntimeExecutionError(
                        "AUTHORIZATION",
                        "AUTHORIZATION_REVOKED",
                    )
        finally:
            if not fetch_task.done():
                fetch_task.cancel()
                with suppress(asyncio.CancelledError):
                    await fetch_task


class RuntimeFetchExecutor:
    """Run one already-dispatched source run through the canonical parser map."""

    def __init__(
        self,
        *,
        gateway: RuntimeGateway,
        transport_factory: Callable[[RuntimeBinding], RuntimeTransport],
        parsers: Mapping[ConnectorKind, DeclarativeParser] = CONNECTOR_PARSERS,
        max_document_bytes: int = 50 * 1024 * 1024,
        file_security_policy: FileSecurityPolicy = DEFAULT_RUNTIME_FILE_POLICY,
        authority_heartbeat_seconds: float = 30.0,
    ) -> None:
        if not 0 < authority_heartbeat_seconds <= 300:
            raise ValueError("authority heartbeat interval must be bounded")
        self._gateway = gateway
        self._transport_factory = transport_factory
        self._parsers = parsers
        self._max_document_bytes = max_document_bytes
        self._file_security_policy = file_security_policy
        self._authority_heartbeat_seconds = authority_heartbeat_seconds

    async def run(self, *, source_id: UUID, run_id: UUID) -> RuntimeRunResult:
        transport: RuntimeTransport | None = None
        binding: RuntimeBinding | None = None
        try:
            acquired = await self._gateway.acquire_execution(source_id, run_id)
            if not acquired:
                cancelled = await self._gateway.cancel_ineligible(source_id, run_id)
                return _empty_result(acquired=False, cancelled=cancelled)

            binding = await self._gateway.revalidate_binding(source_id, run_id)
            if binding is None:
                await self._gateway.cancel_ineligible(source_id, run_id)
                result = _empty_result(acquired=True, cancelled=True)
                await self._gateway.record_outcome(
                    source_id,
                    run_id,
                    None,
                    result=result,
                    failure_kind="AUTHORIZATION",
                )
                return result
            if (
                binding.origin is not RunOrigin.SCHEDULED
                or binding.execution_domain is not ExecutionDomain.PRODUCTION
            ):
                await self._gateway.cancel_ineligible(source_id, run_id)
                result = _empty_result(acquired=True, cancelled=True)
                await self._gateway.record_outcome(
                    source_id,
                    run_id,
                    binding,
                    result=result,
                    failure_kind="ORIGIN_ISOLATION",
                )
                return result

            validated = validate_connector_config(
                binding.connector_kind,
                binding.connector_config,
                source_allowed_hosts=binding.allowed_hosts,
            )
            parser = self._parsers[binding.connector_kind]
            transport = self._transport_factory(binding)
            adapter = ScheduledDeclarativeSourceAdapter(
                binding=binding,
                parser=parser,
                config=validated.document,
                transport=transport,
                gateway=self._gateway,
                authority_heartbeat_seconds=self._authority_heartbeat_seconds,
            )
            result, failure_kind, next_checkpoint = await self._execute_binding(
                binding,
                adapter=adapter,
            )
            await self._gateway.record_outcome(
                source_id,
                run_id,
                binding,
                result=result,
                failure_kind=failure_kind,
                next_checkpoint=next_checkpoint,
            )
            return result
        except ConnectorConfigRejected:
            result = _empty_result(acquired=True, cancelled=False, failed_count=1)
            await self._gateway.record_outcome(
                source_id,
                run_id,
                binding,
                result=result,
                failure_kind="PARSE",
            )
            return result
        except Exception as error:
            failure_kind = _unexpected_failure_kind(error)
            logger.exception(
                "scheduled_source_execution_failed",
                extra={
                    "event_name": "scheduled_source_execution_failed",
                    "source_id": str(source_id),
                    "run_id": str(run_id),
                    "failure_kind": failure_kind,
                    "exception_type": type(error).__name__,
                    "outcome": "FAILED",
                },
            )
            result = _empty_result(acquired=True, cancelled=False, failed_count=1)
            await self._gateway.record_outcome(
                source_id,
                run_id,
                binding,
                result=result,
                failure_kind=failure_kind,
            )
            return result
        finally:
            try:
                if transport is not None:
                    await transport.close()
            finally:
                await self._gateway.close()

    async def _execute_binding(
        self,
        binding: RuntimeBinding,
        *,
        adapter: ScheduledDeclarativeSourceAdapter,
    ) -> tuple[RuntimeRunResult, str | None, SourceCheckpoint | None]:
        records: tuple[DiscoveryRecord, ...] = ()
        checkpoint = binding.checkpoint
        next_checkpoint: SourceCheckpoint | None = None
        fetched_count = 0
        failed_count = 0
        failure_kind: str | None = None
        try:
            batch = await adapter.discover(checkpoint)
            records = batch.records
            checkpoint = batch.next_checkpoint
            next_checkpoint = checkpoint
        except RuntimeExecutionError as error:
            failed_count += 1
            failure_kind = error.failure_kind
        except (OSError, TimeoutError) as error:
            failed_count += 1
            failure_kind = _io_failure_kind(error)

        if failure_kind is None and adapter.initial_not_modified and not records:
            failure_kind = "NOT_MODIFIED"

        if failure_kind is None:
            for record in records:
                try:
                    fetched = await adapter.fetch(record, checkpoint)
                    capture = adapter.take_capture(fetched)
                    if fetched.not_modified:
                        continue
                    await self._persist_document(
                        binding,
                        fetched=fetched,
                        capture=capture,
                        record=record,
                    )
                    fetched_count += 1
                except RuntimeExecutionError as error:
                    failed_count += 1
                    failure_kind = error.failure_kind
                except (OSError, TimeoutError) as error:
                    failed_count += 1
                    failure_kind = _io_failure_kind(error)

        result = RuntimeRunResult(
            acquired=True,
            cancelled=False,
            discovered_count=len(records),
            fetched_count=fetched_count,
            failed_count=failed_count,
            request_count=adapter.request_count,
            response_bytes=adapter.response_bytes,
            discovery_body_bytes=adapter.discovery_body_bytes,
            discovery_structure_sha256=adapter.discovery_structure_sha256,
            latest_published_at=max(
                (record.published_at for record in records if record.published_at is not None),
                default=None,
            ),
            duplicate_ratio=_duplicate_ratio(records),
            required_fields_missing=adapter.required_fields_missing,
        )
        return result, failure_kind, next_checkpoint

    async def _persist_document(
        self,
        binding: RuntimeBinding,
        *,
        fetched: FetchResult,
        capture: RawCapture,
        record: DiscoveryRecord,
    ) -> None:
        try:
            document = parse_runtime_document(
                record,
                fetched,
                max_bytes=self._max_document_bytes,
                file_security_policy=self._file_security_policy,
            )
            await self._gateway.persist_document(
                binding,
                capture=capture,
                record=record,
                document=document,
            )
        except RuntimeExecutionError:
            raise
        except OSError as error:
            reason = _safe_reason_code(error, default="DOCUMENT_REGISTRATION_FAILED")
            await self._gateway.record_parse_failure(capture, reason)
            raise RuntimeExecutionError("DATABASE", reason) from error
        except ValueError as error:
            reason = (
                "MIME_MISMATCH"
                if "MIME" in str(error).upper()
                else _safe_reason_code(error, default="DOCUMENT_PARSE_FAILED")
            )
            await self._gateway.record_parse_failure(capture, reason)
            failure_kind = reason if reason == "MIME_MISMATCH" else "PARSE"
            raise RuntimeExecutionError(failure_kind, reason) from error


class LiveRuntimeTransport:
    """DNS-pinned live transport with one rate-limit/circuit state per exact host."""

    def __init__(
        self,
        binding: RuntimeBinding,
        *,
        before_request: Callable[[str], Awaitable[None]] | None = None,
        after_response: Callable[[str, int], Awaitable[None]] | None = None,
    ) -> None:
        if binding.fetch_policy is None:
            raise ValueError("live runtime binding has no fetch policy")
        self._base_policy = binding.fetch_policy
        self._before_request = before_request
        self._after_response = after_response
        self._request_count = 0
        self._clients: dict[str, ResilientHttpClient] = {}
        self._transport = HttpxTransport()
        self._resolver = SystemResolver()
        self._clock = SystemClock()

    @property
    def request_count(self) -> int:
        return self._request_count

    async def _before_physical_request(self, url: str) -> None:
        if self._before_request is not None:
            await self._before_request(url)
        self._request_count += 1

    async def fetch(
        self,
        url: str,
        *,
        checkpoint: SourceCheckpoint,
        accept: str,
        exact_redirect_host: str,
    ) -> FetchResult:
        if _hostname(url) != exact_redirect_host:
            raise ValueError("runtime request host does not match the redirect boundary")
        client = self._clients.get(exact_redirect_host)
        if client is None:
            policy = FetchPolicy(
                allowed_hosts=(exact_redirect_host,),
                timeout_seconds=self._base_policy.timeout_seconds,
                max_attempts=self._base_policy.max_attempts,
                base_backoff_seconds=self._base_policy.base_backoff_seconds,
                rate_limit_per_minute=self._base_policy.rate_limit_per_minute,
                minimum_interval_seconds=self._base_policy.minimum_interval_seconds,
                circuit_failure_threshold=self._base_policy.circuit_failure_threshold,
                circuit_reset_seconds=self._base_policy.circuit_reset_seconds,
                max_redirects=self._base_policy.max_redirects,
                user_agent=self._base_policy.user_agent,
                max_response_bytes=self._base_policy.max_response_bytes,
                allowed_schemes=self._base_policy.allowed_schemes,
                max_backoff_seconds=self._base_policy.max_backoff_seconds,
            )
            client = ResilientHttpClient(
                policy,
                resolver=self._resolver,
                transport=self._transport,
                clock=self._clock,
                before_request=self._before_physical_request,
                after_response=self._after_response,
            )
            self._clients[exact_redirect_host] = client
        return await client.get(url, checkpoint=checkpoint, accept=accept)

    async def close(self) -> None:
        await self._transport.close()


class PostgresRuntimeGateway:
    """PostgreSQL authority plus private object storage for scheduled runs."""

    def __init__(
        self,
        settings: Settings,
        *,
        engine: AsyncEngine | None = None,
        object_store: S3ObjectStore | None = None,
        malware_scanner: ClamAVScanner | None = None,
    ) -> None:
        self._settings = settings
        self._engine = engine or create_database_engine(settings)
        self._scheduling = PostgresSchedulingService(self._engine)
        self._object_store = object_store or S3ObjectStore(settings)
        self._malware_scanner = malware_scanner or ClamAVScanner(
            settings.clamav_host,
            settings.clamav_port,
            settings.external_io_timeout_seconds,
        )
        self._execution_lease_token: UUID | None = None

    async def acquire_execution(self, source_id: UUID, run_id: UUID) -> bool:
        acquired = await self._scheduling.acquire_execution(
            source_id=source_id,
            run_id=run_id,
        )
        if not acquired:
            return False
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(_ACQUIRED_LEASE_SQL),
                        {"source_id": source_id, "run_id": run_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        token = None if row is None else row["execution_lease_token"]
        if not isinstance(token, UUID):
            raise RuntimeError("acquired source execution has no authoritative lease token")
        self._execution_lease_token = token
        return True

    async def cancel_ineligible(self, source_id: UUID, run_id: UUID) -> bool:
        return await self._scheduling.cancel_ineligible(source_id=source_id, run_id=run_id)

    async def revalidate_binding(self, source_id: UUID, run_id: UUID) -> RuntimeBinding | None:
        now = datetime.now(UTC)
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(_PERSONAL_BINDING_SQL),
                        {"source_id": source_id, "run_id": run_id, "now": now},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        try:
            checkpoint = _runtime_checkpoint_from_row(row)
        except (TypeError, ValueError):
            return None
        config = row["config_document"]
        if not isinstance(config, dict):
            return None
        config_hosts = _string_tuple(row["config_allowed_hosts"])
        authority_mode = str(row.get("authority_mode", "PERSONAL_STREAM"))
        if authority_mode != "PERSONAL_STREAM":
            return None
        fetch: dict[str, object] = {}
        allowed_hosts = config_hosts
        if not allowed_hosts:
            return None
        validated = validate_connector_config(
            ConnectorKind(str(row["connector_type"])),
            config,
            source_allowed_hosts=allowed_hosts,
        )
        fetch_policy = FetchPolicy(
            allowed_hosts=allowed_hosts,
            timeout_seconds=self._settings.external_io_timeout_seconds,
            max_attempts=max(1, int(row["max_attempts"])),
            base_backoff_seconds=max(0, int(row["backoff_base_seconds"])),
            rate_limit_per_minute=_positive_int(fetch.get("rate_limit_per_minute"), default=1),
            minimum_interval_seconds=_positive_int(
                fetch.get("minimum_interval_seconds"), default=900
            ),
            circuit_failure_threshold=5,
            circuit_reset_seconds=1800,
            max_redirects=3,
            user_agent=str(fetch.get("user_agent", "SRBGSourceAdapter/1.0")),
            max_response_bytes=self._settings.fixture_max_bytes,
            allowed_schemes=("http", "https"),
            max_backoff_seconds=max(1, int(row["backoff_cap_seconds"])),
        )
        return RuntimeBinding(
            source_id=source_id,
            run_id=run_id,
            origin=RunOrigin(str(row["run_origin"])),
            execution_domain=ExecutionDomain(str(row["execution_domain"])),
            connector_kind=ConnectorKind(str(row["connector_type"])),
            connector_config=validated.document,
            allowed_hosts=allowed_hosts,
            policy_version_id=row["policy_version_id"],
            connector_config_version_id=row["connector_config_version_id"],
            checkpoint=checkpoint,
            freshness_slo_seconds=int(row["freshness_slo_seconds"]),
            fetch_policy=fetch_policy,
            authority_mode=authority_mode,
            source_stream_id=row.get("source_stream_id"),
            stream_config_version_id=row.get("stream_config_version_id"),
        )

    async def authorize_request(self, binding: RuntimeBinding, *, url: str) -> bool:
        try:
            validate_runtime_url(url, allowed_hosts=binding.allowed_hosts)
        except ConnectorConfigRejected:
            return False
        if not await self._renew_execution_lease(binding):
            return False
        current = await self.revalidate_binding(binding.source_id, binding.run_id)
        return bool(
            current is not None
            and current.origin is RunOrigin.SCHEDULED
            and current.execution_domain is ExecutionDomain.PRODUCTION
            and current.policy_version_id == binding.policy_version_id
            and current.connector_config_version_id == binding.connector_config_version_id
            and current.source_stream_id == binding.source_stream_id
            and current.stream_config_version_id == binding.stream_config_version_id
            and current.connector_config == binding.connector_config
        )

    async def reserve_request(self, binding: RuntimeBinding, *, url: str) -> None:
        if not await self.authorize_request(binding, url=url):
            raise RuntimeExecutionError("AUTHORIZATION", "AUTHORIZATION_REVOKED")
        if not await self._scheduling.reserve_request(
            source_id=binding.source_id,
            run_id=binding.run_id,
        ):
            raise RuntimeExecutionError("AUTHORIZATION", "REQUEST_BUDGET_EXHAUSTED")

    async def record_response_bytes(
        self,
        binding: RuntimeBinding,
        *,
        url: str,
        response_bytes: int,
    ) -> None:
        validate_runtime_url(url, allowed_hosts=binding.allowed_hosts)
        if response_bytes < 0:
            raise RuntimeExecutionError("DATABASE", "NEGATIVE_RESPONSE_BYTES")
        if not await self._scheduling.record_response_bytes(
            source_id=binding.source_id,
            run_id=binding.run_id,
            response_bytes=response_bytes,
        ):
            raise RuntimeExecutionError("DATABASE", "RESPONSE_ACCOUNTING_FAILED")

    async def _renew_execution_lease(self, binding: RuntimeBinding) -> bool:
        token = self._execution_lease_token
        if token is None:
            return False
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_RENEW_EXECUTION_LEASE_SQL),
                        {
                            "source_id": binding.source_id,
                            "run_id": binding.run_id,
                            "lease_token": token,
                            "now": now,
                            "until": now + timedelta(minutes=10),
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        return row is not None

    async def persist_raw(
        self,
        binding: RuntimeBinding,
        *,
        fetched: FetchResult,
        purpose: str,
    ) -> RawCapture:
        del purpose
        content = fetched.content
        if content is None and not fetched.not_modified:
            raise OSError("scheduled response has no immutable body")
        content = content or b""
        content_hash = sha256(content).hexdigest()
        response_hash = fetched.response_sha256
        if response_hash is None or re.fullmatch(r"[0-9a-f]{64}", response_hash) is None:
            raise OSError("scheduled response hash is invalid")
        object_key = f"sha256/{content_hash[:2]}/{content_hash}"
        storage_etag = await self._object_store.put_if_absent(
            object_key,
            content,
            "application/octet-stream",
        )
        security_status = "CLEAN"
        security_reason: str | None = None
        try:
            if content:
                await self._malware_scanner.scan(content)
        except MalwareDetected:
            security_status = "REJECTED"
            security_reason = "MALWARE_DETECTED"
        except MalwareScanInconclusive:
            security_status = "REJECTED"
            security_reason = "MALWARE_SCAN_INCONCLUSIVE"
        raw_id = uuid7()
        capture_id = uuid7()
        parameters = {
            "raw_id": raw_id,
            "capture_id": capture_id,
            "source_id": binding.source_id,
            "run_id": binding.run_id,
            "content_sha256": content_hash,
            "response_sha256": response_hash,
            "object_key": object_key,
            "storage_etag": _bounded_header(storage_etag, 200),
            "byte_size": len(content),
            "declared_mime": _bounded_media_type(fetched.content_type),
            "detected_mime": _detect_mime(content),
            "security_status": security_status,
            "security_reason": security_reason,
            "requested_url": fetched.request_url or fetched.url,
            "final_url": fetched.url,
            "redirect_chain": json.dumps(list(fetched.redirect_chain)),
            "http_status": fetched.status_code,
            "etag": _bounded_header(fetched.etag, 500),
            "last_modified": _bounded_header(fetched.last_modified, 500),
            "captured_at": fetched.fetched_at,
        }
        try:
            async with self._engine.begin() as connection:
                row = (await connection.execute(text(_RECORD_RAW_SQL), parameters)).mappings().one()
        except Exception:
            logger.exception(
                "scheduled_raw_registration_failed",
                extra={
                    "event_name": "scheduled_raw_registration_failed",
                    "source_id": str(binding.source_id),
                    "run_id": str(binding.run_id),
                    "content_sha256": content_hash,
                    "object_key": object_key,
                    "outcome": "RETRYABLE",
                },
            )
            raise RawRegistrationError(
                "raw metadata registration failed after object persistence"
            ) from None
        capture = RawCapture(
            raw_object_id=row["raw_object_id"],
            capture_id=row["capture_id"],
            content_sha256=content_hash,
            byte_size=len(content),
        )
        if security_status != "CLEAN":
            await self.record_parse_failure(capture, security_reason or "RAW_SECURITY_REJECTED")
            raise RuntimeExecutionError("SECURITY", security_reason or "RAW_SECURITY_REJECTED")
        return capture

    async def mark_discovery_parsed(self, capture: RawCapture) -> None:
        logger.info(
            "scheduled_discovery_parsed",
            extra={
                "event_name": "scheduled_discovery_parsed",
                "raw_object_id": str(capture.raw_object_id),
                "outcome": "SUCCEEDED",
            },
        )

    async def record_parse_failure(self, capture: RawCapture, reason_code: str) -> None:
        logger.warning(
            "scheduled_response_parse_failed",
            extra={
                "event_name": "scheduled_response_parse_failed",
                "raw_object_id": str(capture.raw_object_id),
                "reason_code": _bounded_reason(reason_code),
                "outcome": "FAILED",
            },
        )

    async def persist_document(
        self,
        binding: RuntimeBinding,
        *,
        capture: RawCapture,
        record: DiscoveryRecord,
        document: RuntimeDocument,
    ) -> UUID:
        parameters = {
            "document_id": uuid7(),
            "version_id": uuid7(),
            "received_event_id": uuid7(),
            "security_event_id": uuid7(),
            "ready_event_id": uuid7(),
            "source_id": binding.source_id,
            "run_id": binding.run_id,
            "raw_object_id": capture.raw_object_id,
            "capture_id": capture.capture_id,
            "canonical_url": document.canonical_url,
            "document_kind": document.document_kind,
            "content_hash": capture.content_sha256,
            "filename": document.filename,
            "title": document.title or record.title,
            "acquired_at": document.acquired_at,
        }
        async with self._engine.begin() as connection:
            value = await connection.scalar(text(_RECORD_DOCUMENT_SQL), parameters)
        if not isinstance(value, UUID):
            raise OSError("scheduled document registration returned no identifier")
        return value

    async def record_outcome(
        self,
        source_id: UUID,
        run_id: UUID,
        binding: RuntimeBinding | None,
        *,
        result: RuntimeRunResult,
        failure_kind: str | None,
        next_checkpoint: SourceCheckpoint | None = None,
    ) -> str:
        if binding is None or failure_kind in {"AUTHORIZATION", "ORIGIN_ISOLATION"}:
            token = self._execution_lease_token
            if token is None:
                return "LEASE_NOT_OWNED"
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(_CANCEL_OWNED_EXECUTION_SQL),
                    {
                        "now": datetime.now(UTC),
                        "reason": failure_kind,
                        "run_id": run_id,
                        "source_id": source_id,
                        "lease_token": token,
                    },
                )
            return "CANCELLED"
        if not await self._renew_execution_lease(binding):
            return "LEASE_LOST"
        failure = FetchFailure(http_status=304) if failure_kind == "NOT_MODIFIED" else None
        if failure_kind is not None and failure_kind != "NOT_MODIFIED":
            failure = (
                FetchFailure(http_status=int(failure_kind.removeprefix("HTTP_")))
                if failure_kind.startswith("HTTP_")
                and failure_kind.removeprefix("HTTP_").isdigit()
                else FetchFailure(kind=_schedule_failure_kind(failure_kind))
            )
        required_ratio = (
            0.0
            if result.required_fields_missing
            else (
                1.0
                if result.discovered_count == 0
                else min(1.0, result.fetched_count / result.discovered_count)
            )
        )
        if binding.source_stream_id is None:
            zero_discovery_streak = await self._zero_discovery_streak(
                source_id, result=result, failure_kind=failure_kind
            )
            previous_body_bytes, previous_structure_sha256 = (
                await self._previous_discovery_shape(source_id)
            )
        else:
            zero_discovery_streak = await self._personal_zero_discovery_streak(
                binding, result=result, failure_kind=failure_kind
            )
            previous_body_bytes, previous_structure_sha256 = (
                await self._personal_previous_discovery_shape(binding)
            )
        body_length_ratio = (
            result.discovery_body_bytes / previous_body_bytes
            if previous_body_bytes is not None
            and previous_body_bytes > 0
            and result.discovery_body_bytes > 0
            else None
        )
        dom_fingerprint_changed = bool(
            previous_structure_sha256 is not None
            and result.discovery_structure_sha256 is not None
            and previous_structure_sha256 != result.discovery_structure_sha256
        )
        terminal = await self._scheduling.record_outcome(
            source_id=binding.source_id,
            run_id=binding.run_id,
            observation=HealthObservation(
                transport_succeeded=failure_kind not in {
                    "TIMEOUT", "DNS", "TLS", "OBJECT_STORAGE"
                },
                consecutive_zero_discovery=zero_discovery_streak,
                latest_published_at=result.latest_published_at,
                freshness_slo_seconds=binding.freshness_slo_seconds,
                body_length_ratio=body_length_ratio,
                required_field_ratio=required_ratio,
                dom_fingerprint_changed=dom_fingerprint_changed,
                duplicate_ratio=result.duplicate_ratio,
                discovery_body_bytes=result.discovery_body_bytes,
                structure_fingerprint_sha256=result.discovery_structure_sha256,
                new_content_count=result.fetched_count,
                reason_code=_health_reason_code(failure_kind, result),
                http_status=failure.http_status if failure is not None else None,
            ),
            discovered_count=result.discovered_count,
            parsed_count=result.fetched_count,
            request_count=result.request_count,
            response_bytes=result.response_bytes,
            failure=failure,
        )
        if (
            next_checkpoint is not None
            and failure_kind in {None, "NOT_MODIFIED"}
            and terminal in {"SUCCEEDED", "NOT_MODIFIED"}
        ):
            try:
                advanced = await self._advance_successful_checkpoint(
                    binding,
                    checkpoint=next_checkpoint,
                )
            except Exception:
                logger.exception(
                    "scheduled_checkpoint_update_failed",
                    extra={
                        "event_name": "scheduled_checkpoint_update_failed",
                        "source_id": str(binding.source_id),
                        "run_id": str(binding.run_id),
                        "outcome": "RETRY_ON_NEXT_RUN",
                    },
                )
            else:
                if not advanced:
                    logger.error(
                        "scheduled_checkpoint_update_skipped",
                        extra={
                            "event_name": "scheduled_checkpoint_update_skipped",
                            "source_id": str(binding.source_id),
                            "run_id": str(binding.run_id),
                            "outcome": "AUTHORITY_NOT_FOUND",
                        },
                    )
        return terminal

    async def _advance_successful_checkpoint(
        self,
        binding: RuntimeBinding,
        *,
        checkpoint: SourceCheckpoint,
    ) -> bool:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_UPSERT_SUCCESSFUL_CHECKPOINT_SQL),
                        {
                            "checkpoint_id": uuid7(),
                            "source_id": binding.source_id,
                            "run_id": binding.run_id,
                            "cursor": json.dumps(
                                {"value": checkpoint.cursor},
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            "etag": checkpoint.etag,
                            "last_modified": checkpoint.last_modified,
                            "now": now,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        return row is not None

    async def _zero_discovery_streak(
        self,
        source_id: UUID,
        *,
        result: RuntimeRunResult,
        failure_kind: str | None,
    ) -> int:
        if failure_kind is not None or result.discovered_count != 0:
            return 0
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(_RECENT_HEALTH_SQL),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .all()
            )
        streak = 1
        for row in rows:
            if (
                row["transport_status"] != "SUCCEEDED"
                or row["run_status"] != "SUCCEEDED"
                or int(row["discovered_count"]) != 0
            ):
                break
            streak += 1
        return streak

    async def _previous_discovery_shape(
        self, source_id: UUID
    ) -> tuple[int | None, str | None]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(_RECENT_SHAPE_SQL),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None, None
        body_bytes = row["discovery_body_bytes"]
        structure_sha256 = row["structure_fingerprint_sha256"]
        return (
            int(body_bytes) if body_bytes is not None else None,
            str(structure_sha256) if structure_sha256 is not None else None,
        )

    async def _personal_zero_discovery_streak(
        self,
        binding: RuntimeBinding,
        *,
        result: RuntimeRunResult,
        failure_kind: str | None,
    ) -> int:
        if failure_kind is not None or result.discovered_count != 0:
            return 0
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(_RECENT_STREAM_HEALTH_SQL),
                        {"source_stream_id": binding.source_stream_id},
                    )
                )
                .mappings()
                .all()
            )
        streak = 1
        for row in rows:
            if (
                row["transport_status"] != "SUCCEEDED"
                or row["run_status"] != "SUCCEEDED"
                or int(row["discovered_count"]) != 0
            ):
                break
            streak += 1
        return streak

    async def _personal_previous_discovery_shape(
        self, binding: RuntimeBinding
    ) -> tuple[int | None, str | None]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(_RECENT_STREAM_SHAPE_SQL),
                        {"source_stream_id": binding.source_stream_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None, None
        return int(row["discovery_body_bytes"]), str(row["structure_fingerprint_sha256"])

    async def close(self) -> None:
        self._execution_lease_token = None
        await self._scheduling.close()


def parse_runtime_document(
    record: DiscoveryRecord,
    fetched: FetchResult,
    *,
    max_bytes: int,
    file_security_policy: FileSecurityPolicy = DEFAULT_RUNTIME_FILE_POLICY,
) -> RuntimeDocument:
    content = fetched.content
    if content is None or not content or len(content) > max_bytes:
        raise ValueError("document bytes are empty or exceed the bounded limit")
    media_type = _media_type(fetched.content_type)
    detected = _detect_mime(content)
    if media_type == "application/pdf" and detected == "application/pdf":
        inspect_pdf_bytes(
            content,
            filename="source.pdf",
            declared_mime=media_type,
            policy=file_security_policy,
        )
        kind, suffix = "PDF", ".pdf"
    elif media_type in {"text/html", "application/xhtml+xml"} and detected == "text/html":
        parser = _BoundedHtmlParser()
        parser.feed(content.decode("utf-8", errors="replace"))
        parser.close()
        kind, suffix = "HTML", ".html"
    elif media_type == "application/json" and detected == "application/json":
        value: object = json.loads(content)
        if not isinstance(value, (dict, list)):
            raise ValueError("JSON document must be an object or array")
        _validate_json_shape(value)
        kind, suffix = "DISCOVERY_JSON", ".json"
    elif (
        media_type
        in {
            "application/xml",
            "application/rss+xml",
            "application/atom+xml",
            "text/xml",
        }
        and detected == "application/xml"
    ):
        try:
            root = DefusedElementTree.fromstring(
                content,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
        except (ElementTree.ParseError, DefusedXmlException, ValueError) as error:
            raise ValueError("XML document is malformed or unsafe") from error
        _validate_xml_shape(root)
        kind, suffix = "DISCOVERY_XML", ".xml"
    else:
        raise ValueError("document MIME does not match its immutable bytes")
    filename = f"{sha256(record.url.encode()).hexdigest()}{suffix}"
    return RuntimeDocument(
        canonical_url=record.url,
        document_kind=kind,
        detected_mime=detected,
        filename=filename,
        title=record.title[:MAX_TITLE_LENGTH] or None,
        acquired_at=fetched.fetched_at,
    )


def discovery_structure_sha256(content: bytes, content_type: str | None) -> str:
    """Hash bounded structural tokens without retaining response text or attribute values."""

    media_type = _media_type(content_type)
    tokens: set[str]
    if media_type in {"text/html", "application/xhtml+xml"}:
        parser = _StructureHtmlParser()
        parser.feed(content.decode("utf-8", errors="replace"))
        parser.close()
        tokens = parser.tokens
    elif media_type == "application/json":
        value: object = json.loads(content)
        if not isinstance(value, (dict, list)):
            raise ValueError("JSON discovery response must be an object or array")
        _validate_json_shape(value)
        tokens = _json_structure_tokens(value)
    elif media_type in {
        "application/xml",
        "application/rss+xml",
        "application/atom+xml",
        "text/xml",
    }:
        try:
            root = DefusedElementTree.fromstring(
                content,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
        except (ElementTree.ParseError, DefusedXmlException, ValueError) as error:
            raise ValueError("XML discovery response is malformed or unsafe") from error
        _validate_xml_shape(root)
        tokens = _xml_structure_tokens(root)
    else:
        tokens = {f"media:{media_type or 'unknown'}"}
    material = "\n".join(sorted(tokens)).encode()
    return sha256(material).hexdigest()


def _duplicate_ratio(records: tuple[DiscoveryRecord, ...]) -> float:
    if not records:
        return 0.0
    seen_external_ids: set[str] = set()
    seen_urls: set[str] = set()
    duplicates = 0
    for record in records:
        if record.external_id in seen_external_ids or record.url in seen_urls:
            duplicates += 1
        seen_external_ids.add(record.external_id)
        seen_urls.add(record.url)
    return duplicates / len(records)


class _StructureHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str] = []
        self._tags = 0
        self.tokens: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._tags += 1
        if self._tags > MAX_HTML_TAGS:
            raise ValueError("HTML discovery response exceeds the structural limit")
        normalized = tag.casefold()
        path = "/".join((*self._stack, normalized))
        attribute_names = ",".join(sorted(name.casefold() for name, _value in attrs))
        selector_hashes = ",".join(
            sorted(
                f"{name.casefold()}={sha256(value[:512].encode()).hexdigest()}"
                for name, value in attrs
                if value is not None
                and name.casefold() in {"id", "class", "role", "itemprop", "name"}
            )
        )
        self.tokens.add(
            f"{path}|attrs:{attribute_names}|selector-hashes:{selector_hashes}"
        )
        self._stack.append(normalized)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized not in self._stack:
            return
        while self._stack:
            current = self._stack.pop()
            if current == normalized:
                break


def _json_structure_tokens(value: object) -> set[str]:
    tokens: set[str] = set()
    pending: list[tuple[object, str]] = [(value, "$")]
    while pending:
        current, path = pending.pop()
        if isinstance(current, dict):
            tokens.add(f"{path}:object")
            for key, item in current.items():
                child = f"{path}.{key}"
                tokens.add(f"{child}:key")
                pending.append((item, child))
        elif isinstance(current, list):
            tokens.add(f"{path}:array")
            pending.extend((item, f"{path}[]") for item in current)
        else:
            tokens.add(f"{path}:{type(current).__name__}")
    return tokens


def _xml_structure_tokens(root: ElementTree.Element) -> set[str]:
    tokens: set[str] = set()
    pending: list[tuple[ElementTree.Element, str]] = [(root, "")]
    while pending:
        current, parent_path = pending.pop()
        tag = str(current.tag)
        path = f"{parent_path}/{tag}"
        attributes = ",".join(sorted(str(name) for name in current.attrib))
        tokens.add(f"{path}|attrs:{attributes}")
        pending.extend((child, path) for child in current)
    return tokens


class _BoundedHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._tags = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del tag, attrs
        self._tags += 1
        if self._tags > MAX_HTML_TAGS:
            raise ValueError("HTML document exceeds the structural limit")

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)


def _validate_json_shape(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_STRUCTURED_NODES or depth > MAX_STRUCTURED_DEPTH:
            raise ValueError("JSON document exceeds structural limits")
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)


def _validate_xml_shape(root: ElementTree.Element) -> None:
    pending = [(root, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_STRUCTURED_NODES or depth > MAX_STRUCTURED_DEPTH:
            raise ValueError("XML document exceeds structural limits")
        pending.extend((child, depth + 1) for child in current)


def _validate_fetch_identity(
    requested_url: str,
    fetched: FetchResult,
    allowed_hosts: tuple[str, ...],
) -> None:
    validate_runtime_url(requested_url, allowed_hosts=allowed_hosts)
    validate_runtime_url(fetched.url, allowed_hosts=allowed_hosts)
    if (fetched.request_url or requested_url) != requested_url:
        raise RuntimeExecutionError("SECURITY", "REQUEST_URL_MISMATCH")
    requested_host = _hostname(requested_url)
    evidence_urls = (*fetched.redirect_chain, fetched.url)
    if any(_hostname(url) != requested_host for url in evidence_urls):
        raise RuntimeExecutionError("SECURITY", "CROSS_DOMAIN_REDIRECT")
    if fetched.not_modified:
        return
    if fetched.status_code < 200 or fetched.status_code >= 300 or fetched.content is None:
        raise RuntimeExecutionError("TIMEOUT", "UPSTREAM_RESPONSE_INVALID")


def _next_runtime_checkpoint(
    checkpoint: SourceCheckpoint,
    fetched: FetchResult | None,
) -> SourceCheckpoint:
    if fetched is None:
        return checkpoint
    return SourceCheckpoint(
        cursor=checkpoint.cursor,
        etag=fetched.etag or checkpoint.etag,
        last_modified=fetched.last_modified or checkpoint.last_modified,
        consecutive_failures=0,
        circuit_open_until=None,
    )


def _runtime_checkpoint_from_row(
    row: Mapping[str, object] | RowMapping,
) -> SourceCheckpoint:
    cursor_document = row.get("checkpoint_cursor")
    if cursor_document is None:
        cursor: str | None = None
    elif isinstance(cursor_document, dict):
        cursor_value = cursor_document.get("value")
        if cursor_value is not None and not isinstance(cursor_value, str):
            raise ValueError("source checkpoint cursor must be a string")
        cursor = cursor_value
    else:
        raise ValueError("source checkpoint cursor document must be an object")

    etag = row.get("checkpoint_etag")
    last_modified = row.get("checkpoint_last_modified")
    if etag is not None and not isinstance(etag, str):
        raise ValueError("source checkpoint etag must be a string")
    if last_modified is not None and not isinstance(last_modified, str):
        raise ValueError("source checkpoint last-modified must be a string")

    failures_value = row.get("checkpoint_consecutive_failures")
    failures = 0 if failures_value is None else failures_value
    if isinstance(failures, bool) or not isinstance(failures, int) or failures < 0:
        raise ValueError("source checkpoint failure count is invalid")

    circuit_open_until = row.get("checkpoint_circuit_open_until")
    if circuit_open_until is not None and not isinstance(circuit_open_until, datetime):
        raise ValueError("source checkpoint circuit timestamp is invalid")
    return SourceCheckpoint(
        cursor=cursor,
        etag=etag,
        last_modified=last_modified,
        consecutive_failures=failures,
        circuit_open_until=circuit_open_until,
    )


def _empty_result(
    *,
    acquired: bool,
    cancelled: bool,
    failed_count: int = 0,
) -> RuntimeRunResult:
    return RuntimeRunResult(
        acquired=acquired,
        cancelled=cancelled,
        discovered_count=0,
        fetched_count=0,
        failed_count=failed_count,
        request_count=0,
        response_bytes=0,
    )


def _transport_request_count(transport: object) -> int | None:
    value = getattr(transport, "request_count", None)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _media_type(value: str | None) -> str:
    return (value or "application/octet-stream").split(";", 1)[0].strip().casefold()


def _bounded_media_type(value: str | None) -> str:
    media_type = _media_type(value)
    return media_type if 1 <= len(media_type) <= 100 else "application/octet-stream"


def _bounded_header(value: str | None, limit: int) -> str | None:
    if value is None or not 1 <= len(value) <= limit:
        return None
    if any(ord(character) < 32 and character != "\t" for character in value):
        return None
    return value


def _detect_mime(content: bytes) -> str:
    prefix = content[:65536].lstrip().lower()
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith((b"<!doctype html", b"<html")):
        return "text/html"
    if prefix.startswith((b"{", b"[")):
        return "application/json"
    if prefix.startswith(b"<?xml") or prefix.startswith((b"<rss", b"<feed", b"<urlset")):
        return "application/xml"
    return "application/octet-stream"


def _hostname(url: str) -> str:
    try:
        hostname = urlsplit(url).hostname
    except ValueError as error:
        raise RuntimeExecutionError("SECURITY", "URL_HOST_INVALID") from error
    if hostname is None:
        raise RuntimeExecutionError("SECURITY", "URL_HOST_INVALID")
    return hostname.rstrip(".").casefold()


def _safe_reason_code(error: Exception, *, default: str) -> str:
    value = getattr(error, "code", default)
    return _bounded_reason(str(value).upper().replace(" ", "_"))


def _bounded_reason(value: str) -> str:
    return value[:100] if re.fullmatch(r"[A-Z0-9_:-]{1,100}", value) else "UNKNOWN"


def _io_failure_kind(error: Exception) -> str:
    if isinstance(error, HttpStatusError):
        return f"HTTP_{error.status_code}"
    if isinstance(error, (ssl.SSLError, ssl.CertificateError)):
        return "TLS"
    return "TIMEOUT" if isinstance(error, TimeoutError) else "DNS"


def _schedule_failure_kind(value: str) -> str:
    return {
        "OBJECT_STORAGE": "OBJECT_STORAGE",
        "PARSE": "PARSE",
        "TIMEOUT": "TIMEOUT",
        "DNS": "DNS",
        "TLS": "TLS",
        "DATABASE": "DATABASE",
    }.get(value, "PARSE")


def _health_reason_code(
    failure_kind: str | None, result: RuntimeRunResult
) -> str | None:
    if failure_kind == "DNS":
        return "DNS_FAILURE"
    if failure_kind == "TIMEOUT":
        return "TIMEOUT"
    if failure_kind == "TLS":
        return "TLS_FAILURE"
    if failure_kind is not None and failure_kind.startswith("HTTP_"):
        status = failure_kind.removeprefix("HTTP_")
        if status in {"401", "403", "404", "429"}:
            return failure_kind
        if status.isdigit() and 500 <= int(status) <= 599:
            return "HTTP_5XX"
    if failure_kind == "PARSE":
        return "PARSE_FAILED"
    if failure_kind in {
        "LOGIN_REQUIRED",
        "CAPTCHA_DETECTED",
        "PAYWALL_DETECTED",
        "MIME_MISMATCH",
        "ROBOTS_BLOCKED",
    }:
        return failure_kind
    if failure_kind == "AUTHORIZATION":
        return "BUDGET_EXHAUSTED"
    if result.required_fields_missing:
        return "REQUIRED_FIELDS_MISSING"
    if result.discovered_count == 0:
        return "ZERO_DISCOVERY_STREAK"
    return None


def _unexpected_failure_kind(error: Exception) -> str:
    if isinstance(error, RuntimeExecutionError):
        return error.failure_kind
    if isinstance(error, TimeoutError):
        return "TIMEOUT"
    if isinstance(error, HttpStatusError):
        return f"HTTP_{error.status_code}"
    if isinstance(error, (ssl.SSLError, ssl.CertificateError)):
        return "TLS"
    if isinstance(error, RawRegistrationError):
        return "DATABASE"
    if isinstance(error, OSError):
        return "DNS"
    return "PARSE"


def _reject_runtime_access_barriers(content: bytes, content_type: str | None) -> None:
    if _media_type(content_type) not in {"text/html", "application/xhtml+xml"}:
        return
    sample = content[:262_144].decode("utf-8", errors="ignore").casefold()
    markers = (
        ("CAPTCHA_DETECTED", ("captcha", "验证码", "人机验证")),
        ("LOGIN_REQUIRED", ("please login", "sign in to continue", "请登录", "登录后查看")),
        ("PAYWALL_DETECTED", ("subscribe to continue", "paywall", "订阅后阅读", "付费阅读")),
    )
    for reason_code, values in markers:
        if any(value in sample for value in values):
            raise RuntimeExecutionError(reason_code, reason_code)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).rstrip(".").casefold() for item in value if isinstance(item, str))


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return default
    try:
        result = int(value)
    except ValueError:
        return default
    return result if result > 0 else default


_PERSONAL_BINDING_SQL = """
SELECT r.run_origin,r.execution_domain,NULL::uuid AS policy_version_id,
       NULL::uuid AS connector_config_version_id,
       stream_config.connector_type,stream_config.config AS config_document,
       stream.allowed_hosts AS config_allowed_hosts,NULL::jsonb AS policy_document,
       fs.authority_mode,stream.id AS source_stream_id,
       stream_config.id AS stream_config_version_id,
       fs.max_attempts,fs.backoff_base_seconds,fs.backoff_cap_seconds,
       fs.freshness_slo_seconds,
       NULL::jsonb AS checkpoint_cursor,NULL::text AS checkpoint_etag,
       NULL::text AS checkpoint_last_modified,
       fs.consecutive_failures AS checkpoint_consecutive_failures,
       fs.circuit_open_until AS checkpoint_circuit_open_until
  FROM fetch_run r
  JOIN source source_row ON source_row.id=r.source_id
  JOIN fetch_schedule fs ON fs.id=r.schedule_id
  JOIN source_stream stream
    ON stream.id=r.source_stream_id AND stream.id=fs.source_stream_id
   AND stream.source_id=source_row.id
  JOIN stream_config_version stream_config
    ON stream_config.id=r.stream_config_version_id
   AND stream_config.id=fs.stream_config_version_id
   AND stream_config.stream_id=stream.id
 WHERE r.id=:run_id AND r.source_id=:source_id AND r.status='RUNNING'
   AND r.run_origin='SCHEDULED' AND r.execution_domain='PRODUCTION'
   AND fs.authority_mode='PERSONAL_STREAM' AND fs.status='ACTIVE'
   AND source_row.desired_enabled=true
   AND source_row.manual_disabled_at IS NULL
   AND stream.status='READY'
   AND stream.config_sha256=stream_config.config_sha256
   AND fs.access_state='ACCESSIBLE'
   AND fs.requests_used<fs.daily_request_budget
   AND fs.bytes_used<fs.daily_byte_budget
   AND fs.circuit_state IN ('CLOSED','HALF_OPEN')
"""

_ACQUIRED_LEASE_SQL = """
SELECT execution_lease_token
  FROM fetch_run
 WHERE id=:run_id AND source_id=:source_id AND status='RUNNING'
"""

_RENEW_EXECUTION_LEASE_SQL = """
UPDATE fetch_run
   SET heartbeat_at=:now,execution_lease_until=:until
 WHERE id=:run_id AND source_id=:source_id AND status='RUNNING'
   AND execution_lease_token=:lease_token
   AND execution_lease_until>=:now
RETURNING id
"""

_CANCEL_OWNED_EXECUTION_SQL = """
WITH cancelled AS (
  UPDATE fetch_run
     SET status='CANCELLED',completed_at=:now,failure_class=:reason,
         execution_lease_token=NULL,execution_lease_until=NULL
   WHERE id=:run_id AND source_id=:source_id AND status='RUNNING'
     AND execution_lease_token=:lease_token
   RETURNING schedule_id
)
UPDATE fetch_schedule schedule
   SET leased_until=NULL,lease_token=NULL,updated_at=:now
  FROM cancelled
 WHERE schedule.id=cancelled.schedule_id
RETURNING schedule.id
"""

_RECENT_HEALTH_SQL = """
SELECT h.discovered_count,h.transport_status,r.status AS run_status
  FROM source_health_snapshot h
  JOIN fetch_run r ON r.id=h.fetch_run_id
 WHERE h.source_id=:source_id
   AND r.run_origin='SCHEDULED'
   AND r.execution_domain='PRODUCTION'
 ORDER BY h.observed_at DESC,h.id DESC
 LIMIT 2
"""

_RECENT_SHAPE_SQL = """
SELECT discovery_body_bytes,structure_fingerprint_sha256
  FROM source_health_snapshot
 WHERE source_id=:source_id
   AND discovery_body_bytes IS NOT NULL
   AND structure_fingerprint_sha256 IS NOT NULL
 ORDER BY observed_at DESC,id DESC
LIMIT 1
"""

_RECENT_STREAM_HEALTH_SQL = """
SELECT h.discovered_count,h.transport_status,r.status AS run_status
  FROM source_health_snapshot h JOIN fetch_run r ON r.id=h.fetch_run_id
 WHERE h.source_stream_id=:source_stream_id
   AND r.run_origin='SCHEDULED' AND r.execution_domain='PRODUCTION'
 ORDER BY h.observed_at DESC,h.id DESC LIMIT 2
"""

_RECENT_STREAM_SHAPE_SQL = """
SELECT discovery_body_bytes,structure_fingerprint_sha256
  FROM source_health_snapshot
 WHERE source_stream_id=:source_stream_id
   AND discovery_body_bytes IS NOT NULL
   AND structure_fingerprint_sha256 IS NOT NULL
 ORDER BY observed_at DESC,id DESC LIMIT 1
"""

_RECORD_RAW_SQL = """
SELECT raw_object_id,capture_id FROM record_scheduled_source_raw(
  :raw_id,:capture_id,:source_id,:run_id,:content_sha256,:response_sha256,
  :object_key,:storage_etag,:byte_size,:declared_mime,:detected_mime,
  :security_status,:security_reason,:requested_url,:final_url,
  CAST(:redirect_chain AS jsonb),:http_status,:etag,:last_modified,:captured_at
)
"""

_RECORD_DOCUMENT_SQL = """
SELECT record_scheduled_source_document(
  :document_id,:version_id,:received_event_id,:security_event_id,:ready_event_id,
  :source_id,:run_id,:raw_object_id,:capture_id,:canonical_url,:document_kind,
  :content_hash,:filename,:title,:acquired_at
)
"""

_UPSERT_SUCCESSFUL_CHECKPOINT_SQL = """
INSERT INTO source_checkpoint (
  id,source_connector_id,cursor,etag,last_modified,last_success_at,
  consecutive_failures,circuit_open_until,updated_at
)
SELECT :checkpoint_id,r.source_connector_id,CAST(:cursor AS jsonb),:etag,
       :last_modified,:now,0,NULL,:now
  FROM fetch_run r
  JOIN source_connector connector
    ON connector.id=r.source_connector_id AND connector.source_id=r.source_id
 WHERE r.id=:run_id AND r.source_id=:source_id
   AND r.run_origin='SCHEDULED' AND r.execution_domain='PRODUCTION'
   AND r.status IN ('SUCCEEDED','NOT_MODIFIED')
ON CONFLICT (source_connector_id) DO UPDATE SET
  cursor=EXCLUDED.cursor,
  etag=EXCLUDED.etag,
  last_modified=EXCLUDED.last_modified,
  last_success_at=EXCLUDED.last_success_at,
  consecutive_failures=0,
  circuit_open_until=NULL,
  updated_at=EXCLUDED.updated_at
RETURNING source_connector_id
"""
