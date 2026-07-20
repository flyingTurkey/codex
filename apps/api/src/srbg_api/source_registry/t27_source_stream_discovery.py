"""Issue #28 research-only SourceStream discovery boundaries.

The manifest records point-in-time public evidence without granting Owner intent,
SourceAdmission, coverage credit, runtime authority, or publication visibility.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Protocol, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from srbg_api.source_registry.controlled_stream import SourceResearchDisposition


class StreamReadiness(StrEnum):
    BOUNDED = "BOUNDED"
    CANDIDATE = "CANDIDATE"


class EvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ClaimBasisPolicy(StrEnum):
    MANUFACTURER_CLAIM = "MANUFACTURER_CLAIM"
    RESEARCH_CONCLUSION = "RESEARCH_CONCLUSION"
    PROJECT_FIRST_PARTY_RECORD = "PROJECT_FIRST_PARTY_RECORD"
    INDEPENDENT_VERIFICATION = "INDEPENDENT_VERIFICATION"
    AUTHORITY_FINDING = "AUTHORITY_FINDING"


class EngineeringObject(StrEnum):
    HIGHWAY = "HIGHWAY"
    RAILWAY = "RAILWAY"
    BRIDGE = "BRIDGE"
    TUNNEL = "TUNNEL"
    BUILDING = "BUILDING"
    MINING = "MINING"
    MUNICIPAL = "MUNICIPAL"
    WATER_CONSERVANCY = "WATER_CONSERVANCY"
    PORT_WATERWAY = "PORT_WATERWAY"
    AIRPORT = "AIRPORT"
    ENERGY = "ENERGY"


def qualifies_tunnel_gas_monitoring(objects: tuple[EngineeringObject, ...]) -> bool:
    object_set = set(objects)
    return EngineeringObject.TUNNEL in object_set and bool(
        object_set & {EngineeringObject.HIGHWAY, EngineeringObject.RAILWAY}
    )


class CandidateMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=10_000)


class HttpObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    final_url: str
    method: str
    status_code: int = Field(ge=100, le=599)
    content_type: str
    redirect_count: int = Field(ge=0, le=5)
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ComplianceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    status: EvidenceStatus
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    finding: str = Field(min_length=1, max_length=2_000)


class TransportEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    https_url: str
    certificate_valid: bool
    redirect_chain_safe: bool
    finding: str = Field(min_length=1, max_length=2_000)


class NetworkVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verified_at: datetime
    public_network_safe: bool
    redirect_chain_safe: bool
    resolved_public_ips: tuple[str, ...] = Field(min_length=1)
    collection_get: HttpObservation
    detail_get: HttpObservation
    robots_evidence: ComplianceEvidence
    terms_evidence: ComplianceEvidence
    copyright_evidence: ComplianceEvidence
    access_boundary_evidence: ComplianceEvidence
    transport_evidence: TransportEvidence

    @model_validator(mode="after")
    def validate_verification(self) -> Self:
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("verification timestamp must be timezone-aware")
        if any(not ipaddress.ip_address(value).is_global for value in self.resolved_public_ips):
            raise ValueError("resolved addresses must all be public")
        return self


class StreamPrefilter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    engineering_object_terms: tuple[str, ...] = Field(min_length=1)
    lifecycle_terms: tuple[str, ...] = Field(min_length=1)
    required_result_terms: tuple[str, ...] = Field(min_length=1)
    excluded_terms: tuple[str, ...] = Field(min_length=1)


class DiscoveredSourceStream(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stream_key: str = Field(pattern=r"^[a-z0-9-]+$")
    collection_url: str
    collection_path_pattern: str
    allowed_hosts: tuple[str, ...] = Field(min_length=1)
    allowed_path_patterns: tuple[str, ...] = Field(min_length=1)
    connector_type: str
    expected_mime_types: tuple[str, ...] = Field(min_length=1)
    poll_interval_minutes: int = Field(ge=1_440, le=10_080)
    request_timeout_seconds: int = Field(ge=1, le=30)
    max_redirects: int = Field(ge=0, le=5)
    rate_limit_requests_per_minute: int = Field(ge=1, le=10)
    user_agent: str = Field(min_length=10, max_length=200)
    policy_version: str = Field(min_length=1, max_length=100)
    readiness: StreamReadiness
    disposition: SourceResearchDisposition
    blocker_codes: tuple[str, ...] = ()
    source_admission: None = None
    actual_running: bool = False
    pause_appended: bool = False
    coverage_credit_granted: bool = False
    content_relevance: str
    claim_basis_policy: ClaimBasisPolicy
    permitted_claim_bases: tuple[ClaimBasisPolicy, ...] = Field(min_length=1)
    reader_fields: tuple[str, ...] = Field(min_length=1)
    public_full_text_redistribution: bool = False
    prefilter: StreamPrefilter
    verification: NetworkVerification

    @model_validator(mode="after")
    def enforce_research_boundary(self) -> Self:
        parsed = urlsplit(self.collection_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("collection URL must be an absolute HTTP(S) URL")
        if parsed.hostname not in self.allowed_hosts:
            raise ValueError("collection host must be explicitly allowed")
        if parsed.query or "search" in parsed.path.casefold() or parsed.path in ("", "/"):
            raise ValueError("root and search URLs cannot be SourceStreams")
        if re.fullmatch(self.collection_path_pattern, parsed.path) is None:
            raise ValueError("collection URL must match the exact collection path")
        if not any(re.fullmatch(pattern, parsed.path) for pattern in self.allowed_path_patterns):
            raise ValueError("collection path is outside the saved path boundary")
        if (
            self.source_admission is not None
            or self.actual_running
            or self.pause_appended
            or self.coverage_credit_granted
        ):
            raise ValueError("discovery cannot grant admission, runtime, PAUSE, or coverage credit")

        evidence = self.verification
        if evidence.collection_get.url != self.collection_url:
            raise ValueError("collection observation must identify the saved collection URL")
        for observation in (evidence.collection_get, evidence.detail_get):
            final = urlsplit(observation.final_url)
            if (
                final.hostname not in self.allowed_hosts
                or not any(
                    re.fullmatch(pattern, final.path) for pattern in self.allowed_path_patterns
                )
                or observation.redirect_count > self.max_redirects
            ):
                raise ValueError("observed redirect escaped the saved network or path boundary")
            observed_mime = observation.content_type.partition(";")[0].strip().casefold()
            if observed_mime not in self.expected_mime_types:
                raise ValueError("observed MIME is outside the expected boundary")

        if self.disposition is SourceResearchDisposition.ADMISSION_READY:
            compliance = (
                evidence.robots_evidence.status,
                evidence.terms_evidence.status,
                evidence.copyright_evidence.status,
                evidence.access_boundary_evidence.status,
            )
            if (
                self.readiness is not StreamReadiness.BOUNDED
                or parsed.scheme != "https"
                or not evidence.public_network_safe
                or not evidence.redirect_chain_safe
                or not evidence.transport_evidence.certificate_valid
                or not evidence.transport_evidence.redirect_chain_safe
                or evidence.collection_get.status_code != 200
                or any(status is not EvidenceStatus.VERIFIED for status in compliance)
                or self.blocker_codes
            ):
                raise ValueError("ADMISSION_READY requires a bounded, verified, safe HTTPS stream")
        elif not self.blocker_codes:
            raise ValueError("non-ready research disposition must preserve blocker codes")
        return self

    def accepts(self, candidate: CandidateMetadata) -> bool:
        text = f"{candidate.title}\n{candidate.body}".casefold()
        if any(term.casefold() in text for term in self.prefilter.excluded_terms):
            return False
        return all(
            (
                any(
                    term.casefold() in text
                    for term in self.prefilter.engineering_object_terms
                ),
                any(term.casefold() in text for term in self.prefilter.lifecycle_terms),
                any(term.casefold() in text for term in self.prefilter.required_result_terms),
            )
        )

    def allows_claim_basis(self, basis: ClaimBasisPolicy) -> bool:
        return basis in self.permitted_claim_bases


class DiscoveredSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registry_code: str
    institution: str
    official_origin: str
    desired_enabled: bool = False
    streams: tuple[DiscoveredSourceStream, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def remain_disabled(self) -> Self:
        if self.desired_enabled:
            raise ValueError("discovery cannot change Owner desired_enabled")
        return self


class DiscoveryManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    issue_number: int
    parent_spec_number: int
    closure_eligible: bool
    owner_gold_evidence: None = None
    deepseek_real_schema_success: None = None
    runtime_window_evidence: None = None
    closeout_go_evidence: None = None
    sources: tuple[DiscoveredSource, ...]

    @model_validator(mode="after")
    def enforce_issue_scope(self) -> Self:
        if self.parent_spec_number != 1 or self.issue_number != 28:
            raise ValueError("manifest must remain scoped to Issue #28 and Spec #1")
        if not self.schema_version.startswith("t27-"):
            raise ValueError("manifest schema version must remain scoped to T27")
        expected = {"RES-001": "中国公路学会", "RES-005": "隧道建设\uff08中英文\uff09"}
        actual = {source.registry_code: source.institution for source in self.sources}
        if actual != expected or len(self.sources) != 2:
            raise ValueError("T27 manifest must contain exactly RES-001 and RES-005")
        stream_keys = [stream.stream_key for source in self.sources for stream in source.streams]
        if len(stream_keys) != len(set(stream_keys)):
            raise ValueError("SourceStream keys must be unique")
        calculated_closure = all(
            stream.readiness is StreamReadiness.BOUNDED
            and stream.disposition is SourceResearchDisposition.ADMISSION_READY
            for source in self.sources
            for stream in source.streams
        )
        if self.closure_eligible is not calculated_closure:
            raise ValueError("closure eligibility must be derived from every stream")
        return self


class ResearchDispositionRepository(Protocol):
    async def record_research_disposition(
        self,
        *,
        source_registry_code: str,
        stream_key: str,
        disposition: SourceResearchDisposition,
        research_sha256: str,
    ) -> None: ...


async def record_discovery_dispositions(
    manifest: DiscoveryManifest,
    repository: ResearchDispositionRepository,
) -> None:
    """Append research routing facts through a deliberately narrow repository port."""

    for source in manifest.sources:
        for stream in source.streams:
            canonical = json.dumps(
                stream.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            await repository.record_research_disposition(
                source_registry_code=source.registry_code,
                stream_key=stream.stream_key,
                disposition=stream.disposition,
                research_sha256=hashlib.sha256(canonical).hexdigest(),
            )


__all__ = [
    "CandidateMetadata",
    "ClaimBasisPolicy",
    "DiscoveryManifest",
    "EngineeringObject",
    "SourceResearchDisposition",
    "StreamReadiness",
    "qualifies_tunnel_gas_monitoring",
    "record_discovery_dispositions",
]
