from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
import srbg_worker.app as worker
import srbg_worker.source_runtime as runtime
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.contracts import (
    DiscoveryRecord,
    ExecutionDomain,
    FetchResult,
    SourceAdapter,
    SourceCheckpoint,
)
from srbg_api.acquisition.http import FetchPolicy, HttpResponse
from srbg_api.acquisition.live import IndependentDohResolver
from srbg_api.config import Settings
from srbg_api.connectors.config import ConnectorKind
from srbg_api.connectors.parsers import ConnectorRequest, DeclarativeParser, RssAtomConnector
from srbg_api.document_vault.scanner import ClamAVScanner
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.scheduling.domain import HealthObservation
from srbg_worker.source_runtime import (
    LiveRuntimeTransport,
    PostgresRuntimeGateway,
    RawCapture,
    RawRegistrationError,
    RunOrigin,
    RuntimeBinding,
    RuntimeDocument,
    RuntimeExecutionError,
    RuntimeFetchExecutor,
    RuntimeRunResult,
    ScheduledDeclarativeSourceAdapter,
    discovery_structure_sha256,
    parse_runtime_document,
)

NOW = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
SOURCE_ID = UUID("019d0000-0000-7000-8000-000000000001")
RUN_ID = UUID("019d0000-0000-7000-8000-000000000002")


def test_controlled_run_uses_domain_rate_slot_while_normal_runtime_keeps_cycle_interval() -> None:
    assert runtime._runtime_minimum_interval_seconds(controlled_run_id=RUN_ID) == 60
    assert runtime._runtime_minimum_interval_seconds(controlled_run_id=None) == 900


class RecordingParser:
    kind = ConnectorKind.RSS_ATOM

    def __init__(self, events: list[str]) -> None:
        self._events = events

    def initial_requests(self, config: dict[str, object]) -> tuple[ConnectorRequest, ...]:
        del config
        return (
            ConnectorRequest(
                "https://source.example.test/feed.xml",
                "DISCOVERY",
                "application/xml",
            ),
        )

    def discover(
        self,
        fetched: FetchResult,
        config: dict[str, object],
    ) -> tuple[DiscoveryRecord, ...]:
        del fetched, config
        self._events.append("parse:discovery")
        return (
            DiscoveryRecord(
                external_id="notice-1",
                url="https://source.example.test/notices/1.html",
                title="安全通报",
                published_at=NOW,
                discovered_at=NOW,
            ),
        )

    def direct_record(
        self,
        request: ConnectorRequest,
        fetched: FetchResult,
    ) -> DiscoveryRecord:
        del request, fetched
        raise AssertionError("RSS discovery must not use the direct-record path")


class RecordingTransport:
    def __init__(self, results: list[FetchResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str]] = []
        self.checkpoints: list[SourceCheckpoint] = []

    async def fetch(
        self,
        url: str,
        *,
        checkpoint: SourceCheckpoint,
        accept: str,
        exact_redirect_host: str,
    ) -> FetchResult:
        self.checkpoints.append(checkpoint)
        self.calls.append((url, exact_redirect_host))
        result = self._results.pop(0)
        assert result.request_url == url
        assert accept
        return result

    async def close(self) -> None:
        return None


class RejectingTransport:
    calls = 0

    async def fetch(
        self,
        url: str,
        *,
        checkpoint: SourceCheckpoint,
        accept: str,
        exact_redirect_host: str,
    ) -> FetchResult:
        del url, checkpoint, accept, exact_redirect_host
        self.calls += 1
        raise AssertionError("an unauthorized run must not perform network I/O")

    async def close(self) -> None:
        return None


class WaitingTransport:
    def __init__(self) -> None:
        self.cancelled = False

    async def fetch(
        self,
        url: str,
        *,
        checkpoint: SourceCheckpoint,
        accept: str,
        exact_redirect_host: str,
    ) -> FetchResult:
        del url, checkpoint, accept, exact_redirect_host
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True
        raise AssertionError("cancelled source transport must not return")

    async def close(self) -> None:
        return None


class RecordingGateway:
    def __init__(self, binding: RuntimeBinding | None) -> None:
        self.binding = binding
        self.events: list[str] = []
        self.request_authorizations: list[str] = []
        self.outcomes: list[tuple[RuntimeRunResult, str | None]] = []
        self.outcome_checkpoints: list[SourceCheckpoint | None] = []

    async def acquire_execution(self, source_id: UUID, run_id: UUID) -> bool:
        assert (source_id, run_id) == (SOURCE_ID, RUN_ID)
        self.events.append("lease")
        return True

    async def cancel_ineligible(self, source_id: UUID, run_id: UUID) -> bool:
        assert (source_id, run_id) == (SOURCE_ID, RUN_ID)
        self.events.append("cancel")
        return True

    async def revalidate_binding(self, source_id: UUID, run_id: UUID) -> RuntimeBinding | None:
        assert (source_id, run_id) == (SOURCE_ID, RUN_ID)
        self.events.append("revalidate")
        return self.binding

    async def authorize_request(
        self,
        binding: RuntimeBinding,
        *,
        url: str,
    ) -> bool:
        assert binding == self.binding
        self.request_authorizations.append(url)
        self.events.append(f"authorize:{url}")
        return True

    async def record_response_bytes(
        self,
        binding: RuntimeBinding,
        *,
        url: str,
        response_bytes: int,
    ) -> None:
        assert binding == self.binding
        assert response_bytes >= 0
        self.events.append(f"response:{url}")

    async def persist_raw(
        self,
        binding: RuntimeBinding,
        *,
        fetched: FetchResult,
        purpose: str,
    ) -> RawCapture:
        assert binding == self.binding
        self.events.append(f"raw:{purpose}")
        content = fetched.content or b""
        return RawCapture(
            raw_object_id=uuid7(),
            capture_id=uuid7(),
            content_sha256="a" * 64,
            byte_size=len(content),
        )

    async def mark_discovery_parsed(self, capture: RawCapture) -> None:
        assert capture.byte_size >= 0
        self.events.append("discovery:parsed")

    async def record_parse_failure(self, capture: RawCapture, reason_code: str) -> None:
        assert capture.byte_size >= 0
        self.events.append(f"parse-failed:{reason_code}")

    async def persist_document(
        self,
        binding: RuntimeBinding,
        *,
        capture: RawCapture,
        record: DiscoveryRecord,
        document: RuntimeDocument,
    ) -> UUID:
        assert binding == self.binding
        assert capture.byte_size > 0
        assert record.url == document.canonical_url
        self.events.append("document:ready")
        return uuid7()

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
        assert (source_id, run_id) == (SOURCE_ID, RUN_ID)
        if binding is not None:
            assert binding.source_id == SOURCE_ID
        self.outcomes.append((result, failure_kind))
        self.outcome_checkpoints.append(next_checkpoint)
        self.events.append(f"outcome:{failure_kind or 'OK'}")
        return "SUCCEEDED" if failure_kind is None else "FAILED"

    async def close(self) -> None:
        self.events.append("closed")


