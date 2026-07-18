"""Canonical public contracts shared by API and Worker processes."""

import re
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

API_VERSION: Final[Literal["v1"]] = "v1"
CONTENT_SCHEMA_VERSION: Final[Literal["1.1.0"]] = "1.1.0"


class ContractModel(BaseModel):
    """Base class that rejects fields not declared by the public contract."""

    model_config = ConfigDict(extra="forbid")


def _validate_governance_reason(value: str) -> str:
    lowered = value.casefold()
    if (
        any(ord(character) < 32 or ord(character) == 127 for character in value)
        or re.search("(?:https?|vault)://|\\S+@\\S+", lowered)
        or re.search(
            "(?:^|[^a-z])(?:api[_-]?key|authorization|bearer|cookie|credential|password|secret|token|vault)(?:[^a-z]|$)",
            lowered,
        )
    ):
        raise ValueError("governance reason contains forbidden sensitive material")
    return value


GovernanceReason = Annotated[
    str, Field(min_length=1, max_length=500), AfterValidator(_validate_governance_reason)
]


def _validate_evidence_reference(value: str) -> str:
    lowered = value.casefold()
    if (
        any(ord(character) < 33 or ord(character) == 127 for character in value)
        or re.search("://[^/\\s]+@", value)
        or re.search(
            "[?&](?:api[_-]?key|access[_-]?key|auth(?:orization|_token)?|bearer|client[_-]?secret|cookie|credential|password|secret|session|signature|token)=[^&]+",
            lowered,
        )
    ):
        raise ValueError("evidence reference contains forbidden sensitive material")
    return value


