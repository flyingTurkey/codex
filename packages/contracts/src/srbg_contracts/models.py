"""Canonical public contracts shared by API and Worker processes."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

API_VERSION: Final[Literal["v1"]] = "v1"
CONTENT_SCHEMA_VERSION: Final[Literal["1.1.0"]] = "1.1.0"


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


class RelationCandidateStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


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
    loss_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    conflicted_fields: list[CriticalSafetyField] | None = None
    official_direct_causes: list[str] | None = Field(
        default=None,
        description=(
            "null means no formal investigation basis; an empty list means formal evidence "
            "was reviewed and stated no direct-cause finding"
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
    doi: str | None = Field(default=None, pattern=r"^10\.\d{4,9}/\S+$", max_length=300)
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
        default=None, pattern=r"^https://orcid\.org/\d{4}-\d{4}-\d{4}-\d{3}[\dX]$"
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
    doi: str | None = Field(default=None, pattern=r"^10\.\d{4,9}/\S+$", max_length=300)
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
        default=None, pattern=r"^https?://[^\s]+$", max_length=2048
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


class PaperRelationCandidate(ContractModel):
    id: UUID
    source_doi: str = Field(pattern=r"^10\.\d{4,9}/\S+$", max_length=300)
    target_doi: str = Field(pattern=r"^10\.\d{4,9}/\S+$", max_length=300)
    relation_type: PaperRelationType
    status: RelationCandidateStatus
    evidence_ids: list[UUID] = Field(min_length=1)


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
    numeric_value: str | None = Field(default=None, pattern=r"^-?\d+(?:\.\d+)?$")
    unit: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def require_independent_evidence(self) -> "DigitalCaseOutcome":
        if self.verification is OutcomeVerification.VERIFIED and not self.independent_evidence_ids:
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
            item.verification is not OutcomeVerification.VERIFIED for item in self.verified_outcomes
        ):
            raise ValueError("verified outcomes must use VERIFIED verification")
        return self


class DigitalOutcomeAttributionPatch(ContractModel):
    outcome_id: UUID
    attribution_entity_id: UUID
    verification: OutcomeVerification
    independent_evidence_ids: list[UUID] = Field(default_factory=list)


class DigitalCaseReviewPatch(ContractModel):
    engineering_domains: list[str] = Field(max_length=20)
    lifecycle_stages: list[str] = Field(max_length=20)
    technology_tags: list[str] = Field(max_length=50)
    application_scenarios: list[str] = Field(max_length=30)
    maturity_level: MaturityLevel
    maturity_evidence_ids: list[UUID]
    outcome_attributions: list[DigitalOutcomeAttributionPatch]


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
        if (
            self.kind is ProductCapabilityKind.VERIFIED_CAPABILITY
            and not self.independent_evidence_ids
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


class ProductNormalizationCandidateView(ContractModel):
    id: UUID
    incoming_version_id: UUID
    candidate_version_id: UUID
    candidate_type: Literal["MODEL_ALIAS", "VERSION_SUCCESSOR", "POSSIBLE_DUPLICATE"]
    status: Literal["PENDING_REVIEW", "ACCEPTED", "REJECTED"]
    incoming_label: str = Field(min_length=1, max_length=1000)
    candidate_label: str = Field(min_length=1, max_length=1000)
    created_at: datetime


class ProductNormalizationDecisionRequest(ContractModel):
    action: Literal["MERGE_ALIAS", "LINK_AS_NEW_VERSION", "KEEP_DISTINCT"]
    reason: str = Field(min_length=1, max_length=1000)


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
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,79}$")
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
        if self.overridden and not self.override_reason:
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


class SourceLineageRole(StrEnum):
    ORIGINAL = "ORIGINAL"
    REPRINT = "REPRINT"
    MIRROR = "MIRROR"
    INDEPENDENT_REPORT = "INDEPENDENT_REPORT"


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
    original_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
    accepted_claim_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)


class SourceComparison(ContractModel):
    event_id: UUID
    independent_source_count: int = Field(ge=0)
    sources: list[SourceComparisonEntry]


class ClusterCandidateView(ContractModel):
    id: UUID
    kind: Literal["DUPLICATE", "EVENT", "TOPIC", "RELATION"]
    status: Literal["PENDING_REVIEW", "ACCEPTED", "REJECTED"]
    member_ids: list[UUID] = Field(min_length=2, max_length=1000)
    score_bps: int | None = Field(default=None, ge=0, le=10000)
    relation_type: str | None = Field(default=None, min_length=1, max_length=50)
    feature_explanations: list[str] = Field(max_length=30)
    hard_conflicts: list[str] = Field(max_length=10)
    created_at: datetime


class ClusterDecisionRequest(ContractModel):
    action: Literal["MERGE", "SPLIT", "KEEP_DISTINCT", "LINK_RELATION"]
    member_ids: list[UUID] = Field(min_length=2, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    relation_type: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_relation_type(self) -> "ClusterDecisionRequest":
        if self.action == "LINK_RELATION" and self.relation_type is None:
            raise ValueError("relation_type is required for LINK_RELATION")
        if self.action != "LINK_RELATION" and self.relation_type is not None:
            raise ValueError("relation_type is only accepted for LINK_RELATION")
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("member_ids must be unique")
        return self


class ScoreOverrideRequest(ContractModel):
    dimension: ScoreDimension
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=1000)


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
    original_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
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


class FeedPage(ContractModel):
    items: list[ItemSummary]
    next_cursor: str | None
    fingerprint: str = Field(min_length=1, max_length=200)
    generated_at: datetime
    freshness: Literal["fresh", "delayed", "partial"]
    notices: list[FeedNotice]


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
    original_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
    review_status: ReviewStatus
    publication_revision_id: UUID | None
    relation_type: EventRelation | None = None
    evidence_count: int | None = Field(default=None, ge=0)
    document_states: list[DocumentState] | None = None


class EventTimeline(ContractModel):
    event_id: UUID
    items: list[EventItem]


class EventCandidateGenerationResponse(ContractModel):
    candidate_id: UUID
    status: Literal["PENDING_REVIEW"]
    requires_human_review: Literal[True]


class EventRelationView(ContractModel):
    id: UUID
    event_id: UUID
    from_item_id: UUID
    to_item_id: UUID
    relation_type: EventRelation
    reviewed_by: UUID
    reviewed_at: datetime


class EventDetail(ContractModel):
    id: UUID
    title: str = Field(min_length=1, max_length=500)
    event_type: EventType = EventType.SAFETY_INCIDENT
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
    similar_scenario_tags: list[SimilarScenarioTag]
    prevention_measure_tags: list[PreventionMeasureTag]
    topic_ids: list[UUID] = Field(default_factory=list)
    independent_source_count: int = Field(default=0, ge=0)
    scores: ScoreSummary | None = None


class ClaimConflictStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    RESOLVED = "RESOLVED"


class ClaimConflictDecisionAction(StrEnum):
    ACCEPT_CANDIDATE = "ACCEPT_CANDIDATE"
    KEEP_CURRENT = "KEEP_CURRENT"
    MARK_UNRESOLVED = "MARK_UNRESOLVED"


class ClaimConflict(ContractModel):
    id: UUID
    event_id: UUID
    field: CriticalSafetyField
    current_claim_id: UUID | None
    current_value: FactValue | None
    candidate_claim_id: UUID
    candidate_value: FactValue
    status: ClaimConflictStatus
    detected_at: datetime
    resolved_claim_id: UUID | None = None
    resolved_by: UUID | None = None
    resolved_at: datetime | None = None
    resolution_reason: str | None = Field(default=None, min_length=1, max_length=1000)


class ClaimConflictDecisionRequest(ContractModel):
    action: ClaimConflictDecisionAction
    reason: str = Field(min_length=1, max_length=1000)


class ClaimConflictDecisionResponse(ContractModel):
    conflict_id: UUID
    status: ClaimConflictStatus
    action: ClaimConflictDecisionAction
    resolved_claim_id: UUID | None
    resolved_at: datetime | None

    @model_validator(mode="after")
    def validate_resolution_audit(self) -> "ClaimConflictDecisionResponse":
        if self.status is ClaimConflictStatus.RESOLVED:
            if self.action is ClaimConflictDecisionAction.MARK_UNRESOLVED:
                raise ValueError("an unresolved decision cannot resolve a conflict")
            if self.resolved_claim_id is None or self.resolved_at is None:
                raise ValueError("resolved conflicts require the chosen claim and timestamp")
        else:
            if self.action is not ClaimConflictDecisionAction.MARK_UNRESOLVED:
                raise ValueError("pending conflicts require MARK_UNRESOLVED")
            if self.resolved_claim_id is not None or self.resolved_at is not None:
                raise ValueError("pending conflicts cannot contain resolution audit fields")
        return self


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
    paragraph_id: str = Field(pattern=r"^html-p-\d{4}$")
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
    paragraph_id: str | None = Field(default=None, pattern=r"^html-p-\d{4}$")
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, gt=0)
    excerpt: str = Field(min_length=1, max_length=2000)
    excerpt_sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    original_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)

    @model_validator(mode="after")
    def require_one_locator(self) -> "EvidenceView":
        legacy = (
            self.paragraph_id is not None
            and self.char_start is not None
            and self.char_end is not None
        )
        if self.locator is None and not legacy:
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
    preview_url: str = Field(pattern=r"^/api/v1/document-versions/[0-9a-f-]+/pages/\d+/preview$")


class ReviewCandidateDecisionRequest(ContractModel):
    action: Literal["ACCEPT", "REJECT", "CONFIRM_UNRESOLVED"]
    reason: str = Field(min_length=1, max_length=1000)
    target_document_id: UUID | None = None


class VersionChangeEscalationRequest(ContractModel):
    reason: str = Field(min_length=1, max_length=1000)


class ItemDetail(ContractModel):
    item: ItemSummary
    notice: FeedNotice | None = None
    claims: list[ClaimView] | None = None
    evidence: list[EvidenceView] | None = None
    digital_case: DigitalCaseDetail | None = None
    paper: PaperDetail | None = None
    technology_product: TechnologyProductDetail | None = None


class ReviewDecisionRequest(ContractModel):
    action: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=1, max_length=1000)
    digital_case_patch: DigitalCaseReviewPatch | None = None

    @model_validator(mode="after")
    def reject_patch_on_rejection(self) -> "ReviewDecisionRequest":
        if self.action == "REJECT" and self.digital_case_patch is not None:
            raise ValueError("digital case patches are only accepted with APPROVE")
        return self


class ReviewDecisionResponse(ContractModel):
    review_task_id: UUID
    status: ReviewStatus
    publication_revision_id: UUID | None


class PublicationRevisionRequest(ContractModel):
    reason: str = Field(min_length=1, max_length=1000)


class PublicationWithdrawalRequest(ContractModel):
    reason: str = Field(min_length=1, max_length=1000)
    evidence_id: UUID


class ReviewTaskSummary(ContractModel):
    id: UUID
    item_id: UUID
    status: ReviewStatus
    risk_level: RiskLevel
    title: str = Field(min_length=1, max_length=500)
    source_name: str = Field(min_length=1, max_length=200)
    submitted_by: UUID
    submitted_at: datetime
    assigned_to: UUID | None = None


class ReviewTaskDetail(ContractModel):
    task: ReviewTaskSummary
    item: ItemSummary
    claims: list[ClaimView]
    evidence: list[EvidenceView]
    digital_case: DigitalCaseDetail | None = None
    paper: PaperDetail | None = None


class MeResponse(ContractModel):
    user_id: UUID
    display_name: str
    roles: list[UserRole]
    local_identity: bool
