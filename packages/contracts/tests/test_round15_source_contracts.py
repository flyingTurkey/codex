from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import (
    AutomaticPublicationPolicy,
    CreateSourceRequest,
    DocumentDetail,
    DownloadPolicy,
    LegalHoldPolicy,
    RuntimeAuthorization,
    SourceAssessmentSubmission,
    SourceAuthorityAssessment,
    SourceGovernanceMetadataUpdate,
    SourceIndependenceAssessment,
    SourceLifecycleState,
    SourcePolicyV2Submission,
    SourceTrialKind,
    SourceTrialQualitySummary,
)


def _policy_payload() -> dict[str, object]:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    evidence = {
        "result": "ALLOWED",
        "evidence_url": "https://example.test/policy",
        "evidence_sha256": "a" * 64,
        "checked_at": now.isoformat(),
    }
    return {
        "schema_version": "2.0.0",
        "policy_version": "2026-07-16.1",
        "valid_from": now.isoformat(),
        "valid_until": (now + timedelta(days=90)).isoformat(),
        "robots_review": evidence,
        "terms_review": evidence,
        "copyright_review": evidence,
        "fetch": {
            "allowed_domains": ["example.test"],
            "minimum_interval_seconds": 900,
            "rate_limit_per_minute": 4,
            "user_agent": "SRBG-SourceCenter/2.0",
        },
        "storage_policy": "RAW_EVIDENCE_ALLOWED",
        "display_policy": "METADATA_EXCERPT_LINK",
        "download_policy": "ORIGINAL_LINK_ONLY",
        "retention": {"retention_days": 365, "delete_after_retention": False},
        "legal_hold_policy": "SUPPORTED",
        "automatic_publication": "DISABLED",
        "slo": {
            "applicability": "NOT_APPLICABLE",
            "target_minutes": None,
            "reason": "No authorization for a 15-minute collection target",
            "authorization_confirmed": False,
            "technical_conditions_confirmed": False,
        },
        "reason": "Initial controlled policy",
    }


def test_round15_lifecycle_and_authorization_are_closed_sets() -> None:
    assert [item.value for item in SourceLifecycleState] == [
        "CANDIDATE",
        "COMPLIANCE_REVIEW",
        "TRIAL",
        "ACTIVE",
        "PAUSED",
        "RETIRED",
    ]


def test_fixture_document_contract_distinguishes_structured_discovery_responses() -> None:
    schema = DocumentDetail.model_json_schema()

    assert set(schema["properties"]["document_kind"]["enum"]) == {
        "DISCOVERY_JSON",
        "DISCOVERY_XML",
        "HTML",
        "PDF",
    }
    raw_schema = schema["$defs"]["RawObjectSummary"]
    assert set(raw_schema["properties"]["detected_mime"]["enum"]) == {
        "application/json",
        "application/pdf",
        "application/xml",
        "text/html",
    }
    assert [item.value for item in SourceTrialKind] == ["FIXTURE_REPLAY", "LIVE_TRIAL"]
    assert [item.value for item in RuntimeAuthorization] == [
        "DENIED",
        "TRIAL_ONLY",
        "PRODUCTION",
    ]


def test_policy_v2_requires_every_governance_axis_and_rejects_client_authority() -> None:
    policy = SourcePolicyV2Submission.model_validate(_policy_payload())

    assert policy.download_policy is DownloadPolicy.ORIGINAL_LINK_ONLY
    assert policy.legal_hold_policy is LegalHoldPolicy.SUPPORTED
    assert policy.automatic_publication is AutomaticPublicationPolicy.DISABLED

    unsafe_user_agent = _policy_payload()
    unsafe_user_agent["fetch"] = {
        **unsafe_user_agent["fetch"],  # type: ignore[arg-type]
        "user_agent": "ok\r\nX-Evil: yes",
    }
    with pytest.raises(ValidationError):
        SourcePolicyV2Submission.model_validate(unsafe_user_agent)

    for missing in (
        "robots_review",
        "terms_review",
        "copyright_review",
        "retention",
        "legal_hold_policy",
        "automatic_publication",
        "slo",
    ):
        payload = _policy_payload()
        payload.pop(missing)
        with pytest.raises(ValidationError):
            SourcePolicyV2Submission.model_validate(payload)

    forged = _policy_payload() | {
        "status": "APPROVED",
        "lifecycle_state": "ACTIVE",
        "source_trust_score": 100,
    }
    with pytest.raises(ValidationError):
        SourcePolicyV2Submission.model_validate(forged)


