"""Pure policy rules for qualification and administrator source decisions."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final
from urllib.parse import urlsplit

from srbg_contracts import (
    EvidenceCapturePolicy,
    QualificationVerdict,
    ReviewEvidenceResult,
    SourceCandidateDecision,
    StoragePolicy,
)

QUALIFICATION_VALIDITY: Final = timedelta(days=7)
MAX_BATCH_ENABLE_SIZE: Final = 10
_SHA256_PATTERN: Final = re.compile(r"^[a-f0-9]{64}$")


class AutomationRuleViolation(ValueError):
    """Raised when a requested transition violates authoritative source rules."""


@dataclass(frozen=True, slots=True)
class QualificationFacts:
    """Server-observed facts used to produce an immutable qualification bundle."""

    canonical_url: str
    authorization_boundary: str
    robots: ReviewEvidenceResult
    terms: ReviewEvidenceResult
    copyright: ReviewEvidenceResult
    requires_login: bool
    captcha_detected: bool
    paywall_detected: bool
    redirect_boundary_valid: bool
    resolved_addresses_public: bool
    connector_valid: bool
    relevant_item_count: int
    sampled_item_count: int
    material_fingerprint: str
    raw_evidence_storage_prohibited: bool = False
    qualification_evidence_fingerprint: str | None = None

    def __post_init__(self) -> None:
        parsed = urlsplit(self.canonical_url)
        boundary = self.authorization_boundary.rstrip(".").lower()
        hostname = (parsed.hostname or "").rstrip(".").lower()
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("canonical_url must be a credential-free HTTPS URL")
        if (
            re.fullmatch(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
                boundary,
            )
            is None
        ):
            raise ValueError("authorization_boundary must be a fixed DNS host name")
        if hostname != boundary and not hostname.endswith(f".{boundary}"):
            raise ValueError("canonical_url must be inside the authorization boundary")
        if not _SHA256_PATTERN.fullmatch(self.material_fingerprint):
            raise ValueError("material_fingerprint must be a lowercase SHA-256")
        if (
            self.qualification_evidence_fingerprint is not None
            and not _SHA256_PATTERN.fullmatch(self.qualification_evidence_fingerprint)
        ):
            raise ValueError("qualification_evidence_fingerprint must be a lowercase SHA-256")
        if self.sampled_item_count < 0 or self.relevant_item_count < 0:
            raise ValueError("qualification sample counts cannot be negative")
        if self.relevant_item_count > self.sampled_item_count:
            raise ValueError("relevant item count cannot exceed sampled item count")


@dataclass(frozen=True, slots=True)
class QualificationAssessment:
    rule_version: str
    material_fingerprint: str
    verdict: QualificationVerdict
    storage_policy: StoragePolicy
    evidence_capture_policy: EvidenceCapturePolicy
    reason_codes: tuple[str, ...]
    sampled_item_count: int
    relevant_item_count: int
    bundle_sha256: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthorizedCandidateDecision:
    decision: SourceCandidateDecision
    waiver_applied: bool


def _review_reason_codes(
    label: str,
    result: ReviewEvidenceResult,
) -> tuple[list[str], list[str]]:
    if result is ReviewEvidenceResult.ALLOWED:
        return [], []
    reason_code = f"{label}_{result.value}"
    if result is ReviewEvidenceResult.BLOCKED:
        return [reason_code], []
    return [], [reason_code]


def _canonical_bundle_sha256(
    facts: QualificationFacts,
    *,
    rule_version: str,
    verdict: QualificationVerdict,
    storage_policy: StoragePolicy,
    evidence_capture_policy: EvidenceCapturePolicy,
    reason_codes: tuple[str, ...],
) -> str:
    document = {
        "authorization_boundary": facts.authorization_boundary.rstrip(".").lower(),
        "canonical_url": facts.canonical_url,
        "captcha_detected": facts.captcha_detected,
        "connector_valid": facts.connector_valid,
        "copyright": facts.copyright.value,
        "evidence_capture_policy": evidence_capture_policy.value,
        "material_fingerprint": facts.material_fingerprint,
        "qualification_evidence_fingerprint": (
            facts.qualification_evidence_fingerprint or facts.material_fingerprint
        ),
        "paywall_detected": facts.paywall_detected,
        "raw_evidence_storage_prohibited": facts.raw_evidence_storage_prohibited,
        "redirect_boundary_valid": facts.redirect_boundary_valid,
        "relevant_item_count": facts.relevant_item_count,
        "requires_login": facts.requires_login,
        "resolved_addresses_public": facts.resolved_addresses_public,
        "robots": facts.robots.value,
        "rule_version": rule_version,
        "sampled_item_count": facts.sampled_item_count,
        "storage_policy": storage_policy.value,
        "terms": facts.terms.value,
        "verdict": verdict.value,
        "reason_codes": reason_codes,
    }
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def evaluate_qualification(
    facts: QualificationFacts,
    *,
    rule_version: str,
    now: datetime | None = None,
) -> QualificationAssessment:
    """Derive a qualification verdict without granting source activation authority."""

    if not rule_version or len(rule_version) > 100:
        raise ValueError("rule_version must contain between 1 and 100 characters")
    observed_at = datetime.now(UTC) if now is None else _require_aware_utc(now, field="now")

    block_reasons: list[str] = []
    warning_reasons: list[str] = []
    for label, result in (
        ("ROBOTS", facts.robots),
        ("TERMS", facts.terms),
        ("COPYRIGHT", facts.copyright),
    ):
        blocks, warnings = _review_reason_codes(label, result)
        block_reasons.extend(blocks)
        warning_reasons.extend(warnings)
    if facts.raw_evidence_storage_prohibited:
        warning_reasons.append("RAW_EVIDENCE_STORAGE_PROHIBITED")

    non_negotiable_checks = (
        (facts.requires_login, "LOGIN_REQUIRED"),
        (facts.captcha_detected, "CAPTCHA_DETECTED"),
        (facts.paywall_detected, "PAYWALL_DETECTED"),
        (not facts.resolved_addresses_public, "SSRF_UNSAFE_ADDRESS"),
        (not facts.redirect_boundary_valid, "REDIRECT_OUTSIDE_BOUNDARY"),
        (not facts.connector_valid, "CONNECTOR_INVALID"),
        (facts.sampled_item_count == 0, "NO_SAMPLE_ITEMS"),
        (facts.relevant_item_count == 0, "NO_RELEVANT_ITEMS"),
    )
    block_reasons.extend(code for failed, code in non_negotiable_checks if failed)

    if block_reasons:
        verdict = QualificationVerdict.BLOCKED
        storage_policy = StoragePolicy.LINK_ONLY
        evidence_capture_policy = EvidenceCapturePolicy.TRANSIENT_METADATA_ONLY
        reason_codes = tuple(block_reasons + warning_reasons)
    elif warning_reasons:
        verdict = QualificationVerdict.WARN_WAIVABLE
        storage_policy = StoragePolicy.METADATA_ONLY
        evidence_capture_policy = (
            EvidenceCapturePolicy.TRANSIENT_METADATA_ONLY
            if facts.raw_evidence_storage_prohibited
            else EvidenceCapturePolicy.PRIVATE_RAW_ALLOWED
        )
        reason_codes = tuple(warning_reasons)
    else:
        verdict = QualificationVerdict.QUALIFIED
        storage_policy = StoragePolicy.RAW_EVIDENCE_ALLOWED
        evidence_capture_policy = (
            EvidenceCapturePolicy.TRANSIENT_METADATA_ONLY
            if facts.raw_evidence_storage_prohibited
            else EvidenceCapturePolicy.PRIVATE_RAW_ALLOWED
        )
        reason_codes = ()

    bundle_sha256 = _canonical_bundle_sha256(
        facts,
        rule_version=rule_version,
        verdict=verdict,
        storage_policy=storage_policy,
        evidence_capture_policy=evidence_capture_policy,
        reason_codes=reason_codes,
    )
    return QualificationAssessment(
        rule_version=rule_version,
        material_fingerprint=facts.material_fingerprint,
        verdict=verdict,
        storage_policy=storage_policy,
        evidence_capture_policy=evidence_capture_policy,
        reason_codes=reason_codes,
        sampled_item_count=facts.sampled_item_count,
        relevant_item_count=facts.relevant_item_count,
        bundle_sha256=bundle_sha256,
        created_at=observed_at,
        expires_at=observed_at + QUALIFICATION_VALIDITY,
    )


def authorize_candidate_decision(
    assessment: QualificationAssessment,
    *,
    decision: SourceCandidateDecision,
    expected_bundle_sha256: str,
    current_material_fingerprint: str,
    waiver_reason: str | None,
    now: datetime | None = None,
) -> AuthorizedCandidateDecision:
    """Authorize an individual decision against current server-owned evidence."""

    if decision is SourceCandidateDecision.DISMISS:
        return AuthorizedCandidateDecision(decision=decision, waiver_applied=False)

    checked_at = datetime.now(UTC) if now is None else _require_aware_utc(now, field="now")
    if not secrets.compare_digest(expected_bundle_sha256, assessment.bundle_sha256):
        raise AutomationRuleViolation("qualification bundle hash is no longer current")
    if not secrets.compare_digest(current_material_fingerprint, assessment.material_fingerprint):
        raise AutomationRuleViolation("material evidence changed after qualification")
    if assessment.expires_at <= checked_at:
        raise AutomationRuleViolation("qualification bundle has expired")
    if assessment.verdict is QualificationVerdict.BLOCKED:
        raise AutomationRuleViolation("a blocked candidate cannot be enabled")
    if assessment.verdict is QualificationVerdict.WARN_WAIVABLE:
        if waiver_reason is None or not waiver_reason.strip():
            raise AutomationRuleViolation("warning qualification requires an individual waiver")
        return AuthorizedCandidateDecision(decision=decision, waiver_applied=True)
    return AuthorizedCandidateDecision(decision=decision, waiver_applied=False)


def validate_batch_enable(
    assessments: list[QualificationAssessment],
    *,
    expected_rule_version: str,
    now: datetime | None = None,
) -> None:
    """Require an all-green, current and same-rule cohort before batch enable."""

    if not assessments or len(assessments) > MAX_BATCH_ENABLE_SIZE:
        raise AutomationRuleViolation("batch enable requires between 1 and 10 candidates")
    checked_at = datetime.now(UTC) if now is None else _require_aware_utc(now, field="now")
    if any(assessment.rule_version != expected_rule_version for assessment in assessments):
        raise AutomationRuleViolation("batch enable requires one current rule version")
    if any(assessment.verdict is not QualificationVerdict.QUALIFIED for assessment in assessments):
        raise AutomationRuleViolation("batch enable is restricted to an all-green cohort")
    if any(assessment.expires_at <= checked_at for assessment in assessments):
        raise AutomationRuleViolation("batch enable qualification bundle has expired")


def _require_aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return value.astimezone(UTC)