def _binding() -> RuntimeBinding:
    return RuntimeBinding(
        source_id=SOURCE_ID,
        run_id=RUN_ID,
        origin=RunOrigin.SCHEDULED,
        execution_domain=ExecutionDomain.PRODUCTION,
        connector_kind=ConnectorKind.RSS_ATOM,
        connector_config={
            "allowed_hosts": ["source.example.test"],
            "feed_url": "https://source.example.test/feed.xml",
        },
        allowed_hosts=("source.example.test",),
        policy_version_id=uuid7(),
        connector_config_version_id=uuid7(),
        checkpoint=SourceCheckpoint(),
        freshness_slo_seconds=8 * 60 * 60,
    )


def _fetch(url: str, content: bytes, content_type: str) -> FetchResult:
    return FetchResult(
        url=url,
        status_code=200,
        content=content,
        content_type=content_type,
        etag=None,
        last_modified=None,
        fetched_at=NOW,
        request_url=url,
        response_sha256="b" * 64,
    )


@pytest.mark.asyncio
async def test_scheduled_runtime_uses_the_canonical_source_adapter_contract() -> None:
    binding = _binding()
    gateway = RecordingGateway(binding)
    parser = RecordingParser(gateway.events)
    transport = RecordingTransport(
        [
            replace(
                _fetch(
                    "https://source.example.test/feed.xml",
                    b"<rss><channel/></rss>",
                    "application/rss+xml",
                ),
                etag='"list-v1"',
            ),
            _fetch(
                "https://source.example.test/notices/1.html",
                b"<!doctype html><html><body>x</body></html>",
                "text/html",
            ),
        ]
    )
    adapter = ScheduledDeclarativeSourceAdapter(
        binding=binding,
        parser=cast(DeclarativeParser, parser),
        config=binding.connector_config,
        transport=transport,
        gateway=gateway,
        authority_heartbeat_seconds=30,
    )

    assert isinstance(adapter, SourceAdapter)

    batch = await adapter.discover(SourceCheckpoint())
    fetched = await adapter.fetch(batch.records[0], batch.next_checkpoint)
    capture = adapter.take_capture(fetched)

    assert len(batch.records) == 1
    assert capture.byte_size > 0
    assert gateway.request_authorizations == [
        "https://source.example.test/feed.xml",
        "https://source.example.test/notices/1.html",
    ]
    assert gateway.events.index("raw:DISCOVERY") < gateway.events.index("parse:discovery")
    assert batch.next_checkpoint.etag == '"list-v1"'
    assert transport.checkpoints[1] == SourceCheckpoint()


@pytest.mark.asyncio
async def test_scheduled_executor_revalidates_each_request_and_is_raw_first() -> None:
    gateway = RecordingGateway(_binding())
    parser = RecordingParser(gateway.events)
    transport = RecordingTransport(
        [
            _fetch(
                "https://source.example.test/feed.xml",
                b"<rss><channel/></rss>",
                "application/rss+xml",
            ),
            _fetch(
                "https://source.example.test/notices/1.html",
                b"<!doctype html><html><head><title>notice</title></head><body>x</body></html>",
                "text/html",
            ),
        ]
    )
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: cast(DeclarativeParser, parser)},
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.acquired is True
    assert result.cancelled is False
    assert result.discovered_count == 1
    assert result.fetched_count == 1
    assert result.failed_count == 0
    assert result.request_count == 2
    assert result.response_bytes == 97
    assert result.discovery_body_bytes == 21
    assert result.discovery_structure_sha256 is not None
    assert result.latest_published_at == NOW
    assert result.duplicate_ratio == 0.0
    assert gateway.request_authorizations == [
        "https://source.example.test/feed.xml",
        "https://source.example.test/notices/1.html",
    ]
    assert transport.calls == [
        ("https://source.example.test/feed.xml", "source.example.test"),
        ("https://source.example.test/notices/1.html", "source.example.test"),
    ]
    assert gateway.events.index("raw:DISCOVERY") < gateway.events.index("parse:discovery")
    assert gateway.events.index("raw:DOCUMENT") < gateway.events.index("document:ready")
    assert gateway.outcomes == [(result, None)]


@pytest.mark.asyncio
async def test_real_empty_rss_is_measured_as_zero_discovery_instead_of_parse_failure() -> None:
    binding = _binding()
    gateway = RecordingGateway(binding)
    transport = RecordingTransport(
        [
            _fetch(
                "https://source.example.test/feed.xml",
                b"<rss><channel/></rss>",
                "application/xml",
            )
        ]
    )
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: RssAtomConnector()},
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.discovered_count == 0
    assert result.failed_count == 0
    assert gateway.outcomes == [(result, None)]
    assert "discovery:parsed" in gateway.events


@pytest.mark.asyncio
async def test_successful_executor_carries_the_discovery_checkpoint_to_the_outcome() -> None:
    binding = replace(
        _binding(),
        checkpoint=SourceCheckpoint(
            cursor="page-1",
            etag='"old"',
            last_modified="Wed, 15 Jul 2026 00:00:00 GMT",
            consecutive_failures=2,
            circuit_open_until=NOW,
        ),
    )
    gateway = RecordingGateway(binding)
    transport = RecordingTransport(
        [
            FetchResult(
                url="https://source.example.test/feed.xml",
                status_code=200,
                content=b"<rss><channel/></rss>",
                content_type="application/xml",
                etag='"new"',
                last_modified="Thu, 16 Jul 2026 00:00:00 GMT",
                fetched_at=NOW,
                request_url="https://source.example.test/feed.xml",
                response_sha256="b" * 64,
            )
        ]
    )

    result = await RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: RssAtomConnector()},
    ).run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.failed_count == 0
    assert gateway.outcome_checkpoints == [
        SourceCheckpoint(
            cursor="page-1",
            etag='"new"',
            last_modified="Thu, 16 Jul 2026 00:00:00 GMT",
            consecutive_failures=0,
            circuit_open_until=None,
        )
    ]


