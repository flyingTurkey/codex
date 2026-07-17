from __future__ import annotations

import inspect
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
import srbg_worker.app as worker
import srbg_worker.source_qualification as qualification
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.http import HttpResponse
from srbg_api.config import Settings
from srbg_api.document_vault.scanner import ClamAVScanner
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.operations.failures import TASK_POLICIES
from srbg_api.operations.replays import ClaimedReplay, ReplayTaskRedelivery
from srbg_contracts import QualificationCheckView
from srbg_worker.source_qualification import (
    ActivationDispatch,
    ActivationOutboxExecutor,
    CanonicalTargetProvider,
    EvidenceReview,
    PostgresActivationOutboxGateway,
    PostgresQualificationGateway,
    ProviderHit,
    QualificationBinding,
    QualificationExecutor,
    QualificationSummary,
    ResilientTargetProbe,
    SafeTargetCapture,
    SafeTargetEvidence,
)

NOW = datetime(2026, 7, 17, 0, 0, tzinfo=UTC)
QUALIFICATION_RUN_ID = UUID("019d1000-0000-7000-8000-000000000001")
CAMPAIGN_ID = UUID("019d1000-0000-7000-8000-000000000002")
CANDIDATE_ID = UUID("019d1000-0000-7000-8000-000000000003")
LEASE_TOKEN = UUID("019d1000-0000-7000-8000-000000000004")
OUTBOX_ID = UUID("019d1000-0000-7000-8000-000000000005")
SOURCE_ID = UUID("019d1000-0000-7000-8000-000000000006")
FETCH_RUN_ID = UUID("019d1000-0000-7000-8000-000000000007")
PREPARED_SOURCE_ID = UUID("019d1000-0000-7000-8000-000000000009")
PREPARED_POLICY_ID = UUID("019d1000-0000-7000-8000-000000000010")
PREPARED_CONFIG_ID = UUID("019d1000-0000-7000-8000-000000000011")
PREPARED_TRIAL_ID = UUID("019d1000-0000-7000-8000-000000000012")


def _binding() -> QualificationBinding:
    return QualificationBinding(
        qualification_run_id=QUALIFICATION_RUN_ID,
        candidate_id=CANDIDATE_ID,
        campaign_id=CAMPAIGN_ID,
        canonical_url="https://jtt.sc.gov.cn/",
        authorization_boundary="jtt.sc.gov.cn",
        rule_version="source-qualification-v1",
        material_fingerprint="a" * 64,
        lease_token=LEASE_TOKEN,
        prepared_source_id=PREPARED_SOURCE_ID,
        prepared_policy_version_id=PREPARED_POLICY_ID,
        prepared_connector_config_version_id=PREPARED_CONFIG_ID,
        prepared_trial_run_id=PREPARED_TRIAL_ID,
    )


def _target_evidence(url: str = "https://jtt.sc.gov.cn/notice/1.html") -> SafeTargetEvidence:
    return SafeTargetEvidence(
        capture=SafeTargetCapture(
            requested_url=url,
            final_url=url,
            content=b"<html><body>target evidence</body></html>",
            content_type="text/html",
            status_code=200,
            response_sha256="b" * 64,
            captured_at=NOW,
        ),
        resolved_addresses_public=True,
        redirect_boundary_valid=True,
        robots=EvidenceReview.ALLOWED,
        terms=EvidenceReview.ALLOWED,
        copyright=EvidenceReview.ALLOWED,
        requires_login=False,
        captcha_detected=False,
        paywall_detected=False,
        connector_valid=True,
        relevant=True,
    )


class RecordingQualificationGateway:
    def __init__(self, binding: QualificationBinding | None = None) -> None:
        self.binding = _binding() if binding is None else binding
        self.events: list[str] = []
        self.persisted: list[SafeTargetEvidence] = []
        self.summary: QualificationSummary | None = None
        self.failure_codes: list[str] = []

    async def acquire(
        self,
        qualification_run_id: UUID,
    ) -> QualificationBinding | None:
        assert qualification_run_id == QUALIFICATION_RUN_ID
        self.events.append("lease")
        return self.binding

    async def record_target_evidence(
        self,
        binding: QualificationBinding,
        evidence: SafeTargetEvidence,
    ) -> UUID:
        assert binding == self.binding
        self.events.append("gateway:target-evidence")
        self.persisted.append(evidence)
        return UUID("019d1000-0000-7000-8000-000000000008")

    async def complete(
        self,
        binding: QualificationBinding,
        summary: QualificationSummary,
    ) -> str:
        assert binding == self.binding
        self.events.append("complete")
        self.summary = summary
        return "SUCCEEDED"

    async def fail(self, binding: QualificationBinding, *, reason_code: str) -> str:
        assert binding == self.binding
        self.events.append("failed")
        self.failure_codes.append(reason_code)
        return "FAILED"

    async def close(self) -> None:
        self.events.append("closed")


