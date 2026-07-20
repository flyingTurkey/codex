import csv
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "docs" / "codex-kit" / "assets" / "validation"
MANIFEST = VALIDATION / "t31r_sichuan_housing_guizhou_energy_source_stream_discovery.json"
SCHEMA = MANIFEST.with_suffix(".schema.json")
ORIGINAL_MANIFEST = VALIDATION / "t31_glodon_ccteg_source_stream_discovery.json"
ROLLOUT = VALIDATION / "civil_engineering_source_rollout_v2.json"
CAMPAIGN = VALIDATION / "civil_engineering_source_campaign_v2.json"
REGISTRY = ROOT / "docs" / "codex-kit" / "assets" / "source_registry.csv"


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


def test_t31r_manifest_matches_versioned_research_contract() -> None:
    _validate(_load(MANIFEST))


def test_t31r_supersedes_without_overwriting_original_blocker_evidence() -> None:
    original = _load(ORIGINAL_MANIFEST)
    replacement = _load(MANIFEST)

    assert original["issue"] == 32
    assert original["closure_eligible"] is False
    assert replacement["issue"] == 38
    assert replacement["supersedes_issue"] == 32
    assert replacement["parent_spec"] == 1
    assert replacement["rule_version"] == "t31r-replacement-stream-discovery-v1"
    assert replacement["closure_eligible"] is True
    assert {source["institution"] for source in replacement["sources"]} == {
        "四川省住房和城乡建设厅",
        "贵州省能源局",
    }


def test_t31r_locks_two_bounded_admission_ready_streams_without_runtime_authority() -> None:
    payload = _load(MANIFEST)
    streams = {
        source["institution"]: source["streams"][0] for source in payload["sources"]
    }

    assert streams["四川省住房和城乡建设厅"]["collection_url"] == (
        "https://jst.sc.gov.cn/scjst/c101428/article_list.shtml"
    )
    assert streams["贵州省能源局"]["collection_url"] == (
        "https://nyj.guizhou.gov.cn/zwgk/xxgkml/zdlyxx/nykjgl/"
    )
    assert all(stream["readiness"] == "BOUNDED" for stream in streams.values())
    assert all(
        stream["disposition"] == "ADMISSION_READY" for stream in streams.values()
    )
    assert all(stream["blocker_codes"] == [] for stream in streams.values())
    assert all(source["source_status"] == "CANDIDATE" for source in payload["sources"])
    assert all(source["desired_enabled"] is False for source in payload["sources"])
    assert all(source["source_admission"] is None for source in payload["sources"])
    assert all(source["actual_running"] is False for source in payload["sources"])
    assert all(source["pause_appended"] is False for source in payload["sources"])
    assert all(
        source["coverage_credit_granted"] is False for source in payload["sources"]
    )


@pytest.mark.parametrize(
    ("institution", "title", "body", "expected"),
    (
        (
            "四川省住房和城乡建设厅",
            "发布住房城乡建设领域智能建造科技项目榜单",
            "项目覆盖房屋建筑、城市生命线和市政基础设施 BIM 监测",
            True,
        ),
        (
            "四川省住房和城乡建设厅",
            "领取勘察设计工程师注册证书的通知",
            "办理企业资质和人员注册事项",
            False,
        ),
        (
            "贵州省能源局",
            "贵州省智能煤矿项目评定情况公示",
            "对煤矿智能采掘、安全监测和矿山装备项目开展验收",
            True,
        ),
        (
            "贵州省能源局",
            "省能源局召开党组会研究风电项目",
            "部署党建并讨论光伏、电价和节能报告采购",
            False,
        ),
    ),
)
def test_t31r_prefilters_only_direct_engineering_facts(
    institution: str, title: str, body: str, expected: bool
) -> None:
    payload = _load(MANIFEST)
    stream = next(
        source["streams"][0]
        for source in payload["sources"]
        if source["institution"] == institution
    )

    assert _accepts(stream, title, body) is expected


def test_t31r_preserves_authority_and_mining_facet_boundaries() -> None:
    payload = _load(MANIFEST)
    streams = {
        source["institution"]: source["streams"][0] for source in payload["sources"]
    }

    assert streams["四川省住房和城乡建设厅"]["permitted_claim_bases"] == [
        "AUTHORITY_FINDING"
    ]
    assert streams["贵州省能源局"]["permitted_claim_bases"] == [
        "AUTHORITY_FINDING"
    ]
    assert streams["贵州省能源局"]["engineering_objects"] == ["MINING"]
    assert streams["贵州省能源局"]["specialty_facets"] == []
    assert streams["贵州省能源局"]["tunnel_gas_policy"] == (
        "MINING_ONLY_UNLESS_HIGHWAY_OR_RAILWAY_TUNNEL_EVIDENCE"
    )


def test_t31r_updates_registry_and_second_batch_mapping_without_duplicate_sources() -> None:
    with REGISTRY.open(encoding="utf-8", newline="") as source_file:
        rows = list(csv.DictReader(source_file))
    registry = {row["source_id"]: row for row in rows}

    assert sum(row["name"] == "四川省住房和城乡建设厅" for row in rows) == 1
    assert sum(row["name"] == "贵州省能源局" for row in rows) == 1
    assert registry["GOV-017"]["status"] == "CANDIDATE"
    assert registry["GOV-023"]["status"] == "CANDIDATE"
    assert registry["GOV-023"]["enabled"] == "false"

    second_batch = _load(ROLLOUT)["batches"][1]["institutions"]
    assert len(second_batch) == 10
    assert "四川省住房和城乡建设厅" in second_batch
    assert "贵州省能源局" in second_batch
    assert "广联达" not in second_batch
    assert "中国煤炭科工集团" not in second_batch

    campaign = {item["institution"]: item for item in _load(CAMPAIGN)["sources"]}
    assert campaign["四川省住房和城乡建设厅"]["official_origin"] == (
        "https://jst.sc.gov.cn/"
    )
    assert campaign["贵州省能源局"]["official_origin"] == (
        "https://nyj.guizhou.gov.cn/"
    )
    assert "广联达" not in campaign
    assert "中国煤炭科工集团" not in campaign


def test_t31r_rejects_authority_escalation_unknown_compliance_or_fake_closure() -> None:
    payload = _load(MANIFEST)

    enabled = deepcopy(payload)
    enabled["sources"][0]["desired_enabled"] = True
    with pytest.raises(ValidationError):
        _validate(enabled)

    admitted = deepcopy(payload)
    admitted["sources"][0]["source_admission"] = "ADMITTED"
    with pytest.raises(ValidationError):
        _validate(admitted)

    promoted = deepcopy(payload)
    promoted["sources"][1]["streams"][0]["permitted_claim_bases"] = [
        "INDEPENDENT_VERIFICATION"
    ]
    with pytest.raises(ValidationError):
        _validate(promoted)

    unknown = deepcopy(payload)
    unknown["sources"][1]["streams"][0]["compliance"][0]["status"] = "UNKNOWN"
    with pytest.raises((AssertionError, ValidationError)):
        _validate(unknown)

    blocked_but_closed = deepcopy(payload)
    blocked_but_closed["sources"][1]["streams"][0]["blocker_codes"] = [
        "TERMS_UNKNOWN"
    ]
    with pytest.raises(ValidationError):
        _validate(blocked_but_closed)