@pytest.mark.asyncio
async def test_real_rss_missing_required_field_preserves_zero_coverage_signal() -> None:
    binding = _binding()
    gateway = RecordingGateway(binding)
    transport = RecordingTransport(
        [
            _fetch(
                "https://source.example.test/feed.xml",
                b"<rss><channel><item><link>/missing-title</link></item></channel></rss>",
                "application/xml",
            )
        ]
    )
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: RssAtomConnector()},
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.failed_count == 1
    assert result.required_fields_missing is True
    assert gateway.outcomes == [(result, "PARSE")]


@pytest.mark.asyncio
async def test_live_transport_counts_and_reserves_each_physical_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks: list[str] = []

    class PhysicalClient:
        def __init__(self, *_args: object, before_request: Any, **_kwargs: object) -> None:
            self.before_request = before_request

        async def get(
            self,
            url: str,
            *,
            checkpoint: SourceCheckpoint,
            accept: str,
        ) -> FetchResult:
            del checkpoint, accept
            await self.before_request(url)
            await self.before_request("https://source.example.test/redirect")
            return _fetch(url, b"ok", "text/plain")

    async def reserve(url: str) -> None:
        callbacks.append(url)

    monkeypatch.setattr(runtime, "ResilientHttpClient", PhysicalClient)
    binding = replace(
        _binding(),
        fetch_policy=FetchPolicy(
            allowed_hosts=("source.example.test",),
            timeout_seconds=5,
            max_attempts=2,
            base_backoff_seconds=1,
            rate_limit_per_minute=1,
            minimum_interval_seconds=1,
            circuit_failure_threshold=3,
            circuit_reset_seconds=30,
            max_redirects=2,
            user_agent="SRBGSourceAdapter/17",
        ),
    )
    transport = LiveRuntimeTransport(binding, before_request=reserve)

    await transport.fetch(
        "https://source.example.test/feed.xml",
        checkpoint=SourceCheckpoint(),
        accept="application/xml",
        exact_redirect_host="source.example.test",
    )

    assert callbacks == [
        "https://source.example.test/feed.xml",
        "https://source.example.test/redirect",
    ]
    assert transport.request_count == 2


@pytest.mark.asyncio
async def test_live_transport_pins_requests_to_the_injected_trusted_resolver() -> None:
    class TrustedResolver:
        async def resolve(
            self,
            hostname: str,
            *,
            timeout_seconds: float,
        ) -> tuple[str, ...]:
            assert hostname == "source.example.test"
            assert timeout_seconds == 5
            return ("93.184.216.34",)

    class RecordingTransport:
        def __init__(self) -> None:
            self.validated: list[frozenset[str]] = []

        async def request(
            self,
            url: str,
            *,
            headers: dict[str, str],
            timeout_seconds: float,
            max_response_bytes: int,
            validated_ips: frozenset[str],
        ) -> HttpResponse:
            del url, headers, timeout_seconds, max_response_bytes
            self.validated.append(validated_ips)
            return HttpResponse(
                status_code=200,
                headers={"content-type": "text/plain"},
                content=b"ok",
                peer_ip="93.184.216.34",
            )

        async def close(self) -> None:
            return None

    binding = replace(
        _binding(),
        fetch_policy=FetchPolicy(
            allowed_hosts=("source.example.test",),
            timeout_seconds=5,
            max_attempts=1,
            base_backoff_seconds=0,
            rate_limit_per_minute=1,
            minimum_interval_seconds=1,
            circuit_failure_threshold=3,
            circuit_reset_seconds=30,
            max_redirects=0,
            user_agent="SRBGSourceAdapter/17",
        ),
    )
    physical = RecordingTransport()
    transport = LiveRuntimeTransport(
        binding,
        resolver=TrustedResolver(),
        transport=physical,
    )

    fetched = await transport.fetch(
        "https://source.example.test/feed.xml",
        checkpoint=SourceCheckpoint(),
        accept="text/plain",
        exact_redirect_host="source.example.test",
    )

    assert fetched.content == b"ok"
    assert physical.validated == [frozenset({"93.184.216.34"})]


@pytest.mark.asyncio
async def test_revoked_after_lease_records_authorization_failure_without_network() -> None:
    gateway = RecordingGateway(None)
    transport = RejectingTransport()
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.acquired is True
    assert result.cancelled is True
    assert transport.calls == 0
    assert gateway.outcomes == [(result, "AUTHORIZATION")]


@pytest.mark.asyncio
async def test_long_rate_limit_wait_heartbeats_authority_and_cancels_on_revocation() -> None:
    class RevokedDuringWaitGateway(RecordingGateway):
        def __init__(self, binding: RuntimeBinding) -> None:
            super().__init__(binding)
            self.authorization_count = 0

        async def authorize_request(
            self,
            binding: RuntimeBinding,
            *,
            url: str,
        ) -> bool:
            del binding
            self.authorization_count += 1
            self.request_authorizations.append(url)
            return self.authorization_count == 1

    gateway = RevokedDuringWaitGateway(_binding())
    transport = WaitingTransport()
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: cast(DeclarativeParser, RecordingParser(gateway.events))},
        authority_heartbeat_seconds=0.001,
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert gateway.authorization_count >= 2
    assert transport.cancelled is True
    assert "raw:DISCOVERY" not in gateway.events
    assert result.failed_count == 1
    assert gateway.outcomes == [(result, "AUTHORIZATION")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("binding"),
    [
        replace(_binding(), origin=RunOrigin.REPLAY),
        replace(_binding(), origin=RunOrigin.BACKFILL),
        replace(_binding(), origin=RunOrigin.DRILL),
        replace(_binding(), execution_domain=ExecutionDomain.FIXTURE),
        replace(_binding(), execution_domain=ExecutionDomain.TRIAL),
    ],
)
async def test_non_original_or_non_production_run_cannot_enter_real_execution(
    binding: RuntimeBinding,
) -> None:
    gateway = RecordingGateway(binding)
    transport = RejectingTransport()
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert transport.calls == 0
    assert result.cancelled is True
    assert gateway.outcomes == [(result, "ORIGIN_ISOLATION")]


@pytest.mark.asyncio
async def test_cross_domain_redirect_response_is_persisted_but_never_parsed() -> None:
    binding = replace(
        _binding(),
        allowed_hosts=("source.example.test", "cdn.example.test"),
        connector_config={
            "allowed_hosts": ["source.example.test", "cdn.example.test"],
            "feed_url": "https://source.example.test/feed.xml",
        },
    )
    gateway = RecordingGateway(binding)
    transport = RecordingTransport(
        [
            FetchResult(
                url="https://cdn.example.test/feed.xml",
                status_code=200,
                content=b"<rss><channel/></rss>",
                content_type="application/rss+xml",
                etag=None,
                last_modified=None,
                fetched_at=NOW,
                request_url="https://source.example.test/feed.xml",
                redirect_chain=("https://cdn.example.test/feed.xml",),
                response_sha256="c" * 64,
            )
        ]
    )
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: cast(DeclarativeParser, RecordingParser(gateway.events))},
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert "raw:DISCOVERY" in gateway.events
    assert "parse:discovery" not in gateway.events
    assert "parse-failed:CROSS_DOMAIN_REDIRECT" in gateway.events
    assert result.failed_count == 1
    assert gateway.outcomes == [(result, "SECURITY")]


