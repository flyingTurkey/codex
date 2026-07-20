import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from srbg_api.source_registry.t27_source_stream_discovery import (
    CandidateMetadata,
    ClaimBasisPolicy,
    DiscoveryManifest,
    EngineeringObject,
    SourceResearchDisposition,
    StreamReadiness,
    qualifies_tunnel_gas_monitoring,
    record_discovery_dispositions,
)

ROOT = Path(__file__).parents[3]
MANIFEST_PATH = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t27_chts_tunnel_construction_source_stream_discovery.json"
)


def _load_manifest() -> DiscoveryManifest:
    return DiscoveryManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_keeps_two_institutions_and_research_authority_separate() -> None:
    manifest = _load_manifest()

    assert manifest.issue_number == 28
    assert manifest.parent_spec_number == 1
    assert {source.registry_code for source in manifest.sources} == {"RES-001", "RES-005"}
    assert len(manifest.sources) == 2
    assert all(len(source.streams) == 1 for source in manifest.sources)
    assert all(source.desired_enabled is False for source in manifest.sources)
    streams = tuple(stream for source in manifest.sources for stream in source.streams)
    assert all(stream.source_admission is None for stream in streams)
    assert all(stream.actual_running is False for stream in streams)
    assert all(stream.pause_appended is False for stream in streams)
    assert all(stream.coverage_credit_granted is False for stream in streams)


def test_manifest_records_truthful_closure_state_for_each_institution() -> None:
    manifest = _load_manifest()
    chts, journal = manifest.sources

    assert chts.institution == "中国公路学会"
    assert chts.streams[0].readiness is StreamReadiness.BOUNDED
    assert chts.streams[0].disposition is SourceResearchDisposition.ADMISSION_READY
    assert chts.streams[0].blocker_codes == ()

    assert journal.institution == "隧道建设\uff08中英文\uff09"
    assert journal.streams[0].readiness is StreamReadiness.BOUNDED
    journal_stream = journal.streams[0]
    assert journal_stream.disposition is SourceResearchDisposition.ADMISSION_READY
    assert journal_stream.blocker_codes == ()
    assert journal_stream.collection_url == "https://c.wanfangdata.com.cn/magazine/sdjs"
    assert journal_stream.allowed_hosts == (
        "c.wanfangdata.com.cn",
        "d.wanfangdata.com.cn",
    )
    assert manifest.closure_eligible is True


def test_streams_save_exact_collection_network_connector_and_policy_boundaries() -> None:
    manifest = _load_manifest()

    for source in manifest.sources:
        stream = source.streams[0]
        assert stream.collection_url != source.official_origin
        assert stream.collection_path_pattern
        assert stream.allowed_hosts
        assert stream.allowed_path_patterns
        assert stream.connector_type in {"DYNAMIC_HTML_LIST_DETAIL", "HTML_CURRENT_ISSUE_DETAIL"}
        assert stream.expected_mime_types == ("text/html",)
        assert 1_440 <= stream.poll_interval_minutes <= 10_080
        assert stream.request_timeout_seconds == 10
        assert stream.max_redirects == 5
        assert stream.rate_limit_requests_per_minute == 1
        assert stream.user_agent.startswith("SRBG-SourceResearch/")
        assert stream.policy_version.startswith("t27-")
        assert stream.verification.verified_at.date().isoformat() == "2026-07-20"
        assert stream.verification.verified_at.utcoffset() is not None
        assert stream.verification.resolved_public_ips
        assert stream.verification.collection_get.status_code == 200
        assert len(stream.verification.collection_get.response_sha256) == 64


def test_root_search_and_single_documents_cannot_impersonate_a_stream() -> None:
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for invalid_url in (
        "https://www.chts.cn/",
        "https://www.chts.cn/search?q=bridge",
        "https://www.chts.cn/cgtg/CGTGTZ/art/2025/art_a1c8e57396ea4fd687a64bd2792048de.html",
    ):
        candidate: dict[str, Any] = json.loads(json.dumps(base))
        candidate["sources"][0]["streams"][0]["collection_url"] = invalid_url
        with pytest.raises(ValidationError):
            DiscoveryManifest.model_validate(candidate)


