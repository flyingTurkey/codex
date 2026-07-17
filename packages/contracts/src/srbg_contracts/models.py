"""Canonical public contracts shared by API and Worker processes."""

import ipaddress
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
        or re.search(r"(?:https?|vault)://|\S+@\S+", lowered)
        or re.search(
            r"(?:^|[^a-z])(?:api[_-]?key|authorization|bearer|cookie|credential|"
            r"password|secret|token|vault)(?:[^a-z]|$)",
            lowered,
        )
    ):
        raise ValueError("governance reason contains forbidden sensitive material")
    return value


GovernanceReason = Annotated[
    str,
    Field(min_length=1, max_length=500),
    AfterValidator(_validate_governance_reason),
]


def _validate_evidence_reference(value: str) -> str:
    lowered = value.casefold()
    if (
        any(ord(character) < 33 or ord(character) == 127 for character in value)
        or re.search(r"://[^/\s]+@", value)
        or re.search(
            r"[?&](?:api[_-]?key|access[_-]?key|auth(?:orization|_token)?|"
            r"bearer|client[_-]?secret|cookie|credential|password|secret|session|"
            r"signature|token)=[^&]+",
            lowered,
        )
    ):
        raise ValueError("evidence reference contains forbidden sensitive material")
    return value


CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
RegionCode = Annotated[
    str,
    Field(min_length=2, max_length=16, pattern=r"^[A-Z0-9]{2,3}(?:-[A-Z0-9]{1,6})?$"),
]
LanguageTag = Annotated[
    str,
    Field(min_length=2, max_length=35, pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$"),
]
AssessmentReasonCode = Annotated[
    str,
    Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$"),
]
EvidenceReference = Annotated[
    str,
    Field(min_length=1, max_length=500),
    AfterValidator(_validate_evidence_reference),
]


def _normalize_to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


AssessmentTimestamp = Annotated[
    AwareDatetime,
    AfterValidator(_normalize_to_utc),
]


class UserRole(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    SOURCE_ADMIN = "source_admin"
    PLATFORM_ADMIN = "platform_admin"
    AUDITOR = "auditor"
    GOLD_ANNOTATOR = "gold_annotator"
    GOLD_ARBITRATOR = "gold_arbitrator"


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


class SourceState(StrEnum):
    """Deprecated V1 source state retained only for compatibility projections."""

    CANDIDATE = "CANDIDATE"
    COMPLIANCE_REVIEW = "COMPLIANCE_REVIEW"
    FIXTURE_TEST = "FIXTURE_TEST"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"


class SourceLifecycleState(StrEnum):
    """Authoritative V2 source lifecycle computed by the server."""

    CANDIDATE = "CANDIDATE"
    COMPLIANCE_REVIEW = "COMPLIANCE_REVIEW"
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class SourceTrialKind(StrEnum):
    FIXTURE_REPLAY = "FIXTURE_REPLAY"
    LIVE_TRIAL = "LIVE_TRIAL"


class RuntimeAuthorization(StrEnum):
    """Server-derived execution authorization; never accepted as client input."""

    DENIED = "DENIED"
    TRIAL_ONLY = "TRIAL_ONLY"
    PRODUCTION = "PRODUCTION"


class SourceLifecycleAction(StrEnum):
    SUBMIT_COMPLIANCE = "SUBMIT_COMPLIANCE"
    START_FIXTURE_TRIAL = "START_FIXTURE_TRIAL"
    START_LIVE_TRIAL = "START_LIVE_TRIAL"
    APPROVE_PRODUCTION = "APPROVE_PRODUCTION"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    RETIRE = "RETIRE"


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


class DiscoveryChannel(StrEnum):
    DIRECTORY = "DIRECTORY"
    RSS = "RSS"
    SITEMAP = "SITEMAP"
    OUTBOUND_LINK = "OUTBOUND_LINK"
    MANUAL = "MANUAL"
    BAIDU_SEARCH = "BAIDU_SEARCH"


class SourceCandidateStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    QUALIFYING = "QUALIFYING"
    READY_FOR_DECISION = "READY_FOR_DECISION"
    ENABLED = "ENABLED"
    DISMISSED = "DISMISSED"
    BLOCKED = "BLOCKED"
    STALE = "STALE"


class QualificationRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class QualificationVerdict(StrEnum):
    QUALIFIED = "QUALIFIED"
    WARN_WAIVABLE = "WARN_WAIVABLE"
    BLOCKED = "BLOCKED"


class QualificationCheckLevel(StrEnum):
    PASS = "PASS"  # noqa: S105 - qualification outcome, not a credential
    WARN = "WARN"
    BLOCK = "BLOCK"


class EvidenceCapturePolicy(StrEnum):
    """How qualification evidence may be captured, independent of display policy."""

    PRIVATE_RAW_ALLOWED = "PRIVATE_RAW_ALLOWED"
    TRANSIENT_METADATA_ONLY = "TRANSIENT_METADATA_ONLY"


class SourceCandidateDecision(StrEnum):
    ENABLE = "ENABLE"
    DISMISS = "DISMISS"


class SourceCandidateDecisionItemOutcome(StrEnum):
    APPLIED = "APPLIED"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


class SourceCandidateAction(StrEnum):
    REQUEST_QUALIFICATION = "REQUEST_QUALIFICATION"
    ENABLE = "ENABLE"
    DISMISS = "DISMISS"


class SourceStreamStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    REVOKED = "REVOKED"


class SourceStreamAction(StrEnum):
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    REQUEST_REPAIR = "REQUEST_REPAIR"
    REVOKE = "REVOKE"


class DisplayPolicy(StrEnum):
    METADATA_EXCERPT_LINK = "METADATA_EXCERPT_LINK"
    OFFICIAL_READER_LINK = "OFFICIAL_READER_LINK"
    LINK_ONLY = "LINK_ONLY"


class DownloadPolicy(StrEnum):
    DISABLED = "DISABLED"
    ORIGINAL_LINK_ONLY = "ORIGINAL_LINK_ONLY"
    SIGNED_INTERNAL_COPY = "SIGNED_INTERNAL_COPY"


class LegalHoldPolicy(StrEnum):
    SUPPORTED = "SUPPORTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AutomaticPublicationPolicy(StrEnum):
    DISABLED = "DISABLED"
    PUBLICATION_GATE_ELIGIBLE = "PUBLICATION_GATE_ELIGIBLE"


class SloApplicability(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SourcePolicyDecisionOutcome(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SourceTrialRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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
    search_schema_version: Literal["1.0.0"] = "1.0.0"
    semantic_search_enabled: bool = False


class MetricSample(ContractModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$", max_length=80)
    value: int | float
    unit: Literal["count", "percent", "ms", "seconds", "minutes", "microusd"]
    status: Literal["PASS", "FAIL", "UNKNOWN"]


class OperationsOverview(ContractModel):
    observed_at: datetime
    metrics: list[MetricSample]


class FetchScheduleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class FetchScheduleUpdate(ContractModel):
    status: FetchScheduleStatus
    interval_seconds: int = Field(ge=60, le=2_592_000)
    freshness_slo_seconds: int = Field(ge=300, le=31_536_000)
    rate_limit_per_minute: int = Field(ge=1, le=600)
    daily_request_budget: int = Field(ge=1, le=1_000_000)
    daily_byte_budget: int = Field(ge=1, le=10_000_000_000_000)
    expected_version: int = Field(ge=0)
    reason: GovernanceReason


class FetchScheduleView(ContractModel):
    source_id: UUID
    authority_level: str
    status: FetchScheduleStatus
    interval_seconds: int
    next_run_at: datetime
    circuit_state: CircuitState
    circuit_open_until: datetime | None = None
    consecutive_failures: int
    freshness_slo_seconds: int
    rate_limit_per_minute: int
    daily_request_budget: int
    daily_byte_budget: int
    requests_used: int
    bytes_used: int
    version: int
    updated_at: datetime


class SourceAnomalyView(ContractModel):
    id: UUID
    source_id: UUID
    code: str
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]
    detected_at: datetime


class SourceHealthView(ContractModel):
    source_id: UUID
    fetch_run_id: UUID
    transport_status: str
    discovery_status: str
    parse_status: str
    quality_status: str
    freshness_status: str
    rule_version: str
    observed_at: datetime
    anomalies: list[SourceAnomalyView] = Field(default_factory=list)


class ReplayTaskView(ContractModel):
    id: UUID
    task_kind: str
    error_code: str
    priority: int = Field(ge=0, le=9)
    reconstruction_status: Literal["REPLAYABLE", "NON_REPLAYABLE", "BLOCKED"]
    blocked_reason: str | None = None
    source_id: UUID | None = None
    run_id: UUID | None = None
    document_version_id: UUID | None = None
    event_id: UUID | None = None
    failed_at: datetime
    replay_status: str | None = None


class ReplayRequest(ContractModel):
    failed_task_id: UUID
    reason: str = Field(min_length=10, max_length=500)
    priority: int = Field(default=5, ge=0, le=9)


class ReplayResult(ContractModel):
    id: UUID
    failed_task_id: UUID
    task_kind: str
    priority: int = Field(ge=0, le=9)
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "BLOCKED", "NON_REPLAYABLE"]


class FeedbackRequest(ContractModel):
    item_id: UUID | None = None
    event_id: UUID | None = None
    value: Literal["USEFUL", "NOT_USEFUL"]

    @model_validator(mode="after")
    def require_one_identity(self) -> "FeedbackRequest":
        if (self.item_id is None) == (self.event_id is None):
            raise ValueError("exactly one of item_id or event_id is required")
        return self


class PilotMetrics(ContractModel):
    started_at: datetime
    ended_at: datetime
    aggregate_effective_actions: int = Field(ge=0)
    distinct_feedback_users: int = Field(ge=0)
    useful_votes: int = Field(ge=0)
    total_votes: int = Field(ge=0)
    identity_metrics_available: Literal[False] = False
    sufficient_window: bool


class PilotWindowState(StrEnum):
    PREPARING = "PREPARING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class PilotRunOrigin(StrEnum):
    SCHEDULED = "SCHEDULED"
    REPLAY = "REPLAY"
    BACKFILL = "BACKFILL"
    DRILL = "DRILL"


class PilotWindowCreateRequest(ContractModel):
    roster_version: str = Field(pattern=r"^r17-sources-v\d+\.\d+$", max_length=80)
    metric_definition_version: str = Field(
        pattern=r"^phase2-round17-metrics-v\d+\.\d+\.\d+$", max_length=80
    )
    gold_definition_version: str = Field(
        pattern=r"^phase2-round17-gold-v\d+\.\d+\.\d+$", max_length=80
    )
    baseline_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    config_version: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    database_revision: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    source_codes: list[str] = Field(min_length=20, max_length=20)
    environment: Literal["PREPRODUCTION"] = "PREPRODUCTION"
    duration_hours: Literal[168] = 168
    reason: GovernanceReason

    @model_validator(mode="after")
    def require_exact_unique_source_cohort(self) -> "PilotWindowCreateRequest":
        if len(set(self.source_codes)) != 20:
            raise ValueError("the pilot cohort must contain 20 unique source codes")
        if any(re.fullmatch(r"[A-Z]{3}-[0-9]{3}", code) is None for code in self.source_codes):
            raise ValueError("source codes must use the canonical registry format")
        return self


class PilotWindowStartRequest(ContractModel):
    expected_version: int = Field(ge=1)
    reason: GovernanceReason


class PilotSourceResumeRequest(ContractModel):
    expected_version: int = Field(ge=1)
    reason: GovernanceReason


class PilotWindowCompleteRequest(ContractModel):
    expected_version: int = Field(ge=1)
    reason: GovernanceReason


class PilotWindowView(ContractModel):
    id: UUID
    roster_version: str
    metric_definition_version: str
    gold_definition_version: str
    baseline_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    config_version: str
    database_revision: str
    environment: Literal["PREPRODUCTION"]
    duration_hours: Literal[168]
    source_count: int = Field(ge=0, le=20)
    state: PilotWindowState
    version: int = Field(ge=1)
    prepared_at: datetime
    started_at: datetime | None = None
    ends_at: datetime | None = None
    blocker_codes: list[str] = Field(default_factory=list, max_length=100)


class OperatorWorkCategory(StrEnum):
    SOURCE_MAINTENANCE = "SOURCE_MAINTENANCE"
    EXCEPTION_HANDLING = "EXCEPTION_HANDLING"
    R3_REVIEW = "R3_REVIEW"
    COPYRIGHT_CORRECTION = "COPYRIGHT_CORRECTION"


class OperatorTaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class OperatorTaskCreateRequest(ContractModel):
    window_id: UUID
    source_id: UUID | None = None
    category: OperatorWorkCategory
    reason: GovernanceReason

    @model_validator(mode="after")
    def require_uuid7_references(self) -> "OperatorTaskCreateRequest":
        if self.window_id.version != 7:
            raise ValueError("operator tasks must reference a UUIDv7 pilot window")
        if self.source_id is not None and self.source_id.version != 7:
            raise ValueError("operator tasks must reference a UUIDv7 source")
        return self


class OperatorTaskCompleteRequest(ContractModel):
    expected_version: int = Field(ge=2)
    reason: GovernanceReason


class OperatorTaskView(ContractModel):
    id: UUID
    window_id: UUID
    source_id: UUID | None = None
    category: OperatorWorkCategory
    assigned_to: UUID
    status: OperatorTaskStatus
    created_by: UUID
    created_at: datetime
    started_at: datetime | None = None
    completed_by: UUID | None = None
    completed_at: datetime | None = None
    version: int = Field(default=1, ge=1)


class OperatorWorkSessionStart(ContractModel):
    task_id: UUID

    @model_validator(mode="after")
    def require_uuid7_task(self) -> "OperatorWorkSessionStart":
        if self.task_id.version != 7:
            raise ValueError("operator work must reference a UUIDv7 operator task")
        return self


class OperatorWorkSessionHeartbeatRequest(ContractModel):
    expected_version: int = Field(ge=1)


class OperatorWorkSessionStopRequest(ContractModel):
    expected_version: int = Field(ge=1)


class OperatorWorkSessionCorrectionRequest(ContractModel):
    expected_version: int = Field(ge=1)
    active_seconds: int = Field(ge=0, le=43_200)
    reason_code: Literal[
        "TIMER_INTERRUPTED",
        "MISSED_STOP",
        "DUPLICATE_SESSION",
        "ADMINISTRATIVE_CORRECTION",
    ]


class OperatorWorkSessionView(ContractModel):
    id: UUID
    task_id: UUID
    window_id: UUID
    actor_id: UUID
    category: OperatorWorkCategory
    started_at: datetime
    last_activity_at: datetime
    stopped_at: datetime | None = None
    active_seconds: int | None = Field(default=None, ge=0, le=43_200)
    corrected: bool = False
    version: int = Field(default=1, ge=1)


class GoldSampleKind(StrEnum):
    DOCUMENT = "DOCUMENT"
    PAIR = "PAIR"
    EVENT = "EVENT"
    CLAIM_EVIDENCE = "CLAIM_EVIDENCE"
    SEARCH_QUESTION = "SEARCH_QUESTION"


class GoldTaskCreateRequest(ContractModel):
    sample_kind: GoldSampleKind
    sample_ref: str = Field(
        pattern=(
            r"^urn:srbg:(document|pair|event|claim-evidence|search-question):"
            r"[0-9a-f-]{36}(?::[0-9a-f-]{36})?$"
        ),
        max_length=140,
    )
    source_code: str = Field(pattern=r"^[A-Z]{3}-[0-9]{3}$")
    domain: Channel
    production_decision_id: UUID
    assigned_annotator_ids: list[UUID] = Field(min_length=1, max_length=2)
    critical_safety: bool = False
    secondary_review_required: bool = False
    reason: GovernanceReason

    @model_validator(mode="after")
    def require_distinct_assignments(self) -> "GoldTaskCreateRequest":
        if len(set(self.assigned_annotator_ids)) != len(self.assigned_annotator_ids):
            raise ValueError("gold task annotators must be distinct")
        if any(actor.version != 7 for actor in self.assigned_annotator_ids):
            raise ValueError("gold annotator identities must be UUIDv7")
        if self.production_decision_id.version != 7:
            raise ValueError("gold production decision must be UUIDv7")
        prefix, *identities = self.sample_ref.removeprefix("urn:srbg:").split(":")
        expected_prefix = {
            GoldSampleKind.DOCUMENT: "document",
            GoldSampleKind.PAIR: "pair",
            GoldSampleKind.EVENT: "event",
            GoldSampleKind.CLAIM_EVIDENCE: "claim-evidence",
            GoldSampleKind.SEARCH_QUESTION: "search-question",
        }[self.sample_kind]
        expected_identity_count = 2 if self.sample_kind in {
            GoldSampleKind.PAIR,
            GoldSampleKind.CLAIM_EVIDENCE,
        } else 1
        if prefix != expected_prefix or len(identities) != expected_identity_count:
            raise ValueError("gold sample reference does not match its sample kind")
        try:
            parsed_identities = [UUID(value) for value in identities]
        except ValueError as error:
            raise ValueError("gold sample references require UUID identities") from error
        if any(identity.version != 7 for identity in parsed_identities):
            raise ValueError("gold sample references require UUIDv7 identities")
        if self.critical_safety and (
            self.domain is not Channel.SAFETY
            or not self.secondary_review_required
            or len(self.assigned_annotator_ids) != 2
        ):
            raise ValueError("critical safety tasks require two independent annotators")
        if self.secondary_review_required and len(self.assigned_annotator_ids) != 2:
            raise ValueError("secondary review requires two independent annotators")
        if not self.secondary_review_required and len(self.assigned_annotator_ids) != 1:
            raise ValueError("single review tasks require exactly one annotator")
        return self


class GoldTaskView(ContractModel):
    id: UUID
    sample_kind: GoldSampleKind
    sample_ref: str
    source_code: str
    domain: Channel
    production_decision_id: UUID
    critical_safety: bool
    secondary_review_required: bool
    status: Literal["ASSIGNED", "SUBMITTED", "DISAGREEMENT", "ARBITRATED", "FROZEN"]
    assigned_at: datetime


class GoldArbitrationOption(ContractModel):
    annotation_id: UUID
    decision_code: str
    label_value: str | None = Field(default=None, max_length=2000)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=100)
    related_sample_refs: list[EvidenceReference] = Field(default_factory=list, max_length=100)


class GoldArbitrationPacket(ContractModel):
    task: GoldTaskView
    options: list[GoldArbitrationOption] = Field(min_length=2, max_length=2)


class GoldAnnotationRequest(ContractModel):
    task_id: UUID
    sample_kind: GoldSampleKind
    decision_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,79}$")
    label_value: str | None = Field(default=None, max_length=2000)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=100)
    related_sample_refs: list[EvidenceReference] = Field(default_factory=list, max_length=100)