@pytest.mark.asyncio
async def test_raw_registration_failure_never_reaches_parser_or_document() -> None:
    class FailingRawGateway(RecordingGateway):
        async def persist_raw(
            self,
            binding: RuntimeBinding,
            *,
            fetched: FetchResult,
            purpose: str,
        ) -> RawCapture:
            del binding, fetched, purpose
            self.events.append("raw:registration-failed")
            raise OSError("object stored but raw metadata registration failed")

    gateway = FailingRawGateway(_binding())
    transport = RecordingTransport(
        [
            _fetch(
                "https://source.example.test/feed.xml",
                b"<rss><channel/></rss>",
                "application/rss+xml",
            )
        ]
    )
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: cast(DeclarativeParser, RecordingParser(gateway.events))},
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert "parse:discovery" not in gateway.events
    assert "document:ready" not in gateway.events
    assert result.failed_count == 1
    assert gateway.outcomes == [(result, "OBJECT_STORAGE")]


@pytest.mark.asyncio
async def test_database_raw_registration_failure_is_not_misreported_as_storage() -> None:
    class FailingRegistrationGateway(RecordingGateway):
        async def persist_raw(
            self,
            binding: RuntimeBinding,
            *,
            fetched: FetchResult,
            purpose: str,
        ) -> RawCapture:
            del binding, fetched, purpose
            raise RawRegistrationError("content-addressed object is already recoverable")

    gateway = FailingRegistrationGateway(_binding())
    transport = RecordingTransport(
        [
            _fetch(
                "https://source.example.test/feed.xml",
                b"<rss><channel/></rss>",
                "application/rss+xml",
            )
        ]
    )

    result = await RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: cast(DeclarativeParser, RecordingParser(gateway.events))},
    ).run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.failed_count == 1
    assert gateway.outcomes == [(result, "DATABASE")]


@pytest.mark.asyncio
async def test_document_registration_failure_is_reported_as_database_not_parse() -> None:
    class FailingDocumentGateway(RecordingGateway):
        async def persist_document(
            self,
            binding: RuntimeBinding,
            *,
            capture: RawCapture,
            record: DiscoveryRecord,
            document: RuntimeDocument,
        ) -> UUID:
            del binding, capture, record, document
            raise OSError("database unavailable")

    gateway = FailingDocumentGateway(_binding())
    transport = RecordingTransport(
        [
            _fetch(
                "https://source.example.test/feed.xml",
                b"<rss><channel/></rss>",
                "application/rss+xml",
            ),
            _fetch(
                "https://source.example.test/notices/1.html",
                b"<!doctype html><html><body>x</body></html>",
                "text/html",
            ),
        ]
    )

    result = await RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: cast(DeclarativeParser, RecordingParser(gateway.events))},
    ).run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.failed_count == 1
    assert gateway.outcomes == [(result, "DATABASE")]


@pytest.mark.asyncio
async def test_not_modified_response_is_raw_evidence_without_parser_pollution() -> None:
    gateway = RecordingGateway(_binding())
    parser = RecordingParser(gateway.events)
    transport = RecordingTransport(
        [
            FetchResult(
                url="https://source.example.test/feed.xml",
                status_code=304,
                content=None,
                content_type=None,
                etag='"v1"',
                last_modified=None,
                fetched_at=NOW,
                not_modified=True,
                request_url="https://source.example.test/feed.xml",
                response_sha256="d" * 64,
            )
        ]
    )
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: cast(DeclarativeParser, parser)},
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.failed_count == 0
    assert result.response_bytes == 0
    assert "raw:DISCOVERY" in gateway.events
    assert "parse:discovery" not in gateway.events
    assert gateway.outcomes == [(result, "NOT_MODIFIED")]
    assert gateway.outcome_checkpoints == [SourceCheckpoint(etag='"v1"')]


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_build_transport_when_lease_is_not_acquired() -> None:
    class DuplicateGateway(RecordingGateway):
        async def acquire_execution(self, source_id: UUID, run_id: UUID) -> bool:
            del source_id, run_id
            return False

    gateway = DuplicateGateway(_binding())
    transport_built = False

    def transport_factory(_binding: RuntimeBinding) -> RejectingTransport:
        nonlocal transport_built
        transport_built = True
        return RejectingTransport()

    result = await RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=transport_factory,
    ).run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.acquired is False
    assert transport_built is False
    assert gateway.outcomes == []


@pytest.mark.asyncio
async def test_unexpected_parser_error_still_records_a_content_free_final_outcome() -> None:
    class BrokenParser(RecordingParser):
        def initial_requests(self, config: dict[str, object]) -> tuple[ConnectorRequest, ...]:
            del config
            raise RuntimeError("untrusted page body must not be copied into the result")

    gateway = RecordingGateway(_binding())
    transport = RejectingTransport()
    executor = RuntimeFetchExecutor(
        gateway=gateway,
        transport_factory=lambda _binding: transport,
        parsers={ConnectorKind.RSS_ATOM: cast(DeclarativeParser, BrokenParser(gateway.events))},
    )

    result = await executor.run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert result.failed_count == 1
    assert gateway.outcomes == [(result, "PARSE")]
    assert "untrusted page body" not in repr(result)


@pytest.mark.asyncio
async def test_gateway_is_closed_even_if_transport_cleanup_fails() -> None:
    class CloseFailingTransport(RecordingTransport):
        async def close(self) -> None:
            raise OSError("transport cleanup failed")

    gateway = RecordingGateway(_binding())
    transport = CloseFailingTransport(
        [
            FetchResult(
                url="https://source.example.test/feed.xml",
                status_code=304,
                content=None,
                content_type=None,
                etag=None,
                last_modified=None,
                fetched_at=NOW,
                not_modified=True,
                request_url="https://source.example.test/feed.xml",
                response_sha256="e" * 64,
            )
        ]
    )

    with pytest.raises(OSError, match="cleanup"):
        await RuntimeFetchExecutor(
            gateway=gateway,
            transport_factory=lambda _binding: transport,
            parsers={
                ConnectorKind.RSS_ATOM: cast(DeclarativeParser, RecordingParser(gateway.events))
            },
        ).run(source_id=SOURCE_ID, run_id=RUN_ID)

    assert "closed" in gateway.events