class TransientProvider:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.response_body = "provider-response-must-remain-transient"
        self.query = "四川 公路 安全 通报 secret-query"

    async def discover_targets(
        self,
        binding: QualificationBinding,
    ) -> tuple[ProviderHit, ...]:
        assert binding.campaign_id == CAMPAIGN_ID
        self.events.append("provider")
        return (
            ProviderHit(
                url="https://jtt.sc.gov.cn/notice/1.html",
                title="provider-title-must-not-persist",
                snippet="provider-snippet-must-not-persist",
            ),
        )


class RecordingTargetProbe:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.urls: list[str] = []

    async def probe(self, url: str, *, authorization_boundary: str) -> SafeTargetEvidence:
        assert authorization_boundary == "jtt.sc.gov.cn"
        self.events.append("probe:target")
        self.urls.append(url)
        return _target_evidence(url)


@pytest.mark.asyncio
async def test_canonical_target_provider_starts_from_database_candidate_url() -> None:
    binding = replace(_binding(), campaign_id=None)

    hits = await CanonicalTargetProvider().discover_targets(binding)

    assert hits == (ProviderHit(url=binding.canonical_url),)


class _ProbeResolver:
    async def resolve(self, hostname: str, *, timeout_seconds: float) -> tuple[str, ...]:
        assert hostname == "jtt.sc.gov.cn"
        assert timeout_seconds == 1.25
        return ("93.184.216.34",)


class _ProbeTransport:
    def __init__(
        self,
        content: bytes = (
            b'<html><body><a href="/notices/1">engineering bulletin</a></body></html>'
        ),
        *,
        robots_status: int = 200,
        robots_content: bytes = b"User-agent: *\nAllow: /\n",
    ) -> None:
        self.requests: list[dict[str, object]] = []
        self.closed = False
        self.content = content
        self.robots_status = robots_status
        self.robots_content = robots_content

    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse:
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
                "validated_ips": validated_ips,
            }
        )
        is_robots = url == "https://jtt.sc.gov.cn/robots.txt"
        return HttpResponse(
            status_code=self.robots_status if is_robots else 200,
            headers={"content-type": "text/plain" if is_robots else "text/html; charset=utf-8"},
            content=self.robots_content if is_robots else self.content,
            peer_ip="93.184.216.34",
        )

    async def close(self) -> None:
        self.closed = True


class _ProbeClock:
    def monotonic(self) -> float:
        return 1.0

    async def sleep(self, seconds: float) -> None:
        raise AssertionError(f"single-attempt qualification probe must not sleep: {seconds}")

    def now(self) -> datetime:
        return NOW


@pytest.mark.asyncio
async def test_resilient_target_probe_uses_dns_pinning_ssrf_limits_and_timeout() -> None:
    transport = _ProbeTransport()
    probe = ResilientTargetProbe(
        Settings(external_io_timeout_seconds=1.25),
        resolver=_ProbeResolver(),
        transport_factory=lambda: transport,
        clock=_ProbeClock(),
    )

    evidence = await probe.probe(
        "https://jtt.sc.gov.cn/",
        authorization_boundary="jtt.sc.gov.cn",
    )

    assert evidence.capture.content == (
        b'<html><body><a href="/notices/1">engineering bulletin</a></body></html>'
    )
    assert evidence.capture.final_url == "https://jtt.sc.gov.cn/"
    assert evidence.resolved_addresses_public is True
    assert evidence.redirect_boundary_valid is True
    assert evidence.robots is EvidenceReview.ALLOWED
    assert evidence.connector_valid is True
    assert evidence.relevant is True
    assert transport.requests == [
        {
            "url": "https://jtt.sc.gov.cn/robots.txt",
            "headers": {
                "Accept": "text/plain",
                "User-Agent": "SRBGQualificationProbe/1.0",
            },
            "timeout_seconds": 1.25,
            "max_response_bytes": 512 * 1024,
            "validated_ips": frozenset({"93.184.216.34"}),
        },
        {
            "url": "https://jtt.sc.gov.cn/",
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/pdf",
                "User-Agent": "SRBGQualificationProbe/1.0",
            },
            "timeout_seconds": 1.25,
            "max_response_bytes": 50 * 1024 * 1024,
            "validated_ips": frozenset({"93.184.216.34"}),
        }
    ]
    assert transport.closed is True