class GoldAnnotationView(ContractModel):
    id: UUID
    task_id: UUID
    annotator_id: UUID
    sample_kind: GoldSampleKind
    decision_code: str
    submitted_at: datetime
    status: Literal["SUBMITTED", "SUPERSEDED"]


class GoldArbitrationRequest(ContractModel):
    task_id: UUID
    selected_annotation_id: UUID
    reason: GovernanceReason


class GoldReleaseRequest(ContractModel):
    version: str = Field(pattern=r"^phase2-round17-gold-v\d+\.\d+\.\d+$", max_length=80)
    reason: GovernanceReason


class GoldReleaseView(ContractModel):
    id: UUID
    version: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_by: UUID
    frozen_at: datetime
    status: Literal["FROZEN"] = "FROZEN"


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


class QualificationCheckView(ContractModel):
    code: AssessmentReasonCode
    level: QualificationCheckLevel
    message: str = Field(min_length=1, max_length=500)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=50)
    observed_at: AssessmentTimestamp

    @model_validator(mode="after")
    def reject_future_observation(self) -> "QualificationCheckView":
        if self.observed_at > datetime.now(UTC):
            raise ValueError("qualification observations cannot be in the future")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("qualification evidence references must be unique")
        return self


class QualificationBundleView(ContractModel):
    id: UUID
    candidate_id: UUID
    run_id: UUID
    rule_version: str = Field(min_length=1, max_length=100)
    material_fingerprint: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    verdict: QualificationVerdict
    storage_policy: StoragePolicy
    evidence_capture_policy: EvidenceCapturePolicy = EvidenceCapturePolicy.PRIVATE_RAW_ALLOWED
    checks: list[QualificationCheckView] = Field(default_factory=list, max_length=100)
    sampled_item_count: int = Field(ge=0, le=10000)
    relevant_item_count: int = Field(ge=0, le=10000)
    reason_codes: list[AssessmentReasonCode] = Field(default_factory=list, max_length=100)
    bundle_sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: AssessmentTimestamp
    expires_at: AssessmentTimestamp

    @model_validator(mode="after")
    def validate_bundle_consistency(self) -> "QualificationBundleView":
        if self.relevant_item_count > self.sampled_item_count:
            raise ValueError("relevant item count cannot exceed sampled item count")
        if self.expires_at <= self.created_at:
            raise ValueError("qualification bundle expiry must follow creation")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("qualification reason codes must be unique")
        return self


