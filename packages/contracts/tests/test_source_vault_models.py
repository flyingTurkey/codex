from datetime import UTC, datetime, timedelta

import pytest
import srbg_contracts.models as models
from pydantic import ValidationError


def test_create_source_defaults_cannot_be_overridden_by_client() -> None:
    request = models.CreateSourceRequest(
        name="示例来源",
        base_url="https://example.gov.cn/",
        channel=models.SourceChannel.SAFETY,
        source_type=models.SourceType.GOVERNMENT,
        authority_level=models.AuthorityLevel.A1,
        priority="P0",
        collection_method="html_pdf",
        poll_interval_minutes=30,
        owner="source_ops",
    )

    assert request.model_dump(mode="json")["name"] == "示例来源"
    assert not hasattr(request, "enabled")
    assert not hasattr(request, "status")

    with pytest.raises(ValidationError):
        models.CreateSourceRequest.model_validate(
            {**request.model_dump(mode="json"), "enabled": True, "status": "ACTIVE"}
        )


def test_source_policy_contract_rejects_unknown_fields_and_bad_hashes() -> None:
    now = datetime(2026, 7, 13, tzinfo=UTC)
    payload = {
        "policy_version": "1.0.0",
        "status": "VALID",
        "robots_review": {
            "result": "ALLOWED",
            "evidence_url": "https://example.gov.cn/robots.txt",
            "evidence_sha256": "a" * 64,
            "checked_at": now.isoformat(),
        },
        "terms_review": {
            "result": "NOT_PRESENT",
            "evidence_url": "https://example.gov.cn/terms-review",
            "evidence_sha256": "b" * 64,
            "checked_at": now.isoformat(),
        },
        "copyright": {
            "storage_policy": "RAW_EVIDENCE_ALLOWED",
            "display_policy": "METADATA_EXCERPT_LINK",
            "fulltext_allowed": False,
            "image_allowed": False,
            "excerpt_max_chars": 300,
            "attribution_template": "来源: {source_name}",
        },
        "access": {
            "allowed_domains": ["example.gov.cn"],
            "requires_auth": False,
            "rate_limit_per_minute": 10,
            "user_agent": "SRBG-Insight/1.0",
        },
        "review": {
            "valid_until": (now + timedelta(days=90)).isoformat(),
            "approval_id": "approval-1",
        },
    }

    policy = models.SourcePolicySubmission.model_validate(payload)
    assert policy.status == models.SourcePolicyStatus.VALID

    payload["robots_review"]["evidence_sha256"] = "not-a-hash"
    with pytest.raises(ValidationError):
        models.SourcePolicySubmission.model_validate(payload)


def test_source_state_and_role_enums_are_canonical() -> None:
    assert [state.value for state in models.SourceState] == [
        "CANDIDATE",
        "COMPLIANCE_REVIEW",
        "FIXTURE_TEST",
        "APPROVED",
        "ACTIVE",
    ]
    assert models.UserRole.SOURCE_ADMIN.value == "source_admin"