def test_runtime_result_contains_counts_only_and_no_source_content() -> None:
    fields = RuntimeRunResult.__dataclass_fields__

    assert set(fields) == {
        "acquired",
        "cancelled",
        "discovered_count",
        "fetched_count",
        "failed_count",
        "request_count",
        "response_bytes",
        "discovery_body_bytes",
        "discovery_structure_sha256",
        "latest_published_at",
        "duplicate_ratio",
        "required_fields_missing",
    }


def test_runtime_pdf_parser_rejects_active_untrusted_content() -> None:
    record = DiscoveryRecord(
        external_id="unsafe-pdf",
        url="https://source.example.test/unsafe.pdf",
        title="unsafe",
        published_at=NOW,
        discovered_at=NOW,
    )
    fetched = _fetch(
        record.url,
        b"%PDF-1.4\n1 0 obj<</JavaScript 2 0 R>>endobj\n%%EOF",
        "application/pdf",
    )

    with pytest.raises(ValueError):
        parse_runtime_document(record, fetched, max_bytes=1024 * 1024)


def test_runtime_xml_parser_rejects_document_entities() -> None:
    record = DiscoveryRecord(
        external_id="unsafe-xml",
        url="https://source.example.test/unsafe.xml",
        title="unsafe",
        published_at=NOW,
        discovered_at=NOW,
    )
    fetched = _fetch(
        record.url,
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>',
        "application/xml",
    )

    with pytest.raises(ValueError):
        parse_runtime_document(record, fetched, max_bytes=1024 * 1024)


def test_celery_source_task_runs_the_runtime_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: dict[str, object] = {}

    class FakeGateway:
        def __init__(self) -> None:
            self.reservations: list[tuple[RuntimeBinding, str]] = []
            self.responses: list[tuple[RuntimeBinding, str, int]] = []

        async def reserve_request(self, binding: RuntimeBinding, *, url: str) -> None:
            self.reservations.append((binding, url))

        async def record_response_bytes(
            self,
            binding: RuntimeBinding,
            *,
            url: str,
            response_bytes: int,
        ) -> None:
            self.responses.append((binding, url, response_bytes))

    class FakeLiveTransport:
        def __init__(
            self,
            binding: RuntimeBinding,
            *,
            resolver: Any,
            before_request: Any,
            after_response: Any,
        ) -> None:
            self.binding = binding
            self.resolver = resolver
            self.before_request = before_request
            self.after_response = after_response

    class FakeExecutor:
        def __init__(self, **kwargs: object) -> None:
            constructed.update(kwargs)

        async def run(self, *, source_id: UUID, run_id: UUID) -> RuntimeRunResult:
            assert (source_id, run_id) == (SOURCE_ID, RUN_ID)
            return RuntimeRunResult(True, False, 2, 1, 1, 3, 4096)

    gateway = FakeGateway()
    monkeypatch.setattr(worker, "PostgresRuntimeGateway", lambda _settings: gateway)
    monkeypatch.setattr(worker, "RuntimeFetchExecutor", FakeExecutor)
    monkeypatch.setattr(worker, "LiveRuntimeTransport", FakeLiveTransport)

    result = worker.celery_app.tasks["srbg.source.fetch"].run(
        source_id=str(SOURCE_ID),
        run_id=str(RUN_ID),
    )

    assert constructed["gateway"] is gateway
    factory = cast(Any, constructed["transport_factory"])
    binding = _binding()
    live_transport = factory(binding)
    asyncio.run(live_transport.before_request("https://source.example.test/feed.xml"))
    asyncio.run(
        live_transport.after_response("https://source.example.test/feed.xml", 4096)
    )
    assert live_transport.binding == binding
    assert isinstance(live_transport.resolver, IndependentDohResolver)
    assert gateway.reservations == [(binding, "https://source.example.test/feed.xml")]
    assert gateway.responses == [
        (binding, "https://source.example.test/feed.xml", 4096)
    ]
    assert result == {
        "acquired": True,
        "cancelled": False,
        "source_id": str(SOURCE_ID),
        "run_id": str(RUN_ID),
        "discovered_count": 2,
        "fetched_count": 1,
        "failed_count": 1,
        "request_count": 3,
        "response_bytes": 4096,
    }


class _DatabaseResult:
    def __init__(self, row: dict[str, object]) -> None:
        self._row = row

    def mappings(self) -> _DatabaseResult:
        return self

    def one(self) -> dict[str, object]:
        return self._row

    def one_or_none(self) -> dict[str, object] | None:
        return self._row


class _DatabaseConnection:
    def __init__(
        self,
        events: list[str],
        row: dict[str, object],
        *,
        fail: bool = False,
    ) -> None:
        self._events = events
        self._row = row
        self._fail = fail
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> _DatabaseResult:
        self._events.append("db")
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        if self._fail:
            raise RuntimeError("database unavailable")
        return _DatabaseResult(self._row)


class _DatabaseContext:
    def __init__(self, connection: _DatabaseConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _DatabaseConnection:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        del args


class _DatabaseEngine:
    def __init__(self, connection: _DatabaseConnection) -> None:
        self._connection = connection

    def begin(self) -> _DatabaseContext:
        return _DatabaseContext(self._connection)

    def connect(self) -> _DatabaseContext:
        return _DatabaseContext(self._connection)

    async def dispose(self) -> None:
        return None


class _ObjectStore:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        assert key.startswith("sha256/")
        assert content and content_type == "application/octet-stream"
        self._events.append("s3")
        return "immutable-etag"


class _Scanner:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def scan(self, content: bytes) -> None:
        assert content
        self._events.append("scan")


@pytest.mark.asyncio
async def test_postgres_gateway_stores_scans_then_registers_raw_capture() -> None:
    events: list[str] = []
    raw_id = uuid7()
    capture_id = uuid7()
    connection = _DatabaseConnection(
        events,
        {"raw_object_id": raw_id, "capture_id": capture_id},
    )
    gateway = PostgresRuntimeGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore(events)),
        malware_scanner=cast(ClamAVScanner, _Scanner(events)),
    )
    fetched = _fetch(
        "https://source.example.test/feed.xml",
        b"<rss><channel/></rss>",
        "application/rss+xml",
    )

    capture = await gateway.persist_raw(_binding(), fetched=fetched, purpose="DISCOVERY")

    assert events == ["s3", "scan", "db"]
    assert capture.raw_object_id == raw_id
    assert capture.capture_id == capture_id
    assert "record_scheduled_source_raw" in connection.statements[0]
    assert connection.parameters[0]["security_status"] == "CLEAN"
    assert connection.parameters[0]["run_id"] == RUN_ID
    assert "<rss" not in repr(connection.parameters[0])