class SourceCandidateCreateRequest(ContractModel):
    """Discovery input; lifecycle status and qualification facts remain server-owned."""

    url: HttpUrlString = Field(pattern=r"^https://[^\s]+$", max_length=2048)
    industries: list[SourceIndustry] = Field(default_factory=list, max_length=30)
    content_domains: list[SourceContentDomain] = Field(default_factory=list, max_length=30)
    language_tags: list[LanguageTag] = Field(default_factory=list, max_length=20)
    reason: GovernanceReason

    @model_validator(mode="after")
    def require_unique_classification_values(self) -> "SourceCandidateCreateRequest":
        fields = (self.industries, self.content_domains, self.language_tags)
        if any(len(values) != len(set(values)) for values in fields):
            raise ValueError("candidate classification values must be unique")
        return self


class SourceCandidateSummary(ContractModel):
    id: UUID
    institution_name: str
    canonical_url: HttpUrlString
    authorization_boundary: str
    discovery_channels: list[DiscoveryChannel]
    status: SourceCandidateStatus
    industries: list[SourceIndustry] = Field(default_factory=list)
    content_domains: list[SourceContentDomain] = Field(default_factory=list)
    language_tags: list[LanguageTag] = Field(default_factory=list)
    occurrence_count: int = Field(ge=1)
    first_discovered_at: AssessmentTimestamp
    last_discovered_at: AssessmentTimestamp
    latest_qualification: QualificationBundleView | None = None
    available_actions: list[SourceCandidateAction] = Field(default_factory=list)
    batch_enable_eligible: bool = False

    @model_validator(mode="after")
    def validate_discovery_window(self) -> "SourceCandidateSummary":
        if self.last_discovered_at < self.first_discovered_at:
            raise ValueError("last discovery cannot precede first discovery")
        return self


