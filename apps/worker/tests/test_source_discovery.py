from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.http import HttpResponse
from srbg_api.config import Settings
from srbg_api.source_automation.search import SearchItem, SearchQuery, SearchResult
from srbg_worker.source_discovery import (
    QUERY_CATALOG,
    DiscoveryExecutor,
    PostgresDiscoveryGateway,
    PublicDiscoverySeed,
    PublicSeedDiscoveryExecutor,
    RegistrationOutcome,
    SafeDiscoveryTargetProbe,
    VerifiedDiscoveryTarget,
    _institution_origin,
    _target_material_fingerprint,
)

NOW = datetime(2026, 7, 17, tzinfo=UTC)
RUN_ID = UUID("019b0000-0000-7000-8000-000000009101")
CANDIDATE_ID = UUID("019b0000-0000-7000-8000-000000009102")
QUALIFICATION_ID = UUID("019b0000-0000-7000-8000-000000009103")
REQUALIFICATION_ID = UUID("019b0000-0000-7000-8000-000000009104")


def _expected_evidence_ref(
    *,
    canonical_url: str,
    response_sha256: str,
    industries: tuple[str, ...],
    content_domains: tuple[str, ...],
) -> str:
    material = "\n".join(
        (canonical_url, response_sha256, *sorted(industries), *sorted(content_domains))
    )
    return "target-fetch:" + sha256(material.encode()).hexdigest()


def test_target_material_fingerprint_tracks_governance_boundary_not_page_content() -> None:
    first = _target_material_fingerprint(
        "https://jtt.sc.gov.cn/",
        "jtt.sc.gov.cn",
    )
    repeated_after_content_change = _target_material_fingerprint(
        "https://jtt.sc.gov.cn/",
        "jtt.sc.gov.cn",
    )
    changed_boundary = _target_material_fingerprint(
        "https://jt.sc.gov.cn/",
        "jt.sc.gov.cn",
    )

    assert first == repeated_after_content_change
    assert first != changed_boundary
    assert len(first) == 64


def test_provider_result_path_query_and_fragment_are_reduced_to_safe_origin() -> None:
    assert (
        _institution_origin("https://jtt.sc.gov.cn/notices?id=1#content")
        == "https://jtt.sc.gov.cn/"
    )


class _ProbeResolver:
    async def resolve(self, hostname: str, *, timeout_seconds: float) -> tuple[str, ...]:
        assert hostname == "jtt.sc.gov.cn"
        assert timeout_seconds == 2.0
        return ("93.184.216.34",)


class _ProbeTransport:
    calls = 0

    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse:
        type(self).calls += 1
        assert url == "https://jtt.sc.gov.cn/"
        assert headers["User-Agent"] == "SRBGSourceDiscoveryProbe/1.0"
        assert timeout_seconds == 2.0
        assert max_response_bytes == 2 * 1024 * 1024
        assert validated_ips == frozenset({"93.184.216.34"})
        return HttpResponse(
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"verified target body",
            peer_ip="93.184.216.34",
        )

    async def close(self) -> None:
        return None


class _ProbeClock:
    def monotonic(self) -> float:
        return 0.0

    async def sleep(self, seconds: float) -> None:
        raise AssertionError(f"single-attempt target probe tried to sleep: {seconds}")

    def now(self) -> datetime:
        return NOW


@pytest.mark.asyncio
async def test_safe_probe_separates_response_evidence_from_governance_fingerprint() -> None:
    probe = SafeDiscoveryTargetProbe(
        Settings(),
        resolver=_ProbeResolver(),
        transport_factory=_ProbeTransport,
        clock=_ProbeClock(),
    )

    target = await probe.probe("https://jtt.sc.gov.cn/notices/1")

    assert target.canonical_url == "https://jtt.sc.gov.cn/"
    assert len(target.response_sha256) == 64
    assert target.material_fingerprint == _target_material_fingerprint(
        target.canonical_url,
        target.authorization_boundary,
    )
    assert _ProbeTransport.calls == 1


