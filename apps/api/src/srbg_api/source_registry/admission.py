"""Authoritative construction of source policy and onboarding evidence records."""

from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from srbg_contracts import (
    ReviewEvidenceResult,
    SourceOnboardingSubmission,
    SourcePolicyStatus,
    SourcePolicySubmission,
)

REQUIRED_ONBOARDING_CHECKS = frozenset(
    {
        "OWNER_VERIFIED",
        "ROBOTS_REVIEWED",
        "TERMS_REVIEWED",
        "COPYRIGHT_POLICY_SET",
        "RATE_LIMIT_SET",
        "DOMAIN_ALLOWLIST_SET",
        "THIRTY_FIXTURES_VALIDATED",
        "CONTRACT_TEST_PASS",
        "STRUCTURE_BASELINE_SET",
        "SECURITY_TEST_PASS",
        "OWNER_ASSIGNED",
    }
)


class AdmissionRejected(ValueError):
    """Raised when server-authoritative admission evidence is incomplete."""


def build_policy_record(
    source_id: UUID,
    submission: SourcePolicySubmission,
    actor_id: UUID,
    now: datetime,
) -> dict[str, Any]:
    """Build the exact persisted shape of source-policy.schema.json."""

    if submission.status is SourcePolicyStatus.VALID:
        if submission.review.valid_until <= now:
            raise AdmissionRejected("valid source policy must not be expired")
        reviews = (submission.robots_review, submission.terms_review)
        if any(review.result is ReviewEvidenceResult.BLOCKED for review in reviews):
            raise AdmissionRejected("blocked review evidence cannot form a valid policy")
    if len(set(submission.access.allowed_domains)) != len(submission.access.allowed_domains):
        raise AdmissionRejected("allowed domains must be unique")

    document = submission.model_dump(mode="json")
    for review_name in ("robots_review", "terms_review"):
        review = document[review_name]
        review["evidence_sha256"] = sha256(str(review["evidence_url"]).encode()).hexdigest()
    document["source_id"] = str(source_id)
    document["review"] = {
        "reviewed_by": str(actor_id),
        "reviewed_at": now.isoformat(),
        "valid_until": submission.review.valid_until.isoformat(),
        "approval_id": submission.review.approval_id,
    }
    return {
        key: document[key]
        for key in (
            "source_id",
            "policy_version",
            "status",
            "robots_review",
            "terms_review",
            "copyright",
            "access",
            "review",
        )
    }


def build_onboarding_record(
    source_id: UUID,
    source_policy_version: str,
    submission: SourceOnboardingSubmission,
    actor_id: UUID,
    now: datetime,
    *,
    fixture_hashes: list[str],
) -> dict[str, Any]:
    """Build the exact persisted shape of source-onboarding-record.schema.json."""

    checks = submission.model_dump(mode="json")["checks"]
    for check in checks:
        check["evidence_sha256"] = sha256(str(check["evidence_ref"]).encode()).hexdigest()
    codes = [str(check["code"]) for check in checks]
    if len(codes) != len(set(codes)) or set(codes) != REQUIRED_ONBOARDING_CHECKS:
        raise AdmissionRejected("all required onboarding checks must appear exactly once")

    distinct_hashes = sorted(set(fixture_hashes))
    if len(distinct_hashes) < 30:
        raise AdmissionRejected("at least 30 distinct fixture content hashes are required")
    if submission.valid_until <= now:
        raise AdmissionRejected("onboarding evidence must not be expired")
    fixture_set_sha256 = sha256("\n".join(distinct_hashes).encode()).hexdigest()

    return {
        "source_id": str(source_id),
        "source_policy_version": source_policy_version,
        "checks": [{**check, "passed": True} for check in checks],
        "fixture_set_sha256": fixture_set_sha256,
        "sample_count": len(distinct_hashes),
        "reviewer": str(actor_id),
        "reviewed_at": now.isoformat(),
        "valid_until": submission.valid_until.isoformat(),
        "decision": "APPROVED",
    }
