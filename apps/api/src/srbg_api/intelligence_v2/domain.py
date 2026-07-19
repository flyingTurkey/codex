"""Pure v2 qualification and hotspot rules shared by publication paths."""

from dataclasses import dataclass
from enum import StrEnum


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