@pytest.mark.asyncio
async def test_resilient_target_probe_does_not_mark_unrelated_direct_content_relevant() -> None:
    transport = _ProbeTransport(b"<html><body>restaurant menu and weather</body></html>")
    probe = ResilientTargetProbe(
        Settings(external_io_timeout_seconds=1.25),
        resolver=_ProbeResolver(),
        transport_factory=lambda: transport,
        clock=_ProbeClock(),
    )

    evidence = await probe.probe(
        "https://jtt.sc.gov.cn/",
        authorization_boundary="jtt.sc.gov.cn",
    )

    assert evidence.relevant is False
    assert evidence.connector_valid is False


@pytest.mark.asyncio
async def test_missing_robots_file_remains_a_waivable_unknown() -> None:
    transport = _ProbeTransport(robots_status=404, robots_content=b"not found")
    probe = ResilientTargetProbe(
        Settings(external_io_timeout_seconds=1.25),
        resolver=_ProbeResolver(),
        transport_factory=lambda: transport,
        clock=_ProbeClock(),
    )

    evidence = await probe.probe(
        "https://jtt.sc.gov.cn/",
        authorization_boundary="jtt.sc.gov.cn",
    )

    assert evidence.robots is EvidenceReview.NOT_PRESENT


@pytest.mark.asyncio
async def test_explicit_robots_block_creates_blocked_bundle_without_target_body() -> None:
    gateway = RecordingQualificationGateway()
    transport = _ProbeTransport(robots_content=b"User-agent: *\nDisallow: /\n")
    probe = ResilientTargetProbe(
        Settings(external_io_timeout_seconds=1.25),
        resolver=_ProbeResolver(),
        transport_factory=lambda: transport,
        clock=_ProbeClock(),
    )

    result = await QualificationExecutor(
        gateway=gateway,
        provider=CanonicalTargetProvider(),
        target_probe=probe,
    ).run(qualification_run_id=QUALIFICATION_RUN_ID)

    assert result.status == "SUCCEEDED"
    assert gateway.summary is not None
    assert gateway.summary.verdict == "BLOCKED"
    assert "ROBOTS_BLOCKED" in gateway.summary.reason_codes
    assert gateway.persisted == []
    assert [request["url"] for request in transport.requests] == [
        "https://jtt.sc.gov.cn/robots.txt"
    ]


def test_direct_target_relevance_supports_common_chinese_encoding() -> None:
    content = "四川公路桥梁安全生产通报".encode("gb18030")

    assert qualification._target_is_engineering_relevant(
        "https://example.cn/notices/1",
        content,
    )


@pytest.mark.asyncio
async def test_provider_hit_is_immediately_converted_to_target_evidence_before_gateway() -> None:
    gateway = RecordingQualificationGateway()
    events = gateway.events
    provider = TransientProvider(events)
    probe = RecordingTargetProbe(events)

    result = await QualificationExecutor(
        gateway=gateway,
        provider=provider,
        target_probe=probe,
    ).run(
        qualification_run_id=QUALIFICATION_RUN_ID,
    )

    assert events[:4] == ["lease", "provider", "probe:target", "gateway:target-evidence"]
    assert probe.urls == ["https://jtt.sc.gov.cn/notice/1.html"]
    assert gateway.persisted == [_target_evidence()]
    assert gateway.summary is not None
    assert gateway.summary.verdict == "QUALIFIED"
    assert gateway.summary.material_fingerprint == _binding().material_fingerprint
    changed_evidence_summary = qualification._summarize_qualification(
        _binding(),
        [
            replace(
                _target_evidence(),
                capture=replace(_target_evidence().capture, response_sha256="c" * 64),
            )
        ],
    )
    assert changed_evidence_summary.material_fingerprint == gateway.summary.material_fingerprint
    assert changed_evidence_summary.bundle_sha256 != gateway.summary.bundle_sha256
    assert result.status == "SUCCEEDED"
    assert result.target_evidence_count == 1
    persisted_view = repr((gateway.persisted, gateway.summary, result))
    for forbidden in (provider.response_body, provider.query, "provider-title", "provider-snippet"):
        assert forbidden not in persisted_view


