import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from srbg_api.source_registry.source_stream_discovery import (
    CandidateMetadata,
    DiscoveryManifest,
    SourceResearchDisposition,
    StreamReadiness,
    record_discovery_dispositions,
)

ROOT = Path(__file__).parents[3]
MANIFEST_PATH = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t16_mwr_nea_source_stream_discovery.json"
)


def _load_manifest() -> DiscoveryManifest:
    return DiscoveryManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_keeps_two_institutions_and_two_streams_research_only() -> None:
    manifest = _load_manifest()

    assert manifest.issue_number == 17
    assert {source.registry_code for source in manifest.sources} == {"GOV-MWR", "GOV-NEA"}
    assert [len(source.streams) for source in manifest.sources] == [1, 1]
    assert all(source.desired_enabled is False for source in manifest.sources)
    streams = tuple(stream for source in manifest.sources for stream in source.streams)
    assert all(stream.readiness is StreamReadiness.BOUNDED for stream in streams)
    assert all(
        stream.disposition is SourceResearchDisposition.ADMISSION_READY
        for stream in streams
    )
    assert all(stream.blocker_codes == () for stream in streams)
    assert all(stream.source_admission is None for stream in streams)
    assert all(stream.actual_running is False for stream in streams)


def test_manifest_saves_exact_collection_network_and_policy_boundaries() -> None:
    manifest = _load_manifest()
    streams = tuple(stream for source in manifest.sources for stream in source.streams)

    assert {stream.stream_key for stream in streams} == {
        "mwr-engineering-service-notices",
        "nea-coal-department-updates",
    }
    for stream in streams:
        assert stream.expected_mime_types == ("text/html",)
        assert stream.poll_interval_minutes == 1_440
        assert stream.request_timeout_seconds == 10
        assert stream.max_redirects == 0
        assert stream.rate_limit_requests_per_minute == 1
        assert stream.policy_version.startswith("t16-")
        assert stream.verification.verified_at.isoformat() == "2026-07-20T03:30:00+00:00"
        assert stream.verification.collection_get.status_code == 200
        assert stream.verification.public_network_safe is True
        assert stream.verification.redirect_chain_safe is True
        assert stream.verification.robots_evidence.status.value == "VERIFIED"
        assert stream.verification.terms_evidence.status.value == "VERIFIED"
        assert stream.verification.copyright_evidence.status.value == "VERIFIED"

    water = manifest.sources[0]
    assert water.institution == "中华人民共和国水利部"
    assert water.streams[0].collection_url == (
        "https://spjc.mwr.gov.cn/spjc/hallg/notices.jsp"
    )
    assert water.streams[0].connector_type == "HTML_LIST_METADATA_LINK"
    assert water.streams[0].verification.detail_get is None
    energy = manifest.sources[1].streams[0]
    assert energy.collection_url == "https://www.nea.gov.cn/sjzz/mts/index.htm"
    assert energy.allowed_hosts == ("www.nea.gov.cn",)
    assert energy.connector_type == "HTML_LIST_DETAIL"


def test_metadata_only_or_unknown_policy_stream_cannot_bypass_evidence() -> None:
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    water: dict[str, Any] = json.loads(json.dumps(base))
    water_stream = water["sources"][0]["streams"][0]
    water_stream["connector_type"] = "HTML_LIST_DETAIL"
    with pytest.raises(ValidationError, match="detail observation"):
        DiscoveryManifest.model_validate(water)

    energy: dict[str, Any] = json.loads(json.dumps(base))
    energy_stream = energy["sources"][1]["streams"][0]
    energy_stream["verification"]["robots_evidence"]["status"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="ADMISSION_READY"):
        DiscoveryManifest.model_validate(energy)


def test_root_search_or_single_article_cannot_replace_a_collection() -> None:
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    invalid_urls = (
        "https://www.nea.gov.cn/",
        "https://www.nea.gov.cn/search?q=煤矿智能化",
        "https://www.nea.gov.cn/20260209/ea5b9bede4764590bff3c62244f6f57c/c.html",
    )
    for invalid_url in invalid_urls:
        candidate: dict[str, Any] = json.loads(json.dumps(base))
        candidate["sources"][1]["streams"][0]["collection_url"] = invalid_url
        with pytest.raises(ValidationError):
            DiscoveryManifest.model_validate(candidate)


@pytest.mark.parametrize(
    ("stream_key", "title", "body", "expected"),
    (
        (
            "mwr-engineering-service-notices",
            "重大水利工程隧洞全线贯通",
            "工程建设进入验收阶段",
            True,
        ),
        (
            "mwr-engineering-service-notices",
            "全国节水宣传周启动",
            "发布机关行政工作安排",
            False,
        ),
        (
            "mwr-engineering-service-notices",
            "成熟适用水利科技成果推广清单公示",
            "水利工程数字化建设技术进入推广清单",
            True,
        ),
        (
            "nea-coal-department-updates",
            "煤矿智能化建设试点名单发布",
            "矿山安全监测装备进入建设阶段",
            True,
        ),
        (
            "nea-coal-department-updates",
            "煤炭司答复政协提案",
            "召开培训会议并分析煤炭价格",
            False,
        ),
    ),
)
def test_prefilter_keeps_only_direct_domain_lifecycle_facts(
    stream_key: str,
    title: str,
    body: str,
    expected: bool,
) -> None:
    manifest = _load_manifest()
    stream = next(
        stream
        for source in manifest.sources
        for stream in source.streams
        if stream.stream_key == stream_key
    )

    assert stream.accepts(CandidateMetadata(title=title, body=body)) is expected


@pytest.mark.asyncio
async def test_discovery_records_only_two_research_dispositions() -> None:
    class ResearchOnlyRepository:
        def __init__(self) -> None:
            self.recorded: list[tuple[str, str, SourceResearchDisposition, str]] = []

        async def record_research_disposition(
            self,
            *,
            source_registry_code: str,
            stream_key: str,
            disposition: SourceResearchDisposition,
            research_sha256: str,
        ) -> None:
            self.recorded.append((source_registry_code, stream_key, disposition, research_sha256))

    repository = ResearchOnlyRepository()
    await record_discovery_dispositions(_load_manifest(), repository)

    assert [(row[0], row[1], row[2]) for row in repository.recorded] == [
        (
            "GOV-MWR",
            "mwr-engineering-service-notices",
            SourceResearchDisposition.ADMISSION_READY,
        ),
        ("GOV-NEA", "nea-coal-department-updates", SourceResearchDisposition.ADMISSION_READY),
    ]
    assert all(len(row[3]) == 64 for row in repository.recorded)
