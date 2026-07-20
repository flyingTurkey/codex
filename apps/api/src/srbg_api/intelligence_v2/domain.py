"""Pure v2 qualification and hotspot rules shared by publication paths."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from srbg_contracts import PrimaryIntelligenceType


class RelevanceDecision(StrEnum):
    RELEVANT = "RELEVANT"
    IRRELEVANT = "IRRELEVANT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    PRIMARY_TYPE_TIE = "PRIMARY_TYPE_TIE"
    CLASSIFICATION_FAILED = "CLASSIFICATION_FAILED"


def decide_projection(decision: RelevanceDecision, risk_tier: str) -> str:
    """Return the maximum projection; publication remains a service decision."""

    if risk_tier == "R4":
        return "QUARANTINE_ONLY"
    if decision is not RelevanceDecision.RELEVANT:
        return "REVIEW_ONLY"
    if risk_tier == "R3":
        return "R3_METADATA"
    return "FULL"


@dataclass(frozen=True)
class HotspotComponents:
    impact_scope: int
    engineering_materiality: int
    novelty: int
    urgency: int
    evidence_authority: int

    def __post_init__(self) -> None:
        caps = {
            "impact_scope": 25,
            "engineering_materiality": 25,
            "novelty": 20,
            "urgency": 15,
            "evidence_authority": 15,
        }
        for field, cap in caps.items():
            value = getattr(self, field)
            if value < 0 or value > cap:
                raise ValueError(f"{field} must be between 0 and {cap}")

    @property
    def total(self) -> int:
        return sum(
            (
                self.impact_scope,
                self.engineering_materiality,
                self.novelty,
                self.urgency,
                self.evidence_authority,
            )
        )


@dataclass(frozen=True)
class HotspotAwardDecision:
    awarded: bool
    score: int
    trigger: str | None
    rule_version: str = "hotspot-v2.0.0"


HotspotComponentName = Literal[
    "impact_scope",
    "engineering_materiality",
    "novelty",
    "urgency",
    "evidence_authority",
]

_HOTSPOT_COMPONENT_CAPS: dict[HotspotComponentName, int] = {
    "impact_scope": 25,
    "engineering_materiality": 25,
    "novelty": 20,
    "urgency": 15,
    "evidence_authority": 15,
}


@dataclass(frozen=True)
class HotspotCandidateReason:
    text: str
    claim_ids: frozenset[UUID]

    def __post_init__(self) -> None:
        if not self.text.strip() or not self.claim_ids:
            raise ValueError("a hotspot reason requires text and claim references")


@dataclass(frozen=True)
class HotspotCandidate:
    claim_ids: frozenset[UUID]
    reasons: tuple[HotspotCandidateReason, ...]

    def __post_init__(self) -> None:
        if not self.claim_ids or not self.reasons:
            raise ValueError("a hotspot candidate requires claims and reasons")
        if any(not reason.claim_ids.issubset(self.claim_ids) for reason in self.reasons):
            raise ValueError("hotspot reasons may reference only candidate claims")


@dataclass(frozen=True)
class HotspotComponentEvidence:
    component: HotspotComponentName
    points: int
    claim_ids: frozenset[UUID]

    def __post_init__(self) -> None:
        cap = _HOTSPOT_COMPONENT_CAPS[self.component]
        if not 0 <= self.points <= cap:
            raise ValueError(f"{self.component} must be between 0 and {cap}")
        if not self.claim_ids:
            raise ValueError("hotspot component facts require accepted claim references")


@dataclass(frozen=True)
class HotspotSourceEvidence:
    source_id: UUID
    organization_key: str
    lineage_root: str
    role: Literal["ORIGINAL", "REPRINT", "MIRROR", "INDEPENDENT_REPORT"]
    published_at: datetime
    accepted_claim_ids: frozenset[UUID]
    qualified: bool
    authoritative_first_party: bool


@dataclass(frozen=True)
class EvaluatedHotspotAward:
    awarded: bool
    score: int
    trigger: Literal["MULTI_SOURCE_7D", "AUTHORITY_SCORE"] | None
    independent_source_count: int
    reasons: tuple[str, ...]
    reason_codes: tuple[str, ...]
    primary_type: PrimaryIntelligenceType
    components: HotspotComponents
    rule_version: str = "hotspot-v2.0.0"


def calculate_hotspot_award(
    *,
    components: HotspotComponents,
    independent_source_count: int,
    authoritative_first_party: bool,
) -> HotspotAwardDecision:
    score = components.total
    if independent_source_count >= 2:
        return HotspotAwardDecision(True, score, "MULTI_SOURCE_7D")
    if authoritative_first_party and score >= 70:
        return HotspotAwardDecision(True, score, "AUTHORITY_SCORE")
    return HotspotAwardDecision(False, score, None)


def evaluate_hotspot_candidate(
    *,
    candidate: HotspotCandidate,
    component_evidence: tuple[HotspotComponentEvidence, ...],
    sources: tuple[HotspotSourceEvidence, ...],
    primary_type: PrimaryIntelligenceType,
    evaluated_at: datetime,
) -> EvaluatedHotspotAward:
    """Evaluate a model candidate only from current server-owned evidence facts."""

    by_component = {fact.component: fact for fact in component_evidence}
    if set(by_component) != set(_HOTSPOT_COMPONENT_CAPS) or len(by_component) != len(
        component_evidence
    ):
        components = HotspotComponents(0, 0, 0, 0, 0)
        return EvaluatedHotspotAward(
            False,
            0,
            None,
            0,
            (),
            ("HOTSPOT_COMPONENT_FACTS_INCOMPLETE",),
            primary_type,
            components,
        )

    components = HotspotComponents(
        impact_scope=by_component["impact_scope"].points,
        engineering_materiality=by_component["engineering_materiality"].points,
        novelty=by_component["novelty"].points,
        urgency=by_component["urgency"].points,
        evidence_authority=by_component["evidence_authority"].points,
    )
    window_start = evaluated_at - timedelta(days=7)
    eligible = tuple(
        source
        for source in sources
        if source.qualified
        and window_start <= source.published_at <= evaluated_at
        and source.role in {"ORIGINAL", "INDEPENDENT_REPORT"}
        and bool(source.accepted_claim_ids.intersection(candidate.claim_ids))
    )
    current_claim_ids = frozenset(
        claim_id for source in eligible for claim_id in source.accepted_claim_ids
    )
    component_claim_ids = frozenset(
        claim_id for fact in component_evidence for claim_id in fact.claim_ids
    )
    if not candidate.claim_ids.issubset(current_claim_ids) or not component_claim_ids.issubset(
        current_claim_ids
    ):
        return EvaluatedHotspotAward(
            False,
            components.total,
            None,
            0,
            (),
            ("CANDIDATE_CLAIMS_NOT_CURRENT_ACCEPTED",),
            primary_type,
            components,
        )

    organizations: set[str] = set()
    lineages: set[str] = set()
    independent_source_count = 0
    for source in sorted(eligible, key=lambda value: (value.published_at, str(value.source_id))):
        if source.organization_key in organizations or source.lineage_root in lineages:
            continue
        organizations.add(source.organization_key)
        lineages.add(source.lineage_root)
        independent_source_count += 1

    authoritative_first_party = any(source.authoritative_first_party for source in eligible)
    decision = calculate_hotspot_award(
        components=components,
        independent_source_count=independent_source_count,
        authoritative_first_party=authoritative_first_party,
    )
    return EvaluatedHotspotAward(
        awarded=decision.awarded,
        score=decision.score,
        trigger=decision.trigger,  # type: ignore[arg-type]
        independent_source_count=independent_source_count,
        reasons=tuple(reason.text for reason in candidate.reasons) if decision.awarded else (),
        reason_codes=() if decision.awarded else ("HOTSPOT_THRESHOLD_NOT_MET",),
        primary_type=primary_type,
        components=components,
        rule_version=decision.rule_version,
    )
