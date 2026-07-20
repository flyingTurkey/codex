import json
from copy import deepcopy
from pathlib import Path
from typing import Any
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
    / "t18_source_stream_discovery_w4.json"
)
SCHEMA = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t18_source_stream_discovery_w4.schema.json"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(payload: dict[str, Any]) -> None:
    schema = _load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

    for stream in payload["streams"]:
        parsed = urlsplit(stream["collection_url"])
        assert parsed.scheme == "https"
        assert parsed.hostname in stream["allowed_hosts"]
        required_query = stream["collection_boundary"]["required_query"]
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        assert all(query.get(key) == value for key, value in required_query.items())
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


def test_t18_manifest_matches_versioned_research_contract() -> None:
    _validate(_load(MANIFEST))


def test_t18_locks_two_bounded_streams_without_runtime_authority() -> None:
    payload = _load(MANIFEST)

    assert payload["issue"] == 19
    assert payload["rule_version"] == "t18-stream-discovery-w4-v1"
    assert {stream["source_code"] for stream in payload["streams"]} == {
        "GOV-014",
        "RES-004",
    }
    assert {stream["institution"] for stream in payload["streams"]} == {
        "中国民用航空局",
        "中国公路学报",
    }
    assert all(stream["readiness"] == "BOUNDED" for stream in payload["streams"])
    assert all(
        stream["disposition"] == "ADMISSION_READY" for stream in payload["streams"]
    )
    assert all(stream["source_status"] == "CANDIDATE" for stream in payload["streams"])
    assert all(stream["desired_enabled"] is False for stream in payload["streams"])
    assert all(stream["source_admission"] is None for stream in payload["streams"])
    assert all(stream["actual_running"] is False for stream in payload["streams"])
    assert all(stream["pause_appended"] is False for stream in payload["streams"])
    assert all(stream["coverage_credit_granted"] is False for stream in payload["streams"])


def test_t18_uses_exact_collection_and_detail_boundaries() -> None:
    streams = {stream["source_code"]: stream for stream in _load(MANIFEST)["streams"]}

    caac = streams["GOV-014"]
    assert caac["collection_url"] == (
        "https://www.caac.gov.cn/was5/web/search?page=1&channelid=211383&fl=60"
    )
    assert caac["allowed_hosts"] == ["www.caac.gov.cn"]
    assert caac["connector_type"] == "LIST_DETAIL"
    assert caac["collection_boundary"]["required_query"] == {
        "channelid": "211383",
        "fl": "60",
    }
    assert "旅游消费" in caac["excluded_topics"]
    assert "航班经营" in caac["excluded_topics"]

    journal = streams["RES-004"]
    assert journal["collection_url"] == "https://zgglxb.chd.edu.cn/CN/current"
    assert journal["allowed_hosts"] == ["zgglxb.chd.edu.cn"]
    assert journal["connector_type"] == "LIST_DETAIL"
    assert journal["claim_basis"] == "RESEARCH_CONCLUSION"
    assert journal["redistribution"] == "METADATA_ABSTRACT_LINK_ONLY"
    assert journal["fulltext_redistribution_allowed"] is False
    assert "RSS" in journal["compliance"][-1]["finding"]
    assert "2023" in journal["compliance"][-1]["finding"]


def test_t18_rejects_runtime_claims_roots_single_pages_and_unknown_evidence() -> None:
    payload = _load(MANIFEST)

    enabled = deepcopy(payload)
    enabled["streams"][0]["desired_enabled"] = True
    with pytest.raises(ValidationError):
        _validate(enabled)

    root = deepcopy(payload)
    root["streams"][0]["collection_url"] = "https://www.caac.gov.cn/"
    with pytest.raises(ValidationError):
        _validate(root)

    single_document = deepcopy(payload)
    single_document["streams"][1]["collection_url"] = (
        "https://zgglxb.chd.edu.cn/CN/10.19721/j.cnki.1001-7372.2026.06.001"
    )
    with pytest.raises(ValidationError):
        _validate(single_document)

    unknown = deepcopy(payload)
    unknown["streams"][1]["compliance"][0]["status"] = "UNKNOWN"
    with pytest.raises(ValidationError):
        _validate(unknown)