CountryCode = Annotated[str, Field(pattern="^[A-Z]{2}$")]
RegionCode = Annotated[
    str, Field(min_length=2, max_length=16, pattern="^[A-Z0-9]{2,3}(?:-[A-Z0-9]{1,6})?$")
]
LanguageTag = Annotated[
    str, Field(min_length=2, max_length=35, pattern="^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
]
AssessmentReasonCode = Annotated[
    str, Field(min_length=1, max_length=100, pattern="^[A-Z][A-Z0-9_]*$")
]
EvidenceReference = Annotated[
    str, Field(min_length=1, max_length=500), AfterValidator(_validate_evidence_reference)
]


def _normalize_to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


AssessmentTimestamp = Annotated[AwareDatetime, AfterValidator(_normalize_to_utc)]


class UserRole(StrEnum):
    OWNER = "owner"


class Channel(StrEnum):
    DIGITAL = "DIGITAL"
    SAFETY = "SAFETY"


class PublicationRiskTier(StrEnum):
    """Publication handling risk; it never grants content visibility."""

    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


class ContentSeverity(StrEnum):
    """Subject-matter severity, independent from publication handling risk."""

    UNASSESSED = "UNASSESSED"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProjectionLevel(StrEnum):
    """Maximum content projection level decided by server-side policy."""

    NONE = "NONE"
    METADATA_ONLY = "METADATA_ONLY"
    FULL = "FULL"


class SourceChannel(StrEnum):
    DIGITAL = "DIGITAL"
    SAFETY = "SAFETY"
    BOTH = "BOTH"


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
    UNKNOWN = "UNKNOWN"


class SourceIndependenceLevel(StrEnum):
    EDITORIALLY_INDEPENDENT = "EDITORIALLY_INDEPENDENT"
    PARTIALLY_INDEPENDENT = "PARTIALLY_INDEPENDENT"
    NOT_INDEPENDENT = "NOT_INDEPENDENT"
    UNKNOWN = "UNKNOWN"


class SourceIndustry(StrEnum):
    HIGHWAY = "HIGHWAY"
    BRIDGE = "BRIDGE"
    TUNNEL = "TUNNEL"
    RAILWAY = "RAILWAY"
    RAIL_TRANSIT = "RAIL_TRANSIT"
    WATER_CONSERVANCY = "WATER_CONSERVANCY"
    MUNICIPAL = "MUNICIPAL"
    BUILDING = "BUILDING"
    ENERGY = "ENERGY"
    PORT_WATERWAY = "PORT_WATERWAY"
    AIRPORT = "AIRPORT"
    GENERAL_TRANSPORT = "GENERAL_TRANSPORT"
    UNKNOWN = "UNKNOWN"


class SourceContentDomain(StrEnum):
    DIGITAL_TRANSFORMATION_CASE = "DIGITAL_TRANSFORMATION_CASE"
    RESEARCH_PAPER = "RESEARCH_PAPER"
    SOFTWARE_PLATFORM = "SOFTWARE_PLATFORM"
    IOT_EQUIPMENT = "IOT_EQUIPMENT"
    LOW_ALTITUDE_EQUIPMENT = "LOW_ALTITUDE_EQUIPMENT"
    AI_APPLICATION = "AI_APPLICATION"
    SAFETY_REGULATION = "SAFETY_REGULATION"
    STANDARD_GUIDANCE = "STANDARD_GUIDANCE"
    ACCIDENT_INVESTIGATION = "ACCIDENT_INVESTIGATION"
    OFFICIAL_NOTICE = "OFFICIAL_NOTICE"
    PENALTY = "PENALTY"
    RECTIFICATION = "RECTIFICATION"
    UNKNOWN = "UNKNOWN"


class SourceDeclaredRole(StrEnum):
    OFFICIAL_PRIMARY = "OFFICIAL_PRIMARY"
    OFFICIAL_SECONDARY = "OFFICIAL_SECONDARY"
    STANDARDS_PUBLISHER = "STANDARDS_PUBLISHER"
    RESEARCH_PUBLISHER = "RESEARCH_PUBLISHER"
    MANUFACTURER = "MANUFACTURER"
    INDEPENDENT_REPORTER = "INDEPENDENT_REPORTER"
    AGGREGATOR = "AGGREGATOR"
    UNKNOWN = "UNKNOWN"


class ConnectorType(StrEnum):
    RSS_ATOM = "RSS_ATOM"
    JSON_API = "JSON_API"
    SITEMAP = "SITEMAP"
    LIST_DETAIL = "LIST_DETAIL"
    DIRECT_PDF = "DIRECT_PDF"
    MANUAL_IMPORT = "MANUAL_IMPORT"


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


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PublicationStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class EvidenceStatus(StrEnum):
    WITHHELD = "WITHHELD"
    VERIFIED = "VERIFIED"


class DocumentState(StrEnum):
    UPDATED = "UPDATED"
    RE_REVIEW_PENDING = "RE_REVIEW_PENDING"
    WITHDRAWN = "WITHDRAWN"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class VersionProcessingState(StrEnum):
    RECEIVED = "RECEIVED"
    SECURITY_PASSED = "SECURITY_PASSED"
    PARSING = "PARSING"
    OCR_PENDING = "OCR_PENDING"
    OCR_COMPLETE = "OCR_COMPLETE"
    READY = "READY"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


class VersionChangeType(StrEnum):
    INITIAL = "INITIAL"
    METADATA_ONLY = "METADATA_ONLY"
    CONTENT_UPDATE = "CONTENT_UPDATE"
    CORRECTION = "CORRECTION"
    AMENDMENT = "AMENDMENT"
    REPLACEMENT = "REPLACEMENT"
    WITHDRAWAL = "WITHDRAWAL"


class VersionReviewState(StrEnum):
    DETECTED = "DETECTED"
    NO_REVIEW_REQUIRED = "NO_REVIEW_REQUIRED"
    RE_REVIEW_PENDING = "RE_REVIEW_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RegulationStatus(StrEnum):
    DRAFT = "DRAFT"
    NOT_EFFECTIVE = "NOT_EFFECTIVE"
    EFFECTIVE = "EFFECTIVE"
    AMENDED = "AMENDED"
    REPEALED = "REPEALED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class RegulationClassification(StrEnum):
    LAW = "LAW"
    ADMINISTRATIVE_REGULATION = "ADMINISTRATIVE_REGULATION"
    DEPARTMENT_RULE = "DEPARTMENT_RULE"
    NORMATIVE_DOCUMENT = "NORMATIVE_DOCUMENT"
    STANDARD_OR_GUIDE = "STANDARD_OR_GUIDE"


class SafetyCaseReportStage(StrEnum):
    INITIAL_REPORT = "INITIAL_REPORT"
    FOLLOW_UP_REPORT = "FOLLOW_UP_REPORT"
    FINAL_INVESTIGATION = "FINAL_INVESTIGATION"
    ENFORCEMENT = "ENFORCEMENT"
    RECTIFICATION = "RECTIFICATION"


class SafetyCaseProfileMetadataField(StrEnum):
    """Profile fields that require accepted claim-and-evidence authorization."""

    REPORT_STAGE = "report_stage"
    INCIDENT_STATUS = "incident_status"
    ACCIDENT_TYPE = "accident_type"
    ENGINEERING_TYPE = "engineering_type"
    OCCURRED_AT = "occurred_at"
    REGION_NAME = "region_name"
    PROJECT_NAME = "project_name"
    RECTIFICATION_HAS_OPEN_ISSUES = "rectification_has_open_issues"
    SIMILAR_SCENARIO_TAGS = "similar_scenario_tags"
    PREVENTION_MEASURE_TAGS = "prevention_measure_tags"


class IncidentStatus(StrEnum):
    UNVERIFIED_LEAD = "UNVERIFIED_LEAD"
    INITIAL_OFFICIAL_REPORT = "INITIAL_OFFICIAL_REPORT"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    FINAL_INVESTIGATION_REPORT = "FINAL_INVESTIGATION_REPORT"
    ENFORCEMENT_DECISION = "ENFORCEMENT_DECISION"
    RECTIFICATION_FOLLOW_UP = "RECTIFICATION_FOLLOW_UP"
    CLOSED = "CLOSED"
    CORRECTED = "CORRECTED"
    WITHDRAWN = "WITHDRAWN"


class EventRelation(StrEnum):
    FOLLOW_UP = "FOLLOW_UP"
    INVESTIGATES = "INVESTIGATES"
    PENALIZES = "PENALIZES"
    RECTIFIES = "RECTIFIES"
    CORRECTS = "CORRECTS"


class CriticalSafetyField(StrEnum):
    DEATH_COUNT = "DEATH_COUNT"
    INJURY_COUNT = "INJURY_COUNT"
    LOSS_AMOUNT_MINOR = "LOSS_AMOUNT_MINOR"
    OFFICIAL_DIRECT_CAUSES = "OFFICIAL_DIRECT_CAUSES"
    RESPONSIBILITY_FINDINGS = "RESPONSIBILITY_FINDINGS"


class SafetyCaseFactField(StrEnum):
    OCCURRED_AT = "OCCURRED_AT"
    REGION = "REGION"
    PROJECT_NAME = "PROJECT_NAME"
    HAZARD_TYPE = "HAZARD_TYPE"
    ENGINEERING_TYPE = "ENGINEERING_TYPE"
    DEATH_COUNT = "DEATH_COUNT"
    INJURY_COUNT = "INJURY_COUNT"
    LOSS_AMOUNT_MINOR = "LOSS_AMOUNT_MINOR"
    OFFICIAL_DIRECT_CAUSES = "OFFICIAL_DIRECT_CAUSES"
    RESPONSIBILITY_FINDINGS = "RESPONSIBILITY_FINDINGS"
    CORRECTIVE_ACTIONS = "CORRECTIVE_ACTIONS"


class SimilarScenarioTag(StrEnum):
    HIGHWAY_OPERATION_GEOLOGICAL_RISK = "HIGHWAY_OPERATION_GEOLOGICAL_RISK"
    ROADBED_SLOPE_INSTABILITY = "ROADBED_SLOPE_INSTABILITY"
    BRIDGE_APPROACH_TRANSITION = "BRIDGE_APPROACH_TRANSITION"
    EXTREME_WEATHER_EXPOSURE = "EXTREME_WEATHER_EXPOSURE"
    TEMPORARY_STRUCTURE_FAILURE = "TEMPORARY_STRUCTURE_FAILURE"
    TUNNEL_GEOLOGICAL_RISK = "TUNNEL_GEOLOGICAL_RISK"


class PreventionMeasureTag(StrEnum):
    HAZARD_IDENTIFICATION = "HAZARD_IDENTIFICATION"
    MONITORING_AND_EARLY_WARNING = "MONITORING_AND_EARLY_WARNING"
    INSPECTION_AND_MAINTENANCE = "INSPECTION_AND_MAINTENANCE"
    DESIGN_REVIEW = "DESIGN_REVIEW"
    CONSTRUCTION_QUALITY_CONTROL = "CONSTRUCTION_QUALITY_CONTROL"
    EMERGENCY_PREPAREDNESS = "EMERGENCY_PREPAREDNESS"
    TRAFFIC_OPERATION_RISK_CONTROL = "TRAFFIC_OPERATION_RISK_CONTROL"
    RESPONSIBILITY_AND_OVERSIGHT = "RESPONSIBILITY_AND_OVERSIGHT"


class DigitalCaseSourceNature(StrEnum):
    GOVERNMENT_CASE_COLLECTION = "GOVERNMENT_CASE_COLLECTION"
    ENTERPRISE_SELF_REPORT = "ENTERPRISE_SELF_REPORT"


class MaturityLevel(StrEnum):
    CONCEPT = "CONCEPT"
    LAB_PROTOTYPE = "LAB_PROTOTYPE"
    ENGINEERING_PROTOTYPE = "ENGINEERING_PROTOTYPE"
    PILOT = "PILOT"
    SINGLE_PROJECT_PRODUCTION = "SINGLE_PROJECT_PRODUCTION"
    MULTI_PROJECT_REPLICATION = "MULTI_PROJECT_REPLICATION"
    ENTERPRISE_SCALE = "ENTERPRISE_SCALE"
    UNKNOWN = "UNKNOWN"


class ProductEvidenceLevel(StrEnum):
    VENDOR_CLAIM_ONLY = "VENDOR_CLAIM_ONLY"
    PROJECT_EVIDENCE = "PROJECT_EVIDENCE"
    RESEARCH_EVIDENCE = "RESEARCH_EVIDENCE"
    INDEPENDENT_VALIDATION = "INDEPENDENT_VALIDATION"
    OFFICIAL_CERTIFICATION = "OFFICIAL_CERTIFICATION"
    UNKNOWN = "UNKNOWN"


class ProductPermitStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ProductCapabilityKind(StrEnum):
    PROMOTIONAL_CLAIM = "PROMOTIONAL_CLAIM"
    VERIFIED_CAPABILITY = "VERIFIED_CAPABILITY"


class PaperType(StrEnum):
    ARTICLE = "ARTICLE"
    REVIEW = "REVIEW"
    METHOD = "METHOD"
    CASE_STUDY = "CASE_STUDY"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class PaperAccessLevel(StrEnum):
    METADATA_ONLY = "METADATA_ONLY"
    ABSTRACT_ALLOWED = "ABSTRACT_ALLOWED"
    OPEN_FULLTEXT = "OPEN_FULLTEXT"


class PaperOpenStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class PaperRelationStatus(StrEnum):
    CURRENT = "CURRENT"
    CORRECTED = "CORRECTED"
    RETRACTED = "RETRACTED"
    WITHDRAWN = "WITHDRAWN"


class PaperRelationType(StrEnum):
    CORRECTS = "CORRECTS"
    SUPERSEDES = "SUPERSEDES"
    RETRACTS = "RETRACTS"


class AbstractAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_PROVIDED = "NOT_PROVIDED"
    LICENCE_UNCLEAR = "LICENCE_UNCLEAR"


class OutcomeVerification(StrEnum):
    CLAIMED = "CLAIMED"
    VERIFIED = "VERIFIED"


class RecommendedAction(StrEnum):
    READ_ORIGINAL = "READ_ORIGINAL"
    SAVE = "SAVE"
    FOLLOW = "FOLLOW"
    TECHNICAL_RESEARCH = "TECHNICAL_RESEARCH"


class DigitalCaseEntityType(StrEnum):
    ORGANIZATION = "ORGANIZATION"
    TECHNOLOGY = "TECHNOLOGY"
    PROJECT = "PROJECT"


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
    content_schema_version: Literal["1.1.0"] = CONTENT_SCHEMA_VERSION
    search_schema_version: Literal["1.0.0"] = "1.0.0"
    semantic_search_enabled: bool = False


class MetricSample(ContractModel):
    code: str = Field(pattern="^[A-Z][A-Z0-9_]+$", max_length=80)
    value: int | float
    unit: Literal["count", "percent", "ms", "seconds", "minutes", "microusd"]
    status: Literal["PASS", "FAIL", "UNKNOWN"]


class FeedbackRequest(ContractModel):
    item_id: UUID | None = None
    event_id: UUID | None = None
    value: Literal["USEFUL", "NOT_USEFUL"]

    @model_validator(mode="after")
    def require_one_identity(self) -> "FeedbackRequest":
        if (self.item_id is None) == (self.event_id is None):
            raise ValueError("exactly one of item_id or event_id is required")
        return self


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


class PersonalSourceRuntimeState(StrEnum):
    """Observed personal-source runtime state, independent from owner intent."""

    PENDING_CONFIGURATION = "PENDING_CONFIGURATION"
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    ERROR = "ERROR"


class PersonalSourceStreamType(StrEnum):
    UNKNOWN = "UNKNOWN"
    RSS_ATOM = "RSS_ATOM"
    SITEMAP = "SITEMAP"
    JSON_API = "JSON_API"
    DIRECT_PDF = "DIRECT_PDF"
    LIST_DETAIL = "LIST_DETAIL"


class PersonalSourceStreamStatus(StrEnum):
    PROBING = "PROBING"
    READY = "READY"
    PROBE_FAILED = "PROBE_FAILED"


class PersonalStreamRuntimeState(StrEnum):
    STOPPED = "STOPPED"
    SCHEDULED = "SCHEDULED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    HALF_OPEN = "HALF_OPEN"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    INACCESSIBLE = "INACCESSIBLE"


class PersonalStreamHealthStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class PersonalStreamHealthReason(StrEnum):
    DNS_FAILURE = "DNS_FAILURE"
    TLS_FAILURE = "TLS_FAILURE"
    TIMEOUT = "TIMEOUT"
    HTTP_401 = "HTTP_401"
    HTTP_403 = "HTTP_403"
    HTTP_404 = "HTTP_404"
    HTTP_429 = "HTTP_429"
    HTTP_5XX = "HTTP_5XX"
    ROBOTS_BLOCKED = "ROBOTS_BLOCKED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CAPTCHA_DETECTED = "CAPTCHA_DETECTED"
    PAYWALL_DETECTED = "PAYWALL_DETECTED"
    MIME_MISMATCH = "MIME_MISMATCH"
    PARSE_FAILED = "PARSE_FAILED"
    ZERO_DISCOVERY_STREAK = "ZERO_DISCOVERY_STREAK"
    STRUCTURE_CHANGED = "STRUCTURE_CHANGED"
    REQUIRED_FIELDS_MISSING = "REQUIRED_FIELDS_MISSING"
    CONTENT_STALE = "CONTENT_STALE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


class PersonalSourceProbeStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PersonalSourceInputKind(StrEnum):
    HOMEPAGE = "HOMEPAGE"
    LIST_PAGE = "LIST_PAGE"
    RSS_ATOM = "RSS_ATOM"
    SITEMAP = "SITEMAP"
    JSON_API = "JSON_API"
    DIRECT_PDF = "DIRECT_PDF"
    UNKNOWN = "UNKNOWN"


class SourceProfileStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class SourceProfileBasis(StrEnum):
    AUTO_INFERRED = "AUTO_INFERRED"
    PERSONAL_OVERRIDE = "PERSONAL_OVERRIDE"


class SourceProfileCandidate(ContractModel):
    value: str = Field(min_length=1, max_length=100)
    confidence: int = Field(ge=0, le=100)
    reason_code: AssessmentReasonCode
    evidence_ids: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def require_unique_evidence(self) -> "SourceProfileCandidate":
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("profile candidate evidence ids must be unique")
        return self


class SourceProfileModelOutput(ContractModel):
    """Semantic clues only; authority and independence remain server-derived."""

    industry_candidates: list[SourceProfileCandidate] = Field(max_length=20)
    content_domain_candidates: list[SourceProfileCandidate] = Field(max_length=30)
    language_candidates: list[SourceProfileCandidate] = Field(max_length=20)
    country_candidates: list[SourceProfileCandidate] = Field(max_length=20)
    region_candidates: list[SourceProfileCandidate] = Field(max_length=50)
    declared_role_candidates: list[SourceProfileCandidate] = Field(max_length=20)
    organization_clues: list[SourceProfileCandidate] = Field(max_length=20)
    ownership_clues: list[SourceProfileCandidate] = Field(max_length=20)


class SourceProfileOverrideRequest(ContractModel):
    industries: list[SourceIndustry] | None = None
    content_domains: list[SourceContentDomain] | None = None
    language_tags: list[LanguageTag] | None = None
    country_codes: list[CountryCode] | None = None
    region_codes: list[RegionCode] | None = None
    declared_roles: list[SourceDeclaredRole] | None = None
    authority_level: AuthorityLevel | None = None
    independence_level: SourceIndependenceLevel | None = None

    @model_validator(mode="after")
    def validate_override_patch(self) -> "SourceProfileOverrideRequest":
        if not self.model_fields_set:
            raise ValueError("at least one profile override field is required")
        for field in self.model_fields_set:
            value = getattr(self, field)
            if isinstance(value, list):
                if not value:
                    raise ValueError("profile override lists must not be empty")
                if len(value) != len(set(value)):
                    raise ValueError("profile override values must be unique")
        return self


class SourceProfileSummaryView(ContractModel):
    status: SourceProfileStatus
    overall_confidence: int = Field(ge=0, le=100)
    overridden_fields: list[str] = Field(default_factory=list, max_length=8)
    generated_at: datetime


class SourceProfileEvidenceView(ContractModel):
    evidence_id: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=30)
    url: HttpUrlString = Field(pattern="^https://[^\\s]+$", max_length=2048)
    sha256: Sha256String = Field(pattern="^[a-f0-9]{64}$")
    excerpt: str = Field(min_length=1, max_length=2000)