@pytest.mark.asyncio
async def test_default_disabled_target_probe_fails_closed_without_network_or_evidence() -> None:
    gateway = RecordingQualificationGateway()

    result = await QualificationExecutor(
        gateway=gateway,
        provider=CanonicalTargetProvider(),
        target_probe=qualification.DisabledTargetProbe(),
    ).run(
        qualification_run_id=QUALIFICATION_RUN_ID,
    )

    assert result.status == "FAILED"
    assert result.target_evidence_count == 0
    assert gateway.failure_codes == ["TARGET_PROBE_DISABLED"]
    assert gateway.persisted == []


@pytest.mark.asyncio
async def test_transient_metadata_policy_never_persists_target_body() -> None:
    gateway = RecordingQualificationGateway()
    provider = TransientProvider(gateway.events)

    class MetadataOnlyProbe:
        async def probe(self, url: str, *, authorization_boundary: str) -> SafeTargetEvidence:
            assert authorization_boundary == "jtt.sc.gov.cn"
            return replace(
                _target_evidence(url),
                raw_evidence_storage_prohibited=True,
            )

    result = await QualificationExecutor(
        gateway=gateway,
        provider=provider,
        target_probe=MetadataOnlyProbe(),
    ).run(
        qualification_run_id=QUALIFICATION_RUN_ID,
    )

    assert result.status == "SUCCEEDED"
    assert result.target_evidence_count == 1
    assert gateway.persisted == []
    assert gateway.summary is not None
    assert gateway.summary.evidence_capture_policy == "TRANSIENT_METADATA_ONLY"
    assert gateway.summary.storage_policy == "METADATA_ONLY"


@pytest.mark.asyncio
async def test_duplicate_qualification_delivery_stops_at_database_lease() -> None:
    gateway = RecordingQualificationGateway(binding=None)
    gateway.binding = None
    provider = TransientProvider(gateway.events)

    class RejectingProbe:
        async def probe(self, url: str, *, authorization_boundary: str) -> SafeTargetEvidence:
            del url, authorization_boundary
            raise AssertionError("duplicate delivery must not perform target networking")

    result = await QualificationExecutor(
        gateway=gateway,
        provider=provider,
        target_probe=RejectingProbe(),
    ).run(
        qualification_run_id=QUALIFICATION_RUN_ID,
    )

    assert result.acquired is False
    assert result.status == "ALREADY_CLAIMED"
    assert gateway.events == ["lease", "closed"]


def test_qualification_and_production_gateways_are_nominally_isolated() -> None:
    from srbg_worker.source_runtime import PostgresRuntimeGateway

    assert not issubclass(PostgresQualificationGateway, PostgresRuntimeGateway)
    assert "RuntimeBinding" not in inspect.getsource(qualification)
    parameters = inspect.signature(PostgresQualificationGateway.record_target_evidence).parameters
    assert set(parameters) == {
        "self",
        "binding",
        "evidence",
    }


class _DatabaseResult:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    def mappings(self) -> _DatabaseResult:
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self.row

    def all(self) -> list[dict[str, object]]:
        return [] if self.row is None else [self.row]


class _DatabaseConnection:
    def __init__(self, rows: list[dict[str, object] | None]) -> None:
        self.rows = list(rows)
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> _DatabaseResult:
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return _DatabaseResult(self.rows.pop(0) if self.rows else None)


