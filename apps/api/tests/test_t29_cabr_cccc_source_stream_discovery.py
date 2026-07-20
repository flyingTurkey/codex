import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from srbg_api.source_registry.source_stream_discovery import (
    CandidateMetadata,
    ClaimBasisPolicy,
    SourceResearchDisposition,
    StreamReadiness,
    T29DiscoveryManifest,
    record_discovery_dispositions,
)

ROOT = Path(__file__).parents[3]
MANIFEST_PATH = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t29_cabr_cccc_source_stream_discovery.json"
)


def _load_manifest() -> T29DiscoveryManifest:
    return T29DiscoveryManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_reuses_two_canonical_sources_without_granting_authority() -> None:
    manifest = _load_manifest()

    assert manifest.issue_number == 30
    assert manifest.parent_spec_number == 1
    assert {source.registry_code for source in manifest.sources} == {"RES-003", "ENT-001"}
    assert all(len(source.streams) == 1 for source in manifest.sources)
    assert all(source.desired_enabled is False for source in manifest.sources)

    cabr, cccc = manifest.sources
    assert cabr.institution == "中国建筑科学研究院"
    assert cabr.official_origin == "https://www.cabr.cn/"
    assert cccc.institution == "中国交建"
    assert cccc.official_origin == "https://www.ccccltd.cn/"
    assert "中国交通建设集团" in cccc.aliases

    streams = [source.streams[0] for source in manifest.sources]
    assert all(stream.actual_running is False for stream in streams)
    assert all(stream.source_admission is None for stream in streams)
    assert cabr.streams[0].readiness is StreamReadiness.CANDIDATE
    assert cabr.streams[0].disposition is SourceResearchDisposition.MANUAL_SHADOW
    assert set(cabr.streams[0].blocker_codes) == {
        "NO_CONTINUOUS_COLLECTION",
        "TERMS_PROHIBIT_COPYING",
    }
    assert cccc.streams[0].readiness is StreamReadiness.BOUNDED
    assert cccc.streams[0].disposition is SourceResearchDisposition.ADMISSION_READY
    assert cccc.streams[0].blocker_codes == ()


def test_manifest_saves_exact_collection_network_and_policy_boundaries() -> None:
    manifest = _load_manifest()

    for source in manifest.sources:
        stream = source.streams[0]
        assert stream.collection_url != source.official_origin
        assert stream.expected_mime_types == ("text/html",)
        assert stream.request_timeout_seconds == 10
        assert stream.max_redirects <= 5
        assert stream.rate_limit_requests_per_minute == 1
        assert stream.user_agent.startswith("SRBG-SourceResearch/")
        assert stream.policy_version.startswith("t29-")
        assert stream.allowed_hosts
        assert stream.allowed_path_patterns
        assert stream.verification.collection_get.status_code == 200
        assert stream.verification.detail_get.status_code == 200
        assert stream.verification.public_network_safe is True
        assert stream.verification.redirect_chain_safe is True
        assert stream.verification.collection_get.response_sha256 is None
        assert stream.verification.detail_get.response_sha256 is None
    cabr, cccc = manifest.sources
    assert cabr.streams[0].connector_type == "STATIC_HTML_MANUAL"
    assert cabr.streams[0].poll_interval_minutes is None
    assert cabr.streams[0].verification.terms_evidence.status.value == "BLOCKED"
    assert cabr.streams[0].verification.copyright_evidence.status.value == "BLOCKED"
    assert cccc.streams[0].connector_type == "HTML_LIST_DETAIL"
    assert cccc.streams[0].poll_interval_minutes == 1_440
    assert cccc.streams[0].verification.robots_evidence.http_status_code == 404
    assert cccc.streams[0].verification.robots_evidence.status.value == "VERIFIED"
    assert cccc.streams[0].verification.terms_evidence.status.value == "VERIFIED"
    assert cccc.streams[0].verification.copyright_evidence.status.value == "VERIFIED"


def test_claim_basis_keeps_research_project_statements_and_verification_distinct() -> None:
    cabr, cccc = _load_manifest().sources
    cabr_stream = cabr.streams[0]
    cccc_stream = cccc.streams[0]

    assert cabr_stream.claim_basis_policy is ClaimBasisPolicy.RESEARCH_CONCLUSION
    assert cabr_stream.allows_claim_basis(ClaimBasisPolicy.RESEARCH_CONCLUSION) is True
    assert cabr_stream.allows_claim_basis(ClaimBasisPolicy.PROJECT_FIRST_PARTY_RECORD) is False
    assert cabr_stream.allows_claim_basis(ClaimBasisPolicy.MANUFACTURER_CLAIM) is True
    assert cabr_stream.allows_claim_basis(ClaimBasisPolicy.INDEPENDENT_VERIFICATION) is False

    assert cccc_stream.claim_basis_policy is ClaimBasisPolicy.PROJECT_FIRST_PARTY_RECORD
    assert cccc_stream.allows_claim_basis(ClaimBasisPolicy.PROJECT_FIRST_PARTY_RECORD) is True
    assert cccc_stream.allows_claim_basis(ClaimBasisPolicy.MANUFACTURER_CLAIM) is True
    assert cccc_stream.allows_claim_basis(ClaimBasisPolicy.RESEARCH_CONCLUSION) is False
    assert cccc_stream.allows_claim_basis(ClaimBasisPolicy.INDEPENDENT_VERIFICATION) is False


@pytest.mark.parametrize(
    ("registry_code", "title", "body", "expected"),
    (
        ("RES-003", "建筑工程抗震韧性关键技术研究成果", "房屋建筑设计与安全监测", True),
        ("RES-003", "集团召开年度党建工作会议", "部署品牌宣传和人才招聘", False),
        ("ENT-001", "跨海大桥主桥顺利合龙", "项目完成桥梁施工关键节点", True),
        ("ENT-001", "中国交建发布年度经营业绩", "资本市场与党建工作取得成效", False),
    ),
)
def test_stream_prefilter_keeps_only_in_scope_research_or_project_facts(
    registry_code: str,
    title: str,
    body: str,
    expected: bool,
) -> None:
    source = next(
        source for source in _load_manifest().sources if source.registry_code == registry_code
    )

    assert source.streams[0].accepts(CandidateMetadata(title=title, body=body)) is expected


def test_unknown_compliance_cannot_be_promoted_to_admission_ready() -> None:
    candidate = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    candidate["sources"][1]["streams"][0]["verification"]["robots_evidence"]["status"] = (
        "UNKNOWN"
    )

    with pytest.raises(ValidationError, match="ADMISSION_READY"):
        T29DiscoveryManifest.model_validate(candidate)


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

    assert [(row[0], row[2]) for row in repository.recorded] == [
        ("RES-003", SourceResearchDisposition.MANUAL_SHADOW),
        ("ENT-001", SourceResearchDisposition.ADMISSION_READY),
    ]
    assert all(len(row[3]) == 64 for row in repository.recorded)
