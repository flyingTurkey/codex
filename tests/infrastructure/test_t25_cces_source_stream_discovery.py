import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t25_cces_source_stream_discovery.json"
)
SCHEMA = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t25_cces_source_stream_discovery.schema.json"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(payload: dict[str, Any]) -> None:
    schema = _load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def test_t25_manifest_matches_the_versioned_research_contract() -> None:
    _validate(_load(MANIFEST))


def test_t25_closes_only_after_a_secure_public_platform_replaces_plaintext() -> None:
    payload = _load(MANIFEST)

    assert payload["ticket"] == {
        "issue": 26,
        "parent_spec": 1,
        "blocked_by": [{"issue": 8, "state": "CLOSED"}],
        "closure_eligible": True,
    }
    assert payload["research_outcome"] == {
        "stream_readiness": "BOUNDED",
        "source_research_disposition": "ADMISSION_READY",
        "admission_ready": True,
        "blocking_reason_codes": [],
    }
    assert payload["control_state_mutations"] == {
        "desired_enabled_changed": False,
        "source_admission_written": False,
        "runtime_state_changed": False,
        "pause_appended": False,
        "real_collection_executed": False,
    }


def test_t25_keeps_two_bounded_streams_as_one_disabled_source() -> None:
    payload = _load(MANIFEST)
    source = payload["source"]
    streams = payload["streams"]

    assert source == {
        "source_code": "RES-011",
        "institution": "中国土木工程学会",
        "official_origin": "https://www.cces.net.cn/",
        "source_count_credit": 1,
        "registry_status": "CANDIDATE",
        "desired_enabled": False,
    }
    assert len(streams) == 2
    assert {stream["stream_id"] for stream in streams} == {
        "RES-011-STANDARD-RELEASES",
        "RES-011-ZHANTIANYOU-AWARDS",
    }
    assert all(stream["stream_readiness"] == "BOUNDED" for stream in streams)
    dispositions = {
        stream["stream_id"]: stream["source_research_disposition"]
        for stream in streams
    }
    assert dispositions == {
        "RES-011-STANDARD-RELEASES": "ADMISSION_READY",
        "RES-011-ZHANTIANYOU-AWARDS": "BOUNDARY_DISCOVERY",
    }
    assert all(stream["source_admission"] is None for stream in streams)
    assert all(stream["actual_running"] is False for stream in streams)
    assert all(stream["pause_appended"] is False for stream in streams)
    assert all(stream["coverage_credit_granted"] is False for stream in streams)


def test_t25_saves_exact_collection_network_mime_frequency_and_policy_boundaries() -> None:
    streams = {stream["stream_id"]: stream for stream in _load(MANIFEST)["streams"]}

    standards = streams["RES-011-STANDARD-RELEASES"]
    assert standards["collection_url"] == (
        "https://www.ttbz.org.cn/standard.html#org_"
        "bHFxbDM4aDZ6YTR3NzN0ZzBmYWp1NnNraml1YjhjYg=="
    )
    assert standards["collection_path_pattern"] == r"^/standard\.html$"
    assert standards["api_url"] == (
        "https://www.ttbz.org.cn/cms-proxy/ms/portal/standardInfo/"
        "getPortalStandardList"
    )
    assert standards["request_method"] == "POST"
    assert standards["request_body"] == {
        "pageNo": 1,
        "pageSize": 20,
        "organUniqueId": "lqql38h6za4w73tg0faju6skjiub8cb",
        "standardStatus": 1,
    }
    assert standards["detail_path_pattern"] == (
        r"^/standardDetail/[a-z0-9]{31}\.html$"
    )
    assert standards["allowed_hosts"] == ["www.ttbz.org.cn"]
    assert standards["connector_type"] == "JSON_POST_FILTER_HTML_DETAIL"
    assert standards["expected_mime_types"] == ["application/json", "text/html"]
    assert standards["source_research_disposition"] == "ADMISSION_READY"
    assert standards["blocking_reason_codes"] == []

    awards = streams["RES-011-ZHANTIANYOU-AWARDS"]
    assert awards["collection_url"] == "http://cces.net.cn/html/tm/29/38/38.html"
    assert awards["detail_path_pattern"] == (
        r"^/html/tm/29/38/(?:67|68|599|615)/content/[0-9]+\.html$"
    )
    assert awards["allowed_hosts"] == ["cces.net.cn"]
    assert awards["connector_type"] == "HTML_LIST_DETAIL"
    assert awards["expected_mime_types"] == ["text/html"]
    assert awards["source_research_disposition"] == "BOUNDARY_DISCOVERY"
    assert awards["blocking_reason_codes"] == ["HTTPS_UNAVAILABLE"]

    for stream in streams.values():
        assert stream["poll_interval_minutes"] == 1440
        assert stream["minimum_request_interval_seconds"] == 15
        assert stream["maximum_list_pages_per_run"] == 3
        assert stream["request_timeout_seconds"] == 10
        assert stream["max_redirects"] == 5
        assert stream["frequency_authorized"] is False
        assert stream["policy_version"] == "t25-cces-source-stream-discovery-v2"