class SourceProfileFieldExplanation(ContractModel):
    confidence: int = Field(ge=0, le=100)
    reason_codes: list[AssessmentReasonCode] = Field(max_length=20)
    evidence_ids: list[str] = Field(max_length=50)
    basis: SourceProfileBasis = SourceProfileBasis.AUTO_INFERRED


class SourceProfileValues(ContractModel):
    industries: list[SourceIndustry]
    content_domains: list[SourceContentDomain]
    language_tags: list[LanguageTag]
    country_codes: list[CountryCode]
    region_codes: list[RegionCode]
    declared_roles: list[SourceDeclaredRole]
    authority_level: AuthorityLevel
    independence_level: SourceIndependenceLevel


class SourceProfileView(ContractModel):
    snapshot_id: UUID
    version: int = Field(ge=1)
    status: SourceProfileStatus
    automatic: SourceProfileValues
    effective: SourceProfileValues
    field_explanations: dict[str, SourceProfileFieldExplanation]
    overall_confidence: int = Field(ge=0, le=100)
    overridden_fields: list[str] = Field(default_factory=list, max_length=8)
    evidence: list[SourceProfileEvidenceView] = Field(max_length=50)
    technical_facts: list[str] = Field(max_length=20)
    reason_codes: list[AssessmentReasonCode] = Field(max_length=50)
    rule_version: str = Field(min_length=1, max_length=50)
    prompt_version: str = Field(min_length=1, max_length=50)
    schema_version: str = Field(min_length=1, max_length=50)
    model_version: str = Field(min_length=1, max_length=100)
    input_sha256: Sha256String = Field(pattern="^[a-f0-9]{64}$")
    generated_at: datetime


class DiscoverySettingPatchRequest(ContractModel):
    automation_enabled: bool | None = None

    @model_validator(mode="after")
    def require_enabled_value(self) -> "DiscoverySettingPatchRequest":
        if "automation_enabled" not in self.model_fields_set or self.automation_enabled is None:
            raise ValueError("automation_enabled is required and must not be null")
        return self


class DiscoverySettingView(ContractModel):
    automation_enabled: bool
    discovery_interval_seconds: int = Field(ge=3600, le=86400)
    next_run_at: datetime | None = None
    baidu_status: Literal["DISABLED", "KEY_MISSING", "AVAILABLE", "BUDGET_EXHAUSTED"]
    updated_at: datetime


class DiscoveryTopicPatchRequest(ContractModel):
    keywords: list[str] | None = Field(default=None, max_length=50)
    excluded_terms: list[str] | None = Field(default=None, max_length=50)
    focus_regions: list[str] | None = Field(default=None, max_length=50)
    enabled: bool | None = None

    @field_validator("keywords", "excluded_terms", "focus_regions", mode="before")
    @classmethod
    def normalize_terms(cls, value: object) -> object:
        if value is None or not isinstance(value, list):
            return value
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 100:
                raise ValueError("topic terms must contain 1 to 100 visible characters")
            clean = item.strip()
            if clean not in normalized:
                normalized.append(clean)
        return normalized

    @model_validator(mode="after")
    def validate_topic_patch(self) -> "DiscoveryTopicPatchRequest":
        if not self.model_fields_set:
            raise ValueError("at least one discovery topic field is required")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("discovery topic patch fields must not be null")
        if "keywords" in self.model_fields_set and (not self.keywords):
            raise ValueError("discovery topic keywords must not be empty")
        return self


class DiscoveryTopicView(ContractModel):
    id: UUID
    code: Literal["HIGHWAY", "BRIDGE", "TUNNEL", "RAIL", "DIGITAL", "AI_IOT_LOW_ALTITUDE", "SAFETY"]
    name: str = Field(min_length=1, max_length=100)
    keywords: list[str] = Field(min_length=1, max_length=50)
    excluded_terms: list[str] = Field(max_length=50)
    focus_regions: list[str] = Field(max_length=50)
    enabled: bool
    version: int = Field(ge=1)
    updated_at: datetime


class DiscoveryDailyUsageView(ContractModel):
    local_date: date
    probe_used: int = Field(ge=0, le=100)
    probe_limit: int = Field(default=100, ge=1, le=100)
    probe_remaining: int = Field(default=0, ge=0, le=100)
    auto_enable_used: int = Field(ge=0, le=20)
    auto_enable_limit: int = Field(default=20, ge=1, le=20)
    auto_enable_remaining: int = Field(default=0, ge=0, le=20)

    @model_validator(mode="after")
    def derive_remaining(self) -> "DiscoveryDailyUsageView":
        self.probe_remaining = self.probe_limit - self.probe_used
        self.auto_enable_remaining = self.auto_enable_limit - self.auto_enable_used
        return self


class SourceAutoScoreSummaryView(ContractModel):
    snapshot_id: UUID
    total_score: int = Field(ge=0, le=100)
    eligible: bool
    reason_codes: list[str] = Field(max_length=30)
    rule_version: str = Field(min_length=1, max_length=80)
    evaluated_at: datetime


class SourceAutoScoreDetailView(SourceAutoScoreSummaryView):
    source_id: UUID
    topic_relevance_score: int = Field(ge=0, le=35)
    connector_stability_score: int = Field(ge=0, le=25)
    sample_completeness_score: int = Field(ge=0, le=20)
    profile_evidence_score: int = Field(ge=0, le=10)
    content_validity_score: int = Field(ge=0, le=10)
    component_explanations: dict[str, str]
    hard_gate_results: dict[str, bool]
    evidence_refs: list[str] = Field(max_length=100)