@pytest.mark.asyncio
async def test_s3_orphan_after_database_failure_is_content_addressed_and_retryable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[str] = []
    connection = _DatabaseConnection(events, {}, fail=True)
    gateway = PostgresRuntimeGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore(events)),
        malware_scanner=cast(ClamAVScanner, _Scanner(events)),
    )
    fetched = _fetch(
        "https://source.example.test/feed.xml",
        b"<rss><channel/></rss>",
        "application/rss+xml",
    )

    with pytest.raises(OSError, match="after object persistence"):
        await gateway.persist_raw(_binding(), fetched=fetched, purpose="DISCOVERY")

    assert events == ["s3", "scan", "db"]
    assert "scheduled_raw_registration_failed" in caplog.text
    assert "<rss" not in caplog.text


@pytest.mark.asyncio
async def test_postgres_binding_requires_personal_stream_authority() -> None:
    events: list[str] = []
    policy_id = uuid7()
    config_id = uuid7()
    connection = _DatabaseConnection(
        events,
        {
            "run_origin": "SCHEDULED",
            "execution_domain": "PRODUCTION",
            "policy_version_id": None,
            "connector_config_version_id": None,
            "connector_type": "RSS_ATOM",
            "config_document": {
                "allowed_hosts": ["source.example.test"],
                "feed_url": "https://source.example.test/feed.xml",
            },
            "config_allowed_hosts": ["source.example.test"],
            "policy_document": None,
            "authority_mode": "PERSONAL_STREAM",
            "source_stream_id": policy_id,
            "stream_config_version_id": config_id,
            "max_attempts": 3,
            "backoff_base_seconds": 30,
            "backoff_cap_seconds": 1800,
            "freshness_slo_seconds": 8 * 60 * 60,
            "checkpoint_cursor": None,
            "checkpoint_etag": None,
            "checkpoint_last_modified": None,
            "checkpoint_consecutive_failures": 2,
            "checkpoint_circuit_open_until": NOW,
        },
    )
    gateway = PostgresRuntimeGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore(events)),
        malware_scanner=cast(ClamAVScanner, _Scanner(events)),
    )

    binding = await gateway.revalidate_binding(SOURCE_ID, RUN_ID)

    assert binding is not None
    assert binding.origin is RunOrigin.SCHEDULED
    assert binding.execution_domain is ExecutionDomain.PRODUCTION
    assert binding.freshness_slo_seconds == 8 * 60 * 60
    assert binding.fetch_policy is not None
    assert binding.source_stream_id == policy_id
    assert binding.stream_config_version_id == config_id
    assert binding.checkpoint == SourceCheckpoint(
        cursor=None,
        etag=None,
        last_modified=None,
        consecutive_failures=2,
        circuit_open_until=NOW,
    )
    statement = connection.statements[0]
    assert "r.run_origin" in statement
    assert "PRODUCTION_APPROVAL" not in statement
    assert "source_policy_version" not in statement
    assert "JOIN connector_config_version" not in statement
    assert "r.status='RUNNING'" in statement
    assert "fs.authority_mode='PERSONAL_STREAM'" in statement
    assert "source_row.desired_enabled=true" in statement
    assert "source_row.manual_disabled_at IS NULL" in statement
    assert "fs.freshness_slo_seconds" in statement
    assert (
        "fs.interval_seconds=(p.document #>> '{fetch,minimum_interval_seconds}')"
        not in statement
    )


def test_discovery_structure_fingerprint_ignores_text_but_detects_dom_changes() -> None:
    first = b"<html><body><article><a>first</a></article></body></html>"
    text_only = b"<html><body><article><a>second</a></article></body></html>"
    changed = b"<html><body><main><a>second</a></main></body></html>"
    selector_before = (
        b'<html><body><article class="old-list"><a>second</a></article></body></html>'
    )
    selector_after = (
        b'<html><body><article class="new-list"><a>second</a></article></body></html>'
    )

    assert discovery_structure_sha256(first, "text/html") == discovery_structure_sha256(
        text_only, "text/html"
    )
    assert discovery_structure_sha256(first, "text/html") != discovery_structure_sha256(
        changed, "text/html"
    )
    assert discovery_structure_sha256(
        selector_before, "text/html"
    ) != discovery_structure_sha256(selector_after, "text/html")


def test_runtime_health_shape_is_content_free_and_carried_to_outcome() -> None:
    result = RuntimeRunResult(
        acquired=True,
        cancelled=False,
        discovered_count=2,
        fetched_count=2,
        failed_count=0,
        request_count=3,
        response_bytes=1024,
        discovery_body_bytes=512,
        discovery_structure_sha256="a" * 64,
        latest_published_at=NOW,
        duplicate_ratio=0.0,
    )

    assert result.discovery_body_bytes == 512
    assert result.discovery_structure_sha256 == "a" * 64
    assert "<html" not in repr(result)


@pytest.mark.asyncio
async def test_postgres_authorization_renews_the_owned_lease_before_revalidation() -> None:
    events: list[str] = []
    policy_id = uuid7()
    config_id = uuid7()
    lease_token = uuid7()
    connection = _DatabaseConnection(
        events,
        {
            "id": RUN_ID,
            "run_origin": "SCHEDULED",
            "execution_domain": "PRODUCTION",
            "policy_version_id": policy_id,
            "connector_config_version_id": config_id,
            "connector_type": "RSS_ATOM",
            "config_document": {
                "allowed_hosts": ["source.example.test"],
                "feed_url": "https://source.example.test/feed.xml",
            },
            "config_allowed_hosts": ["source.example.test"],
            "policy_document": {
                "fetch": {
                    "allowed_domains": ["source.example.test"],
                    "minimum_interval_seconds": 900,
                    "rate_limit_per_minute": 1,
                    "user_agent": "SRBGSourceAdapter/17",
                },
                "slo": {"target_minutes": 480},
            },
            "max_attempts": 3,
            "backoff_base_seconds": 30,
            "backoff_cap_seconds": 1800,
            "freshness_slo_seconds": 8 * 60 * 60,
        },
    )
    gateway = PostgresRuntimeGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore(events)),
        malware_scanner=cast(ClamAVScanner, _Scanner(events)),
    )
    gateway._execution_lease_token = lease_token
    binding = replace(
        _binding(),
        policy_version_id=policy_id,
        connector_config_version_id=config_id,
    )

    authorized = await gateway.authorize_request(
        binding,
        url="https://source.example.test/feed.xml",
    )

    assert authorized is True
    assert len(connection.statements) == 2
    assert "UPDATE fetch_run" in connection.statements[0]
    assert "execution_lease_token=:lease_token" in connection.statements[0]
    assert connection.parameters[0]["lease_token"] == lease_token
    assert "SELECT r.run_origin" in connection.statements[1]


