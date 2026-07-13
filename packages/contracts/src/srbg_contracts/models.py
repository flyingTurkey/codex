"""Canonical public contracts shared by API and Worker processes."""

from datetime import datetime
from enum import StrEnum
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

API_VERSION: Final[Literal["v1"]] = "v1"
CONTENT_SCHEMA_VERSION: Final[Literal["1.0.0"]] = "1.0.0"


class ContractModel(BaseModel):
    """Base class that rejects fields not declared by the public contract."""

    model_config = ConfigDict(extra="forbid")


class UserRole(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    SOURCE_ADMIN = "source_admin"
    PLATFORM_ADMIN = "platform_admin"
    AUDITOR = "auditor"


class Channel(StrEnum):
    DIGITAL = "DIGITAL"
    SAFETY = "SAFETY"


class SourceChannel(StrEnum):
    DIGITAL = "DIGITAL"
    SAFETY = "SAFETY"
    BOTH = "BOTH"


class SourceState(StrEnum):
    CANDIDATE = "CANDIDATE"
    COMPLIANCE_REVIEW = "COMPLIANCE_REVIEW"
    FIXTURE_TEST = "FIXTURE_TEST"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"


class SourceType(StrEnum):
    GOVERNMENT = "government"
    STANDARDS = "standards"
    JOURNAL = "journal"
    RESEARCH_INSTITUTE = "research_institute"
    ASSOCIATION = "association"
    ENTERPRISE = "enterprise"
    MEDIA = "media"
    ACADEMIC_API = "academic_api"
    ACADEMIC_DATABASE = "academic_database"


class AuthorityLevel(StrEnum):
    A0 = "A0"
    A1 = "A1"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class SourcePolicyStatus(StrEnum):
    DRAFT = "DRAFT"
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ReviewEvidenceResult(StrEnum):
    ALLOWED = "ALLOWED"
    RESTRICTED = "RESTRICTED"
    NOT_PRESENT = "NOT_PRESENT"
    BLOCKED = "BLOCKED"


class StoragePolicy(StrEnum):
    RAW_EVIDENCE_ALLOWED = "RAW_EVIDENCE_ALLOWED"
    METADATA_ONLY = "METADATA_ONLY"
    LINK_ONLY = "LINK_ONLY"


class DisplayPolicy(StrEnum):
    METADATA_EXCERPT_LINK = "METADATA_EXCERPT_LINK"
    OFFICIAL_READER_LINK = "OFFICIAL_READER_LINK"
    LINK_ONLY = "LINK_ONLY"


class ScanStatus(StrEnum):
    CLEAN = "CLEAN"
    REJECTED = "REJECTED"


class ItemType(StrEnum):
    DIGITAL_CASE = "DIGITAL_CASE"
    JOURNAL_PAPER = "JOURNAL_PAPER"
    SOFTWARE_PRODUCT = "SOFTWARE_PRODUCT"
    IOT_PRODUCT = "IOT_PRODUCT"
    LOW_ALTITUDE_EQUIPMENT = "LOW_ALTITUDE_EQUIPMENT"
    AI_EQUIPMENT = "AI_EQUIPMENT"
    SAFETY_REGULATION = "SAFETY_REGULATION"
    SAFETY_CASE = "SAFETY_CASE"


class RiskLevel(StrEnum):
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


class DependencyName(StrEnum):
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    OBJECT_STORAGE = "object_storage"


class DependencyCheck(ContractModel):
    status: Literal["up", "down"]
    latency_ms: int = Field(ge=0)
    error_code: Literal["timeout", "unavailable", "misconfigured"] | None = None


class LivenessResponse(ContractModel):
    status: Literal["ok"] = "ok"
    service: Literal["api"] = "api"
    timestamp: datetime


class ReadinessResponse(ContractModel):
    status: Literal["ready", "not_ready"]
    service: Literal["api"] = "api"
    timestamp: datetime
    checks: dict[DependencyName, DependencyCheck]


class VersionResponse(ContractModel):
    api_version: Literal["v1"] = API_VERSION
    content_schema_version: Literal["1.0.0"] = CONTENT_SCHEMA_VERSION


class ProblemDetails(ContractModel):
    type: str = "about:blank"
    title: str
    status: int = Field(ge=400, le=599)
    detail: str | None = None
    instance: str | None = None
    request_id: str


class CursorPage[T](ContractModel):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool


HttpUrlString = str
Sha256String = str


class CreateSourceRequest(ContractModel):
    name: str = Field(min_length=1, max_length=200)
    base_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
    channel: SourceChannel
    source_type: SourceType
    authority_level: AuthorityLevel
    priority: Literal["P0", "P1", "P2"]
    collection_method: str = Field(min_length=1, max_length=50)
    poll_interval_minutes: int = Field(ge=1, le=10080)
    owner: str = Field(min_length=1, max_length=100)


class ReviewEvidence(ContractModel):
    result: ReviewEvidenceResult
    evidence_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
    evidence_sha256: Sha256String | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    checked_at: datetime


class CopyrightPolicy(ContractModel):
    storage_policy: StoragePolicy
    display_policy: DisplayPolicy
    fulltext_allowed: bool
    image_allowed: bool
    excerpt_max_chars: int = Field(ge=0, le=1000)
    attribution_template: str = Field(min_length=1, max_length=500)


class SourceAccessPolicy(ContractModel):
    allowed_domains: list[str] = Field(min_length=1)
    requires_auth: bool
    rate_limit_per_minute: int = Field(ge=1, le=10000)
    user_agent: str = Field(min_length=1, max_length=300)


class SourcePolicyReviewSubmission(ContractModel):
    valid_until: datetime
    approval_id: str = Field(min_length=1, max_length=200)


class SourcePolicySubmission(ContractModel):
    policy_version: str = Field(min_length=1, max_length=50)
    status: SourcePolicyStatus
    robots_review: ReviewEvidence
    terms_review: ReviewEvidence
    copyright: CopyrightPolicy
    access: SourceAccessPolicy
    review: SourcePolicyReviewSubmission


class SourceTransitionRequest(ContractModel):
    target_state: SourceState
    reason: str = Field(min_length=1, max_length=500)


class SourceActionRequest(ContractModel):
    reason: str = Field(min_length=1, max_length=500)


class OnboardingCheckEvidence(ContractModel):
    code: str = Field(min_length=1, max_length=100)
    evidence_ref: str = Field(min_length=1, max_length=2048)
    evidence_sha256: Sha256String | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class SourceOnboardingSubmission(ContractModel):
    checks: list[OnboardingCheckEvidence] = Field(min_length=11)
    valid_until: datetime


class SourceSummary(ContractModel):
    id: UUID
    registry_code: str | None
    name: str
    base_url: str
    channel: SourceChannel
    source_type: SourceType
    authority_level: AuthorityLevel
    priority: str
    state: SourceState
    enabled: bool
    effective_active: bool
    fixture_count: int = Field(ge=0)
    created_at: datetime


class SourceEligibility(ContractModel):
    effective_active: bool
    policy_valid: bool
    onboarding_valid: bool
    onboarding_policy_matches: bool
    required_checks_complete: bool
    fixture_count: int = Field(ge=0)
    required_fixture_count: int = 30
    fixture_set_sha256: str | None = None
    missing_reasons: list[str]


class SourceDetail(SourceSummary):
    collection_method: str
    poll_interval_minutes: int
    owner: str
    eligibility: SourceEligibility


class RawObjectSummary(ContractModel):
    id: UUID
    sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    detected_mime: Literal["text/html", "application/pdf"]
    byte_size: int = Field(ge=0)
    scan_status: ScanStatus


class DocumentVersionSummary(ContractModel):
    id: UUID
    version_number: int = Field(ge=1)
    content_hash: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    original_filename: str
    title: str | None
    acquired_at: datetime


class DocumentDetail(ContractModel):
    id: UUID
    source_id: UUID
    source_name: str
    canonical_url: str
    document_kind: Literal["HTML", "PDF"]
    first_discovered_at: datetime
    current_version: DocumentVersionSummary
    raw_object: RawObjectSummary


class FixtureUploadResponse(ContractModel):
    document: DocumentDetail
    raw_object_deduplicated: bool
    version_created: bool


class MeResponse(ContractModel):
    user_id: UUID
    display_name: str
    roles: list[UserRole]
    local_identity: bool
