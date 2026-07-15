"""Deterministic evidence rules for Round05 digital cases."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

RELEVANCE_RULE_VERSION = "relevance-v1.0.0"

ENGINEERING_WEIGHTS: dict[str, Decimal] = {
    "HIGHWAY": Decimal("1.00"),
    "BRIDGE": Decimal("1.00"),
    "TUNNEL": Decimal("1.00"),
    "ROAD": Decimal("0.95"),
    "GENERAL_CONSTRUCTION": Decimal("0.90"),
    "MUNICIPAL": Decimal("0.75"),
    "BUILDING": Decimal("0.65"),
    "RAILWAY": Decimal("0.65"),
    "WATER_CONSERVANCY": Decimal("0.55"),
    "PORT_WATERWAY": Decimal("0.55"),
    "GEOLOGICAL_ENGINEERING": Decimal("0.75"),
}

LIFECYCLE_STAGES = frozenset(
    {
        "PLANNING",
        "SURVEY",
        "DESIGN",
        "PROCUREMENT",
        "CONSTRUCTION_PREPARATION",
        "CONSTRUCTION",
        "QUALITY_INSPECTION",
        "SAFETY_MANAGEMENT",
        "COMPLETION_ACCEPTANCE",
        "OPERATION",
        "MAINTENANCE",
        "EMERGENCY_RESPONSE",
    }
)
TECHNOLOGY_TAGS = frozenset(
    {
        "BIM",
        "CIM",
        "GIS",
        "DIGITAL_TWIN",
        "INTERNET_OF_THINGS",
        "SENSOR_NETWORK",
        "FIVE_G",
        "BEIDOU_GNSS",
        "RTK",
        "UAV",
        "LOW_ALTITUDE_PLATFORM",
        "CONSTRUCTION_ROBOT",
        "UNMANNED_EQUIPMENT",
        "COMPUTER_VISION",
        "MACHINE_LEARNING",
        "GENERATIVE_AI",
        "INDUSTRY_LARGE_MODEL",
        "KNOWLEDGE_GRAPH",
        "CLOUD_COMPUTING",
        "EDGE_COMPUTING",
        "DATA_LAKE",
        "DIGITAL_PROJECT_MANAGEMENT",
        "SMART_SITE",
        "PREDICTIVE_MAINTENANCE",
        "THREE_D_SCANNING",
        "PHOTOGRAMMETRY",
        "AR_VR",
        "CYBERSECURITY",
    }
)
APPLICATION_SCENARIOS = frozenset(
    {
        "PROGRESS_CONTROL",
        "COST_CONTROL",
        "QUALITY_CONTROL",
        "SAFETY_MONITORING",
        "PERSONNEL_MANAGEMENT",
        "EQUIPMENT_MANAGEMENT",
        "MATERIAL_MANAGEMENT",
        "SUPPLY_CHAIN",
        "DESIGN_COLLABORATION",
        "CONSTRUCTION_SIMULATION",
        "INSPECTION",
        "STRUCTURAL_HEALTH_MONITORING",
        "GEOLOGICAL_FORECAST",
        "ENVIRONMENTAL_MONITORING",
        "TRAFFIC_ORGANIZATION",
        "EMERGENCY_COMMAND",
        "KNOWLEDGE_MANAGEMENT",
        "DOCUMENT_INTELLIGENCE",
        "DECISION_SUPPORT",
    }
)


@dataclass(frozen=True, slots=True)
class RelevanceFactorResult:
    code: Literal["ENGINEERING_DOMAIN", "SICHUAN", "SRBG_DIRECT"]
    label: str
    points: int


@dataclass(frozen=True, slots=True)
class RelevanceResult:
    score: int
    rule_version: str
    factors: tuple[RelevanceFactorResult, ...]


@dataclass(frozen=True, slots=True)
class MaturityEvidence:
    named_project_count: int
    deployment_count: int | None
    operating_months: int | None
    acceptance_evidence_count: int = 0
    enterprise_scope_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class OutcomeEvidence:
    attributed_entity_id: UUID
    evidence_source_entity_ids: tuple[UUID, ...]
    evidence_roles: tuple[str, ...]


def calculate_relevance(
    engineering_domains: list[str],
    *,
    is_sichuan: bool,
    has_direct_srbg_relation: bool,
) -> RelevanceResult:
    unknown = sorted(set(engineering_domains).difference(ENGINEERING_WEIGHTS))
    if unknown:
        raise ValueError(f"unsupported engineering domains: {', '.join(unknown)}")
    highest = max((ENGINEERING_WEIGHTS[code] for code in engineering_domains), default=Decimal(0))
    engineering_points = int((Decimal(70) * highest).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    factors = (
        RelevanceFactorResult("ENGINEERING_DOMAIN", "工程专业匹配", engineering_points),
        RelevanceFactorResult("SICHUAN", "四川实施", 20 if is_sichuan else 0),
        RelevanceFactorResult(
            "SRBG_DIRECT", "四川路桥直接关系", 10 if has_direct_srbg_relation else 0
        ),
    )
    return RelevanceResult(
        score=min(100, sum(factor.points for factor in factors)),
        rule_version=RELEVANCE_RULE_VERSION,
        factors=factors,
    )


def validate_taxonomy(
    *,
    engineering_domains: list[str],
    lifecycle_stages: list[str],
    technology_tags: list[str],
    application_scenarios: list[str],
) -> tuple[str, ...]:
    valid = (
        set(engineering_domains) <= set(ENGINEERING_WEIGHTS)
        and set(lifecycle_stages) <= LIFECYCLE_STAGES
        and set(technology_tags) <= TECHNOLOGY_TAGS
        and set(application_scenarios) <= APPLICATION_SCENARIOS
    )
    return () if valid else ("DIGITAL_TAXONOMY_CODE_INVALID",)


def validate_maturity(level: str, evidence: MaturityEvidence) -> tuple[str, ...]:
    production_levels = {
        "SINGLE_PROJECT_PRODUCTION",
        "MULTI_PROJECT_REPLICATION",
        "ENTERPRISE_SCALE",
    }
    if level not in production_levels:
        return ()
    has_operational_evidence = (
        any(
            value is not None and value > 0
            for value in (evidence.deployment_count, evidence.operating_months)
        )
        or evidence.acceptance_evidence_count > 0
    )
    reasons: list[str] = []
    if evidence.named_project_count < 1 or not has_operational_evidence:
        reasons.append("MATURITY_PRODUCTION_EVIDENCE_REQUIRED")
    if level == "MULTI_PROJECT_REPLICATION" and evidence.named_project_count < 2:
        reasons.append("MATURITY_MULTI_PROJECT_EVIDENCE_REQUIRED")
    if level == "ENTERPRISE_SCALE" and not evidence.enterprise_scope_confirmed:
        reasons.append("MATURITY_ENTERPRISE_SCOPE_EVIDENCE_REQUIRED")
    return tuple(reasons)


def validate_outcome_verification(verification: str, evidence: OutcomeEvidence) -> tuple[str, ...]:
    if verification == "CLAIMED":
        return ()
    if verification != "VERIFIED":
        raise ValueError(f"unsupported outcome verification: {verification}")
    has_independent_role = "INDEPENDENT_CONFIRMATION" in evidence.evidence_roles
    has_independent_source = any(
        source_id != evidence.attributed_entity_id
        for source_id in evidence.evidence_source_entity_ids
    )
    if not has_independent_role or not has_independent_source:
        return ("INDEPENDENT_EVIDENCE_REQUIRED",)
    return ()
