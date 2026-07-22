"""Fail-closed admission rules for the staged civil-engineering source portfolio."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from srbg_api.identifiers import uuid7


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


def review_gate_result(
    value: object,
    *,
    allowed_results: set[str],
) -> bool | None:
    """Map policy evidence without turning missing knowledge into a prohibition."""

    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, str):
        return None
    normalized = result.strip().upper()
    if normalized in allowed_results:
        return True
    if normalized in {"BLOCKED", "DENIED", "DISALLOWED", "FORBIDDEN", "RESTRICTED"}:
        return False
    return None


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


async def append_production_admission_assessment(
    connection: AsyncConnection,
    *,
    source_id: UUID,
    metrics: SourceAdmissionMetrics,
    sample_cutoff: datetime,
    sample_manifest_sha256: str,
    evidence_refs: dict[str, Any],
    actor_id: UUID,
    assessed_at: datetime,
    rule_version: str = "civil-source-rollout-v2-engineering-1.0.0",
) -> str:
    """Append the authoritative source-admission fact used by live qualification."""

    if sample_cutoff.tzinfo is None or assessed_at.tzinfo is None:
        raise ValueError("source admission timestamps must include timezone")
    if re.fullmatch(r"[0-9a-f]{64}", sample_manifest_sha256) is None:
        raise ValueError("source admission manifest hash is invalid")
    if re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", rule_version) is None:
        raise ValueError("source admission rule version is invalid")
    verdict = production_admission_verdict(metrics, calibration=None)
    metrics_payload = {
        key: value for key, value in metrics.__dict__.items() if key != "sample_size"
    }
    await connection.execute(
        text(
            "INSERT INTO source_admission_assessment_v2("
            "id,source_id,rule_version,sample_cutoff,lookback_days,sample_size,"
            "sample_manifest_sha256,metrics,evidence_refs,verdict,assessed_by,assessed_at) "
            "VALUES(:id,:source,:rule,:cutoff,90,:size,:manifest,CAST(:metrics AS jsonb),"
            "CAST(:refs AS jsonb),:verdict,:actor,:now)"
        ),
        {
            "id": uuid7(),
            "source": source_id,
            "rule": rule_version,
            "cutoff": sample_cutoff,
            "size": metrics.sample_size,
            "manifest": sample_manifest_sha256,
            "metrics": json.dumps(metrics_payload, sort_keys=True, separators=(",", ":")),
            "refs": json.dumps(evidence_refs, sort_keys=True, separators=(",", ":")),
            "verdict": verdict,
            "actor": actor_id,
            "now": assessed_at,
        },
    )
    return verdict