class _Provider:
    def __init__(self, items: tuple[SearchItem, ...]) -> None:
        self.items = items
        self.calls = 0
        self.queries: list[str] = []

    async def search(self, query: SearchQuery, *, now: datetime) -> SearchResult:
        self.calls += 1
        self.queries.append(query.query)
        assert query.top_k == 50
        assert now == NOW
        return SearchResult(items=self.items)


class _Probe:
    def __init__(self, *, fail_hosts: frozenset[str] = frozenset()) -> None:
        self.fail_hosts = fail_hosts
        self.calls: list[str] = []

    async def probe(self, url: str) -> VerifiedDiscoveryTarget:
        self.calls.append(url)
        host = url.split("/", 3)[2]
        if host in self.fail_hosts:
            raise OSError("controlled probe failure")
        digest = "a" * 64 if host.startswith("jtt") else "b" * 64
        return VerifiedDiscoveryTarget(
            canonical_url=f"https://{host}/",
            authorization_boundary=host,
            response_sha256=digest,
            material_fingerprint="c" * 64,
        )


class _Gateway:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                VerifiedDiscoveryTarget,
                str,
                tuple[str, ...],
                tuple[str, ...],
                str,
            ]
        ] = []

    async def register_and_request(
        self,
        target: VerifiedDiscoveryTarget,
        *,
        discovery_channel: str,
        industries: tuple[str, ...],
        content_domains: tuple[str, ...],
        evidence_ref: str,
        discovery_run_id: UUID,
        now: datetime,
    ) -> RegistrationOutcome:
        assert discovery_run_id == RUN_ID
        assert now == NOW
        self.calls.append(
            (target, discovery_channel, industries, content_domains, evidence_ref)
        )
        return RegistrationOutcome(CANDIDATE_ID, QUALIFICATION_ID, created=True)

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_disabled_discovery_performs_zero_provider_probe_or_database_io() -> None:
    provider = _Provider((SearchItem("https://jtt.sc.gov.cn/a", None),))
    probe = _Probe()
    gateway = _Gateway()

    outcome = await DiscoveryExecutor(
        enabled=False,
        provider=provider,
        probe=probe,
        gateway=gateway,
    ).run(query_code="HIGHWAY_SAFETY", discovery_run_id=RUN_ID, now=NOW)

    assert outcome.disabled is True
    assert outcome.as_task_result() == {
        "discovery_run_id": str(RUN_ID),
        "query_code": "HIGHWAY_SAFETY",
        "disabled": True,
        "provider_calls": 0,
        "provider_failures": 0,
        "budget_stops": 0,
        "budget_alerts": 0,
        "targets_seen": 0,
        "targets_probed": 0,
        "targets_rejected": 0,
        "candidates_registered": 0,
        "qualifications_requested": 0,
    }
    assert provider.calls == 0
    assert probe.calls == []
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_target_is_probed_before_registration_and_classification_comes_from_query_code(
) -> None:
    events: list[str] = []

    class OrderedProbe(_Probe):
        async def probe(self, url: str) -> VerifiedDiscoveryTarget:
            events.append("probe")
            return await super().probe(url)

    class OrderedGateway(_Gateway):
        async def register_and_request(
            self,
            target: VerifiedDiscoveryTarget,
            *,
            discovery_channel: str,
            industries: tuple[str, ...],
            content_domains: tuple[str, ...],
            evidence_ref: str,
            discovery_run_id: UUID,
            now: datetime,
        ) -> RegistrationOutcome:
            events.append("register")
            return await super().register_and_request(
                target,
                discovery_channel=discovery_channel,
                industries=industries,
                content_domains=content_domains,
                evidence_ref=evidence_ref,
                discovery_run_id=discovery_run_id,
                now=now,
            )

    provider = _Provider(
        (
            SearchItem("https://jtt.sc.gov.cn/notices/1", None),
            SearchItem("https://jtt.sc.gov.cn/notices/2", None),
        )
    )
    probe = OrderedProbe()
    gateway = OrderedGateway()

    outcome = await DiscoveryExecutor(
        enabled=True,
        provider=provider,
        probe=probe,
        gateway=gateway,
    ).run(query_code="HIGHWAY_SAFETY", discovery_run_id=RUN_ID, now=NOW)

    assert events == ["probe", "register"]
    assert len(probe.calls) == 1  # institution-host deduplication happens before direct probing
    assert gateway.calls[0][1] == "BAIDU_SEARCH"
    assert gateway.calls[0][2] == ("HIGHWAY",)
    assert gateway.calls[0][3] == QUERY_CATALOG["HIGHWAY_SAFETY"].content_domains
    assert gateway.calls[0][4] == _expected_evidence_ref(
        canonical_url="https://jtt.sc.gov.cn/",
        response_sha256="a" * 64,
        industries=("HIGHWAY",),
        content_domains=QUERY_CATALOG["HIGHWAY_SAFETY"].content_domains,
    )
    assert outcome.candidates_registered == 1
    assert outcome.qualifications_requested == 1