class PersonalSourceCreateRequest(ContractModel):
    url: HttpUrlString = Field(pattern="^https://[^\\s]+$", max_length=2048)


class PersonalSourceReprobeRequest(ContractModel):
    stream_id: UUID | None = None


class PersonalSourceStreamView(ContractModel):
    id: UUID
    stream_type: PersonalSourceStreamType
    normalized_url: HttpUrlString = Field(pattern="^https://[^\\s]+$", max_length=2048)
    allowed_hosts: list[str] = Field(min_length=1, max_length=32)
    config_sha256: Sha256String | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    discovery_method: str = Field(min_length=1, max_length=40)
    status: PersonalSourceStreamStatus
    failure_reason: str | None = Field(default=None, max_length=500)
    actual_running: bool = False
    runtime_state: PersonalStreamRuntimeState = PersonalStreamRuntimeState.STOPPED
    health_status: PersonalStreamHealthStatus = PersonalStreamHealthStatus.UNKNOWN
    health_reason: PersonalStreamHealthReason | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    next_self_heal_at: datetime | None = None
    last_successful_fetch_at: datetime | None = None
    last_content_discovered_at: datetime | None = None
    health_observation_id: UUID | None = None
    health_observed_at: datetime | None = None


class StreamProbeRunView(ContractModel):
    id: UUID
    requested_url: HttpUrlString = Field(pattern="^https://[^\\s]+$", max_length=2048)
    input_kind: PersonalSourceInputKind
    status: PersonalSourceProbeStatus
    duration_ms: int | None = Field(default=None, ge=0)
    failure_code: str | None = Field(default=None, max_length=80)
    failure_reason: str | None = Field(default=None, max_length=500)


class PersonalSourcePatchRequest(ContractModel):
    desired_enabled: bool | None = None
    display_name: str | None = Field(default=None, max_length=200)

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_display_name(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("display_name must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def require_non_null_patch_field(self) -> "PersonalSourcePatchRequest":
        allowed_fields = {"desired_enabled", "display_name"}
        provided = self.model_fields_set & allowed_fields
        if not provided:
            raise ValueError("at least one personal source field is required")
        if any(getattr(self, field) is None for field in provided):
            raise ValueError("personal source patch fields must not be null")
        return self


class PersonalSourceView(ContractModel):
    id: UUID
    display_name: str = Field(min_length=1, max_length=200)
    url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)
    desired_enabled: bool
    runtime_state: PersonalSourceRuntimeState
    manual_disabled_at: datetime | None = None
    normalized_origin: HttpUrlString | None = Field(
        default=None, pattern="^https://[^\\s]+$", max_length=2048
    )
    streams: list[PersonalSourceStreamView] = Field(default_factory=list)
    latest_probe_run: StreamProbeRunView | None = None
    profile_summary: SourceProfileSummaryView | None = None
    auto_score_summary: SourceAutoScoreSummaryView | None = None


class PersonalSourceRunSummaryView(ContractModel):
    last_run_at: datetime | None = None
    last_run_status: str | None = Field(default=None, max_length=30)
    discovered_count: int = Field(default=0, ge=0)
    fetched_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    next_run_at: datetime | None = None


class PersonalSourceActivityItemView(ContractModel):
    id: UUID
    kind: Literal[
        "OWNER_ENABLED",
        "OWNER_DISABLED",
        "AUTO_ENABLED",
        "DISPLAY_NAME_CHANGED",
        "URL_PROBE",
        "COLLECTION_RUN",
    ]
    occurred_at: datetime
    stream_id: UUID | None = None
    status: str = Field(min_length=1, max_length=40)
    reason_code: str | None = Field(default=None, max_length=100)
    discovered_count: int | None = Field(default=None, ge=0)
    fetched_count: int | None = Field(default=None, ge=0)
    failed_count: int | None = Field(default=None, ge=0)


class PersonalSourceActivityPage(ContractModel):
    items: list[PersonalSourceActivityItemView] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, max_length=500)
    run_summary: PersonalSourceRunSummaryView


class RawObjectSummary(ContractModel):
    id: UUID
    sha256: Sha256String = Field(pattern="^[a-f0-9]{64}$")
    detected_mime: Literal["text/html", "application/pdf", "application/xml", "application/json"]
    byte_size: int = Field(ge=0)
    scan_status: ScanStatus


class DocumentVersionSummary(ContractModel):
    id: UUID
    version_number: int = Field(ge=1)
    content_hash: Sha256String = Field(pattern="^[a-f0-9]{64}$")
    original_filename: str
    title: str | None
    acquired_at: datetime


class DocumentDetail(ContractModel):
    id: UUID
    source_id: UUID
    source_name: str
    canonical_url: str
    document_kind: Literal["HTML", "PDF", "DISCOVERY_XML", "DISCOVERY_JSON"]
    first_discovered_at: datetime
    current_version: DocumentVersionSummary
    raw_object: RawObjectSummary


class FixtureUploadResponse(ContractModel):
    document: DocumentDetail
    raw_object_deduplicated: bool
    version_created: bool


class FeedNotice(ContractModel):
    code: str = Field(min_length=1, max_length=100)
    level: Literal["info", "warning", "error"]
    message: str = Field(min_length=1, max_length=500)


class SafetyRegulationTypeSummary(ContractModel):
    kind: Literal["SAFETY_REGULATION"]
    document_number: str = Field(min_length=1, max_length=200)
    issuing_authority: str = Field(min_length=1, max_length=200)
    regulation_status: RegulationStatus
    classification: RegulationClassification


class SafetyCaseTypeSummary(ContractModel):
    """Reviewed safety-case projection; only ``kind`` is safe for an R3 stub."""

    kind: Literal["SAFETY_CASE"]
    event_id: UUID | None = None
    report_stage: SafetyCaseReportStage | None = None
    incident_status: IncidentStatus | None = None
    hazard_type: str | None = Field(default=None, min_length=1, max_length=100)
    engineering_type: str | None = Field(default=None, min_length=1, max_length=100)
    occurred_at: datetime | None = None
    region: str | None = Field(default=None, min_length=1, max_length=200)
    deaths: int | None = Field(default=None, ge=0)
    injuries: int | None = Field(default=None, ge=0)
    loss_amount_minor: int | None = Field(default=None, ge=0)
    loss_currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    conflicted_fields: list[CriticalSafetyField] | None = None
    official_direct_causes: list[str] | None = Field(
        default=None,
        description=(
            "null means no formal investigation basis; an empty list means formal "
            "evidence was reviewed and stated no direct-cause finding"
        ),
    )
    responsibility_findings: list[str] | None = Field(
        default=None,
        description=(
            "null means no formal investigation or enforcement basis; an empty list means "
            "formal evidence was reviewed and stated no responsibility finding"
        ),
    )
    rectification_has_open_issues: bool | None = Field(
        default=None,
        description="Reviewed rectification evaluation result; null means not established",
    )
    similar_scenario_tags: list[SimilarScenarioTag] | None = None
    prevention_measure_tags: list[PreventionMeasureTag] | None = None

    @model_validator(mode="after")
    def hide_conflicted_values(self) -> "SafetyCaseTypeSummary":
        field_map = {
            CriticalSafetyField.DEATH_COUNT: "deaths",
            CriticalSafetyField.INJURY_COUNT: "injuries",
            CriticalSafetyField.LOSS_AMOUNT_MINOR: "loss_amount_minor",
            CriticalSafetyField.OFFICIAL_DIRECT_CAUSES: "official_direct_causes",
            CriticalSafetyField.RESPONSIBILITY_FINDINGS: "responsibility_findings",
        }
        for field in self.conflicted_fields or []:
            if getattr(self, field_map[field]) is not None:
                raise ValueError(f"conflicted field {field.value} must be hidden")
        if (self.loss_amount_minor is None) != (self.loss_currency is None):
            raise ValueError("loss amount and currency must be provided together")
        return self


class RelevanceFactor(ContractModel):
    code: Literal["ENGINEERING_DOMAIN", "SICHUAN", "SRBG_DIRECT"]
    label: str = Field(min_length=1, max_length=100)
    points: int = Field(ge=0, le=70)


class RelevanceSummary(ContractModel):
    score: int = Field(ge=0, le=100)
    rule_version: Literal["relevance-v1.0.0"]
    factors: list[RelevanceFactor] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def require_factor_total(self) -> "RelevanceSummary":
        if sum(factor.points for factor in self.factors) != self.score:
            raise ValueError("relevance factor points must equal score")
        return self


class DigitalCaseTypeSummary(ContractModel):
    kind: Literal["DIGITAL_CASE"]
    maturity_level: MaturityLevel
    application_scenarios: list[str] = Field(max_length=20)
    source_nature: DigitalCaseSourceNature
    deployment_scale: str | None = Field(default=None, max_length=500)
    publisher_claim_label: str | None = Field(default=None, max_length=100)
    srbg_relationship: str = Field(min_length=1, max_length=500)
    relevance: RelevanceSummary
    ai_short_comment: None = None


