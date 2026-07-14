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


TypeSummaryValue = Annotated[
    SafetyRegulationTypeSummary | SafetyCaseTypeSummary,
    Field(discriminator="kind"),
]


class TypeSummary(RootModel[TypeSummaryValue]):
    """Tagged union exported for TypeScript consumers."""


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
    report_stage: SafetyCaseReportStage
    incident_status: IncidentStatus
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
    project_name: str | None = Field(default=None, min_length=1, max_length=300)
    occurred_at: datetime | None = None
    region: str | None = Field(default=None, min_length=1, max_length=200)
    hazard_type: str | None = Field(default=None, min_length=1, max_length=100)
    engineering_type: str | None = Field(default=None, min_length=1, max_length=100)
    incident_status: IncidentStatus
    rectification_has_open_issues: bool | None = None
    confirmed_facts: list[ConfirmedFact]
    unverified_facts: list[UnverifiedFact]
    timeline: EventTimeline
    relations: list[EventRelationView]
    similar_scenario_tags: list[SimilarScenarioTag]
    prevention_measure_tags: list[PreventionMeasureTag]


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


class ReviewDecisionRequest(ContractModel):
    action: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=1, max_length=1000)


class ReviewDecisionResponse(ContractModel):
    review_task_id: UUID
    status: ReviewStatus
    publication_revision_id: UUID | None


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


class MeResponse(ContractModel):
    user_id: UUID
    display_name: str
    roles: list[UserRole]
    local_identity: bool
