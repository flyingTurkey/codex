from dataclasses import replace

import pytest
from srbg_api.source_automation.domain import (
    AutomationRuleViolation,
    QualificationFacts,
    authorize_candidate_decision,
    evaluate_qualification,
    validate_batch_enable,
)
from srbg_contracts import (
    QualificationVerdict,
    ReviewEvidenceResult,
    SourceCandidateDecision,
    StoragePolicy,
)


def _public_facts() -> QualificationFacts:
    return QualificationFacts(
        canonical_url="https://jtt.sc.gov.cn/jtt/c101520/list.shtml",
        authorization_boundary="jtt.sc.gov.cn",
        robots=ReviewEvidenceResult.ALLOWED,
        terms=ReviewEvidenceResult.ALLOWED,
        copyright=ReviewEvidenceResult.ALLOWED,
        requires_login=False,
        captcha_detected=False,
        paywall_detected=False,
        redirect_boundary_valid=True,
        resolved_addresses_public=True,
        connector_valid=True,
        relevant_item_count=5,
        sampled_item_count=5,
        material_fingerprint="a" * 64,
    )


def test_public_source_with_no_explicit_terms_gets_restricted_fast_path() -> None:
    assessment = evaluate_qualification(
        replace(_public_facts(), terms=ReviewEvidenceResult.NOT_PRESENT),
        rule_version="source-qualification-v1",
    )

    assert assessment.verdict is QualificationVerdict.WARN_WAIVABLE
    assert assessment.storage_policy is StoragePolicy.METADATA_ONLY
    assert "TERMS_NOT_PRESENT" in assessment.reason_codes
    assert "LOGIN_REQUIRED" not in assessment.reason_codes


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("robots", ReviewEvidenceResult.BLOCKED, "ROBOTS_BLOCKED"),
        ("requires_login", True, "LOGIN_REQUIRED"),
        ("captcha_detected", True, "CAPTCHA_DETECTED"),
        ("paywall_detected", True, "PAYWALL_DETECTED"),
        ("resolved_addresses_public", False, "SSRF_UNSAFE_ADDRESS"),
        ("redirect_boundary_valid", False, "REDIRECT_OUTSIDE_BOUNDARY"),
    ],
)
def test_non_negotiable_access_and_network_controls_are_hard_blocks(
    field: str, value: object, reason_code: str
) -> None:
    assessment = evaluate_qualification(
        replace(_public_facts(), **{field: value}),
        rule_version="source-qualification-v1",
    )

    assert assessment.verdict is QualificationVerdict.BLOCKED
    assert reason_code in assessment.reason_codes


def test_warning_needs_an_individual_waiver_and_material_change_invalidates_it() -> None:
    warning = evaluate_qualification(
        replace(_public_facts(), copyright=ReviewEvidenceResult.RESTRICTED),
        rule_version="source-qualification-v1",
    )
    with pytest.raises(AutomationRuleViolation, match="waiver"):
        authorize_candidate_decision(
            warning,
            decision=SourceCandidateDecision.ENABLE,
            expected_bundle_sha256=warning.bundle_sha256,
            current_material_fingerprint="a" * 64,
            waiver_reason=None,
        )

    authorized = authorize_candidate_decision(
        warning,
        decision=SourceCandidateDecision.ENABLE,
        expected_bundle_sha256=warning.bundle_sha256,
        current_material_fingerprint="a" * 64,
        waiver_reason="Only metadata, a short factual excerpt and the original link will be shown",
    )
    assert authorized.waiver_applied is True

    with pytest.raises(AutomationRuleViolation, match="material"):
        authorize_candidate_decision(
            warning,
            decision=SourceCandidateDecision.ENABLE,
            expected_bundle_sha256=warning.bundle_sha256,
            current_material_fingerprint="c" * 64,
            waiver_reason="The previous waiver must not survive a material change",
        )


def test_batch_enable_only_accepts_unexpired_all_green_same_rule_bundles() -> None:
    green = evaluate_qualification(_public_facts(), rule_version="source-qualification-v1")
    second = evaluate_qualification(
        replace(_public_facts(), canonical_url="https://jtt.sc.gov.cn/safety/list.shtml"),
        rule_version="source-qualification-v1",
    )
    validate_batch_enable([green, second], expected_rule_version="source-qualification-v1")

    warning = evaluate_qualification(
        replace(_public_facts(), terms=ReviewEvidenceResult.NOT_PRESENT),
        rule_version="source-qualification-v1",
    )
    with pytest.raises(AutomationRuleViolation, match="all-green"):
        validate_batch_enable([green, warning], expected_rule_version="source-qualification-v1")

    changed_rule = evaluate_qualification(
        _public_facts(), rule_version="source-qualification-v2"
    )
    with pytest.raises(AutomationRuleViolation, match="rule version"):
        validate_batch_enable(
            [green, changed_rule],
            expected_rule_version="source-qualification-v1",
        )