class PaperTypeSummary(ContractModel):
    kind: Literal["JOURNAL_PAPER"]
    doi: str | None = Field(default=None, pattern="^10\\.\\d{4,9}/\\S+$", max_length=300)
    journal: str | None = Field(default=None, max_length=300)
    year: int | None = Field(default=None, ge=1000, le=9999)
    paper_type: PaperType
    access_level: PaperAccessLevel
    open_status: PaperOpenStatus
    maturity_level: MaturityLevel
    engineering_domains: list[str] = Field(max_length=20)
    technology_tags: list[str] = Field(max_length=50)
    relation_status: PaperRelationStatus
    ai_short_comment: None = None


class PaperAuthor(ContractModel):
    name: str = Field(min_length=1, max_length=300)
    orcid: str | None = Field(
        default=None, pattern="^https://orcid\\.org/\\d{4}-\\d{4}-\\d{4}-\\d{3}[\\dX]$"
    )
    institutions: list[str] = Field(max_length=30)


class ResearchInterpretation(ContractModel):
    research_object: str | None = Field(default=None, max_length=1000)
    method: str | None = Field(default=None, max_length=1000)
    conditions: list[str] = Field(max_length=30)
    conclusions: list[str] = Field(max_length=30)
    limitations: list[str] = Field(max_length=30)
    claim_ids: list[UUID] = Field(min_length=1)
    evidence_ids: list[UUID] = Field(min_length=1)


class SimilarPaper(ContractModel):
    item_id: UUID
    title: str = Field(min_length=1, max_length=500)
    journal: str | None = Field(default=None, max_length=300)
    year: int | None = Field(default=None, ge=1000, le=9999)
    match_reasons: list[str] = Field(min_length=1, max_length=20)


class PaperDetail(ContractModel):
    doi: str | None = Field(default=None, pattern="^10\\.\\d{4,9}/\\S+$", max_length=300)
    journal: str | None = Field(default=None, max_length=300)
    issns: list[str] = Field(max_length=20)
    authors: list[PaperAuthor] = Field(max_length=500)
    volume: str | None = Field(default=None, max_length=50)
    issue: str | None = Field(default=None, max_length=50)
    pages: str | None = Field(default=None, max_length=100)
    year: int | None = Field(default=None, ge=1000, le=9999)
    abstract: str | None = Field(default=None, max_length=20000)
    abstract_availability: AbstractAvailability
    keywords: list[str] = Field(max_length=100)
    access_level: PaperAccessLevel
    open_status: PaperOpenStatus
    open_fulltext_url: HttpUrlString | None = Field(
        default=None, pattern="^https?://[^\\s]+$", max_length=2048
    )
    maturity_level: MaturityLevel
    engineering_domains: list[str] = Field(max_length=20)
    technology_tags: list[str] = Field(max_length=50)
    research_interpretation: ResearchInterpretation | None = None
    similar_papers: list[SimilarPaper] = Field(max_length=5)
    relation_status: PaperRelationStatus

    @model_validator(mode="after")
    def enforce_access_boundary(self) -> "PaperDetail":
        if self.access_level is PaperAccessLevel.METADATA_ONLY and self.abstract is not None:
            raise ValueError("metadata-only papers cannot expose an abstract")
        if self.access_level is not PaperAccessLevel.OPEN_FULLTEXT and self.open_fulltext_url:
            raise ValueError("fulltext links require OPEN_FULLTEXT access")
        return self


class DigitalCaseEntity(ContractModel):
    id: UUID
    entity_type: DigitalCaseEntityType
    name: str = Field(min_length=1, max_length=300)
    relation_type: str = Field(min_length=1, max_length=50)
    claim_id: UUID


class DigitalCaseOutcome(ContractModel):
    id: UUID
    statement: str = Field(min_length=1, max_length=1000)
    attribution: str = Field(min_length=1, max_length=300)
    verification: OutcomeVerification
    evidence_ids: list[UUID] = Field(min_length=1)
    independent_evidence_ids: list[UUID] = Field(default_factory=list)
    metric_name: str | None = Field(default=None, max_length=200)
    numeric_value: str | None = Field(default=None, pattern="^-?\\d+(?:\\.\\d+)?$")
    unit: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def require_independent_evidence(self) -> "DigitalCaseOutcome":
        if self.verification is OutcomeVerification.VERIFIED and (
            not self.independent_evidence_ids
        ):
            raise ValueError("verified outcomes require independent evidence")
        return self


class DigitalCaseDetail(ContractModel):
    engineering_domains: list[str] = Field(max_length=20)
    lifecycle_stages: list[str] = Field(max_length=20)
    technology_tags: list[str] = Field(max_length=50)
    application_scenarios: list[str] = Field(max_length=30)
    maturity_level: MaturityLevel
    deployment_scale: str | None = Field(default=None, max_length=500)
    entities: list[DigitalCaseEntity]
    claimed_outcomes: list[DigitalCaseOutcome]
    verified_outcomes: list[DigitalCaseOutcome]
    applicability: list[str]
    replication_conditions: list[str]
    limitations: list[str]
    risks: list[str]
    recommended_actions: list[RecommendedAction]
    ai_short_comment: None = None

    @model_validator(mode="after")
    def keep_outcome_groups_separate(self) -> "DigitalCaseDetail":
        if any(
            item.verification is not OutcomeVerification.CLAIMED for item in self.claimed_outcomes
        ):
            raise ValueError("claimed outcomes must use CLAIMED verification")
        if any(
            item.verification is not OutcomeVerification.VERIFIED
            for item in self.verified_outcomes
        ):
            raise ValueError("verified outcomes must use VERIFIED verification")
        return self


class _ProductTypeSummaryBase(ContractModel):
    vendor_name: str = Field(min_length=1, max_length=300)
    product_name: str = Field(min_length=1, max_length=300)
    product_kind: str = Field(min_length=1, max_length=100)
    model_no: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=200)
    evidence_level: ProductEvidenceLevel
    promotional_claim_count: int = Field(ge=0)
    verified_capability_count: int = Field(ge=0)


class SoftwareProductTypeSummary(_ProductTypeSummaryBase):
    kind: Literal["SOFTWARE_PRODUCT"]
    interfaces: list[str] = Field(max_length=30)
    deployment_modes: list[str] = Field(max_length=20)


class IotProductTypeSummary(_ProductTypeSummaryBase):
    kind: Literal["IOT_PRODUCT"]
    connectivity: list[str] = Field(max_length=30)
    maturity_level: MaturityLevel


class LowAltitudeEquipmentTypeSummary(_ProductTypeSummaryBase):
    kind: Literal["LOW_ALTITUDE_EQUIPMENT"]
    platform_type: str | None = Field(default=None, max_length=100)
    payload_types: list[str] = Field(max_length=30)
    permit_status: ProductPermitStatus


class AiEquipmentTypeSummary(_ProductTypeSummaryBase):
    kind: Literal["AI_EQUIPMENT"]
    equipment_form: str | None = Field(default=None, max_length=100)
    ai_tasks: list[str] = Field(max_length=30)
    maturity_level: MaturityLevel
    production_validation: bool


class ProductCapability(ContractModel):
    claim_id: UUID
    statement: str = Field(min_length=1, max_length=1000)
    attribution: str = Field(min_length=1, max_length=300)
    kind: ProductCapabilityKind
    evidence_ids: list[UUID] = Field(min_length=1)
    independent_evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_independent_evidence(self) -> "ProductCapability":
        if self.kind is ProductCapabilityKind.VERIFIED_CAPABILITY and (
            not self.independent_evidence_ids
        ):
            raise ValueError("verified product capabilities require independent evidence")
        if self.kind is ProductCapabilityKind.PROMOTIONAL_CLAIM and self.independent_evidence_ids:
            raise ValueError("promotional claims cannot carry independent verification")
        return self


class ProductEntity(ContractModel):
    id: UUID
    name: str = Field(min_length=1, max_length=300)


class ProductEngineeringCase(ContractModel):
    item_id: UUID
    title: str = Field(min_length=1, max_length=500)
    evidence_ids: list[UUID] = Field(min_length=1)


class TechnologyProductDetail(ContractModel):
    vendor: ProductEntity
    product: ProductEntity
    model: ProductEntity | None = None
    current_version: str | None = Field(default=None, max_length=200)
    version_history: list[str] = Field(max_length=100)
    product_kind: str = Field(min_length=1, max_length=100)
    promotional_claims: list[ProductCapability]
    verified_capabilities: list[ProductCapability]
    interfaces: list[str] = Field(max_length=30)
    deployment_modes: list[str] = Field(max_length=20)
    application_scenarios: list[str] = Field(max_length=30)
    engineering_cases: list[ProductEngineeringCase] = Field(max_length=50)
    evidence_level: ProductEvidenceLevel
    permit_status: ProductPermitStatus
    limitations: list[str] = Field(max_length=50)
    procurement_notice: Literal["仅供技术调研，不构成采购建议"]  # noqa: RUF001
    low_altitude_notice: Literal["产品发布不代表空域、适航、飞手和项目许可。"] | None = None

    @model_validator(mode="after")
    def keep_capability_groups_separate(self) -> "TechnologyProductDetail":
        if any(
            capability.kind is not ProductCapabilityKind.PROMOTIONAL_CLAIM
            for capability in self.promotional_claims
        ):
            raise ValueError("promotional claims must remain vendor-attributed")
        if any(
            capability.kind is not ProductCapabilityKind.VERIFIED_CAPABILITY
            for capability in self.verified_capabilities
        ):
            raise ValueError("verified capabilities must remain independently evidenced")
        return self