class SourceCandidateDetail(SourceCandidateSummary):
    discovery_references: list[EvidenceReference] = Field(default_factory=list, max_length=100)
    qualification_history: list[QualificationBundleView] = Field(
        default_factory=list,
        max_length=50,
    )
    enabled_source_id: UUID | None = None
    dismissed_reason: str | None = None


class SourceCandidatePage(ContractModel):
    items: list[SourceCandidateSummary]
    next_cursor: str | None = None
    has_more: bool
    status_counts: dict[SourceCandidateStatus, int] = Field(default_factory=dict)


class SourceCandidateQualificationRequest(ContractModel):
    reason: GovernanceReason


class QualificationRunView(ContractModel):
    id: UUID
    candidate_id: UUID
    status: QualificationRunStatus
    rule_version: str = Field(min_length=1, max_length=100)
    requested_by: UUID
    created_at: AssessmentTimestamp
    started_at: AssessmentTimestamp | None = None
    completed_at: AssessmentTimestamp | None = None
    failure_code: AssessmentReasonCode | None = None
    bundle: QualificationBundleView | None = None


class SourceCandidateDecisionRequest(ContractModel):
    decision: SourceCandidateDecision
    expected_bundle_sha256: Sha256String | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    reason: GovernanceReason
    waiver_reason: GovernanceReason | None = None

    @model_validator(mode="after")
    def bind_enable_to_bundle(self) -> "SourceCandidateDecisionRequest":
        if self.decision is SourceCandidateDecision.ENABLE and self.expected_bundle_sha256 is None:
            raise ValueError("enable requires the expected qualification bundle SHA-256")
        if self.decision is SourceCandidateDecision.DISMISS and self.waiver_reason is not None:
            raise ValueError("dismiss does not accept a qualification waiver")
        return self


