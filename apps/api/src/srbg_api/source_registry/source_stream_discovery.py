"""Validated research-only SourceStream discovery manifests.

Discovery facts deliberately stop before Owner intent, SourceAdmission, or runtime
authorization.  They make a bounded collection reviewable without turning it on.
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
    SAMPLE = "SAMPLE"
    MANUAL_ONLY = "MANUAL_ONLY"


class EvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ClaimBasisPolicy(StrEnum):
    MANUFACTURER_CLAIM = "MANUFACTURER_CLAIM"
    RESEARCH_CONCLUSION = "RESEARCH_CONCLUSION"
    PROJECT_FIRST_PARTY_RECORD = "PROJECT_FIRST_PARTY_RECORD"
    INDEPENDENT_VERIFICATION = "INDEPENDENT_VERIFICATION"


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
    response_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ComplianceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    status: EvidenceStatus
    http_status_code: int | None = Field(default=None, ge=100, le=599)
    response_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    finding: str = Field(min_length=1, max_length=1_000)


class NetworkVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verified_at: datetime
    public_network_safe: bool
    redirect_chain_safe: bool
    resolved_public_ips: tuple[str, ...] = Field(min_length=1)
    collection_get: HttpObservation
    detail_get: HttpObservation | None
    robots_evidence: ComplianceEvidence
    terms_evidence: ComplianceEvidence
    copyright_evidence: ComplianceEvidence

    @model_validator(mode="after")
    def require_utc_timestamp(self) -> Self:
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("verification timestamp must be timezone-aware")
        if any(not ipaddress.ip_address(value).is_global for value in self.resolved_public_ips):
            raise ValueError("resolved addresses must all be public")
        return self


class StreamPrefilter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    engineering_object_terms: tuple[str, ...] = Field(min_length=1)
    lifecycle_terms: tuple[str, ...] = Field(min_length=1)
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
    poll_interval_minutes: int | None = Field(default=None, ge=1_440, le=10_080)
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
    content_relevance: str
    claim_basis_policy: ClaimBasisPolicy
    permitted_claim_bases: tuple[ClaimBasisPolicy, ...] = Field(min_length=1)
    public_redistribution: bool
    prefilter: StreamPrefilter
    verification: NetworkVerification

    @model_validator(mode="after")
    def enforce_research_only_boundary(self) -> Self:
        parsed = urlsplit(self.collection_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("collection URL must be an absolute HTTP(S) URL")
        if parsed.scheme == "http":
            if self.disposition is SourceResearchDisposition.ADMISSION_READY:
                raise ValueError("HTTP-only collection cannot be ADMISSION_READY")
            if "HTTPS_UNAVAILABLE" not in self.blocker_codes:
                raise ValueError("HTTP-only collection must preserve HTTPS_UNAVAILABLE")
        if parsed.hostname not in self.allowed_hosts:
            raise ValueError("collection host must be explicitly allowed")
        if parsed.query or "search" in parsed.path.casefold() or parsed.path in ("", "/"):
            raise ValueError("root and search URLs cannot be SourceStreams")
        if re.fullmatch(self.collection_path_pattern, parsed.path) is None:
            raise ValueError("collection URL must match the exact collection path")
        if not any(re.fullmatch(pattern, parsed.path) for pattern in self.allowed_path_patterns):
            raise ValueError("collection path is outside the saved path boundary")
        if self.source_admission is not None or self.actual_running:
            raise ValueError("discovery cannot grant admission or runtime authority")
        if self.disposition is not SourceResearchDisposition.MANUAL_SHADOW and (
            self.poll_interval_minutes is None
        ):
            raise ValueError("automatable research dispositions require a candidate interval")

        evidence = self.verification
        if evidence.collection_get.url != self.collection_url:
            raise ValueError("collection observation must identify the saved collection URL")
        if self.connector_type == "HTML_LIST_DETAIL" and evidence.detail_get is None:
            raise ValueError("HTML_LIST_DETAIL requires a detail observation")
        if self.connector_type == "HTML_LIST_METADATA_LINK" and evidence.detail_get is not None:
            raise ValueError("metadata-only connector cannot fetch a detail observation")
        observations = (evidence.collection_get,) + (
            (evidence.detail_get,) if evidence.detail_get is not None else ()
        )
        for observation in observations:
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
            )
            if (
                self.readiness is not StreamReadiness.BOUNDED
                or any(status is not EvidenceStatus.VERIFIED for status in compliance)
                or not evidence.public_network_safe
                or not evidence.redirect_chain_safe
                or evidence.collection_get.status_code != 200
                or self.blocker_codes
            ):
                raise ValueError("ADMISSION_READY requires a bounded stream and verified evidence")
        if self.disposition is SourceResearchDisposition.MANUAL_SHADOW and not self.blocker_codes:
            raise ValueError("MANUAL_SHADOW must preserve its automation blocker")
        return self

    def accepts(self, candidate: CandidateMetadata) -> bool:
        text = f"{candidate.title}\n{candidate.body}".casefold()
        if any(term.casefold() in text for term in self.prefilter.excluded_terms):
            return False
        return any(
            term.casefold() in text for term in self.prefilter.engineering_object_terms
        ) and any(term.casefold() in text for term in self.prefilter.lifecycle_terms)

    def allows_claim_basis(self, basis: ClaimBasisPolicy) -> bool:
        return basis in self.permitted_claim_bases


class DiscoveredSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registry_code: str
    institution: str
    official_origin: str
    aliases: tuple[str, ...] = ()
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
    sources: tuple[DiscoveredSource, ...]

    @model_validator(mode="after")
    def enforce_issue_scope(self) -> Self:
        issue_scopes = {
            17: ("t16-", {"GOV-MWR", "GOV-NEA"}),
            21: ("t20-", {"ENT-003", "ENT-009"}),
        }
        if self.parent_spec_number != 1 or self.issue_number not in issue_scopes:
            raise ValueError("manifest must remain scoped to a supported Issue and Spec #1")
        version_prefix, expected_codes = issue_scopes[self.issue_number]
        if not self.schema_version.startswith(version_prefix):
            raise ValueError("manifest schema version does not match its Issue scope")
        codes = [source.registry_code for source in self.sources]
        if set(codes) != expected_codes or len(codes) != 2:
            raise ValueError("manifest must contain exactly its Issue-scoped institutions")
        stream_keys = [stream.stream_key for source in self.sources for stream in source.streams]
        if len(stream_keys) != len(set(stream_keys)):
            raise ValueError("SourceStream keys must be unique")
        return self


class T29DiscoveryManifest(BaseModel):
    """Issue #30 research facts for CABR and CCCC, without admission authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    issue_number: int
    parent_spec_number: int
    sources: tuple[DiscoveredSource, ...]

    @model_validator(mode="after")
    def enforce_issue_scope(self) -> Self:
        if self.parent_spec_number != 1 or self.issue_number != 30:
            raise ValueError("manifest must remain scoped to Issue #30 and Spec #1")
        if not self.schema_version.startswith("t29-"):
            raise ValueError("manifest schema version must remain scoped to T29")
        codes = [source.registry_code for source in self.sources]
        if codes != ["RES-003", "ENT-001"]:
            raise ValueError("T29 manifest must contain RES-003 then ENT-001 exactly once")
        cccc = self.sources[1]
        if (
            cccc.institution != "中国交建"
            or cccc.official_origin != "https://www.ccccltd.cn/"
            or "中国交通建设集团" not in cccc.aliases
        ):
            raise ValueError("T29 must preserve the canonical CCCC Source and alias")
        stream_keys = [stream.stream_key for source in self.sources for stream in source.streams]
        if len(stream_keys) != len(set(stream_keys)):
            raise ValueError("SourceStream keys must be unique")
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
    manifest: DiscoveryManifest | T29DiscoveryManifest,
    repository: ResearchDispositionRepository,
) -> None:
    """Append only research routing facts; no stronger repository capability is accepted."""

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
    "SourceResearchDisposition",
    "StreamReadiness",
    "T29DiscoveryManifest",
    "record_discovery_dispositions",
]
