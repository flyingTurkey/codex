"""Pure projection policy with independent risk, severity, and visibility axes."""

from dataclasses import dataclass

from srbg_contracts import ContentSeverity, ProjectionLevel, PublicationRiskTier

_METADATA_SURFACES = frozenset({"FEED", "EVENT", "TITLE_SEARCH"})
_FULL_SURFACES = frozenset(
    {
        "FEED",
        "EVENT",
        "TITLE_SEARCH",
        "SELECTED",
        "DAILY",
        "RECOMMENDATION",
        "NOTIFICATION",
        "FULLTEXT_EXPORT",
    }
)


@dataclass(frozen=True, slots=True)
class ProjectionInput:
    publication_risk_tier: PublicationRiskTier
    review_status: str
    publication_status: str | None
    official_source: bool
    content_severity: ContentSeverity = ContentSeverity.UNASSESSED


@dataclass(frozen=True, slots=True)
class ProjectionDecision:
    level: ProjectionLevel
    allowed_surfaces: frozenset[str]
    reason: str


def decide_projection(value: ProjectionInput) -> ProjectionDecision:
    """Return the maximum safe server-side projection; severity never grants access."""

    risk = PublicationRiskTier(value.publication_risk_tier)
    if risk == PublicationRiskTier.R4:
        return ProjectionDecision(ProjectionLevel.NONE, frozenset(), "R4_ISOLATED")
    if (
        risk == PublicationRiskTier.R3
        and value.review_status == "PENDING"
        and value.official_source
    ):
        return ProjectionDecision(
            ProjectionLevel.METADATA_ONLY,
            _METADATA_SURFACES,
            "R3_PENDING_OFFICIAL_METADATA_ALLOWLIST",
        )
    if value.review_status == "APPROVED" and value.publication_status == "PUBLISHED":
        return ProjectionDecision(ProjectionLevel.FULL, _FULL_SURFACES, "PUBLISHED_REVIEWED")
    return ProjectionDecision(ProjectionLevel.NONE, frozenset(), "NOT_ELIGIBLE")