def test_t25_records_replacement_compliance_without_treating_metadata_as_fulltext() -> None:
    payload = _load(MANIFEST)
    checks = {item["check"]: item for item in payload["verification"]["checks"]}

    assert set(checks) == {
        "PUBLIC_NETWORK",
        "REDIRECTS",
        "TLS",
        "ROBOTS",
        "TERMS",
        "COPYRIGHT",
        "ACCESS_BOUNDARY",
        "PUBLIC_REACHABILITY",
    }
    assert checks["PUBLIC_NETWORK"]["status"] == "VERIFIED_PUBLIC"
    assert checks["TLS"]["status"] == "VERIFIED_VALID"
    assert checks["ROBOTS"]["status"] == "VERIFIED_ALLOWED"
    assert checks["TERMS"]["status"] == "VERIFIED_PUBLIC_SERVICE_SCOPE"
    assert checks["COPYRIGHT"]["status"] == "VERIFIED_METADATA_ONLY"
    assert payload["verification"]["resolved_public_ips"] == ["28.0.0.98"]
    assert payload["replacement"] == {
        "superseded_blocker": "HTTPS_UNAVAILABLE",
        "superseded_collection_url": (
            "http://cces.net.cn/html/tm/98/102/102.html"
        ),
        "replacement_operator": "中国标准化研究院",
        "replacement_platform": "全国团体标准信息平台",
        "replacement_stream_id": "RES-011-STANDARD-RELEASES",
        "publisher_identity": "中国土木工程学会",
    }
    assert all(
        observation["status_code"] == 200
        and observation["redirect_count"] == 0
        and len(observation["response_sha256"]) == 64
        for observation in payload["verification"]["http_observations"]
    )


def test_t25_excludes_roots_search_single_pages_and_non_engineering_association_noise() -> None:
    payload = _load(MANIFEST)
    rejected = {candidate["kind"]: candidate for candidate in payload["rejected_candidates"]}

    assert rejected["ROOT"]["url"] == "http://cces.net.cn/html/tm/"
    assert rejected["SEARCH"]["selected_as_stream"] is False
    assert rejected["SINGLE_DOCUMENT"]["selected_as_stream"] is False
    assert rejected["ACADEMIC_RESULTS_STALE"]["selected_as_stream"] is False
    assert rejected["CONFERENCE_PROMOTION"]["selected_as_stream"] is False

    for stream in payload["streams"]:
        assert "党建" in stream["excluded_topics"]
        assert "会议宣传" in stream["excluded_topics"]
        assert "会员活动" in stream["excluded_topics"]
        assert stream["fulltext_redistribution_allowed"] is False


def test_t25_preserves_association_claim_basis_without_authority_promotion() -> None:
    streams = _load(MANIFEST)["streams"]

    assert all(stream["claim_basis"] == "PROJECT_FIRST_PARTY_RECORD" for stream in streams)
    assert all(stream["authority_finding_allowed"] is False for stream in streams)
    assert all(stream["independent_verification_allowed"] is False for stream in streams)
    assert all(
        stream["redistribution"] == "METADATA_NECESSARY_EXCERPT_ORIGINAL_LINK_ONLY"
        for stream in streams
    )


def test_t25_names_the_existing_national_standards_metadata_candidate_for_w2() -> None:
    pair = _load(MANIFEST)["w2_pair"]

    assert pair == {
        "wave": "SECOND_BATCH_W2",
        "existing_stream_id": "GOV-008-STANDARD-METADATA-CANDIDATE",
        "institution": "全国标准信息公共服务平台",
        "collection_entry": "https://std.samr.gov.cn/search/std",
        "existing_research_ref": (
            "docs/research/2026-07-19-civil-engineering-authoritative-"
            "source-expansion.md#s05-全国标准信息公共服务平台"
        ),
        "research_repeated": False,
        "source_admission_granted": False,
    }


def test_t25_contract_rejects_runtime_or_replacement_boundary_forgery() -> None:
    payload = _load(MANIFEST)

    mutations: list[tuple[list[str | int], Any]] = [
        (["ticket", "closure_eligible"], False),
        (["research_outcome", "source_research_disposition"], "BOUNDARY_DISCOVERY"),
        (["research_outcome", "admission_ready"], False),
        (["source", "desired_enabled"], True),
        (["streams", 0, "source_admission"], "ADMITTED"),
        (["streams", 0, "actual_running"], True),
        (["streams", 0, "pause_appended"], True),
        (["streams", 0, "coverage_credit_granted"], True),
        (["verification", "checks", 2, "status"], "BLOCKED"),
        (["streams", 0, "allowed_hosts"], ["cces.net.cn"]),
        (["streams", 0, "request_body", "organUniqueId"], "different-org"),
        (["verification", "http_observations", 3, "method"], "GET"),
        (["verification", "http_observations", 0, "content_type"], "application/json"),
    ]
    for path, value in mutations:
        candidate = deepcopy(payload)
        cursor: Any = candidate
        for part in path[:-1]:
            cursor = cursor[part]
        cursor[path[-1]] = value
        with pytest.raises(ValidationError):
            _validate(candidate)