class _DatabaseContext:
    def __init__(self, connection: _DatabaseConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _DatabaseConnection:
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        del args


class _DatabaseEngine:
    def __init__(self, connection: _DatabaseConnection) -> None:
        self.connection = connection

    def begin(self) -> _DatabaseContext:
        return _DatabaseContext(self.connection)

    def connect(self) -> _DatabaseContext:
        return _DatabaseContext(self.connection)

    async def dispose(self) -> None:
        return None


class _ObjectStore:
    def __init__(self) -> None:
        self.objects: list[tuple[str, bytes, str]] = []

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        self.objects.append((key, content, content_type))
        return "target-etag"


class _Scanner:
    async def scan(self, content: bytes) -> None:
        assert content == b"<html><body>target evidence</body></html>"


@pytest.mark.asyncio
async def test_postgres_qualification_dispatcher_reads_pending_and_expired_leases() -> None:
    connection = _DatabaseConnection([{"id": QUALIFICATION_RUN_ID}])
    gateway = PostgresQualificationGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore()),
        malware_scanner=cast(ClamAVScanner, _Scanner()),
    )

    pending_ids = await gateway.pending_ids(limit=500)

    assert pending_ids == (QUALIFICATION_RUN_ID,)
    assert "list_pending_source_qualification_ids" in connection.statements[0]
    assert "source_qualification_run" not in connection.statements[0]
    assert connection.parameters[0]["limit"] == 100


@pytest.mark.asyncio
async def test_postgres_qualification_lease_and_capture_are_qualification_only() -> None:
    lease_row = {
        "candidate_id": CANDIDATE_ID,
        "campaign_id": None,
        "canonical_url": "https://jtt.sc.gov.cn/",
        "authorization_boundary": "jtt.sc.gov.cn",
        "rule_version": "source-qualification-v1",
        "material_fingerprint": "a" * 64,
        "lease_token": LEASE_TOKEN,
        "prepared_source_id": None,
        "prepared_policy_version_id": None,
        "prepared_connector_config_version_id": None,
        "prepared_trial_run_id": None,
    }
    capture_id = UUID("019d1000-0000-7000-8000-000000000008")
    connection = _DatabaseConnection([lease_row, {"id": capture_id}])
    object_store = _ObjectStore()
    gateway = PostgresQualificationGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, object_store),
        malware_scanner=cast(ClamAVScanner, _Scanner()),
    )

    binding = await gateway.acquire(QUALIFICATION_RUN_ID)
    assert binding is not None
    assert binding.campaign_id is None
    persisted_id = await gateway.record_target_evidence(binding, _target_evidence())

    assert persisted_id == capture_id
    assert "acquire_source_qualification" in connection.statements[0]
    assert "source_qualification_run" not in connection.statements[0]
    assert "record_source_qualification_capture" in connection.statements[1]
    assert not any(
        verb in connection.statements[1] for verb in ("INSERT ", "UPDATE ", "DELETE ")
    )
    assert object_store.objects[0][0].startswith("qualification/sha256/")
    values = repr(connection.parameters)
    assert "provider-title" not in values
    assert "provider-snippet" not in values
    assert "secret-query" not in values


@pytest.mark.asyncio
async def test_postgres_qualification_persists_checks_matching_public_contract() -> None:
    bundle_id = UUID("019d1000-0000-7000-8000-000000000013")
    connection = _DatabaseConnection([{"id": bundle_id}])
    gateway = PostgresQualificationGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
        object_store=cast(S3ObjectStore, _ObjectStore()),
        malware_scanner=cast(ClamAVScanner, _Scanner()),
    )
    summary = qualification._summarize_qualification(_binding(), [_target_evidence()])

    status = await gateway.complete(_binding(), summary)

    assert status == "SUCCEEDED"
    checks = json.loads(cast(str, connection.parameters[0]["checks"]))
    parsed = [QualificationCheckView.model_validate(check) for check in checks]
    assert parsed[0].level.value == "PASS"
    assert parsed[0].observed_at == summary.created_at