class ScoreDimension(StrEnum):
    RELEVANCE = "RELEVANCE"
    AUTHORITY = "AUTHORITY"
    IMPACT = "IMPACT"
    NOVELTY = "NOVELTY"
    TIMELINESS = "TIMELINESS"
    EVIDENCE = "EVIDENCE"
    CONFIDENCE = "CONFIDENCE"
    HEAT = "HEAT"


class ScoreFeature(ContractModel):
    code: str = Field(pattern="^[A-Z][A-Z0-9_]{1,79}$")
    label: str = Field(min_length=1, max_length=100)
    points: int = Field(ge=-100, le=100)
    explanation: str = Field(min_length=1, max_length=500)


class ScoreDimensionSummary(ContractModel):
    dimension: ScoreDimension
    raw_score: int = Field(ge=0, le=100)
    score: int = Field(ge=0, le=100)
    features: list[ScoreFeature] = Field(max_length=20)
    rule_version: Literal["scoring-v1.0.0"]
    calculated_at: datetime
    overridden: bool = False
    override_reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_override_audit(self) -> "ScoreDimensionSummary":
        if self.overridden and (not self.override_reason):
            raise ValueError("overridden scores require an override reason")
        if not self.overridden and self.override_reason is not None:
            raise ValueError("override reason requires overridden=true")
        if not self.overridden and self.score != self.raw_score:
            raise ValueError("effective score can differ only through an audited override")
        return self


class ScoreSummary(ContractModel):
    relevance: ScoreDimensionSummary | None = None
    authority: ScoreDimensionSummary | None = None
    impact: ScoreDimensionSummary | None = None
    novelty: ScoreDimensionSummary | None = None
    timeliness: ScoreDimensionSummary | None = None
    evidence: ScoreDimensionSummary | None = None
    confidence: ScoreDimensionSummary | None = None
    heat: ScoreDimensionSummary | None = None

    @model_validator(mode="after")
    def validate_named_dimensions(self) -> "ScoreSummary":
        values = {
            "relevance": ScoreDimension.RELEVANCE,
            "authority": ScoreDimension.AUTHORITY,
            "impact": ScoreDimension.IMPACT,
            "novelty": ScoreDimension.NOVELTY,
            "timeliness": ScoreDimension.TIMELINESS,
            "evidence": ScoreDimension.EVIDENCE,
            "confidence": ScoreDimension.CONFIDENCE,
            "heat": ScoreDimension.HEAT,
        }
        if not any(getattr(self, field) is not None for field in values):
            raise ValueError("a score summary requires at least one named dimension")
        for field, expected in values.items():
            value = getattr(self, field)
            if value is not None and value.dimension is not expected:
                raise ValueError(f"{field} must contain the {expected.value} dimension")
        return self


class EventType(StrEnum):
    SAFETY_INCIDENT = "SAFETY_INCIDENT"
    REGULATION_CHANGE = "REGULATION_CHANGE"
    DIGITAL_PROJECT = "DIGITAL_PROJECT"
    RESEARCH_RESULT = "RESEARCH_RESULT"
    PRODUCT_RELEASE = "PRODUCT_RELEASE"


class EventStatus(StrEnum):
    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    SPLIT = "SPLIT"
    WITHDRAWN = "WITHDRAWN"


class SourceLineageRole(StrEnum):
    ORIGINAL = "ORIGINAL"
    REPRINT = "REPRINT"
    MIRROR = "MIRROR"
    INDEPENDENT_REPORT = "INDEPENDENT_REPORT"
    VENDOR_STATEMENT = "VENDOR_STATEMENT"
    MEDIA_REPORT = "MEDIA_REPORT"
    INDEPENDENT_VERIFICATION = "INDEPENDENT_VERIFICATION"


class AutomaticRelationshipKind(StrEnum):
    DUPLICATE = "DUPLICATE"
    SAME_EVENT = "SAME_EVENT"
    FOLLOW_UP_OF = "FOLLOW_UP_OF"
    INVESTIGATES = "INVESTIGATES"
    MODEL_ALIAS = "MODEL_ALIAS"
    VERSION_SUCCESSOR = "VERSION_SUCCESSOR"
    TOPIC = "TOPIC"
    RELATED_CONTENT = "RELATED_CONTENT"


class AutomaticRelationshipView(ContractModel):
    id: UUID
    relationship_key: str = Field(min_length=1, max_length=500)
    kind: AutomaticRelationshipKind
    source_item_id: UUID
    target_item_id: UUID
    status: Literal["ACTIVE", "INVALIDATED", "WITHDRAWN", "SUPERSEDED"]
    score_bps: int = Field(ge=0, le=10000)
    reason_codes: list[str] = Field(max_length=20)
    algorithm_version: str = Field(min_length=1, max_length=100)
    model_version: str | None = Field(default=None, max_length=200)
    input_fingerprint_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    created_at: datetime


class EventSplitAllocation(ContractModel):
    item_id: UUID
    child_event_id: UUID


class OwnerRelationshipCorrectionRequest(ContractModel):
    command_id: UUID
    action: Literal[
        "WITHDRAW_RELATION", "SPLIT_EVENT", "KEEP_INDEPENDENT", "CORRECT_MODEL_RELATION"
    ]
    reason: str = Field(min_length=1, max_length=1000)
    decision_id: UUID | None = None
    member_item_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    allocations: list[EventSplitAllocation] = Field(default_factory=list, max_length=1000)
    corrected_kind: Literal["MODEL_ALIAS", "VERSION_SUCCESSOR"] | None = None
    corrected_source_item_id: UUID | None = None
    corrected_target_item_id: UUID | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "OwnerRelationshipCorrectionRequest":
        if self.action == "WITHDRAW_RELATION" and self.decision_id is None:
            raise ValueError("decision_id is required for withdrawal")
        if self.action == "SPLIT_EVENT" and (not self.allocations):
            raise ValueError("allocations are required for event split")
        if self.action == "KEEP_INDEPENDENT" and len(set(self.member_item_ids)) < 2:
            raise ValueError("at least two distinct member_item_ids are required")
        if self.action == "CORRECT_MODEL_RELATION" and (
            self.corrected_kind is None
            or self.corrected_source_item_id is None
            or self.corrected_target_item_id is None
            or (self.corrected_source_item_id == self.corrected_target_item_id)
        ):
            raise ValueError("a complete distinct corrected model relation is required")
        return self


class OwnerRelationshipCorrectionResponse(ContractModel):
    correction_id: UUID
    event_id: UUID
    action: str
    event_version: int = Field(ge=1)
    projection_generation: int = Field(ge=1)


class HotTopicSummary(ContractModel):
    id: UUID
    title: str = Field(min_length=1, max_length=500)
    domain: Channel
    heat_score: int = Field(ge=0, le=100)
    event_count: int = Field(ge=1)
    independent_source_count: int = Field(ge=0)
    latest_activity_at: datetime
    rule_version: Literal["scoring-v1.0.0"]


class HotTopicPage(ContractModel):
    items: list[HotTopicSummary]
    next_cursor: str | None = None
    generated_at: datetime
    evaluation_tier: Literal["INTERNAL_TEST_FIXTURE", "HUMAN_GOLD"]
    auto_merge_enabled: Literal[False] = False


class SourceComparisonEntry(ContractModel):
    item_id: UUID
    source_name: str = Field(min_length=1, max_length=200)
    organization_key: str = Field(min_length=1, max_length=200)
    lineage_root: str = Field(min_length=1, max_length=200)
    role: SourceLineageRole
    source_published_at: datetime | None = None
    original_url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)
    accepted_claim_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)


class SourceComparison(ContractModel):
    event_id: UUID
    independent_source_count: int = Field(ge=0)
    sources: list[SourceComparisonEntry]


TypeSummaryValue = Annotated[
    SafetyRegulationTypeSummary
    | SafetyCaseTypeSummary
    | DigitalCaseTypeSummary
    | PaperTypeSummary
    | SoftwareProductTypeSummary
    | IotProductTypeSummary
    | LowAltitudeEquipmentTypeSummary
    | AiEquipmentTypeSummary,
    Field(discriminator="kind"),
]


class TypeSummary(RootModel[TypeSummaryValue]):
    """Tagged union exported for TypeScript consumers."""


class PublishedEvidenceReferenceV1(ContractModel):
    evidence_id: UUID
    locator: str = Field(min_length=1, max_length=1000)
    content_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class PublishedClaimV1(ContractModel):
    claim_id: UUID
    field_name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)
    fact_kind: Literal["EVIDENCE_FACT"] = "EVIDENCE_FACT"


class AiJudgmentEvidencePreview(ContractModel):
    evidence_id: UUID
    excerpt: str = Field(min_length=1, max_length=2000)
    excerpt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    locator: str = Field(min_length=1, max_length=1000)