def test_policy_v2_rejects_missing_or_blocked_legal_evidence_and_invalid_slo() -> None:
    for result in ("NOT_PRESENT", "BLOCKED"):
        payload = _policy_payload()
        payload["terms_review"] = {
            **payload["terms_review"],  # type: ignore[arg-type]
            "result": result,
        }
        with pytest.raises(ValidationError):
            SourcePolicyV2Submission.model_validate(payload)

    payload = _policy_payload()
    payload["slo"] = {
        "applicability": "APPLICABLE",
        "target_minutes": None,
        "reason": None,
        "authorization_confirmed": True,
        "technical_conditions_confirmed": True,
    }
    with pytest.raises(ValidationError):
        SourcePolicyV2Submission.model_validate(payload)

    payload = _policy_payload()
    payload["slo"] = {
        "applicability": "NOT_APPLICABLE",
        "target_minutes": None,
        "reason": "not applicable",
        "authorization_confirmed": True,
        "technical_conditions_confirmed": False,
    }
    with pytest.raises(ValidationError, match="cannot claim authorization"):
        SourcePolicyV2Submission.model_validate(payload)


def test_policy_v2_normalizes_validity_and_review_evidence_to_utc() -> None:
    payload = _policy_payload()
    payload["valid_from"] = "2026-07-16T16:00:00+08:00"
    payload["valid_until"] = "2026-10-14T16:00:00+08:00"
    for review_key in ("robots_review", "terms_review", "copyright_review"):
        payload[review_key] = {
            **payload[review_key],  # type: ignore[arg-type]
            "checked_at": "2026-07-16T15:30:00+08:00",
        }

    policy = SourcePolicyV2Submission.model_validate(payload)

    assert policy.valid_from == datetime(2026, 7, 16, 8, tzinfo=UTC)
    for review in (
        policy.robots_review,
        policy.terms_review,
        policy.copyright_review,
    ):
        assert review.checked_at == datetime(2026, 7, 16, 7, 30, tzinfo=UTC)

    for forbidden_domain in ("localhost", "127.0.0.1", "169.254.169.254"):
        payload = _policy_payload()
        payload["fetch"] = {
            **payload["fetch"],  # type: ignore[arg-type]
            "allowed_domains": [forbidden_domain],
        }
        with pytest.raises(ValidationError):
            SourcePolicyV2Submission.model_validate(payload)

    payload = _policy_payload()
    payload["robots_review"] = {
        **payload["robots_review"],  # type: ignore[arg-type]
        "evidence_sha256": None,
    }
    with pytest.raises(ValidationError):
        SourcePolicyV2Submission.model_validate(payload)

    payload = _policy_payload()
    payload["slo"] = {
        "applicability": "APPLICABLE",
        "target_minutes": 15,
        "reason": None,
        "authorization_confirmed": False,
        "technical_conditions_confirmed": True,
    }
    with pytest.raises(ValidationError):
        SourcePolicyV2Submission.model_validate(payload)


def test_lifecycle_actions_never_accept_a_target_state() -> None:
    from srbg_contracts import SourceLifecycleActionRequest, SourceProductionApprovalRequest

    with pytest.raises(ValidationError):
        SourceLifecycleActionRequest.model_validate(
            {"reason": "client forgery", "target_state": "ACTIVE"}
        )
    with pytest.raises(ValidationError):
        SourceProductionApprovalRequest.model_validate(
            {
                "policy_version_id": str(UUID("019b1500-0000-7000-8000-000000000001")),
                "connector_config_version_id": str(
                    UUID("019b1500-0000-7000-8000-000000000002")
                ),
                "trial_run_id": str(UUID("019b1500-0000-7000-8000-000000000003")),
                "reason": "client forgery",
                "active": True,
            }
        )


def test_trial_quality_summary_has_bounded_database_derived_counts() -> None:
    summary = SourceTrialQualitySummary(
        raw_count=3,
        ready_count=2,
        parse_failed_count=0,
        security_failed_count=0,
        rejected_raw_attempt_count=0,
        ready_ratio_bps=6667,
    )

    assert summary.ready_ratio_bps == 6667
    with pytest.raises(ValidationError, match="READY ratio"):
        SourceTrialQualitySummary(
            raw_count=3,
            ready_count=2,
            parse_failed_count=0,
            security_failed_count=0,
            rejected_raw_attempt_count=0,
            ready_ratio_bps=9000,
        )


def test_trial_quality_keeps_rejected_attempts_visible_in_security_failures() -> None:
    summary = SourceTrialQualitySummary(
        raw_count=1,
        ready_count=1,
        parse_failed_count=0,
        security_failed_count=2,
        rejected_raw_attempt_count=2,
        ready_ratio_bps=10000,
    )

    assert summary.security_failed_count == 2
    assert summary.rejected_raw_attempt_count == 2

    with pytest.raises(ValidationError, match="subset"):
        SourceTrialQualitySummary(
            raw_count=1,
            ready_count=1,
            parse_failed_count=0,
            security_failed_count=0,
            rejected_raw_attempt_count=1,
            ready_ratio_bps=10000,
        )


def test_governance_reasons_reject_urls_credentials_and_control_characters() -> None:
    from srbg_contracts import SourceLifecycleActionRequest

    for reason in (
        "inspect https://example.test/private",
        "authorization bearer token",
        "contact admin@example.test",
        "line one\nline two",
    ):
        with pytest.raises(ValidationError, match="forbidden sensitive material"):
            SourceLifecycleActionRequest(reason=reason)


