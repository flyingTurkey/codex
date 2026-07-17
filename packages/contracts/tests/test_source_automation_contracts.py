from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import (
    DiscoveryChannel,
    QualificationCheckLevel,
    QualificationCheckView,
    QualificationVerdict,
    SourceCandidateBatchDecisionRequest,
    SourceCandidateBatchTarget,
    SourceCandidateDecision,
    SourceCandidateDecisionRequest,
    SourceCandidateStatus,
    SourceIndustry,
    SourceStreamStatus,
    SourceStreamView,
    StoragePolicy,
)

CANDIDATE_ID = UUID("019b1800-0000-7000-8000-000000000001")


def test_source_automation_enums_cover_discovery_lifecycle_and_engineering_scope() -> None:
    assert DiscoveryChannel.BAIDU_SEARCH == "BAIDU_SEARCH"
    assert DiscoveryChannel.SITEMAP == "SITEMAP"
    assert SourceCandidateStatus.READY_FOR_DECISION == "READY_FOR_DECISION"
    assert QualificationVerdict.WARN_WAIVABLE == "WARN_WAIVABLE"
    assert SourceStreamStatus.ACTIVE == "ACTIVE"
    assert {
        SourceIndustry.WATER_CONSERVANCY,
        SourceIndustry.MUNICIPAL,
        SourceIndustry.BUILDING,
        SourceIndustry.ENERGY,
        SourceIndustry.PORT_WATERWAY,
        SourceIndustry.AIRPORT,
    }.issubset(set(SourceIndustry))


def test_candidate_decision_is_bound_to_a_current_qualification_hash() -> None:
    request = SourceCandidateDecisionRequest(
        decision=SourceCandidateDecision.ENABLE,
        expected_bundle_sha256="a" * 64,
        reason="enable qualified public engineering source",
    )

    assert request.expected_bundle_sha256 == "a" * 64
    assert request.waiver_reason is None

    with pytest.raises(ValidationError):
        SourceCandidateDecisionRequest(
            decision=SourceCandidateDecision.ENABLE,
            expected_bundle_sha256="client-says-current",
            reason="invalid hash",
        )


def test_batch_enable_requires_unique_bounded_targets_and_one_rule_version() -> None:
    target = SourceCandidateBatchTarget(
        candidate_id=CANDIDATE_ID,
        expected_bundle_sha256="b" * 64,
    )
    request = SourceCandidateBatchDecisionRequest(
        targets=[target],
        expected_rule_version="source-qualification-v1",
        reason="enable the all-green cohort",
    )
    assert request.targets == [target]

    with pytest.raises(ValidationError):
        SourceCandidateBatchDecisionRequest(
            targets=[target, target],
            expected_rule_version="source-qualification-v1",
            reason="duplicates are unsafe",
        )


def test_qualification_check_and_storage_policy_do_not_conflate_warning_with_block() -> None:
    now = datetime.now(UTC)
    check = QualificationCheckView(
        code="TERMS_NOT_PRESENT",
        level=QualificationCheckLevel.WARN,
        message="No explicit public terms were found",
        evidence_refs=["qualification-artifact:terms-probe"],
        observed_at=now,
    )
    assert check.level is QualificationCheckLevel.WARN
    assert StoragePolicy.METADATA_ONLY != StoragePolicy.RAW_EVIDENCE_ALLOWED

    with pytest.raises(ValidationError):
        QualificationCheckView(
            code="STALE",
            level=QualificationCheckLevel.PASS,
            message="invalid time",
            evidence_refs=[],
            observed_at=now + timedelta(days=1),
        )


def test_stream_view_exposes_the_authoritative_cursor_timestamp() -> None:
    now = datetime.now(UTC)
    stream = SourceStreamView(
        id=UUID("019b1800-0000-7000-8000-000000000010"),
        source_id=UUID("019b1800-0000-7000-8000-000000000011"),
        candidate_id=CANDIDATE_ID,
        institution_name="Engineering source",
        canonical_url="https://example.gov.cn/",
        authorization_boundary="example.gov.cn",
        stream_key="DEFAULT",
        status=SourceStreamStatus.ACTIVE,
        rule_version="source-qualification-v1",
        updated_at=now,
    )

    assert stream.updated_at == now