@pytest.mark.asyncio
async def test_provider_material_never_reaches_persistence_or_task_result() -> None:
    provider = _Provider((SearchItem("https://jtt.sc.gov.cn/secret-path", None),))
    gateway = _Gateway()
    outcome = await DiscoveryExecutor(
        enabled=True,
        provider=provider,
        probe=_Probe(),
        gateway=gateway,
    ).run(query_code="HIGHWAY_SAFETY", discovery_run_id=RUN_ID, now=NOW)

    result_text = repr(outcome.as_task_result())
    persisted_text = repr(gateway.calls)
    assert QUERY_CATALOG["HIGHWAY_SAFETY"].query not in result_text
    assert "secret-path" not in persisted_text
    assert "title" not in persisted_text
    assert "snippet" not in persisted_text
    assert set(outcome.as_task_result()) == {
        "discovery_run_id",
        "query_code",
        "disabled",
        "provider_calls",
        "provider_failures",
        "budget_stops",
        "budget_alerts",
        "targets_seen",
        "targets_probed",
        "targets_rejected",
        "candidates_registered",
        "qualifications_requested",
    }


@pytest.mark.asyncio
async def test_per_target_failures_are_isolated_and_round_limit_is_bounded() -> None:
    provider = _Provider(
        (
            SearchItem("https://bad.example.com/a", None),
            SearchItem("https://good.example.com/b", None),
            SearchItem("https://ignored.example.com/c", None),
        )
    )
    probe = _Probe(fail_hosts=frozenset({"bad.example.com"}))
    gateway = _Gateway()
    outcome = await DiscoveryExecutor(
        enabled=True,
        provider=provider,
        probe=probe,
        gateway=gateway,
        max_candidates_per_query=2,
    ).run(query_code="BRIDGE_DIGITAL", discovery_run_id=RUN_ID, now=NOW)

    assert probe.calls == ["https://bad.example.com/a", "https://good.example.com/b"]
    assert len(gateway.calls) == 1
    assert outcome.targets_rejected == 1
    assert outcome.candidates_registered == 1


