import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t23_sichuan_transport_source_stream_discovery.json"
)
SCHEMA = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t23_sichuan_transport_source_stream_discovery.schema.json"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(payload: dict[str, Any]) -> None:
    schema = _load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

    source = payload["source"]
    for stream in payload["streams"]:
        parsed = urlsplit(stream["collection_url"])
        assert parsed.scheme == "https"
        assert parsed.hostname in stream["allowed_hosts"]
        assert parsed.path not in ("", "/")
        assert "search" not in parsed.path.casefold()
        assert re.fullmatch(stream["collection_path_pattern"], parsed.path)
        assert stream["collection_url"] != source["official_origin"]
        assert all(
            urlsplit(observation["final_url"]).hostname in stream["allowed_hosts"]
            for observation in stream["http_observations"]
        )


def test_t23_manifest_matches_versioned_research_contract() -> None:
    _validate(_load(MANIFEST))


def test_t23_locks_one_source_and_four_bounded_streams_without_control_mutation() -> None:
    payload = _load(MANIFEST)

    assert payload["ticket"] == {
        "issue": 24,
        "parent_spec": 1,
        "blocked_by": [{"issue": 8, "state": "CLOSED"}],
        "closure_eligible": True,
    }
    assert payload["source"] == {
        "source_code": "GOV-015",
        "institution": "四川省交通运输厅",
        "official_origin": "https://jtt.sc.gov.cn/",
        "source_count_credit": 1,
        "registry_status": "CANDIDATE",
        "desired_enabled": False,
    }
    assert {stream["stream_key"] for stream in payload["streams"]} == {
        "SCJTT_TECH_INFORMATION",
        "SCJTT_CONSTRUCTION_UPDATES",
        "SCJTT_QUALITY_SUPERVISION",
        "SCJTT_SAFETY_SUPERVISION",
    }
    assert all(stream["readiness"] == "BOUNDED" for stream in payload["streams"])
    assert all(
        stream["disposition"] == "ADMISSION_READY" for stream in payload["streams"]
    )
    assert payload["control_state_mutations"] == {
        "desired_enabled_changed": False,
        "source_admission_written": False,
        "runtime_state_changed": False,
        "pause_appended": False,
        "real_admission_wave_executed": False,
        "coverage_credit_granted": False,
    }


def test_t23_saves_exact_collection_network_mime_frequency_and_filter_boundaries() -> None:
    payload = _load(MANIFEST)
    streams = {stream["stream_key"]: stream for stream in payload["streams"]}

    assert streams["SCJTT_TECH_INFORMATION"]["collection_url"] == (
        "https://jtt.sc.gov.cn/jtt/c101567/zfxxgk_list.shtml"
    )
    assert streams["SCJTT_CONSTRUCTION_UPDATES"]["collection_url"] == (
        "https://jtt.sc.gov.cn/jtt/c101544/zfxxgk_list.shtml"
    )
    assert streams["SCJTT_QUALITY_SUPERVISION"]["collection_url"] == (
        "https://jtt.sc.gov.cn/jtt/c102110/zhijian_list.shtml"
    )
    assert streams["SCJTT_SAFETY_SUPERVISION"]["collection_url"] == (
        "https://jtt.sc.gov.cn/jtt/c102111/zhijian_list.shtml"
    )

    for stream in streams.values():
        assert stream["allowed_hosts"] == ["jtt.sc.gov.cn"]
        assert stream["connector_type"] == "HTML_LIST_DETAIL"
        assert stream["expected_mime_types"] == ["text/html"]
        assert stream["poll_interval_minutes"] == 1440
        assert stream["rate_limit_requests_per_minute"] == 1
        assert stream["request_timeout_seconds"] == 10
        assert stream["max_redirects"] == 5
        assert stream["policy_version"].startswith("t23-")
        assert stream["content_relevance"] in {"DIRECT", "FILTERED"}
        assert stream["accepted_topics"]
        assert stream["excluded_topics"]
        assert stream["redistribution"] == "METADATA_EXCERPT_LINK_ONLY"
        assert stream["fulltext_redistribution_allowed"] is False

    assert "培训会" in streams["SCJTT_TECH_INFORMATION"]["excluded_topics"]
    assert "招标采购" in streams["SCJTT_CONSTRUCTION_UPDATES"]["excluded_topics"]
    assert "党建纪检" in streams["SCJTT_QUALITY_SUPERVISION"]["excluded_topics"]
    assert "道路运输经营" in streams["SCJTT_SAFETY_SUPERVISION"]["excluded_topics"]


def test_t23_preserves_point_in_time_compliance_and_restricted_copyright_evidence() -> None:
    payload = _load(MANIFEST)

    assert payload["verified_at"] == "2026-07-20T11:10:48+08:00"
    assert payload["network_verification"] == {
        "resolved_public_ips": ["28.0.0.69"],
        "public_network_safe": True,
        "https_redirects_observed": 0,
        "http_upgrade_observed": False,
        "https_only_collection_policy": True,
    }
    checks = {item["check"]: item for item in payload["compliance"]}
    assert set(checks) == {
        "PUBLIC_NETWORK",
        "REDIRECTS",
        "ROBOTS",
        "TERMS",
        "COPYRIGHT",
        "ACCESS_BOUNDARY",
        "PUBLIC_REACHABILITY",
    }
    assert checks["ROBOTS"]["http_status"] == 404
    assert checks["ROBOTS"]["result"] == "VERIFIED_NOT_PUBLISHED_NOT_PERMISSION"
    assert checks["TERMS"]["result"] == "VERIFIED_SITE_STATEMENT"
    assert checks["COPYRIGHT"]["result"] == "VERIFIED_RESTRICTED"
    assert "全文" in checks["COPYRIGHT"]["finding"]
    assert all(item["result"] != "UNKNOWN" for item in checks.values())


def test_t23_rejects_roots_search_single_documents_and_runtime_claims() -> None:
    payload = _load(MANIFEST)

    for invalid_url in (
        "https://jtt.sc.gov.cn/",
        "https://jtt.sc.gov.cn/jtt/search?q=bridge",
        "https://jtt.sc.gov.cn/jtt/c102111/2025/4/1/2c13fc4dba7f4a8e89086383bb32e18b.shtml",
    ):
        candidate = deepcopy(payload)
        candidate["streams"][0]["collection_url"] = invalid_url
        with pytest.raises((ValidationError, AssertionError)):
            _validate(candidate)

    enabled = deepcopy(payload)
    enabled["source"]["desired_enabled"] = True
    with pytest.raises(ValidationError):
        _validate(enabled)

    admitted = deepcopy(payload)
    admitted["streams"][0]["source_admission"] = {"decision": "ADMIT"}
    with pytest.raises(ValidationError):
        _validate(admitted)


def test_t23_defines_second_batch_w1_without_merging_jurisdictions() -> None:
    payload = _load(MANIFEST)

    assert payload["second_batch_w1"] == {
        "sichuan_transport": {
            "source_code": "GOV-015",
            "jurisdiction": "中国四川",
            "stream_keys": [
                "SCJTT_TECH_INFORMATION",
                "SCJTT_CONSTRUCTION_UPDATES",
                "SCJTT_QUALITY_SUPERVISION",
                "SCJTT_SAFETY_SUPERVISION",
            ],
        },
        "mem_accident_investigation": {
            "source_code": "GOV-007",
            "institution": "应急管理部",
            "jurisdiction": "中国全国",
            "collection_url": (
                "https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/index.shtml"
            ),
            "existing_research_only": True,
        },
        "cross_jurisdiction_fact_merge_allowed": False,
        "wave_admission_executed": False,
    }
