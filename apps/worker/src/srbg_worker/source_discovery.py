"""Automated, budgeted source discovery with a transient provider boundary.

Only fixed query codes cross the Celery boundary. Provider-authored query results remain in
memory until a DNS-pinned direct target fetch proves the target; persistence receives only an
institution origin, server-owned classification, and cryptographic target evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from types import MappingProxyType
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from srbg_api.acquisition.contracts import SourceCheckpoint
from srbg_api.acquisition.http import (
    Clock,
    FetchPolicy,
    HttpResponse,
    ResilientHttpClient,
    Resolver,
)
from srbg_api.acquisition.live import HttpxTransport, SystemClock, SystemResolver
from srbg_api.config import Settings
from srbg_api.personal_search import SearchBudgetExceeded, SearchQuery, SearchResult
from srbg_contracts import SourceContentDomain, SourceIndustry

DISCOVERY_ACTOR_ID = UUID("019b0000-0000-7000-8000-000000009001")
QUALIFICATION_RULE_VERSION = "source-qualification-v1"
MAX_DISCOVERY_TARGET_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_CANDIDATES_PER_QUERY = 20
PublicDiscoveryChannel = Literal["DIRECTORY", "RSS", "SITEMAP", "OUTBOUND_LINK"]
_PUBLIC_DISCOVERY_CHANNELS = frozenset({"DIRECTORY", "RSS", "SITEMAP", "OUTBOUND_LINK"})
_ALLOWED_INDUSTRIES = frozenset(item.value for item in SourceIndustry)
_ALLOWED_CONTENT_DOMAINS = frozenset(item.value for item in SourceContentDomain)


@dataclass(frozen=True, slots=True)
class DiscoveryQuerySpec:
    code: str
    query: str
    industries: tuple[str, ...]
    content_domains: tuple[str, ...]

    def __post_init__(self) -> None:
        if re.fullmatch("[A-Z0-9_]{3,80}", self.code) is None:
            raise ValueError("discovery query code is invalid")
        if not self.query.strip() or len(self.query) > 500:
            raise ValueError("discovery query text is invalid")
        if not self.industries or not self.content_domains:
            raise ValueError("discovery classification cannot be empty")


_DIGITAL_DOMAINS = (
    "DIGITAL_TRANSFORMATION_CASE",
    "RESEARCH_PAPER",
    "SOFTWARE_PLATFORM",
    "IOT_EQUIPMENT",
    "LOW_ALTITUDE_EQUIPMENT",
    "AI_APPLICATION",
)
_SAFETY_DOMAINS = (
    "SAFETY_REGULATION",
    "STANDARD_GUIDANCE",
    "ACCIDENT_INVESTIGATION",
    "OFFICIAL_NOTICE",
    "PENALTY",
    "RECTIFICATION",
)
_INDUSTRY_TERMS = (
    ("HIGHWAY", "公路工程"),
    ("BRIDGE", "桥梁工程"),
    ("TUNNEL", "隧道工程"),
    ("RAILWAY", "铁路工程"),
    ("RAIL_TRANSIT", "城市轨道交通工程"),
    ("WATER_CONSERVANCY", "水利工程"),
    ("MUNICIPAL", "市政工程"),
    ("BUILDING", "建筑工程"),
    ("ENERGY", "能源工程"),
    ("PORT_WATERWAY", "港口航道工程"),
    ("AIRPORT", "机场工程"),
    ("GENERAL_TRANSPORT", "交通工程"),
)


def _build_query_catalog() -> Mapping[str, DiscoveryQuerySpec]:
    catalog: dict[str, DiscoveryQuerySpec] = {}
    for industry, term in _INDUSTRY_TERMS:
        digital_code = f"{industry}_DIGITAL"
        safety_code = f"{industry}_SAFETY"
        catalog[digital_code] = DiscoveryQuerySpec(
            digital_code,
            f"{term} 数字化转型 智慧建造 人工智能 物联网 低空设备",
            (industry,),
            _DIGITAL_DOMAINS,
        )
        catalog[safety_code] = DiscoveryQuerySpec(
            safety_code,
            f"{term} 安全规定 标准指南 事故调查 通报 处罚 整改",
            (industry,),
            _SAFETY_DOMAINS,
        )
    return MappingProxyType(catalog)


QUERY_CATALOG = _build_query_catalog()


@dataclass(frozen=True, slots=True)
class VerifiedDiscoveryTarget:
    canonical_url: str
    authorization_boundary: str
    response_sha256: str
    material_fingerprint: str

    def __post_init__(self) -> None:
        origin = _institution_origin(self.canonical_url)
        if origin != self.canonical_url:
            raise ValueError("verified candidate URL must be a canonical HTTPS institution origin")
        if urlsplit(origin).hostname != self.authorization_boundary:
            raise ValueError("verified target boundary does not match its origin")
        if re.fullmatch("[0-9a-f]{64}", self.response_sha256) is None:
            raise ValueError("verified target response hash is invalid")
        if re.fullmatch("[0-9a-f]{64}", self.material_fingerprint) is None:
            raise ValueError("verified target material fingerprint is invalid")


@dataclass(frozen=True, slots=True)
class RegistrationOutcome:
    candidate_id: UUID
    qualification_run_id: UUID | None
    created: bool


@dataclass(frozen=True, slots=True)
class PublicDiscoverySeed:
    """Transient output contract for credential-free public discovery adapters."""

    url: str
    industries: tuple[str, ...]
    content_domains: tuple[str, ...]
    parent_source_id: UUID | None = None
    depth: int = 0

    def __post_init__(self) -> None:
        if _institution_origin(self.url) is None:
            raise ValueError("public discovery seed must be a safe HTTPS URL")
        _validate_classification(self.industries, self.content_domains)
        if self.depth not in {0, 1}:
            raise ValueError("public discovery seed depth must be zero or one")


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    discovery_run_id: UUID
    query_code: str
    disabled: bool = False
    provider_calls: int = 0
    provider_failures: int = 0
    budget_stops: int = 0
    budget_alerts: int = 0
    targets_seen: int = 0
    targets_probed: int = 0
    targets_rejected: int = 0
    candidates_registered: int = 0
    qualifications_requested: int = 0

    def as_task_result(self) -> dict[str, object]:
        """Return a deliberately narrow Celery-safe result without provider or target material."""
        return {
            "discovery_run_id": str(self.discovery_run_id),
            "query_code": self.query_code,
            "disabled": self.disabled,
            "provider_calls": self.provider_calls,
            "provider_failures": self.provider_failures,
            "budget_stops": self.budget_stops,
            "budget_alerts": self.budget_alerts,
            "targets_seen": self.targets_seen,
            "targets_probed": self.targets_probed,
            "targets_rejected": self.targets_rejected,
            "candidates_registered": self.candidates_registered,
            "qualifications_requested": self.qualifications_requested,
        }


class DiscoverySearchProvider(Protocol):
    async def search(self, query: SearchQuery, *, now: datetime) -> SearchResult: ...


class DiscoveryTargetProbe(Protocol):
    async def probe(self, url: str) -> VerifiedDiscoveryTarget: ...


class DiscoveryOccurrenceTracker(Protocol):
    async def register_occurrence(
        self,
        url: str,
        *,
        discovery_channel: str,
        industries: tuple[str, ...],
        content_domains: tuple[str, ...],
        parent_source_id: UUID | None,
        depth: int,
        now: datetime,
    ) -> bool: ...


class DiscoveryGateway(Protocol):
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
    ) -> RegistrationOutcome: ...

    async def close(self) -> None: ...


class PublicSeedDiscoveryAdapter(Protocol):
    """Extension seam for reviewed Directory/RSS/Sitemap/Outbound adapters.

    Implementations receive no credential parameter and their returned URLs stay transient until
    ``PublicSeedDiscoveryExecutor`` proves each target through the shared SSRF boundary.
    """

    adapter_code: str
    channel: PublicDiscoveryChannel

    async def discover(self, *, limit: int) -> tuple[PublicDiscoverySeed, ...]: ...


class DiscoveryExecutor:
    def __init__(
        self,
        *,
        enabled: bool,
        provider: DiscoverySearchProvider,
        probe: DiscoveryTargetProbe,
        gateway: DiscoveryGateway,
        occurrence_tracker: DiscoveryOccurrenceTracker | None = None,
        max_candidates_per_query: int = DEFAULT_MAX_CANDIDATES_PER_QUERY,
    ) -> None:
        if not 1 <= max_candidates_per_query <= 50:
            raise ValueError("per-query candidate limit must be between 1 and 50")
        self._enabled = enabled
        self._provider = provider
        self._probe = probe
        self._gateway = gateway
        self._occurrence_tracker = occurrence_tracker
        self._max_candidates_per_query = max_candidates_per_query

    async def run(
        self, *, query_code: str, discovery_run_id: UUID, now: datetime
    ) -> DiscoveryOutcome:
        spec = QUERY_CATALOG.get(query_code)
        if spec is None:
            raise ValueError("unknown automated discovery query code")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("automated discovery time must be timezone-aware")
        if not self._enabled:
            return DiscoveryOutcome(discovery_run_id, query_code, disabled=True)
        try:
            search_result = await self._provider.search(
                SearchQuery(query=spec.query, top_k=50), now=now
            )
        except SearchBudgetExceeded:
            return DiscoveryOutcome(discovery_run_id, query_code, provider_calls=0, budget_stops=1)
        except Exception:
            return DiscoveryOutcome(
                discovery_run_id, query_code, provider_calls=1, provider_failures=1
            )
        seen_origins: set[str] = set()
        targets_seen = 0
        targets_probed = 0
        targets_rejected = 0
        candidates_registered = 0
        qualifications_requested = 0
        for item in search_result.items:
            origin = _institution_origin(item.url)
            if origin is None or origin in seen_origins:
                continue
            if targets_seen >= self._max_candidates_per_query:
                break
            seen_origins.add(origin)
            targets_seen += 1
            try:
                if self._occurrence_tracker is not None and (
                    not await self._occurrence_tracker.register_occurrence(
                        item.url,
                        discovery_channel="BAIDU_SEARCH",
                        industries=spec.industries,
                        content_domains=spec.content_domains,
                        parent_source_id=None,
                        depth=0,
                        now=now,
                    )
                ):
                    continue
                verified = await self._probe.probe(item.url)
                targets_probed += 1
                if verified.canonical_url != origin:
                    raise ValueError("direct target response crossed the institution boundary")
                registration = await self._gateway.register_and_request(
                    verified,
                    discovery_channel="BAIDU_SEARCH",
                    industries=spec.industries,
                    content_domains=spec.content_domains,
                    evidence_ref=_target_evidence_ref(
                        verified, industries=spec.industries, content_domains=spec.content_domains
                    ),
                    discovery_run_id=discovery_run_id,
                    now=now,
                )
            except Exception:
                targets_rejected += 1
                continue
            if registration.created:
                candidates_registered += 1
            if registration.qualification_run_id is not None:
                qualifications_requested += 1
        return DiscoveryOutcome(
            discovery_run_id,
            query_code,
            provider_calls=1,
            budget_alerts=1 if search_result.budget_alert_required else 0,
            targets_seen=targets_seen,
            targets_probed=targets_probed,
            targets_rejected=targets_rejected,
            candidates_registered=candidates_registered,
            qualifications_requested=qualifications_requested,
        )


class PublicSeedDiscoveryExecutor:
    """Run a configured public-seed adapter through the same proof and persistence gate."""

    def __init__(
        self,
        *,
        enabled: bool,
        adapter: PublicSeedDiscoveryAdapter,
        probe: DiscoveryTargetProbe,
        gateway: DiscoveryGateway,
        occurrence_tracker: DiscoveryOccurrenceTracker | None = None,
        max_candidates_per_run: int = DEFAULT_MAX_CANDIDATES_PER_QUERY,
    ) -> None:
        if re.fullmatch("[A-Z0-9_]{3,80}", adapter.adapter_code) is None:
            raise ValueError("public discovery adapter code is invalid")
        if adapter.channel not in _PUBLIC_DISCOVERY_CHANNELS:
            raise ValueError("public discovery adapter channel is invalid")
        if not 1 <= max_candidates_per_run <= 50:
            raise ValueError("public discovery candidate limit must be between 1 and 50")
        self._enabled = enabled
        self._adapter = adapter
        self._probe = probe
        self._gateway = gateway
        self._occurrence_tracker = occurrence_tracker
        self._limit = max_candidates_per_run

    async def run(self, *, discovery_run_id: UUID, now: datetime) -> DiscoveryOutcome:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("public discovery time must be timezone-aware")
        if not self._enabled:
            return DiscoveryOutcome(discovery_run_id, self._adapter.adapter_code, disabled=True)
        try:
            seeds = await self._adapter.discover(limit=self._limit)
        except Exception:
            return DiscoveryOutcome(
                discovery_run_id, self._adapter.adapter_code, provider_failures=1
            )
        targets_seen = 0
        targets_probed = 0
        targets_rejected = 0
        candidates_registered = 0
        qualifications_requested = 0
        seen_origins: set[str] = set()
        for seed in seeds[: self._limit]:
            origin = _institution_origin(seed.url)
            if origin is None or origin in seen_origins:
                continue
            seen_origins.add(origin)
            targets_seen += 1
            try:
                if self._occurrence_tracker is not None and (
                    not await self._occurrence_tracker.register_occurrence(
                        seed.url,
                        discovery_channel=self._adapter.channel,
                        industries=seed.industries,
                        content_domains=seed.content_domains,
                        parent_source_id=seed.parent_source_id,
                        depth=seed.depth,
                        now=now,
                    )
                ):
                    continue
                target = await self._probe.probe(seed.url)
                targets_probed += 1
                if target.canonical_url != origin:
                    raise ValueError("public seed crossed the institution boundary")
                registration = await self._gateway.register_and_request(
                    target,
                    discovery_channel=self._adapter.channel,
                    industries=seed.industries,
                    content_domains=seed.content_domains,
                    evidence_ref=_target_evidence_ref(
                        target, industries=seed.industries, content_domains=seed.content_domains
                    ),
                    discovery_run_id=discovery_run_id,
                    now=now,
                )
            except Exception:
                targets_rejected += 1
                continue
            if registration.created:
                candidates_registered += 1
            if registration.qualification_run_id is not None:
                qualifications_requested += 1
        return DiscoveryOutcome(
            discovery_run_id,
            self._adapter.adapter_code,
            provider_calls=1,
            targets_seen=targets_seen,
            targets_probed=targets_probed,
            targets_rejected=targets_rejected,
            candidates_registered=candidates_registered,
            qualifications_requested=qualifications_requested,
        )


class _ClosableTransport(Protocol):
    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse: ...

    async def close(self) -> None: ...


class SafeDiscoveryTargetProbe:
    """Prove a provider target through the shared DNS-pinned SSRF boundary."""

    def __init__(
        self,
        settings: Settings,
        *,
        resolver: Resolver | None = None,
        transport_factory: type[_ClosableTransport] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._settings = settings
        self._resolver = resolver or SystemResolver()
        self._transport_factory = transport_factory or HttpxTransport
        self._clock = clock or SystemClock()

    async def probe(self, url: str) -> VerifiedDiscoveryTarget:
        origin = _institution_origin(url)
        if origin is None:
            raise ValueError("provider target is not a safe HTTPS institution URL")
        boundary = urlsplit(origin).hostname
        if boundary is None:
            raise ValueError("provider target has no institution boundary")
        transport = self._transport_factory()
        client = ResilientHttpClient(
            FetchPolicy(
                allowed_hosts=(boundary,),
                timeout_seconds=self._settings.external_io_timeout_seconds,
                max_attempts=1,
                base_backoff_seconds=0.0,
                rate_limit_per_minute=6,
                minimum_interval_seconds=1,
                circuit_failure_threshold=1,
                circuit_reset_seconds=60.0,
                max_redirects=2,
                user_agent="SRBGSourceDiscoveryProbe/1.0",
                max_response_bytes=min(
                    MAX_DISCOVERY_TARGET_BYTES, self._settings.fixture_max_bytes
                ),
            ),
            resolver=self._resolver,
            transport=transport,
            clock=self._clock,
        )
        try:
            result = await client.get(
                origin,
                checkpoint=SourceCheckpoint(),
                accept="text/html,application/xhtml+xml,application/pdf,application/xml",
            )
        finally:
            await transport.close()
        if not result.content or result.response_sha256 is None:
            raise OSError("direct discovery target returned no verifiable body")
        final_origin = _institution_origin(result.url)
        if final_origin != origin:
            raise ValueError("direct discovery target crossed the institution boundary")
        fingerprint = _target_material_fingerprint(origin, boundary)
        return VerifiedDiscoveryTarget(
            canonical_url=origin,
            authorization_boundary=boundary,
            response_sha256=result.response_sha256,
            material_fingerprint=fingerprint,
        )


def _institution_origin(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or parsed.username is not None
        or (parsed.password is not None)
        or (port not in {None, 443})
        or (len(value) > 2048)
    ):
        return None
    normalized_host = hostname.rstrip(".").lower()
    if (
        len(normalized_host) > 253
        or re.fullmatch("(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}", normalized_host)
        is None
    ):
        return None
    return f"https://{normalized_host}/"


def _validate_classification(industries: tuple[str, ...], content_domains: tuple[str, ...]) -> None:
    if (
        not industries
        or not content_domains
        or len(industries) > 30
        or (len(content_domains) > 30)
        or any(re.fullmatch("[A-Z0-9_]{2,80}", value) is None for value in industries)
        or any(re.fullmatch("[A-Z0-9_]{2,80}", value) is None for value in content_domains)
        or any(value not in _ALLOWED_INDUSTRIES for value in industries)
        or any(value not in _ALLOWED_CONTENT_DOMAINS for value in content_domains)
    ):
        raise ValueError("automated source classification is invalid")


def _target_evidence_ref(
    target: VerifiedDiscoveryTarget,
    *,
    industries: tuple[str, ...],
    content_domains: tuple[str, ...],
) -> str:
    material = "\n".join(
        (
            target.canonical_url,
            target.response_sha256,
            *sorted(industries),
            *sorted(content_domains),
        )
    )
    return f"target-fetch:{sha256(material.encode()).hexdigest()}"


def _target_material_fingerprint(canonical_url: str, authorization_boundary: str) -> str:
    return sha256(f"{canonical_url}\n{authorization_boundary}".encode()).hexdigest()