class _ScalarResult:
    def __init__(self, value: UUID | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> UUID | None:
        return self.value


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []
        self._results = iter(
            (CANDIDATE_ID, QUALIFICATION_ID, CANDIDATE_ID, REQUALIFICATION_ID)
        )

    async def scalar(self, statement: object, parameters: dict[str, object]) -> UUID | None:
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return next(self._results)


class _Context:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        del args


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def begin(self) -> _Context:
        return _Context(self.connection)

    async def dispose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_postgres_gateway_is_idempotent_and_requests_qualification_after_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated_ids = iter(
        UUID(f"019b0000-0000-7000-8000-{value:012d}")
        for value in range(9102, 9112)
    )
    monkeypatch.setattr(
        "srbg_worker.source_discovery.uuid7",
        lambda: next(generated_ids),
    )
    connection = _Connection()
    gateway = PostgresDiscoveryGateway(cast(AsyncEngine, _Engine(connection)))
    target = VerifiedDiscoveryTarget(
        canonical_url="https://jtt.sc.gov.cn/",
        authorization_boundary="jtt.sc.gov.cn",
        response_sha256="a" * 64,
        material_fingerprint="c" * 64,
    )
    evidence_ref = _expected_evidence_ref(
        canonical_url=target.canonical_url,
        response_sha256=target.response_sha256,
        industries=("HIGHWAY",),
        content_domains=("SAFETY_REGULATION",),
    )

    first = await gateway.register_and_request(
        target,
        discovery_channel="BAIDU_SEARCH",
        industries=("HIGHWAY",),
        content_domains=("SAFETY_REGULATION",),
        evidence_ref=evidence_ref,
        discovery_run_id=RUN_ID,
        now=NOW,
    )
    second = await gateway.register_and_request(
        target,
        discovery_channel="BAIDU_SEARCH",
        industries=("HIGHWAY",),
        content_domains=("SAFETY_REGULATION",),
        evidence_ref=evidence_ref,
        discovery_run_id=RUN_ID,
        now=NOW,
    )

    assert first == RegistrationOutcome(CANDIDATE_ID, QUALIFICATION_ID, created=True)
    assert second == RegistrationOutcome(
        CANDIDATE_ID,
        REQUALIFICATION_ID,
        created=False,
    )
    assert "register_discovered_source_candidate" in connection.statements[0]
    assert "request_automated_source_qualification" in connection.statements[1]
    assert "register_discovered_source_candidate" in connection.statements[2]
    assert "request_automated_source_qualification" in connection.statements[3]
    assert all("FROM source_candidate" not in statement for statement in connection.statements)
    serialized_parameters = repr(connection.parameters)
    assert "secret-path" not in serialized_parameters
    assert QUERY_CATALOG["HIGHWAY_SAFETY"].query not in serialized_parameters


class _SitemapAdapter:
    adapter_code = "PUBLIC_SITEMAP_V1"
    channel = "SITEMAP"

    def __init__(self) -> None:
        self.calls: list[int] = []

    async def discover(self, *, limit: int) -> tuple[PublicDiscoverySeed, ...]:
        self.calls.append(limit)
        return (
            PublicDiscoverySeed(
                url="https://jtt.sc.gov.cn/sitemap-item",
                industries=("HIGHWAY",),
                content_domains=("OFFICIAL_NOTICE",),
            ),
        )


@pytest.mark.asyncio
async def test_public_directory_rss_sitemap_outbound_adapter_seam_uses_same_target_gate(
) -> None:
    adapter = _SitemapAdapter()
    probe = _Probe()
    gateway = _Gateway()

    outcome = await PublicSeedDiscoveryExecutor(
        enabled=True,
        adapter=adapter,
        probe=probe,
        gateway=gateway,
    ).run(discovery_run_id=RUN_ID, now=NOW)

    assert adapter.calls == [20]
    assert probe.calls == ["https://jtt.sc.gov.cn/sitemap-item"]
    assert gateway.calls[0][1] == "SITEMAP"
    assert gateway.calls[0][2:4] == (("HIGHWAY",), ("OFFICIAL_NOTICE",))
    assert outcome.candidates_registered == 1


def test_public_seed_cannot_expand_the_first_release_content_scope() -> None:
    with pytest.raises(ValueError, match="classification"):
        PublicDiscoverySeed(
            url="https://jtt.sc.gov.cn/",
            industries=("HIGHWAY",),
            content_domains=("TENDER_NOTICE",),
        )