class AiJudgmentPreview(ContractModel):
    id: UUID
    document_version_id: UUID
    field_name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=2000)
    confidence_bps: int = Field(ge=0, le=10000)
    attribution: str | None = Field(default=None, max_length=500)
    reason_codes: list[str] = Field(min_length=1, max_length=30)
    rule_version: str = Field(min_length=1, max_length=100)
    evidence: list[AiJudgmentEvidencePreview] = Field(default_factory=list, max_length=100)
    status: Literal["UNVERIFIED_AI_JUDGMENT"] = "UNVERIFIED_AI_JUDGMENT"


class PublishedEventSummaryV1(ContractModel):
    """Versioned, event-keyed content projection for internal readers."""

    id: UUID
    publication_revision_id: UUID | None
    event_revision_id: UUID | None = None
    publication_revision_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    projection_version: Literal["1.0.0", "1.1.0"]
    generation: int = Field(ge=1)
    domain: Channel
    content_type: ItemType
    title: str = Field(min_length=1, max_length=500)
    source_name: str = Field(min_length=1, max_length=200)
    source_published_at: datetime | None
    first_discovered_at: datetime
    original_url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)
    review_status: ReviewStatus
    discovery_status: Literal["MACHINE_DISCOVERED", "HUMAN_CURATED"]
    fact_review_status: Literal["PENDING_HUMAN_REVIEW", "HUMAN_REVIEWED"]
    publication_risk_tier: PublicationRiskTier
    content_severity: ContentSeverity
    projection_level: ProjectionLevel
    one_sentence_fact: str | None = Field(default=None, max_length=500)
    type_summary: TypeSummaryValue | None = None
    event_type: EventType | None = None
    event_status: EventStatus = EventStatus.ACTIVE
    canonical_event_id: UUID | None = None
    event_version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def enforce_projection_level(self) -> "PublishedEventSummaryV1":
        if self.projection_level == ProjectionLevel.NONE:
            raise ValueError("NONE projections must not be serialized")
        if self.projection_level == ProjectionLevel.METADATA_ONLY and (
            self.one_sentence_fact is not None or self.type_summary is not None
        ):
            raise ValueError("metadata-only projections cannot contain accepted facts")
        return self


class PublishedDocumentReferenceV1(ContractModel):
    document_id: UUID
    source_role: SourceLineageRole | None = None
    source_role_pending: bool = False
    source_name: str = Field(min_length=1, max_length=200)
    original_url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)
    publication_revision_ids: list[UUID] = Field(default_factory=list, max_length=1000)


class PublishedEventDetailV1(ContractModel):
    summary: PublishedEventSummaryV1
    claims: list[PublishedClaimV1] = Field(max_length=500)
    evidence: list[PublishedEvidenceReferenceV1] = Field(max_length=500)
    documents: list[PublishedDocumentReferenceV1] = Field(default_factory=list, max_length=500)
    source_comparison: list[PublishedDocumentReferenceV1] = Field(
        default_factory=list, max_length=500
    )
    type_detail: TypeSummaryValue | None = None

    @model_validator(mode="after")
    def enforce_metadata_only_detail(self) -> "PublishedEventDetailV1":
        if self.summary.projection_level == ProjectionLevel.METADATA_ONLY and (
            self.claims or self.evidence
        ):
            raise ValueError("metadata-only projections cannot contain claims or evidence")
        return self


class AiAssistance(ContractModel):
    status: Literal["ASSISTED", "DEGRADED"]
    pipeline_run_id: UUID | None = None
    prompt_version: str | None = Field(default=None, max_length=80)
    schema_version: str | None = Field(default=None, max_length=80)
    model_profile: str | None = Field(default=None, max_length=80)
    generated_at: datetime | None = None
    accepted_claims_only: bool = False


class PublicationRevisionState(ContractModel):
    revision_number: int = Field(ge=1)
    action: Literal["PUBLISH", "REVISE", "WITHDRAW", "REPUBLISH"]
    created_at: datetime
    withdrawn_at: datetime | None = None


class SearchContext(ContractModel):
    match_kind: Literal["EXACT_IDENTIFIER", "TITLE_ENTITY_TAG", "BODY", "SEMANTIC"]
    matched_fields: list[str] = Field(default_factory=list, max_length=10)
    matched_identifiers: list[str] = Field(default_factory=list, max_length=10)
    semantic_status: Literal["DISABLED", "ENABLED", "DEGRADED"]


class AiJudgmentSignal(ContractModel):
    why_worth_attention: str = Field(min_length=1, max_length=500)
    potential_industry_impacts: list[str] = Field(default_factory=list, max_length=10)
    potential_engineering_scenarios: list[str] = Field(default_factory=list, max_length=10)
    current_limitations: list[str] = Field(default_factory=list, max_length=10)
    questions_to_verify: list[str] = Field(default_factory=list, max_length=10)
    used_claim_ids: list[UUID] = Field(min_length=1, max_length=100)


class ItemSummary(ContractModel):
    id: UUID
    publication_revision_id: UUID | None
    domain: Channel
    content_type: ItemType
    title: str = Field(min_length=1, max_length=500)
    source_name: str = Field(min_length=1, max_length=200)
    source_published_at: datetime | None
    first_discovered_at: datetime
    activity_at: datetime
    original_url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)
    review_status: ReviewStatus
    one_sentence_fact: str | None = Field(default=None, max_length=500)
    source_role: str | None = Field(default=None, max_length=100)
    last_updated_at: datetime | None = None
    publication_status: PublicationStatus | None = None
    evidence_status: EvidenceStatus | None = None
    evidence_count: int | None = Field(default=None, ge=0)
    tags: list[str] | None = None
    relevance_reason: str | None = Field(default=None, max_length=500)
    type_summary: TypeSummaryValue | None = None
    is_saved: bool | None = None
    detail_available: bool | None = None
    document_states: list[DocumentState] | None = None
    has_version_history: bool | None = None
    scores: ScoreSummary | None = None
    ai_assistance: AiAssistance | None = None
    revision_state: PublicationRevisionState | None = None
    search_context: SearchContext | None = None
    signal_id: UUID | None = None
    automatic_result_type: (
        Literal["EVIDENCE_FACT", "AI_JUDGMENT", "UNVERIFIED_AI", "AI_PROCESSING_FAILED"] | None
    ) = None
    ai_judgment: AiJudgmentSignal | None = None
    processing_failure_reasons: list[str] = Field(default_factory=list, max_length=20)


class EventSummary(ItemSummary):
    """The sole feed/search/saved/report identity after the Round 14 switch."""

    event_type: EventType
    event_status: EventStatus
    canonical_event_id: UUID
    event_version: int = Field(ge=1)


class FeedPage(ContractModel):
    items: list[EventSummary]
    next_cursor: str | None
    fingerprint: str = Field(min_length=1, max_length=200)
    generated_at: datetime
    freshness: Literal["fresh", "delayed", "partial"]
    notices: list[FeedNotice]


class SaveItemRequest(ContractModel):
    item_id: UUID
    collection_id: UUID | None = None


class SaveEventRequest(ContractModel):
    event_id: UUID
    collection_id: UUID | None = None


class CollectionCreateRequest(ContractModel):
    name: str = Field(min_length=1, max_length=100)


class CollectionPatchRequest(ContractModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    archived: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "CollectionPatchRequest":
        if self.name is None and self.archived is None:
            raise ValueError("at least one collection field is required")
        return self


class CollectionSummary(ContractModel):
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    item_count: int = Field(ge=0)
    archived: bool
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class DailyReportItem(ContractModel):
    item_id: UUID | None = None
    event_id: UUID | None = None
    event_revision_id: UUID | None = None
    publication_revision_id: UUID | None = None
    signal_id: UUID | None = None
    automatic_result_type: (
        Literal["EVIDENCE_FACT", "AI_JUDGMENT", "UNVERIFIED_AI", "AI_PROCESSING_FAILED"] | None
    ) = None
    position: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=1000)
    current_state: Literal["PUBLISHED", "WITHDRAWN", "SOURCE_UNAVAILABLE"]
    original_url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)


class DailyReportSection(ContractModel):
    kind: Literal[
        "TODAY_HIGHLIGHTS",
        "DIGITAL_SELECTED",
        "SAFETY_HIGHLIGHTS",
        "WATCHLIST",
        "SOURCE_ANOMALIES",
        "EVIDENCE_FACTS",
        "AI_JUDGMENTS",
        "UNVERIFIED_AI",
        "AI_PROCESSING_FAILURES",
    ]
    title: str = Field(min_length=1, max_length=100)
    items: list[DailyReportItem]


class DailyReport(ContractModel):
    id: UUID
    report_date: date
    status: Literal["DRAFT", "PUBLISHED"]
    snapshot_at: datetime
    published_at: datetime | None = None
    requires_regeneration: bool
    sections: list[DailyReportSection]


class FingerprintResponse(ContractModel):
    generated_at: datetime
    feed_generation: int = Field(ge=0)
    search_generation: int = Field(ge=0)
    hot_topics_generation: int = Field(ge=0)
    latest_daily_report_id: UUID | None = None
    fingerprint: str = Field(pattern="^sha256:[0-9a-f]{64}$")


class ClaimView(ContractModel):
    id: UUID
    claim_type: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[UUID] = Field(min_length=1)
    decision_status: Literal["PENDING", "ACCEPTED", "REJECTED"] | None = None


