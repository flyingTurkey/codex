import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t31_glodon_ccteg_source_stream_discovery.json"
)
SCHEMA = MANIFEST.with_suffix(".schema.json")


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _validate(payload: dict[str, Any]) -> None:
    schema = _load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

    for source in payload["sources"]:
        assert len(source["streams"]) == 1
        stream = source["streams"][0]
        parsed = urlsplit(stream["collection_url"])
        assert parsed.scheme == "https"
        assert parsed.hostname in stream["allowed_hosts"]
        assert re.fullmatch(
            stream["collection_boundary"]["collection_path_pattern"], parsed.path
        )
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        assert query == stream["collection_boundary"]["required_query"]
        checks = {item["check"]: item for item in stream["compliance"]}
        assert set(checks) == {
            "PUBLIC_NETWORK",
            "REDIRECTS",
            "ROBOTS",
            "TERMS",
            "COPYRIGHT",
            "ACCESS_BOUNDARY",
            "PUBLIC_REACHABILITY",
        }
        assert all(item["status"] != "UNKNOWN" for item in checks.values())


def _accepts(stream: dict[str, Any], title: str, body: str) -> bool:
    text = f"{title}\n{body}".casefold()
    rules = stream["prefilter"]
    return (
        not any(term.casefold() in text for term in rules["excluded_terms"])
        and any(term.casefold() in text for term in rules["engineering_object_terms"])
        and any(term.casefold() in text for term in rules["lifecycle_terms"])
    )


def test_t31_manifest_matches_versioned_research_contract() -> None:
    _validate(_load(MANIFEST))


def test_t31_preserves_two_sources_and_research_runtime_separation() -> None:
    payload = _load(MANIFEST)

    assert payload["issue"] == 32
    assert payload["parent_spec"] == 1
    assert payload["rule_version"] == "t31-stream-discovery-w5-v1"
    assert {source["institution"] for source in payload["sources"]} == {
        "广联达",
        "中国煤炭科工集团",
    }
    assert len(payload["sources"]) == 2
    assert all(source["source_status"] == "CANDIDATE" for source in payload["sources"])
    assert all(source["desired_enabled"] is False for source in payload["sources"])
    assert all(source["source_admission"] is None for source in payload["sources"])
    assert all(source["actual_running"] is False for source in payload["sources"])
    assert all(source["pause_appended"] is False for source in payload["sources"])
    assert all(source["coverage_credit_granted"] is False for source in payload["sources"])
    assert payload["closure_eligible"] is False


def test_t31_locks_exact_bounded_collections_but_fails_closed_on_terms() -> None:
    payload = _load(MANIFEST)
    streams = {
        source["institution"]: source["streams"][0] for source in payload["sources"]
    }

    glodon = streams["广联达"]
    assert glodon["collection_url"] == "https://www.glodon.com/case/index/5.html"
    assert glodon["allowed_hosts"] == ["www.glodon.com"]
    assert glodon["connector_type"] == "HTML_LIST_DETAIL"
    assert glodon["readiness"] == "BOUNDED"
    assert glodon["disposition"] == "MANUAL_SHADOW"
    assert glodon["blocker_codes"] == ["TERMS_PROHIBIT_AUTOMATED_ACCESS"]

    ccteg = streams["中国煤炭科工集团"]
    assert ccteg["collection_url"] == (
        "https://www.ccteg.cn/zh/article/textList/40?idss=183"
    )
    assert ccteg["collection_boundary"]["required_query"] == {"idss": "183"}
    assert ccteg["allowed_hosts"] == ["www.ccteg.cn"]
    assert ccteg["connector_type"] == "HTML_LIST_DETAIL"
    assert ccteg["readiness"] == "BOUNDED"
    assert ccteg["disposition"] == "MANUAL_SHADOW"
    assert ccteg["blocker_codes"] == ["TERMS_REQUIRE_WRITTEN_PERMISSION"]


@pytest.mark.parametrize(
    ("institution", "title", "body", "expected"),
    (
        (
            "广联达",
            "阜溧高速梁场应用 AI+智慧建造平台",
            "BIM、GIS 与物联网支撑公路施工进度和安全管理",
            True,
        ),
        (
            "广联达",
            "广联达发布年度财报并举办品牌 AI 大会",
            "介绍企业经营和市场活动",
            False,
        ),
        (
            "中国煤炭科工集团",
            "井下氮气降温装置投入矿井防灭火",
            "新装备用于煤矿安全监测与灾害防控",
            True,
        ),
        (
            "中国煤炭科工集团",
            "集团党委召开经营工作会议",
            "部署党建、品牌宣传和年度经营任务",
            False,
        ),
    ),
)
def test_t31_prefilters_only_direct_engineering_lifecycle_facts(
    institution: str, title: str, body: str, expected: bool
) -> None:
    payload = _load(MANIFEST)
    stream = next(
        source["streams"][0]
        for source in payload["sources"]
        if source["institution"] == institution
    )

    assert _accepts(stream, title, body) is expected


def test_t31_preserves_claim_basis_and_mining_facet_boundaries() -> None:
    payload = _load(MANIFEST)
    streams = {
        source["institution"]: source["streams"][0] for source in payload["sources"]
    }

    assert streams["广联达"]["permitted_claim_bases"] == ["MANUFACTURER_CLAIM"]
    assert "INDEPENDENT_VERIFICATION" not in streams["中国煤炭科工集团"][
        "permitted_claim_bases"
    ]
    assert streams["中国煤炭科工集团"]["engineering_objects"] == ["MINING"]
    assert streams["中国煤炭科工集团"]["specialty_facets"] == []
    assert streams["中国煤炭科工集团"]["tunnel_gas_policy"] == (
        "MINING_ONLY_UNLESS_HIGHWAY_OR_RAILWAY_TUNNEL_EVIDENCE"
    )


def test_t31_rejects_authority_escalation_or_unknown_compliance() -> None:
    payload = _load(MANIFEST)

    enabled = deepcopy(payload)
    enabled["sources"][0]["desired_enabled"] = True
    with pytest.raises(ValidationError):
        _validate(enabled)

    admitted = deepcopy(payload)
    admitted["sources"][0]["source_admission"] = "ADMITTED"
    with pytest.raises(ValidationError):
        _validate(admitted)

    admission_ready = deepcopy(payload)
    admission_ready["sources"][0]["streams"][0]["disposition"] = "ADMISSION_READY"
    with pytest.raises(ValidationError):
        _validate(admission_ready)

    unknown = deepcopy(payload)
    unknown["sources"][1]["streams"][0]["compliance"][0]["status"] = "UNKNOWN"
    with pytest.raises((AssertionError, ValidationError)):
        _validate(unknown)
