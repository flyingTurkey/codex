from datetime import UTC, datetime, timedelta
from uuid import UUID

from srbg_api.source_automation.repository import _candidate_summary
from srbg_contracts import SourceCandidateAction


def test_blocked_candidate_can_be_dismissed_or_requalified_but_never_enabled() -> None:
    now = datetime.now(UTC)
    row = {
        "id": UUID("019b1800-0000-7000-8000-000000000001"),
        "institution_name": "Example engineering authority",
        "canonical_url": "https://example.gov.cn/",
        "authorization_boundary": "example.gov.cn",
        "discovery_channels": ["SITEMAP"],
        "status": "BLOCKED",
        "industries": ["HIGHWAY"],
        "content_domains": ["SAFETY_REGULATION"],
        "language_tags": ["zh-CN"],
        "occurrence_count": 1,
        "first_discovered_at": now,
        "last_discovered_at": now,
        "bundle_id": UUID("019b1800-0000-7000-8000-000000000002"),
        "bundle_candidate_id": UUID("019b1800-0000-7000-8000-000000000001"),
        "bundle_run_id": UUID("019b1800-0000-7000-8000-000000000003"),
        "bundle_rule_version": "source-qualification-v1",
        "bundle_material_fingerprint": "a" * 64,
        "bundle_verdict": "BLOCKED",
        "bundle_storage_policy": "LINK_ONLY",
        "bundle_evidence_capture_policy": "TRANSIENT_METADATA_ONLY",
        "bundle_checks": [],
        "bundle_sampled_item_count": 1,
        "bundle_relevant_item_count": 0,
        "bundle_reason_codes": ["ROBOTS_BLOCKED"],
        "bundle_bundle_sha256": "b" * 64,
        "bundle_created_at": now,
        "bundle_valid_until": now + timedelta(days=7),
    }

    candidate = _candidate_summary(row)

    assert candidate.available_actions == [
        SourceCandidateAction.REQUEST_QUALIFICATION,
        SourceCandidateAction.DISMISS,
    ]
    assert SourceCandidateAction.ENABLE not in candidate.available_actions


def test_failed_candidate_without_a_bundle_can_still_be_dismissed() -> None:
    now = datetime.now(UTC)
    row = {
        "id": UUID("019b1800-0000-7000-8000-000000000011"),
        "institution_name": "Unreachable engineering authority",
        "canonical_url": "https://unreachable.example.gov.cn/",
        "authorization_boundary": "unreachable.example.gov.cn",
        "discovery_channels": ["BAIDU_SEARCH"],
        "status": "BLOCKED",
        "industries": ["HIGHWAY"],
        "content_domains": ["SAFETY_REGULATION"],
        "language_tags": ["zh-CN"],
        "occurrence_count": 1,
        "first_discovered_at": now,
        "last_discovered_at": now,
        "bundle_id": None,
    }

    candidate = _candidate_summary(row)

    assert candidate.latest_qualification is None
    assert candidate.available_actions == [
        SourceCandidateAction.REQUEST_QUALIFICATION,
        SourceCandidateAction.DISMISS,
    ]