FactValue = str | int | list[str]


class ConfirmedFact(ContractModel):
    source_item_id: UUID
    claim_id: UUID
    field: SafetyCaseFactField
    label: str = Field(min_length=1, max_length=100)
    value: FactValue
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    evidence_ids: list[UUID] = Field(min_length=1)
    status: Literal["CONFIRMED"] = "CONFIRMED"
    reviewed_at: datetime


class UnverifiedFact(ContractModel):
    """Public-safe unresolved fact: candidate values are intentionally absent."""

    source_item_id: UUID
    claim_id: UUID | None = None
    conflict_id: UUID | None = None
    field: SafetyCaseFactField
    label: str = Field(min_length=1, max_length=100)
    value: None = None
    display_value: Literal["待核实"] = "待核实"
    status: Literal["PENDING_REVIEW", "CONFLICTING"]
    reason: str = Field(min_length=1, max_length=500)
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_conflict_reference(self) -> "UnverifiedFact":
        if self.status == "CONFLICTING" and self.conflict_id is None:
            raise ValueError("conflicting facts require a conflict id")
        return self


class EventItem(ContractModel):
    item_id: UUID
    title: str = Field(min_length=1, max_length=500)
    report_stage: SafetyCaseReportStage | None = None
    incident_status: IncidentStatus | None = None
    source_name: str = Field(min_length=1, max_length=200)
    source_published_at: datetime | None
    original_url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)
    review_status: ReviewStatus
    publication_revision_id: UUID | None
    relation_type: EventRelation | None = None
    evidence_count: int | None = Field(default=None, ge=0)
    document_states: list[DocumentState] | None = None


class EventTimeline(ContractModel):
    event_id: UUID
    items: list[EventItem]


class EventRelationView(ContractModel):
    id: UUID
    event_id: UUID
    from_item_id: UUID
    to_item_id: UUID
    relation_type: EventRelation
    reviewed_by: UUID
    reviewed_at: datetime


class EventAutomaticResultView(ContractModel):
    signal_id: UUID
    result_type: Literal["EVIDENCE_FACT", "AI_JUDGMENT", "UNVERIFIED_AI", "AI_PROCESSING_FAILED"]
    title: str = Field(min_length=1, max_length=500)
    original_url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)
    judgment: AiJudgmentSignal | None = None
    failure_reason_codes: list[str] = Field(default_factory=list, max_length=20)


class EventDetail(ContractModel):
    id: UUID
    title: str = Field(min_length=1, max_length=500)
    event_type: EventType
    event_status: EventStatus = EventStatus.ACTIVE
    canonical_event_id: UUID | None = None
    event_version: int = Field(default=1, ge=1)
    split_child_event_ids: list[UUID] = Field(default_factory=list)
    project_name: str | None = Field(default=None, min_length=1, max_length=300)
    occurred_at: datetime | None = None
    region: str | None = Field(default=None, min_length=1, max_length=200)
    hazard_type: str | None = Field(default=None, min_length=1, max_length=100)
    engineering_type: str | None = Field(default=None, min_length=1, max_length=100)
    incident_status: IncidentStatus | None = None
    rectification_has_open_issues: bool | None = None
    confirmed_facts: list[ConfirmedFact]
    unverified_facts: list[UnverifiedFact]
    timeline: EventTimeline
    relations: list[EventRelationView]
    automatic_relationships: list[AutomaticRelationshipView] = Field(
        default_factory=list, max_length=1000
    )
    similar_scenario_tags: list[SimilarScenarioTag]
    prevention_measure_tags: list[PreventionMeasureTag]
    topic_ids: list[UUID] = Field(default_factory=list)
    independent_source_count: int = Field(default=0, ge=0)
    scores: ScoreSummary | None = None
    summary: PublishedEventSummaryV1 | None = None
    claims: list[PublishedClaimV1] = Field(default_factory=list, max_length=500)
    evidence: list[PublishedEvidenceReferenceV1] = Field(default_factory=list, max_length=500)
    documents: list[PublishedDocumentReferenceV1] = Field(default_factory=list, max_length=500)
    source_comparison: list[PublishedDocumentReferenceV1] = Field(
        default_factory=list, max_length=500
    )
    type_detail: TypeSummaryValue | None = None
    ai_judgments: list[AiJudgmentPreview] = Field(default_factory=list, max_length=500)
    automatic_results: list[EventAutomaticResultView] = Field(default_factory=list, max_length=500)


class PageBoundingBox(ContractModel):
    """Rotation-normalized PDF coordinates in integer thousandths of a point."""

    x0: int = Field(ge=0)
    y0: int = Field(ge=0)
    x1: int = Field(gt=0)
    y1: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_extents(self) -> "PageBoundingBox":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("bounding box must have positive width and height")
        return self


class HtmlParagraphLocator(ContractModel):
    type: Literal["HTML_PARAGRAPH"]
    paragraph_id: str = Field(pattern="^html-p-\\d{4}$")
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)


class _PdfBlockLocator(ContractModel):
    page_number: int = Field(ge=1, le=10000)
    block_id: UUID
    bbox: PageBoundingBox


class PdfTextLocator(_PdfBlockLocator):
    type: Literal["PDF_TEXT"]


class PdfOcrLocator(_PdfBlockLocator):
    type: Literal["PDF_OCR"]
    confidence_bps: int = Field(ge=0, le=10000)


class PdfTableCellLocator(ContractModel):
    type: Literal["PDF_TABLE_CELL"]
    page_number: int = Field(ge=1, le=10000)
    table_cell_id: UUID
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    bbox: PageBoundingBox
    confidence_bps: int | None = Field(default=None, ge=0, le=10000)


EvidenceLocator = Annotated[
    HtmlParagraphLocator | PdfTextLocator | PdfOcrLocator | PdfTableCellLocator,
    Field(discriminator="type"),
]


class EvidenceView(ContractModel):
    id: UUID
    claim_ids: list[UUID] = Field(min_length=1)
    document_version_id: UUID | None = None
    locator: EvidenceLocator | None = None
    paragraph_id: str | None = Field(default=None, pattern="^html-p-\\d{4}$")
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, gt=0)
    excerpt: str = Field(min_length=1, max_length=2000)
    excerpt_sha256: Sha256String = Field(pattern="^[a-f0-9]{64}$")
    original_url: HttpUrlString = Field(pattern="^https?://[^\\s]+$", max_length=2048)

    @model_validator(mode="after")
    def require_one_locator(self) -> "EvidenceView":
        legacy = (
            self.paragraph_id is not None
            and self.char_start is not None
            and (self.char_end is not None)
        )
        if self.locator is None and (not legacy):
            raise ValueError("evidence requires a typed or legacy HTML locator")
        return self


class VersionTimelineEntry(ContractModel):
    version_id: UUID
    version_number: int = Field(ge=1)
    processing_state: VersionProcessingState
    change_type: VersionChangeType
    material: bool
    review_state: VersionReviewState
    acquired_at: datetime
    is_current: bool


class VersionTimelineResponse(ContractModel):
    item_id: UUID
    versions: list[VersionTimelineEntry]


class DiffHunk(ContractModel):
    operation: Literal["INSERT", "DELETE", "REPLACE", "EQUAL"]
    before: str | None = Field(default=None, max_length=4000)
    after: str | None = Field(default=None, max_length=4000)


class PageDiff(ContractModel):
    page_number: int = Field(ge=1, le=10000)
    category: Literal["METADATA", "HEADER_FOOTER", "BODY", "CRITICAL_FIELD"]
    hunks: list[DiffHunk] = Field(max_length=500)


class CriticalFieldDiff(ContractModel):
    field: Literal["document_number", "published_at", "effective_at", "legal_effect"]
    before: str | None = Field(default=None, max_length=1000)
    after: str | None = Field(default=None, max_length=1000)


class VersionDiffResponse(ContractModel):
    item_id: UUID
    from_version_id: UUID
    to_version_id: UUID
    change_type: VersionChangeType
    material: bool
    changed_token_count: int = Field(ge=0)
    changed_token_ratio_bps: int = Field(ge=0, le=10000)
    pages: list[PageDiff] = Field(max_length=1000)
    critical_fields: list[CriticalFieldDiff] = Field(max_length=20)


class DocumentPageView(ContractModel):
    document_version_id: UUID
    page_number: int = Field(ge=1, le=10000)
    page_count: int = Field(ge=1, le=10000)
    width_mpt: int = Field(gt=0)
    height_mpt: int = Field(gt=0)
    rotation: Literal[0, 90, 180, 270]
    text_source: Literal["NATIVE", "OCR", "MIXED"]
    preview_url: str = Field(pattern="^/api/v1/document-versions/[0-9a-f-]+/pages/\\d+/preview$")


class ItemDetail(ContractModel):
    item: ItemSummary
    notice: FeedNotice | None = None
    claims: list[ClaimView] | None = None
    evidence: list[EvidenceView] | None = None
    digital_case: DigitalCaseDetail | None = None
    paper: PaperDetail | None = None
    technology_product: TechnologyProductDetail | None = None


class MeResponse(ContractModel):
    user_id: UUID
    display_name: str
    roles: list[UserRole]
    local_identity: bool
