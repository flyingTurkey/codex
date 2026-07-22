"""Fail-closed admission rules for the staged civil-engineering source portfolio."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SourceAdmissionMetrics:
    sample_size: int
    robots_allowed: bool | None
    terms_allowed: bool | None
    copyright_reviewed: bool | None
    public_network_safe: bool
    fetch_success_bps: int
    parse_evidence_success_bps: int
    metadata_success_bps: int
    useful_yield_bps: int
    duplicate_bps: int
    hard_negative_leaks: int
    hard_negative_evaluated: bool = True

    def __post_init__(self) -> None:
        if self.sample_size < 0 or self.sample_size > 30:
            raise ValueError("source admission sample_size must be between 0 and 30")
        for field in (
            "fetch_success_bps",
            "parse_evidence_success_bps",
            "metadata_success_bps",
            "useful_yield_bps",
            "duplicate_bps",
        ):
            value = getattr(self, field)
            if value < 0 or value > 10_000:
                raise ValueError(f"{field} must be between 0 and 10000")
        if self.hard_negative_leaks < 0:
            raise ValueError("hard_negative_leaks cannot be negative")


@dataclass(frozen=True)
class SourceSampleCandidate:
    document_version_id: str
    canonical_key: str
    source_published_at: datetime


def select_admission_sample(
    values: list[SourceSampleCandidate],
    *,
    cutoff: datetime,
) -> tuple[SourceSampleCandidate, ...]:
    """Select the newest 30 unique public documents in the fixed 90-day window."""

    if cutoff.tzinfo is None:
        raise ValueError("source admission cutoff must include timezone")
    lower_bound = cutoff - timedelta(days=90)
    eligible = sorted(
        (
            value
            for value in values
            if value.source_published_at.tzinfo is not None
            and lower_bound <= value.source_published_at <= cutoff
            and value.canonical_key
        ),
        key=lambda value: (value.source_published_at, value.document_version_id),
        reverse=True,
    )
    selected: list[SourceSampleCandidate] = []
    seen: set[str] = set()
    for value in eligible:
        if value.canonical_key in seen:
            continue
        seen.add(value.canonical_key)
        selected.append(value)
        if len(selected) == 30:
            break
    return tuple(selected)


def admission_verdict(value: SourceAdmissionMetrics) -> str:
    if not all(
        (
            value.robots_allowed,
            value.terms_allowed,
            value.copyright_reviewed,
            value.public_network_safe,
            value.hard_negative_evaluated,
        )
    ):
        return "PAUSE"
    if value.hard_negative_leaks:
        return "PAUSE"
    if value.sample_size < 30:
        return "OBSERVE"
    soft_pass = (
        value.fetch_success_bps >= 9800
        and value.parse_evidence_success_bps >= 9500
        and value.metadata_success_bps >= 9800
        and value.useful_yield_bps >= 5000
        and value.duplicate_bps <= 3000
    )
    return "ADMIT" if soft_pass else "OBSERVE"


def production_admission_verdict(
    value: SourceAdmissionMetrics,
    *,
    calibration: object | None,
) -> str:
    """Authorize bounded collection unless an explicit hard server gate denies it.

    ``calibration`` remains as a source-compatible argument for callers deployed with
    the former Owner-Gold path. It is deliberately ignored and grants no authority.
    """

    del calibration
    explicitly_forbidden = any(
        gate is False
        for gate in (value.robots_allowed, value.terms_allowed, value.copyright_reviewed)
    )
    if not value.public_network_safe or explicitly_forbidden:
        return "PAUSE"
    return "ADMIT"
