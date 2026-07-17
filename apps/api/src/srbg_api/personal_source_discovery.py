"""Personal source discovery scoring and server-authoritative enablement rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import floor

AUTO_SCORE_RULE_VERSION = "personal-source-auto-score-v1"
AUTO_ENABLE_THRESHOLD = 70


def _bounded(value: int, maximum: int, *, field: str) -> int:
    if not 0 <= value <= maximum:
        raise ValueError(f"{field} must be between 0 and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class AutoScoreComponents:
    topic_relevance: int
    connector_stability: int
    sample_completeness: int
    profile_evidence: int
    content_validity: int

    def __post_init__(self) -> None:
        _bounded(self.topic_relevance, 35, field="topic_relevance")
        _bounded(self.connector_stability, 25, field="connector_stability")
        _bounded(self.sample_completeness, 20, field="sample_completeness")
        _bounded(self.profile_evidence, 10, field="profile_evidence")
        _bounded(self.content_validity, 10, field="content_validity")

    @property
    def total(self) -> int:
        return (
            self.topic_relevance
            + self.connector_stability
            + self.sample_completeness
            + self.profile_evidence
            + self.content_validity
        )


@dataclass(frozen=True, slots=True)
class ScoringInput:
    successful_sample_count: int
    relevant_sample_count: int
    stability_checks_passed: int
    complete_field_count: int
    possible_field_count: int
    profile_confidences: tuple[int, int, int, int]
    valid_sample_count: int
    latest_published_at: datetime | None

    def __post_init__(self) -> None:
        if self.successful_sample_count < 1:
            raise ValueError("successful_sample_count must be positive")
        if not 0 <= self.relevant_sample_count <= self.successful_sample_count:
            raise ValueError("relevant_sample_count is invalid")
        if not 0 <= self.valid_sample_count <= self.successful_sample_count:
            raise ValueError("valid_sample_count is invalid")
        _bounded(self.stability_checks_passed, 5, field="stability_checks_passed")
        if self.possible_field_count < 1:
            raise ValueError("possible_field_count must be positive")
        if not 0 <= self.complete_field_count <= self.possible_field_count:
            raise ValueError("complete_field_count is invalid")
        if any(not 0 <= value <= 100 for value in self.profile_confidences):
            raise ValueError("profile confidence must be between 0 and 100")
        if self.latest_published_at is not None and self.latest_published_at.tzinfo is None:
            raise ValueError("latest_published_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class AutoEnableGate:
    public_network: bool
    ssrf_safe: bool
    robots_permitted: bool
    access_open: bool
    terms_permitted: bool
    copyright_permitted: bool
    connector_executable: bool
    sample_parsed: bool
    evidence_current: bool
    sticky_disabled: bool


@dataclass(frozen=True, slots=True)
class AutoEnableDecision:
    total: int
    eligible: bool
    reason_codes: tuple[str, ...]


def calculate_auto_score(value: ScoringInput, *, now: datetime) -> AutoScoreComponents:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    observed_at = now.astimezone(UTC)
    relevance = floor(35 * value.relevant_sample_count / value.successful_sample_count)
    stability = floor(25 * value.stability_checks_passed / 5)
    completeness = floor(20 * value.complete_field_count / value.possible_field_count)
    profile = floor(10 * (sum(value.profile_confidences) / 4) / 100)
    validity = floor(5 * value.valid_sample_count / value.successful_sample_count)
    if value.latest_published_at is not None:
        age_days = max(
            0,
            (observed_at - value.latest_published_at.astimezone(UTC)).days,
        )
        validity += 5 if age_days <= 30 else 3 if age_days <= 90 else 1 if age_days <= 365 else 0
    return AutoScoreComponents(relevance, stability, completeness, profile, validity)


def evaluate_auto_enable(
    score: AutoScoreComponents,
    gate: AutoEnableGate,
) -> AutoEnableDecision:
    reasons: list[str] = []
    checks = (
        (score.total < AUTO_ENABLE_THRESHOLD, "SCORE_BELOW_70"),
        (not gate.public_network, "PUBLIC_NETWORK_GATE_FAILED"),
        (not gate.ssrf_safe, "SSRF_GATE_FAILED"),
        (not gate.robots_permitted, "ROBOTS_NOT_PERMITTED"),
        (not gate.access_open, "ACCESS_BARRIER_DETECTED"),
        (not gate.terms_permitted, "TERMS_NOT_PERMITTED"),
        (not gate.copyright_permitted, "COPYRIGHT_NOT_PERMITTED"),
        (not gate.connector_executable, "CONNECTOR_NOT_EXECUTABLE"),
        (not gate.sample_parsed, "NO_PARSED_SAMPLE"),
        (not gate.evidence_current, "SCORING_EVIDENCE_STALE"),
        (gate.sticky_disabled, "OWNER_STICKY_DISABLED"),
    )
    reasons.extend(code for failed, code in checks if failed)
    return AutoEnableDecision(score.total, not reasons, tuple(reasons))


def validate_discovery_depth(depth: int) -> int:
    if depth not in {0, 1}:
        raise ValueError("discovery depth must be zero or one")
    return depth