class SourceCandidateDecisionResult(ContractModel):
    candidate_id: UUID
    status: SourceCandidateStatus
    source_id: UUID | None = None
    production_refetch_enqueued: bool
    idempotent_replay: bool
    decided_at: AssessmentTimestamp


class SourceCandidateBatchTarget(ContractModel):
    candidate_id: UUID
    expected_bundle_sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")


class SourceCandidateBatchDecisionRequest(ContractModel):
    targets: list[SourceCandidateBatchTarget] = Field(min_length=1, max_length=10)
    expected_rule_version: str = Field(min_length=1, max_length=100)
    reason: GovernanceReason

    @model_validator(mode="after")
    def require_unique_candidates(self) -> "SourceCandidateBatchDecisionRequest":
        candidate_ids = [target.candidate_id for target in self.targets]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("batch decision candidate targets must be unique")
        return self


class SourceCandidateDecisionItemResult(ContractModel):
    candidate_id: UUID
    outcome: SourceCandidateDecisionItemOutcome
    status: SourceCandidateStatus | None = None
    source_id: UUID | None = None
    production_refetch_enqueued: bool
    reason_code: AssessmentReasonCode | None = None


class SourceCandidateBatchDecisionResult(ContractModel):
    items: list[SourceCandidateDecisionItemResult] = Field(min_length=1, max_length=10)
    rule_version: str
    decided_at: AssessmentTimestamp
    idempotent_replay: bool


class SourceStreamView(ContractModel):
    id: UUID
    source_id: UUID
    candidate_id: UUID | None
    institution_name: str
    canonical_url: HttpUrlString
    authorization_boundary: str
    stream_key: str = Field(min_length=1, max_length=200)
    status: SourceStreamStatus
    rule_version: str
    available_actions: list[SourceStreamAction] = Field(default_factory=list)
    last_success_at: AssessmentTimestamp | None = None
    last_failure_at: AssessmentTimestamp | None = None
    consecutive_failure_count: int = Field(default=0, ge=0)
    next_fetch_at: AssessmentTimestamp | None = None
    updated_at: AssessmentTimestamp


class SourceStreamPage(ContractModel):
    items: list[SourceStreamView]
    next_cursor: str | None = None
    has_more: bool