class RecordingActivationGateway:
    def __init__(self) -> None:
        self.prepare_calls: list[UUID] = []
        self.completed: list[ActivationDispatch] = []
        self.already_succeeded = False

    async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]:
        assert limit == 50
        return (OUTBOX_ID,)

    async def prepare(self, outbox_id: UUID) -> ActivationDispatch | None:
        self.prepare_calls.append(outbox_id)
        return ActivationDispatch(
            outbox_id=OUTBOX_ID,
            source_id=SOURCE_ID,
            fetch_run_id=FETCH_RUN_ID,
            needs_dispatch=not self.already_succeeded,
        )

    async def mark_succeeded(self, dispatch: ActivationDispatch) -> bool:
        self.completed.append(dispatch)
        self.already_succeeded = True
        return True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_activation_outbox_dispatches_a_new_production_fetch_once() -> None:
    gateway = RecordingActivationGateway()
    messages: list[dict[str, str]] = []

    async def dispatch_source_fetch(source_id: UUID, run_id: UUID) -> None:
        messages.append({"source_id": str(source_id), "run_id": str(run_id)})

    executor = ActivationOutboxExecutor(
        gateway=gateway,
        dispatch_source_fetch=dispatch_source_fetch,
    )
    first = await executor.run(OUTBOX_ID)
    replay = await executor.run(OUTBOX_ID)

    assert messages == [{"source_id": str(SOURCE_ID), "run_id": str(FETCH_RUN_ID)}]
    assert first.status == "SUCCEEDED"
    assert first.dispatched is True
    assert replay.status == "SUCCEEDED"
    assert replay.dispatched is False
    assert gateway.completed == [
        ActivationDispatch(OUTBOX_ID, SOURCE_ID, FETCH_RUN_ID, needs_dispatch=True)
    ]


@pytest.mark.asyncio
async def test_postgres_activation_prepares_a_fresh_scheduled_production_run_idempotently() -> None:
    connection = _DatabaseConnection(
        [
            {
                "outbox_id": OUTBOX_ID,
                "source_id": SOURCE_ID,
                "fetch_run_id": FETCH_RUN_ID,
                "needs_dispatch": True,
            }
        ]
    )
    gateway = PostgresActivationOutboxGateway(
        Settings(),
        engine=cast(AsyncEngine, _DatabaseEngine(connection)),
    )

    dispatch = await gateway.prepare(OUTBOX_ID)

    assert dispatch == ActivationDispatch(
        OUTBOX_ID,
        SOURCE_ID,
        FETCH_RUN_ID,
        needs_dispatch=True,
    )
    statement = connection.statements[0]
    assert "prepare_source_activation" in statement
    assert "source_activation_outbox" not in statement
    assert not any(verb in statement for verb in ("INSERT ", "UPDATE ", "DELETE "))
    assert connection.parameters[0]["fetch_run_id"] != QUALIFICATION_RUN_ID


def test_celery_qualification_payload_and_result_are_identifier_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execute(run_id: UUID) -> dict[str, object]:
        assert run_id == QUALIFICATION_RUN_ID
        return {
            "qualification_run_id": str(run_id),
            "status": "SUCCEEDED",
            "acquired": True,
            "target_evidence_count": 1,
        }

    monkeypatch.setattr(worker, "_execute_source_qualification", fake_execute)
    task = worker.celery_app.tasks["srbg.sources.qualify"]

    result = task.run(qualification_run_id=str(QUALIFICATION_RUN_ID))

    assert set(result) == {
        "qualification_run_id",
        "status",
        "acquired",
        "target_evidence_count",
    }
    with pytest.raises(TypeError):
        task.run(
            qualification_run_id=str(QUALIFICATION_RUN_ID),
            query="must-not-enter-broker",
        )
    with pytest.raises(TypeError):
        task.run(
            qualification_run_id=str(QUALIFICATION_RUN_ID),
            campaign_id=str(CAMPAIGN_ID),
        )


@pytest.mark.asyncio
async def test_pending_qualification_dispatcher_emits_only_run_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, dict[str, str]]] = []

    class PendingGateway:
        async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]:
            assert limit == 50
            return (QUALIFICATION_RUN_ID,)

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        worker,
        "PostgresQualificationGateway",
        lambda settings: PendingGateway(),
    )
    monkeypatch.setattr(
        worker,
        "settings",
        worker.settings.model_copy(update={"source_qualification_enabled": True}),
    )
    monkeypatch.setattr(
        worker.celery_app,
        "send_task",
        lambda name, *, kwargs, **_options: sent.append((name, kwargs)),
    )

    result = await worker._dispatch_pending_source_qualifications()

    assert result == {"dispatched": 1}
    assert sent == [
        (
            "srbg.sources.qualify",
            {"qualification_run_id": str(QUALIFICATION_RUN_ID)},
        )
    ]


def test_qualification_probe_feature_flag_is_off_by_default_without_live_transport() -> None:
    assert isinstance(
        worker._build_qualification_target_probe(Settings()),
        qualification.DisabledTargetProbe,
    )
    assert isinstance(
        worker._build_qualification_target_probe(Settings(source_qualification_enabled=True)),
        ResilientTargetProbe,
    )