@pytest.mark.asyncio
async def test_gateway_revalidates_authority_then_atomically_reserves_request_budget() -> None:
    class BudgetScheduling:
        def __init__(self) -> None:
            self.calls: list[tuple[UUID, UUID]] = []
            self.available = True

        async def reserve_request(
            self,
            *,
            source_id: UUID,
            run_id: UUID,
        ) -> bool:
            self.calls.append((source_id, run_id))
            return self.available

    class ReservationGateway(PostgresRuntimeGateway):
        def __init__(self, scheduling: BudgetScheduling) -> None:
            self._scheduling = cast(Any, scheduling)
            self.authorized = True
            self.authorized_urls: list[str] = []

        async def authorize_request(self, binding: RuntimeBinding, *, url: str) -> bool:
            assert binding.source_id == SOURCE_ID
            self.authorized_urls.append(url)
            return self.authorized

    scheduling = BudgetScheduling()
    gateway = ReservationGateway(scheduling)
    binding = _binding()

    await gateway.reserve_request(binding, url="https://source.example.test/feed.xml")
    scheduling.available = False
    with pytest.raises(RuntimeExecutionError, match="REQUEST_BUDGET_EXHAUSTED"):
        await gateway.reserve_request(binding, url="https://source.example.test/detail")
    gateway.authorized = False
    with pytest.raises(RuntimeExecutionError, match="AUTHORIZATION_REVOKED"):
        await gateway.reserve_request(binding, url="https://source.example.test/revoked")

    assert gateway.authorized_urls == [
        "https://source.example.test/feed.xml",
        "https://source.example.test/detail",
        "https://source.example.test/revoked",
    ]
    assert scheduling.calls == [(SOURCE_ID, RUN_ID), (SOURCE_ID, RUN_ID)]


class _RecentHealthResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> _RecentHealthResult:
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows

    def one_or_none(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None


class _RecentHealthConnection:
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        shape: dict[str, object] | None = None,
    ) -> None:
        self._rows = rows
        self._shape = shape
        self.statements: list[str] = []

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> _RecentHealthResult:
        assert parameters == {"source_id": SOURCE_ID}
        self.statements.append(str(statement))
        if "structure_fingerprint_sha256" in str(statement):
            return _RecentHealthResult([] if self._shape is None else [self._shape])
        return _RecentHealthResult(self._rows)


class _OutcomeScheduling:
    def __init__(self, terminal: str = "SUCCEEDED") -> None:
        self.observations: list[HealthObservation] = []
        self.request_counts: list[int] = []
        self.terminal = terminal

    async def record_outcome(self, **kwargs: object) -> str:
        observation = kwargs["observation"]
        assert isinstance(observation, HealthObservation)
        self.observations.append(observation)
        request_count = kwargs["request_count"]
        assert isinstance(request_count, int)
        self.request_counts.append(request_count)
        return self.terminal

    async def close(self) -> None:
        return None


class _AcquiringScheduling:
    async def acquire_execution(self, *, source_id: UUID, run_id: UUID) -> bool:
        assert (source_id, run_id) == (SOURCE_ID, RUN_ID)
        return True

    async def close(self) -> None:
        return None


class _CheckpointOutcomeGateway(PostgresRuntimeGateway):
    async def _renew_execution_lease(self, binding: RuntimeBinding) -> bool:
        assert binding.source_id == SOURCE_ID
        return True

    async def _zero_discovery_streak(
        self,
        source_id: UUID,
        *,
        result: RuntimeRunResult,
        failure_kind: str | None,
    ) -> int:
        del result, failure_kind
        assert source_id == SOURCE_ID
        return 0

    async def _previous_discovery_shape(
        self,
        source_id: UUID,
    ) -> tuple[int | None, str | None]:
        assert source_id == SOURCE_ID
        return None, None


@pytest.mark.asyncio
async def test_successful_postgres_outcome_advances_the_run_connector_checkpoint() -> None:
    connector_id = UUID("019d0000-0000-7000-8000-000000000003")
    events: list[str] = []
    connection = _DatabaseConnection(
        events,
        {"source_connector_id": connector_id},
    )
    gateway = _CheckpointOutcomeGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore(events)),
        malware_scanner=cast(ClamAVScanner, _Scanner(events)),
    )
    gateway._scheduling = cast(Any, _OutcomeScheduling("SUCCEEDED"))
    checkpoint = SourceCheckpoint(
        cursor="page-8",
        etag='"new"',
        last_modified="Thu, 16 Jul 2026 00:00:00 GMT",
    )

    terminal = await gateway.record_outcome(
        SOURCE_ID,
        RUN_ID,
        _binding(),
        result=RuntimeRunResult(True, False, 0, 0, 0, 1, 128),
        failure_kind=None,
        next_checkpoint=checkpoint,
    )

    assert terminal == "SUCCEEDED"
    assert len(connection.statements) == 1
    assert "INSERT INTO source_checkpoint" in connection.statements[0]
    assert "r.source_connector_id" in connection.statements[0]
    assert "r.status IN ('SUCCEEDED','NOT_MODIFIED')" in connection.statements[0]
    assert connection.parameters[0]["source_id"] == SOURCE_ID
    assert connection.parameters[0]["run_id"] == RUN_ID
    assert connection.parameters[0]["cursor"] == '{"value":"page-8"}'
    assert connection.parameters[0]["etag"] == '"new"'
    assert connection.parameters[0]["last_modified"] == "Thu, 16 Jul 2026 00:00:00 GMT"


@pytest.mark.asyncio
async def test_failed_postgres_outcome_never_advances_the_source_checkpoint() -> None:
    events: list[str] = []
    connection = _DatabaseConnection(events, {})
    gateway = _CheckpointOutcomeGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore(events)),
        malware_scanner=cast(ClamAVScanner, _Scanner(events)),
    )
    gateway._scheduling = cast(Any, _OutcomeScheduling("FAILED"))

    terminal = await gateway.record_outcome(
        SOURCE_ID,
        RUN_ID,
        _binding(),
        result=RuntimeRunResult(True, False, 0, 0, 1, 1, 128),
        failure_kind="PARSE",
        next_checkpoint=SourceCheckpoint(cursor="must-not-advance", etag='"new"'),
    )

    assert terminal == "FAILED"
    assert connection.statements == []


