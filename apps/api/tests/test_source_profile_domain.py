import json
from dataclasses import replace

import pytest
from pydantic import ValidationError
from srbg_api.source_profiles import (
    ProfileEvidence,
    ProfileRuleInput,
    build_source_profile,
    canonical_profile_input_hash,
    validate_model_evidence,
)
from srbg_contracts import SourceProfileModelOutput


def _evidence() -> tuple[ProfileEvidence, ...]:
    return (
        ProfileEvidence(
            evidence_id="homepage-1",
            kind="HOMEPAGE",
            url="https://www.mot.gov.cn/",
            sha256="a" * 64,
            excerpt="中华人民共和国交通运输部 公路安全生产 政策法规",
        ),
        ProfileEvidence(
            evidence_id="about-1",
            kind="ABOUT",
            url="https://www.mot.gov.cn/jigou/",
            sha256="b" * 64,
            excerpt="交通运输部是国务院组成部门。",
        ),
    )


def test_local_rules_remain_available_when_model_is_unavailable() -> None:
    profile = build_source_profile(
        ProfileRuleInput(
            origin="https://www.mot.gov.cn/",
            stream_types=("RSS_ATOM", "DIRECT_PDF"),
            evidence=_evidence(),
        ),
        model_output=None,
        partial_reason="MODEL_UNAVAILABLE",
    )

    assert profile.status == "PARTIAL"
    assert profile.industries == ("HIGHWAY", "GENERAL_TRANSPORT")
    assert profile.content_domains == ("SAFETY_REGULATION",)
    assert profile.language_tags == ("zh-CN",)
    assert profile.country_codes == ("CN",)
    assert profile.authority_level == "A0"
    assert profile.authority_basis == "AUTO_INFERRED"
    assert "MODEL_UNAVAILABLE" in profile.reason_codes
    assert {fact.code for fact in profile.technical_facts} == {"DIRECT_PDF", "RSS_ATOM"}


def test_budget_disabled_is_partial_and_never_changes_local_result() -> None:
    local = build_source_profile(
        ProfileRuleInput("https://example.cn/", (), _evidence()),
        model_output=None,
        partial_reason="BUDGET_DISABLED",
    )
    assert local.status == "PARTIAL"
    assert "BUDGET_DISABLED" in local.reason_codes


def test_model_contract_rejects_extra_or_forbidden_authority_fields() -> None:
    payload = {
        "industry_candidates": [],
        "content_domain_candidates": [],
        "language_candidates": [],
        "country_candidates": [],
        "region_candidates": [],
        "declared_role_candidates": [],
        "organization_clues": [],
        "ownership_clues": [],
        "authority_level": "A0",
    }
    with pytest.raises(ValidationError):
        SourceProfileModelOutput.model_validate(payload)


def test_forged_evidence_id_or_url_is_rejected() -> None:
    base = {
        "industry_candidates": [
            {
                "value": "HIGHWAY",
                "confidence": 80,
                "reason_code": "MODEL_HIGHWAY",
                "evidence_ids": ["forged"],
            }
        ],
        "content_domain_candidates": [],
        "language_candidates": [],
        "country_candidates": [],
        "region_candidates": [],
        "declared_role_candidates": [],
        "organization_clues": [],
        "ownership_clues": [],
    }
    output = SourceProfileModelOutput.model_validate(base)
    with pytest.raises(ValueError, match="server-issued"):
        validate_model_evidence(output, _evidence())
    base["industry_candidates"][0]["evidence_url"] = "https://evil.example/"
    with pytest.raises(ValidationError):
        SourceProfileModelOutput.model_validate(base)


def test_input_hash_is_canonical_and_changes_with_evidence() -> None:
    left = canonical_profile_input_hash(
        ProfileRuleInput("https://www.mot.gov.cn/", ("RSS_ATOM",), _evidence())
    )
    right = canonical_profile_input_hash(
        ProfileRuleInput("https://www.mot.gov.cn/", ("RSS_ATOM",), tuple(reversed(_evidence())))
    )
    changed = canonical_profile_input_hash(
        ProfileRuleInput(
            "https://www.mot.gov.cn/",
            ("RSS_ATOM",),
            (_evidence()[0], replace(_evidence()[1], sha256="c" * 64)),
        )
    )
    assert left == right
    assert left != changed
    assert len(json.loads(json.dumps({"hash": left}))["hash"]) == 64