@pytest.mark.asyncio
async def test_disabled_qualification_dispatch_does_not_construct_database_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        worker,
        "settings",
        worker.settings.model_copy(update={"source_qualification_enabled": False}),
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("disabled qualification must not construct database I/O")

    monkeypatch.setattr(worker, "PostgresQualificationGateway", forbidden)

    assert await worker._dispatch_pending_source_qualifications() == {
        "disabled": True,
        "dispatched": 0,
    }


def test_worker_registers_qualification_and_activation_routes_and_failure_policies() -> None:
    assert worker.celery_app.conf.task_routes["srbg.sources.qualify"] == {
        "queue": "qualification"
    }
    assert worker.celery_app.conf.task_routes["srbg.sources.activation_outbox"] == {
        "queue": "celery"
    }
    activation_schedule = worker.celery_app.conf.beat_schedule["dispatch-source-activation-outbox"]
    assert activation_schedule["task"] == "srbg.sources.activation_outbox"
    qualification_schedule = worker.celery_app.conf.beat_schedule[
        "dispatch-pending-source-qualifications"
    ]
    assert qualification_schedule["task"] == "srbg.sources.qualify"
    assert TASK_POLICIES["srbg.sources.qualify"] == ("SOURCE_QUALIFICATION", True)
    assert TASK_POLICIES["srbg.sources.activation_outbox"] == (
        "SOURCE_ACTIVATION_OUTBOX",
        True,
    )


@pytest.mark.asyncio
async def test_operations_replay_redelivers_source_task_with_identifier_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay = ClaimedReplay(
        id=UUID("019d1000-0000-7000-8000-000000000020"),
        failed_task_id=UUID("019d1000-0000-7000-8000-000000000021"),
        task_kind="SOURCE_QUALIFICATION",
        priority=9,
        source_id=None,
        run_id=None,
        document_version_id=None,
        event_id=None,
        processing_version=None,
        lease_token=UUID("019d1000-0000-7000-8000-000000000022"),
        execution_id=QUALIFICATION_RUN_ID,
    )
    redelivery = ReplayTaskRedelivery(
        task_name="srbg.sources.qualify",
        argument_name="qualification_run_id",
        argument_id=QUALIFICATION_RUN_ID,
    )
    sent: list[tuple[str, dict[str, str]]] = []

    async def fake_prepare(engine: object, claimed: ClaimedReplay) -> ReplayTaskRedelivery:
        assert claimed == replay
        assert engine is fake_engine
        return redelivery

    fake_engine = object()
    monkeypatch.setattr(worker, "prepare_task_redelivery", fake_prepare)
    monkeypatch.setattr(
        worker.celery_app,
        "send_task",
        lambda name, *, kwargs: sent.append((name, kwargs)),
    )

    await worker._execute_replay_kind(replay, cast(AsyncEngine, fake_engine))

    assert sent == [
        (
            "srbg.sources.qualify",
            {"qualification_run_id": str(QUALIFICATION_RUN_ID)},
        )
    ]


@pytest.mark.asyncio
async def test_operations_replay_terminal_source_task_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay = ClaimedReplay(
        id=UUID("019d1000-0000-7000-8000-000000000023"),
        failed_task_id=UUID("019d1000-0000-7000-8000-000000000024"),
        task_kind="SOURCE_ACTIVATION_OUTBOX",
        priority=9,
        source_id=None,
        run_id=None,
        document_version_id=None,
        event_id=None,
        processing_version=None,
        lease_token=UUID("019d1000-0000-7000-8000-000000000025"),
        execution_id=OUTBOX_ID,
        noop_reason="ACTIVATION_OUTBOX_TERMINAL_NOOP",
    )
    fake_engine = object()

    async def fake_prepare(
        engine: object,
        claimed: ClaimedReplay,
    ) -> ReplayTaskRedelivery | None:
        assert engine is fake_engine
        assert claimed == replay
        return None

    monkeypatch.setattr(worker, "prepare_task_redelivery", fake_prepare)
    monkeypatch.setattr(
        worker.celery_app,
        "send_task",
        lambda *args, **kwargs: pytest.fail(f"terminal replay dispatched: {args}, {kwargs}"),
    )

    await worker._execute_replay_kind(replay, cast(AsyncEngine, fake_engine))