@pytest.mark.asyncio
async def test_postgres_gateway_captures_the_authoritative_acquired_lease_token() -> None:
    lease_token = uuid7()
    events: list[str] = []
    connection = _DatabaseConnection(
        events,
        {"execution_lease_token": lease_token},
    )
    gateway = PostgresRuntimeGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore(events)),
        malware_scanner=cast(ClamAVScanner, _Scanner(events)),
    )
    gateway._scheduling = cast(Any, _AcquiringScheduling())

    acquired = await gateway.acquire_execution(SOURCE_ID, RUN_ID)

    assert acquired is True
    assert gateway._execution_lease_token == lease_token
    assert "execution_lease_token" in connection.statements[0]
    assert connection.parameters[0] == {"source_id": SOURCE_ID, "run_id": RUN_ID}


@pytest.mark.asyncio
async def test_zero_discovery_streak_uses_only_prior_real_scheduled_successes() -> None:
    class StreakGateway(PostgresRuntimeGateway):
        async def _renew_execution_lease(self, binding: RuntimeBinding) -> bool:
            assert binding.source_id == SOURCE_ID
            return True

    connection = _RecentHealthConnection(
        [
            {
                "discovered_count": 0,
                "transport_status": "SUCCEEDED",
                "run_status": "SUCCEEDED",
            },
            {
                "discovered_count": 0,
                "transport_status": "SUCCEEDED",
                "run_status": "SUCCEEDED",
            },
        ]
    )
    gateway = StreakGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(cast(Any, connection))),
        object_store=cast(S3ObjectStore, _ObjectStore([])),
        malware_scanner=cast(ClamAVScanner, _Scanner([])),
    )
    scheduling = _OutcomeScheduling()
    gateway._scheduling = cast(Any, scheduling)

    await gateway.record_outcome(
        SOURCE_ID,
        RUN_ID,
        _binding(),
        result=RuntimeRunResult(True, False, 0, 0, 0, 1, 128),
        failure_kind=None,
    )

    observation = scheduling.observations[0]
    assert scheduling.request_counts == [1]
    assert observation.consecutive_zero_discovery == 3
    assert "r.run_origin='SCHEDULED'" in connection.statements[0]
    assert "r.execution_domain='PRODUCTION'" in connection.statements[0]
    assert "LIMIT 2" in connection.statements[0]


@pytest.mark.asyncio
async def test_runtime_compares_consecutive_discovery_shapes_without_storing_content() -> None:
    class ShapeGateway(PostgresRuntimeGateway):
        async def _renew_execution_lease(self, binding: RuntimeBinding) -> bool:
            assert binding.source_id == SOURCE_ID
            return True

    connection = _RecentHealthConnection(
        [],
        shape={
            "discovery_body_bytes": 256,
            "structure_fingerprint_sha256": "a" * 64,
        },
    )
    gateway = ShapeGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(cast(Any, connection))),
        object_store=cast(S3ObjectStore, _ObjectStore([])),
        malware_scanner=cast(ClamAVScanner, _Scanner([])),
    )
    scheduling = _OutcomeScheduling()
    gateway._scheduling = cast(Any, scheduling)

    await gateway.record_outcome(
        SOURCE_ID,
        RUN_ID,
        _binding(),
        result=RuntimeRunResult(
            True,
            False,
            2,
            2,
            0,
            1,
            512,
            discovery_body_bytes=512,
            discovery_structure_sha256="b" * 64,
            latest_published_at=NOW,
            duplicate_ratio=0.5,
        ),
        failure_kind=None,
    )

    observation = scheduling.observations[0]
    assert observation.body_length_ratio == 2.0
    assert observation.dom_fingerprint_changed is True
    assert observation.discovery_body_bytes == 512
    assert observation.structure_fingerprint_sha256 == "b" * 64
    assert observation.latest_published_at == NOW
    assert observation.duplicate_ratio == 0.5
    assert "<html" not in repr(observation)


@pytest.mark.asyncio
async def test_required_field_parse_failure_is_recorded_as_zero_field_coverage() -> None:
    class RequiredFieldGateway(PostgresRuntimeGateway):
        async def _renew_execution_lease(self, binding: RuntimeBinding) -> bool:
            assert binding.source_id == SOURCE_ID
            return True

    connection = _RecentHealthConnection([])
    gateway = RequiredFieldGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(cast(Any, connection))),
        object_store=cast(S3ObjectStore, _ObjectStore([])),
        malware_scanner=cast(ClamAVScanner, _Scanner([])),
    )
    scheduling = _OutcomeScheduling()
    gateway._scheduling = cast(Any, scheduling)

    await gateway.record_outcome(
        SOURCE_ID,
        RUN_ID,
        _binding(),
        result=RuntimeRunResult(
            True,
            False,
            0,
            0,
            1,
            1,
            128,
            required_fields_missing=True,
        ),
        failure_kind="PARSE",
    )

    assert scheduling.observations[0].required_field_ratio == 0.0


def test_round17_migration_exposes_the_worker_runtime_function_abi() -> None:
    migration = Path("apps/api/migrations/versions/0017b_round17_pilot.py").read_text(
        encoding="utf-8"
    )
    raw_signature = (
        "record_scheduled_source_raw(uuid,uuid,uuid,uuid,text,text,text,text,bigint,"
        "text,text,text,text,text,text,jsonb,integer,text,text,timestamptz)"
    )
    document_signature = (
        "record_scheduled_source_document(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,"
        "uuid,text,text,text,text,text,timestamptz)"
    )

    assert raw_signature in migration
    assert document_signature in migration
    assert "RETURNS TABLE(raw_object_id uuid,capture_id uuid)" in migration
    assert "p_response_sha256 text" in migration
    assert "p_security_status text" in migration
    assert "p_raw_object_id uuid" in migration
    assert "p_content_hash text" in migration
    raw_function = migration.split("CREATE FUNCTION record_scheduled_source_raw(", 1)[1].split(
        "CREATE FUNCTION record_scheduled_source_document(", 1
    )[0]
    assert "run.status='RUNNING'" in raw_function
    assert "run.execution_lease_until>=p_captured_at" in raw_function
    assert "decision.trial_run_id=source_row.current_trial_run_id" in raw_function


def test_source_fetch_operations_replay_is_retired() -> None:
    assert not hasattr(worker, "execute_source_fetch_replay")
    assert not hasattr(worker, "_execute_replay_kind")
    assert "srbg.operations.replay" not in worker.celery_app.tasks
