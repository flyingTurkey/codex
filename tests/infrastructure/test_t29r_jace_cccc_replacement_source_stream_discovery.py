import csv
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "docs" / "codex-kit" / "assets" / "validation"
MANIFEST = VALIDATION / "t29r_jace_cccc_source_stream_discovery.json"
SCHEMA = VALIDATION / "t29r_jace_cccc_source_stream_discovery.schema.json"
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


def test_t29r_manifest_matches_versioned_replacement_contract() -> None:
    _validate(_load(MANIFEST))


def test_t29r_supersedes_only_cabr_without_granting_runtime_authority() -> None:
    payload = _load(MANIFEST)

    assert payload["issue"] == 39
    assert payload["supersedes_issue"] == 30
    assert payload["parent_spec"] == 1
    assert {stream["source_code"] for stream in payload["streams"]} == {
        "RES-013",
        "ENT-001",
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


def test_t29r_locks_jace_current_issue_api_and_reuses_cccc_stream() -> None:
    streams = {stream["source_code"]: stream for stream in _load(MANIFEST)["streams"]}

    jace = streams["RES-013"]
    assert jace["official_origin"] == "https://jace.chd.edu.cn/"
    assert jace["collection_url"] == (
        "https://jace.chd.edu.cn/rc-pub/front/front-period/"
        "getFirstTwoPeriods?publicationIndexId=1474"
    )
    assert parse_qs(urlsplit(jace["collection_url"]).query) == {
        "publicationIndexId": ["1474"]
    }
    assert jace["detail_url_template"] == (
        "https://jace.chd.edu.cn/rc-pub/front/front-article/"
        "getArticlesByPeriodicalIdGroupByColumn/{period_id}?size=50&showCover=true"
    )
    assert jace["query_contract"] == {
        "collection": {"publicationIndexId": "1474"},
        "detail": {"size_max": 50, "showCover": "true"},
    }
    assert jace["connector_type"] == "JSON_CURRENT_ISSUE"
    assert jace["expected_mime_types"] == ["application/json"]
    assert jace["claim_basis"] == "RESEARCH_CONCLUSION"
    assert jace["permitted_claim_bases"] == ["RESEARCH_CONCLUSION"]
    assert "期刊公告" in jace["excluded_topics"]
    assert "纯材料化学且无工程对象" in jace["excluded_topics"]

    cccc = streams["ENT-001"]
    assert cccc["institution"] == "中国交建"
    assert cccc["aliases"] == [
        "中国交通建设集团",
        "中国交通建设集团有限公司",
        "中国交通建设股份有限公司",
    ]
    assert cccc["collection_url"] == "https://www.ccccltd.cn/news/jcxw/jx/"
    assert cccc["claim_basis"] == "PROJECT_FIRST_PARTY_RECORD"
    assert "经营业绩" in cccc["excluded_topics"]


def test_t29r_updates_registry_rollout_and_campaign_without_changing_source_count() -> None:
    with REGISTRY.open(encoding="utf-8", newline="") as source_file:
        registry = {row["source_id"]: row for row in csv.DictReader(source_file)}

    assert registry["RES-013"]["name"] == "建筑科学与工程学报"
    assert registry["RES-013"]["base_url"] == "https://jace.chd.edu.cn/"
    assert registry["RES-013"]["status"] == "CANDIDATE"
    assert registry["RES-013"]["enabled"] == "false"

    rollout = _load(ROLLOUT)
    assert sum(batch["target_count"] for batch in rollout["batches"]) == 30
    second_batch = rollout["batches"][1]["institutions"]
    assert len(second_batch) == 10
    assert "建筑科学与工程学报" in second_batch
    assert "中国建筑科学研究院" not in second_batch
    assert "中国交通建设集团" in second_batch

    campaign = {item["institution"]: item for item in _load(CAMPAIGN)["sources"]}
    assert len(campaign) == 20
    assert campaign["建筑科学与工程学报"]["official_origin"] == "https://jace.chd.edu.cn/"
    assert campaign["中国交通建设集团"]["official_origin"] == "https://www.ccccltd.cn/"
    assert "中国建筑科学研究院" not in campaign


def test_t29r_fails_closed_on_unknown_compliance_runtime_or_claim_promotion() -> None:
    payload = _load(MANIFEST)

    unknown = deepcopy(payload)
    unknown["streams"][0]["compliance"][0]["status"] = "UNKNOWN"
    with pytest.raises((ValidationError, AssertionError)):
        _validate(unknown)

    running = deepcopy(payload)
    running["streams"][0]["actual_running"] = True
    with pytest.raises(ValidationError):
        _validate(running)

    promoted = deepcopy(payload)
    promoted["streams"][0]["claim_basis"] = "INDEPENDENT_VERIFICATION"
    with pytest.raises(ValidationError):
        _validate(promoted)

    broadened = deepcopy(payload)
    broadened["streams"][0]["query_contract"]["detail"]["size_max"] = 500
    with pytest.raises(ValidationError):
        _validate(broadened)