def test_admission_ready_fails_closed_on_unknown_compliance_or_unsafe_network() -> None:
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    unknown_terms: dict[str, Any] = json.loads(json.dumps(base))
    unknown_terms["sources"][0]["streams"][0]["verification"]["terms_evidence"][
        "status"
    ] = "UNKNOWN"
    with pytest.raises(ValidationError, match="ADMISSION_READY"):
        DiscoveryManifest.model_validate(unknown_terms)

    unsafe_network: dict[str, Any] = json.loads(json.dumps(base))
    unsafe_network["sources"][0]["streams"][0]["verification"]["public_network_safe"] = False
    with pytest.raises(ValidationError, match="ADMISSION_READY"):
        DiscoveryManifest.model_validate(unsafe_network)


def test_private_dns_and_redirect_escape_are_rejected() -> None:
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    private_dns: dict[str, Any] = json.loads(json.dumps(base))
    private_dns["sources"][0]["streams"][0]["verification"]["resolved_public_ips"] = [
        "127.0.0.1"
    ]
    with pytest.raises(ValidationError, match="public"):
        DiscoveryManifest.model_validate(private_dns)

    redirect_escape: dict[str, Any] = json.loads(json.dumps(base))
    redirect_escape["sources"][0]["streams"][0]["verification"]["detail_get"][
        "final_url"
    ] = "https://example.com/cgtg/CGTGTZ/art/2025/example.html"
    with pytest.raises(ValidationError, match="redirect"):
        DiscoveryManifest.model_validate(redirect_escape)


@pytest.mark.parametrize(
    ("title", "body", "expected"),
    (
        (
            "中国公路学会公布公路交通智能装备科技成果入库名单",
            "成果直接用于高速公路施工与养护",
            True,
        ),
        ("关于召开智慧公路成果交流会的通知", "会议报名与酒店安排", False),
        ("学会会员代表大会顺利召开", "会员活动与理事会换届", False),
        ("综合新闻\uff1a行业热点一周回顾", "没有实质工程新事实", False),
    ),
)
def test_chts_prefilter_excludes_promotion_membership_and_general_news(
    title: str,
    body: str,
    expected: bool,
) -> None:
    stream = _load_manifest().sources[0].streams[0]

    assert stream.accepts(CandidateMetadata(title=title, body=body)) is expected


def test_journal_projection_is_limited_to_bibliography_abstract_and_original_link() -> None:
    journal = _load_manifest().sources[1].streams[0]

    assert journal.claim_basis_policy is ClaimBasisPolicy.RESEARCH_CONCLUSION
    assert journal.public_full_text_redistribution is False
    assert journal.reader_fields == (
        "BIBLIOGRAPHIC_METADATA",
        "PUBLISHED_ABSTRACT",
        "ORIGINAL_LINK",
    )
    assert journal.allows_claim_basis(ClaimBasisPolicy.RESEARCH_CONCLUSION) is True
    assert journal.allows_claim_basis(ClaimBasisPolicy.AUTHORITY_FINDING) is False
    assert journal.verification.collection_get.url.startswith(
        "https://c.wanfangdata.com.cn/magazine/"
    )
    assert journal.verification.detail_get.url == (
        "https://d.wanfangdata.com.cn/periodical/sdjs202605001"
    )
    assert journal.verification.transport_evidence.certificate_valid is True


@pytest.mark.parametrize(
    ("objects", "expected"),
    (
        ((EngineeringObject.TUNNEL, EngineeringObject.HIGHWAY), True),
        ((EngineeringObject.TUNNEL, EngineeringObject.RAILWAY), True),
        ((EngineeringObject.TUNNEL,), False),
        ((EngineeringObject.TUNNEL, EngineeringObject.MINING), False),
        ((EngineeringObject.MINING,), False),
    ),
)
def test_tunnel_gas_facet_requires_transport_tunnel_combination(
    objects: tuple[EngineeringObject, ...],
    expected: bool,
) -> None:
    assert qualifies_tunnel_gas_monitoring(objects) is expected


@pytest.mark.asyncio
async def test_discovery_records_only_research_dispositions() -> None:
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
        ("RES-001", "chts-engineering-results", SourceResearchDisposition.ADMISSION_READY),
        (
            "RES-005",
            "tunnel-construction-current-issue",
            SourceResearchDisposition.ADMISSION_READY,
        ),
    ]
    assert all(len(row[3]) == 64 for row in repository.recorded)