@pytest.mark.parametrize(
    "evidence_url",
    (
        "https://reviewer:password@example.test/robots.txt",
        "https://example.test/robots.txt?token=secret",
        "https://example.test/robots.txt?api_key=secret",
    ),
)
def test_source_policy_rejects_credentials_in_review_evidence_urls(
    evidence_url: str,
) -> None:
    payload = _policy_payload()
    for review_name in ("robots_review", "terms_review", "copyright_review"):
        review = dict(payload[review_name])  # type: ignore[arg-type]
        review["evidence_url"] = evidence_url
        payload[review_name] = review

    with pytest.raises(ValidationError, match="forbidden sensitive material"):
        SourcePolicyV2Submission.model_validate(payload)


def test_source_governance_list_items_are_bounded_and_safe() -> None:
    candidate = {
        "name": "bounded source",
        "base_url": "https://example.test",
        "channel": "SAFETY",
        "source_type": "government",
        "authority_level": "A1",
        "priority": "P0",
        "collection_method": "RSS",
        "poll_interval_minutes": 60,
        "owner": "source-ops",
        "country_codes": ["CN"],
        "region_codes": ["CN-SC"],
        "language_tags": ["zh-CN"],
    }
    assert CreateSourceRequest.model_validate(candidate).country_codes == ["CN"]
    for field, value in (
        ("country_codes", ["CHINA"]),
        ("region_codes", ["CN-SC\nFORGED"]),
        ("language_tags", ["z" * 36]),
    ):
        invalid = dict(candidate)
        invalid[field] = value
        with pytest.raises(ValidationError):
            CreateSourceRequest.model_validate(invalid)

    with pytest.raises(ValidationError):
        SourceGovernanceMetadataUpdate.model_validate(
            {
                "governance_owner_id": "019b1500-0000-7000-8000-000000000001",
                "country_codes": ["CN"],
                "region_codes": ["CN-SC\x00"],
                "language_tags": ["zh-CN"],
                "industries": ["HIGHWAY"],
                "content_domains": ["SAFETY_REGULATION"],
                "declared_roles": ["OFFICIAL_PRIMARY"],
                "reason": "bounded governance metadata",
            }
        )

    with pytest.raises(ValidationError):
        SourceAssessmentSubmission.model_validate(
            {
                "authority": {
                    "level": "A1",
                    "rule_version": "round15-v1",
                    "reason_codes": ["bad-code"],
                    "evidence_refs": ["https://example.test/evidence?token=secret"],
                    "assessed_at": "2026-07-16T00:00:00Z",
                },
                "independence": {
                    "level": "EDITORIALLY_INDEPENDENT",
                    "rule_version": "round15-v1",
                    "reason_codes": ["EDITORIAL_REVIEW"],
                    "evidence_refs": ["review:editorial-policy"],
                    "assessed_at": "2026-07-16T00:00:00Z",
                },
                "reason": "bounded assessment input",
            }
        )


def test_source_assessment_timestamps_reject_naive_and_normalize_to_utc() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        SourceAuthorityAssessment.model_validate(
            {
                "level": "A1",
                "rule_version": "authority-v1",
                "reason_codes": ["GOVERNMENT_PUBLISHER"],
                "evidence_refs": ["policy:official-domain"],
                "assessed_at": "2026-07-16T08:00:00",
            }
        )
    with pytest.raises(ValidationError, match="timezone"):
        SourceIndependenceAssessment.model_validate(
            {
                "level": "EDITORIALLY_INDEPENDENT",
                "rule_version": "independence-v1",
                "reason_codes": ["EDITORIAL_CONTROL"],
                "evidence_refs": ["review:editorial-policy"],
                "assessed_at": datetime(2026, 7, 16, 8),
            }
        )

    submission = SourceAssessmentSubmission.model_validate(
        {
            "authority": {
                "level": "A1",
                "rule_version": "authority-v1",
                "reason_codes": ["GOVERNMENT_PUBLISHER"],
                "evidence_refs": ["policy:official-domain"],
                "assessed_at": "2026-07-16T08:00:00+08:00",
            },
            "independence": {
                "level": "EDITORIALLY_INDEPENDENT",
                "rule_version": "independence-v1",
                "reason_codes": ["EDITORIAL_CONTROL"],
                "evidence_refs": ["review:editorial-policy"],
                "assessed_at": "2026-07-16T07:30:00+07:30",
            },
            "reason": "normalize assessment timestamps",
        }
    )

    assert submission.authority.assessed_at == datetime(2026, 7, 16, tzinfo=UTC)
    assert submission.authority.assessed_at.tzinfo is UTC
    assert submission.independence.assessed_at == datetime(2026, 7, 16, tzinfo=UTC)
    assert submission.independence.assessed_at.tzinfo is UTC