class SourceAttentionItem(ContractModel):
    stream: SourceStreamView
    reason_codes: list[AssessmentReasonCode] = Field(min_length=1, max_length=20)
    first_observed_at: AssessmentTimestamp
    last_observed_at: AssessmentTimestamp

    @model_validator(mode="after")
    def validate_attention_window(self) -> "SourceAttentionItem":
        if self.last_observed_at < self.first_observed_at:
            raise ValueError("last attention observation cannot precede the first")
        return self


class SourceAttentionPage(ContractModel):
    items: list[SourceAttentionItem]
    next_cursor: str | None = None
    has_more: bool


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
    governance_owner_id: UUID | None = None
    country_codes: list[CountryCode] = Field(default_factory=list, max_length=20)
    region_codes: list[RegionCode] = Field(default_factory=list, max_length=50)
    language_tags: list[LanguageTag] = Field(default_factory=list, max_length=20)
    industries: list[SourceIndustry] = Field(default_factory=list, max_length=20)
    content_domains: list[SourceContentDomain] = Field(default_factory=list, max_length=30)
    declared_roles: list[SourceDeclaredRole] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_unique_governance_values(self) -> "CreateSourceRequest":
        fields = (
            self.country_codes,
            self.region_codes,
            self.language_tags,
            self.industries,
            self.content_domains,
            self.declared_roles,
        )
        if any(len(values) != len(set(values)) for values in fields):
            raise ValueError("source governance metadata values must be unique")
        return self


class ReviewEvidence(ContractModel):
    result: ReviewEvidenceResult
    evidence_url: Annotated[
        HttpUrlString,
        AfterValidator(_validate_evidence_reference),
    ] = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
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
    user_agent: str = Field(min_length=1, max_length=300, pattern=r"^[^\x00-\x1f\x7f]+$")


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


class SourceFetchPolicy(ContractModel):
    allowed_domains: list[str] = Field(min_length=1, max_length=100)
    minimum_interval_seconds: int = Field(ge=1, le=604800)
    rate_limit_per_minute: int = Field(ge=1, le=10000)
    user_agent: str = Field(min_length=1, max_length=300, pattern=r"^[^\x00-\x1f\x7f]+$")

    @model_validator(mode="after")
    def validate_domains(self) -> "SourceFetchPolicy":
        normalized = [domain.rstrip(".").lower() for domain in self.allowed_domains]
        if any(
            not domain
            or "://" in domain
            or "/" in domain
            or "@" in domain
            or "*" in domain
            or domain == "localhost"
            or re.fullmatch(
                r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
                domain,
            )
            is None
            for domain in normalized
        ):
            raise ValueError("allowed domains must be fixed host names")
        for domain in normalized:
            try:
                ipaddress.ip_address(domain)
            except ValueError:
                continue
            raise ValueError("allowed domains cannot be IP literals")
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed domains must be unique")
        self.allowed_domains = normalized
        return self


class SourceRetentionPolicy(ContractModel):
    retention_days: int = Field(ge=1, le=36500)
    delete_after_retention: bool


class SourceSloPolicy(ContractModel):
    applicability: SloApplicability
    target_minutes: int | None = Field(default=None, ge=1, le=10080)
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    authorization_confirmed: bool
    technical_conditions_confirmed: bool

    @model_validator(mode="after")
    def validate_applicability(self) -> "SourceSloPolicy":
        if self.applicability is SloApplicability.APPLICABLE:
            if self.target_minutes is None:
                raise ValueError("an applicable SLO requires a target")
            if not self.authorization_confirmed or not self.technical_conditions_confirmed:
                raise ValueError(
                    "an applicable SLO requires authorization and technical confirmation"
                )
        if self.applicability is SloApplicability.NOT_APPLICABLE:
            if self.target_minutes is not None or self.reason is None:
                raise ValueError("a non-applicable SLO requires a reason and no target")
            if self.authorization_confirmed or self.technical_conditions_confirmed:
                raise ValueError(
                    "a non-applicable SLO cannot claim authorization or technical confirmation"
                )
        return self


class SourcePolicyV2Submission(ContractModel):
    """Declarative policy input; status and approval are server-owned facts."""

    schema_version: Literal["2.0.0"]
    policy_version: str = Field(min_length=1, max_length=50)
    valid_from: datetime
    valid_until: datetime
    robots_review: ReviewEvidence
    terms_review: ReviewEvidence
    copyright_review: ReviewEvidence
    fetch: SourceFetchPolicy
    storage_policy: StoragePolicy
    display_policy: DisplayPolicy
    download_policy: DownloadPolicy
    retention: SourceRetentionPolicy
    legal_hold_policy: LegalHoldPolicy
    automatic_publication: AutomaticPublicationPolicy
    slo: SourceSloPolicy
    reason: GovernanceReason

    @model_validator(mode="after")
    def validate_governance_policy(self) -> "SourcePolicyV2Submission":
        timestamps = (
            self.valid_from,
            self.valid_until,
            self.robots_review.checked_at,
            self.terms_review.checked_at,
            self.copyright_review.checked_at,
        )
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            raise ValueError("policy timestamps must include a UTC offset")
        if self.valid_until <= self.valid_from:
            raise ValueError("policy validity window must be positive")
        reviews = (self.robots_review, self.terms_review, self.copyright_review)
        if any(review.result is not ReviewEvidenceResult.ALLOWED for review in reviews):
            raise ValueError("robots, terms and copyright evidence must explicitly allow use")
        if any(review.evidence_sha256 is None for review in reviews):
            raise ValueError("governance evidence requires a server-verifiable SHA-256")
        self.valid_from = self.valid_from.astimezone(UTC)
        self.valid_until = self.valid_until.astimezone(UTC)
        self.robots_review = self.robots_review.model_copy(
            update={"checked_at": self.robots_review.checked_at.astimezone(UTC)}
        )
        self.terms_review = self.terms_review.model_copy(
            update={"checked_at": self.terms_review.checked_at.astimezone(UTC)}
        )
        self.copyright_review = self.copyright_review.model_copy(
            update={"checked_at": self.copyright_review.checked_at.astimezone(UTC)}
        )
        return self


