# ruff: noqa: RUF001
from uuid import UUID

import pytest
from srbg_api.papers.domain import (
    PaperAccessInput,
    bibliographic_fingerprint,
    determine_access_level,
    format_bibtex,
    format_gbt7714,
    format_ris,
    normalize_doi,
    rank_similar_papers,
)


def test_normalize_doi_collapses_prefix_case_whitespace_and_percent_encoding() -> None:
    assert normalize_doi(" https://doi.org/10.1000%2FABC%20 ") == "10.1000/abc"
    assert normalize_doi("doi: 10.1000/ABC") == "10.1000/abc"
    assert normalize_doi(None) is None


def test_normalize_doi_rejects_non_doi_values() -> None:
    with pytest.raises(ValueError, match="invalid DOI"):
        normalize_doi("OpenAlex:W123")


def test_no_doi_fingerprint_is_stable_but_does_not_claim_identity() -> None:
    left = bibliographic_fingerprint("  桥梁 智能检测：方法研究 ", "张 三", 2025)
    right = bibliographic_fingerprint("桥梁智能检测:方法研究", "张三", 2025)
    assert left == right
    assert len(left) == 64


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (PaperAccessInput(False, False, False), "METADATA_ONLY"),
        (PaperAccessInput(True, False, False), "ABSTRACT_ALLOWED"),
        (PaperAccessInput(True, True, True), "OPEN_FULLTEXT"),
        (PaperAccessInput(True, True, False), "ABSTRACT_ALLOWED"),
    ],
)
def test_access_level_requires_explicit_abstract_and_fulltext_licence(
    policy: PaperAccessInput, expected: str
) -> None:
    assert determine_access_level(policy) == expected


def test_citation_exports_use_canonical_metadata_and_escape_special_characters() -> None:
    paper = {
        "title": "桥梁监测与数字孪生: 方法与验证",
        "authors": ["张三", "Li, Wei"],
        "journal": "中国公路学报",
        "year": 2025,
        "volume": "38",
        "issue": "7",
        "pages": "1-12",
        "doi": "10.1000/bridge.2025.1",
    }
    assert "TY  - JOUR" in format_ris(paper)
    assert "DO  - 10.1000/bridge.2025.1" in format_ris(paper)
    assert "@article{" in format_bibtex(paper)
    assert "title = {桥梁监测与数字孪生: 方法与验证}" in format_bibtex(paper)
    assert format_gbt7714(paper).endswith("doi:10.1000/bridge.2025.1.")


def test_similar_papers_are_acl_filtered_reasoned_and_have_no_score() -> None:
    candidates = [
        {
            "id": UUID("019b0000-0000-7000-8000-000000006001"),
            "engineering_domains": ["BRIDGE"],
            "technology_tags": ["DIGITAL_TWIN", "SENSOR_NETWORK"],
            "visible": True,
        },
        {
            "id": UUID("019b0000-0000-7000-8000-000000006002"),
            "engineering_domains": ["BRIDGE"],
            "technology_tags": ["DIGITAL_TWIN"],
            "visible": False,
        },
    ]
    ranked = rank_similar_papers(
        engineering_domains=["BRIDGE"],
        technology_tags=["DIGITAL_TWIN"],
        candidates=candidates,
    )
    assert [item["id"] for item in ranked] == [candidates[0]["id"]]
    assert ranked[0]["match_reasons"] == ["工程专业：BRIDGE", "技术标签：DIGITAL_TWIN"]
    assert "score" not in ranked[0]
