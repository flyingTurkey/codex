import csv
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "docs" / "codex-kit" / "assets" / "validation"
MANIFEST = VALIDATION / "t20r_cscec_xcmg_source_stream_discovery.json"
SCHEMA = VALIDATION / "t20r_cscec_xcmg_source_stream_discovery.schema.json"
ROLLOUT = VALIDATION / "civil_engineering_source_rollout_v2.json"
CAMPAIGN = VALIDATION / "civil_engineering_source_campaign_v2.json"
REGISTRY = ROOT / "docs" / "codex-kit" / "assets" / "source_registry.csv"


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
        assert stream["collection_url"] != stream["official_origin"]
        assert {item["check"] for item in stream["compliance"]} == {
            "PUBLIC_NETWORK",
            "REDIRECTS",
            "ROBOTS",
            "TERMS",
            "COPYRIGHT",
            "ACCESS_BOUNDARY",
            "PUBLIC_REACHABILITY",
        }
        assert all(item["status"] != "UNKNOWN" for item in stream["compliance"])


def test_t20r_manifest_matches_versioned_research_contract() -> None:
    _validate(_load(MANIFEST))


def test_t20r_replaces_sources_without_granting_runtime_authority() -> None:
    payload = _load(MANIFEST)

    assert payload["issue"] == 37
    assert payload["supersedes_issue"] == 21
    assert payload["parent_spec"] == 1
    assert {stream["source_code"] for stream in payload["streams"]} == {
        "ENT-002",
        "ENT-010",
    }
    assert all(stream["readiness"] == "BOUNDED" for stream in payload["streams"])
    assert all(stream["disposition"] == "ADMISSION_READY" for stream in payload["streams"])
    assert all(stream["desired_enabled"] is False for stream in payload["streams"])
    assert all(stream["source_admission"] is None for stream in payload["streams"])
    assert all(stream["actual_running"] is False for stream in payload["streams"])
    assert all(stream["pause_appended"] is False for stream in payload["streams"])
    assert all(stream["coverage_credit_granted"] is False for stream in payload["streams"])
    assert all(stream["attachments_allowed"] is False for stream in payload["streams"])
    assert all(stream["public_redistribution"] is False for stream in payload["streams"])


def test_t20r_locks_exact_collection_and_claim_boundaries() -> None:
    streams = {stream["source_code"]: stream for stream in _load(MANIFEST)["streams"]}

    cscec = streams["ENT-002"]
    assert cscec["collection_url"] == "https://www.cscec.com/xwzx_new/zqydt_new/"
    assert cscec["claim_basis"] == "PROJECT_FIRST_PARTY_RECORD"
    assert "党建" in cscec["excluded_topics"]
    assert "资本市场" in cscec["excluded_topics"]

    xcmg = streams["ENT-010"]
    assert xcmg["collection_url"] == "https://www.xcmg.com/case/case.htm"
    assert xcmg["claim_basis"] == "MANUFACTURER_CLAIM"
    assert xcmg["list_request"] == {
        "method": "POST",
        "url": "https://www.xcmg.com/ext/ajax_case.jsp",
        "form": {"flag": "case", "ids": "1,1,", "channelId": "22571"},
    }
    assert "ERP" in xcmg["excluded_topics"]
    assert "生产线" in xcmg["excluded_topics"]


def test_t20r_updates_canonical_registry_and_first_batch_mapping() -> None:
    with REGISTRY.open(encoding="utf-8", newline="") as source_file:
        registry = {row["source_id"]: row for row in csv.DictReader(source_file)}

    assert registry["ENT-002"]["name"] == "中国建筑"
    assert registry["ENT-010"]["name"] == "徐工集团"
    assert registry["ENT-010"]["status"] == "CANDIDATE"
    assert registry["ENT-010"]["enabled"] == "false"

    first_batch = _load(ROLLOUT)["batches"][0]["institutions"]
    assert len(first_batch) == 10
    assert "中国建筑" in first_batch
    assert "徐工集团" in first_batch
    assert "中国中铁" not in first_batch
    assert "三一集团" not in first_batch

    campaign = {item["institution"]: item for item in _load(CAMPAIGN)["sources"]}
    assert campaign["中国建筑"]["official_origin"] == "https://www.cscec.com/"
    assert campaign["徐工集团"]["official_origin"] == "https://www.xcmg.com/"
    assert "中国中铁" not in campaign
    assert "三一集团" not in campaign


def test_t20r_rejects_roots_runtime_claims_unknown_evidence_and_wrong_claim_basis() -> None:
    payload = _load(MANIFEST)

    root = deepcopy(payload)
    root["streams"][0]["collection_url"] = root["streams"][0]["official_origin"]
    with pytest.raises((ValidationError, AssertionError)):
        _validate(root)

    running = deepcopy(payload)
    running["streams"][1]["actual_running"] = True
    with pytest.raises(ValidationError):
        _validate(running)

    unknown = deepcopy(payload)
    unknown["streams"][0]["compliance"][0]["status"] = "UNKNOWN"
    with pytest.raises((ValidationError, AssertionError)):
        _validate(unknown)

    promoted = deepcopy(payload)
    promoted["streams"][1]["claim_basis"] = "INDEPENDENT_VERIFICATION"
    with pytest.raises(ValidationError):
        _validate(promoted)