class SourcePolicyDecisionRequest(ContractModel):
    outcome: SourcePolicyDecisionOutcome
    reason: GovernanceReason


class SourcePolicyVersionView(ContractModel):
    id: UUID
    source_id: UUID
    schema_version: str
    policy_version: str
    status: str
    valid_from: datetime
    valid_until: datetime
    document_sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    document: dict[str, object]
    submitted_by: UUID
    decided_by: UUID | None = None
    created_at: datetime


class SourceTrialRunRequest(ContractModel):
    kind: SourceTrialKind
    policy_version_id: UUID
    connector_config_version_id: UUID
    reason: GovernanceReason


class SourceTrialQualitySummary(ContractModel):
    raw_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    parse_failed_count: int = Field(ge=0)
    security_failed_count: int = Field(ge=0)
    rejected_raw_attempt_count: int = Field(ge=0)
    ready_ratio_bps: int = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def validate_database_derived_ratio(self) -> "SourceTrialQualitySummary":
        if self.rejected_raw_attempt_count > self.security_failed_count:
            raise ValueError("rejected raw attempts must be a subset of security failures")
        document_security_failures = self.security_failed_count - self.rejected_raw_attempt_count
        classified_count = self.ready_count + self.parse_failed_count + document_security_failures
        if classified_count > self.raw_count:
            raise ValueError("document outcome counts cannot exceed raw_count")
        expected_ratio = 0
        if self.raw_count:
            expected_ratio = (self.ready_count * 10000 + self.raw_count // 2) // self.raw_count
        if self.ready_ratio_bps != expected_ratio:
            raise ValueError(
                "READY ratio must be the nearest basis-point ratio of READY "
                "document raw objects to document-level raw objects"
            )
        return self


class SourceTrialRunView(ContractModel):
    id: UUID
    source_id: UUID
    kind: SourceTrialKind
    status: SourceTrialRunStatus
    policy_version_id: UUID
    connector_config_version_id: UUID
    requested_by: UUID
    started_at: datetime | None = None
    completed_at: datetime | None = None
    quality_summary: SourceTrialQualitySummary | None = None
    created_at: datetime


class SourceProductionApprovalRequest(ContractModel):
    policy_version_id: UUID
    connector_config_version_id: UUID
    trial_run_id: UUID
    reason: GovernanceReason


class SourceLifecycleActionRequest(ContractModel):
    reason: GovernanceReason


class SourceLifecycleEventView(ContractModel):
    id: UUID
    source_id: UUID
    from_state: SourceLifecycleState | None
    to_state: SourceLifecycleState
    action: SourceLifecycleAction | None
    reason_code: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    actor_id: UUID | None
    policy_version_id: UUID | None = None
    governance_decision_id: UUID | None = None
    migration_rule_version: str | None = None
    created_at: datetime


class SourceAuthorityAssessment(ContractModel):
    level: AuthorityLevel
    rule_version: str = Field(min_length=1, max_length=50)
    reason_codes: list[AssessmentReasonCode] = Field(min_length=1, max_length=20)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=50)
    assessed_at: AssessmentTimestamp


class SourceIndependenceAssessment(ContractModel):
    level: SourceIndependenceLevel
    rule_version: str = Field(min_length=1, max_length=50)
    reason_codes: list[AssessmentReasonCode] = Field(min_length=1, max_length=20)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=50)
    assessed_at: AssessmentTimestamp


class SourceGovernanceMetadataUpdate(ContractModel):
    """Governance-owned coverage metadata; lifecycle authority is intentionally absent."""

    governance_owner_id: UUID
    country_codes: list[CountryCode] = Field(min_length=1, max_length=20)
    region_codes: list[RegionCode] = Field(min_length=1, max_length=50)
    language_tags: list[LanguageTag] = Field(min_length=1, max_length=20)
    industries: list[SourceIndustry] = Field(min_length=1, max_length=20)
    content_domains: list[SourceContentDomain] = Field(min_length=1, max_length=30)
    declared_roles: list[SourceDeclaredRole] = Field(min_length=1, max_length=20)
    reason: GovernanceReason

    @model_validator(mode="after")
    def require_unique_values(self) -> "SourceGovernanceMetadataUpdate":
        fields = (
            self.country_codes,
            self.region_codes,
            self.language_tags,
            self.industries,
            self.content_domains,
            self.declared_roles,
        )
        if any(len(values) != len(set(values)) for values in fields):
            raise ValueError("governance metadata values must be unique")
        return self


class SourceAssessmentSubmission(ContractModel):
    """Append-only explainable authority and independence assessments."""

    authority: SourceAuthorityAssessment
    independence: SourceIndependenceAssessment
    reason: GovernanceReason


class ConnectorDefinitionView(ContractModel):
    id: UUID
    connector_type: ConnectorType
    definition_version: str
    schema_version: str
    schema_document: dict[str, object]
    schema_sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    executor_key: str
    capabilities: list[str]


class ConnectorConfigPreviewRequest(ContractModel):
    connector_type: ConnectorType
    definition_version: str = Field(min_length=1, max_length=30)
    config: dict[str, object]


class ConnectorConfigRequest(ConnectorConfigPreviewRequest):
    reason: GovernanceReason


class ConnectorConfigPreview(ContractModel):
    connector_type: ConnectorType
    definition_version: str
    schema_version: str
    schema_sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    config: dict[str, object]
    network_io_performed: Literal[False]


class ConnectorConfigVersionView(ContractModel):
    id: UUID
    source_id: UUID
    policy_version_id: UUID
    connector_type: ConnectorType
    definition_version: str
    version_number: int = Field(ge=1)
    config_sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    config: dict[str, object]
    allowed_hosts: list[str]
    credential_configured: bool
    validation_status: Literal["VALID", "INVALID"]
    created_by: UUID
    created_at: datetime


class SourceAuditEventView(ContractModel):
    id: UUID
    event_type: str
    actor_id: UUID
    reason: str
    request_id: str
    created_at: datetime


class SourceCoverageCell(ContractModel):
    industry: SourceIndustry
    content_domain: SourceContentDomain
    source_type: SourceType
    region: str
    language: str
    candidate_count: int = Field(ge=0)
    trial_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    gap: bool

    @model_validator(mode="after")
    def active_defines_gap(self) -> "SourceCoverageCell":
        if self.gap is not (self.active_count == 0):
            raise ValueError("coverage gaps are defined by the absence of ACTIVE sources")
        return self


class SourceCoverageMatrix(ContractModel):
    generated_at: datetime
    cells: list[SourceCoverageCell]
    gap_cell_count: int = Field(ge=0)


class SourceTransitionRequest(ContractModel):
    target_state: SourceState
    reason: GovernanceReason


class SourceActionRequest(ContractModel):
    reason: GovernanceReason


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
    lifecycle_state: SourceLifecycleState
    runtime_authorization: RuntimeAuthorization
    available_actions: list[SourceLifecycleAction] = Field(default_factory=list)
    governance_owner_id: UUID | None = None
    country_codes: list[str] = Field(default_factory=list)
    region_codes: list[str] = Field(default_factory=list)
    language_tags: list[str] = Field(default_factory=list)
    industries: list[SourceIndustry] = Field(default_factory=list)
    content_domains: list[SourceContentDomain] = Field(default_factory=list)
    declared_roles: list[SourceDeclaredRole] = Field(default_factory=list)


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
    source_authority: SourceAuthorityAssessment | None = None
    source_independence: SourceIndependenceAssessment | None = None
    current_policy_version_id: UUID | None = None
    current_connector_config_version_id: UUID | None = None
    current_trial_run_id: UUID | None = None


class RawObjectSummary(ContractModel):
    id: UUID
    sha256: Sha256String = Field(pattern=r"^[a-f0-9]{64}$")
    detected_mime: Literal[
        "text/html",
        "application/pdf",
        "application/xml",
        "application/json",
    ]
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


class PublishedEvidenceReferenceV1(ContractModel):
    evidence_id: UUID
    locator: str = Field(min_length=1, max_length=1000)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublishedClaimV1(ContractModel):
    claim_id: UUID
    field_name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)


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
    original_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
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
    original_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
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
    match_kind: Literal[
        "EXACT_IDENTIFIER",
        "TITLE_ENTITY_TAG",
        "BODY",
        "SEMANTIC",
    ]
    matched_fields: list[str] = Field(default_factory=list, max_length=10)
    matched_identifiers: list[str] = Field(default_factory=list, max_length=10)
    semantic_status: Literal["DISABLED", "ENABLED", "DEGRADED"]


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
    search_context: SearchContext | None = None


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
    publication_revision_id: UUID
    position: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=1000)
    current_state: Literal["PUBLISHED", "WITHDRAWN", "SOURCE_UNAVAILABLE"]
    original_url: HttpUrlString = Field(pattern=r"^https?://[^\s]+$", max_length=2048)


class DailyReportSection(ContractModel):
    kind: Literal[
        "TODAY_HIGHLIGHTS",
        "DIGITAL_SELECTED",
        "SAFETY_HIGHLIGHTS",
        "WATCHLIST",
        "SOURCE_ANOMALIES",
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


class DailyDraftRequest(ContractModel):
    report_date: date


class FingerprintResponse(ContractModel):
    generated_at: datetime
    feed_generation: int = Field(ge=0)
    search_generation: int = Field(ge=0)
    hot_topics_generation: int = Field(ge=0)
    latest_daily_report_id: UUID | None = None
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


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
    task_type: Literal[
        "CONTENT_REVIEW",
        "SECURITY_REVIEW",
        "CORRECTION_REVIEW",
        "WITHDRAWAL_REVIEW",
        "CLAIM_REVIEW",
    ] = "CONTENT_REVIEW"


class AiReviewTrace(ContractModel):
    model_profile: str
    prompt_version: str
    schema_version: str
    pricing_version: str | None = None
    provider_request_id: str | None = None
    rejection_reason: str | None = None


class ReviewTaskDetail(ContractModel):
    task: ReviewTaskSummary
    item: ItemSummary
    claims: list[ClaimView]
    evidence: list[EvidenceView]
    digital_case: DigitalCaseDetail | None = None
    paper: PaperDetail | None = None
    ai_trace: AiReviewTrace | None = None


class MeResponse(ContractModel):
    user_id: UUID
    display_name: str
    roles: list[UserRole]
    local_identity: bool
