import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from srbg_api.source_registry.source_stream_discovery import (
    CandidateMetadata,
    ClaimBasisPolicy,
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
    / "t20_crec_sany_source_stream_discovery.json"
)


def _load_manifest() -> DiscoveryManifest:
    return DiscoveryManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_locks_two_institutions_without_granting_runtime_authority() -> None:
    manifest = _load_manifest()

    assert {source.registry_code for source in manifest.sources} == {"ENT-003", "ENT-009"}
    assert len(manifest.sources) == 2
    assert all(len(source.streams) == 1 for source in manifest.sources)
    assert all(source.desired_enabled is False for source in manifest.sources)
    streams = tuple(stream for source in manifest.sources for stream in source.streams)
    assert all(stream.actual_running is False for stream in streams)
    assert all(stream.source_admission is None for stream in streams)

    crec, sany = manifest.sources
    assert crec.institution == "中国中铁"
    assert crec.streams[0].readiness is StreamReadiness.BOUNDED
    assert crec.streams[0].disposition is SourceResearchDisposition.MANUAL_SHADOW
    assert "TERMS_PROHIBIT_AUTOMATED_STORAGE" in crec.streams[0].blocker_codes
    assert sany.institution == "三一集团"
    assert sany.streams[0].readiness is StreamReadiness.BOUNDED
    assert sany.streams[0].disposition is SourceResearchDisposition.ADMISSION_READY


def test_manifest_saves_exact_collection_network_and_policy_boundaries() -> None:
    manifest = _load_manifest()

    for source in manifest.sources:
        stream = source.streams[0]
        assert stream.collection_url != source.official_origin
        assert stream.connector_type == "HTML_LIST_DETAIL"
        assert stream.expected_mime_types == ("text/html",)
        assert stream.poll_interval_minutes >= 1_440
        assert stream.request_timeout_seconds == 10
        assert stream.max_redirects == 5
        assert stream.rate_limit_requests_per_minute == 1
        assert stream.user_agent.startswith("SRBG-SourceResearch/")
        assert stream.policy_version.startswith("t20-")
        assert stream.allowed_hosts
        assert stream.allowed_path_patterns
        assert stream.verification.verified_at.isoformat() == "2026-07-20T02:31:00+00:00"
        assert stream.verification.collection_get.status_code == 200
        assert len(stream.verification.collection_get.response_sha256) == 64
        assert stream.verification.public_network_safe is True
        assert stream.verification.redirect_chain_safe is True
        assert stream.verification.robots_evidence.url.endswith("/robots.txt")
        assert stream.verification.terms_evidence.url.startswith("https://")
        assert stream.verification.copyright_evidence.url.startswith("https://")


def test_manifest_rejects_root_search_or_single_document_as_a_stream() -> None:
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    stream = base["sources"][0]["streams"][0]

    for invalid_url in (
        "https://www.crecg.com/",
        "https://www.crecg.com/search?q=bridge",
        "https://www.crecg.com/web/xwzx61/zfgsdt39/2026071615173141490/index.html",
    ):
        candidate: dict[str, Any] = json.loads(json.dumps(base))
        candidate["sources"][0]["streams"][0] = stream | {"collection_url": invalid_url}
        with pytest.raises(ValidationError):
            DiscoveryManifest.model_validate(candidate)


def test_unknown_compliance_evidence_cannot_be_admission_ready() -> None:
    candidate = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    candidate["sources"][1]["streams"][0]["verification"]["robots_evidence"]["status"] = "UNKNOWN"

    with pytest.raises(ValidationError, match="ADMISSION_READY"):
        DiscoveryManifest.model_validate(candidate)


def test_private_dns_or_redirect_escape_is_rejected() -> None:
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    private_dns: dict[str, Any] = json.loads(json.dumps(base))
    private_dns["sources"][1]["streams"][0]["verification"]["resolved_public_ips"] = ["127.0.0.1"]
    with pytest.raises(ValidationError, match="public"):
        DiscoveryManifest.model_validate(private_dns)

    redirect_escape: dict[str, Any] = json.loads(json.dumps(base))
    redirect_escape["sources"][1]["streams"][0]["verification"]["detail_get"]["final_url"] = (
        "https://example.com/case/14600.html"
    )
    with pytest.raises(ValidationError, match="redirect"):
        DiscoveryManifest.model_validate(redirect_escape)


@pytest.mark.parametrize(
    ("registry_code", "title", "body", "expected"),
    (
        (
            "ENT-003",
            "沪宁合高铁南通特大桥钢混连续刚构合龙",
            "项目完成桥梁施工关键节点",
            True,
        ),
        ("ENT-003", "中国中铁党委召开党建思想会议", "部署品牌宣传工作", False),
        (
            "ENT-009",
            "三一无人摊压机群在京哈高速连续施工",
            "路面机械用于公路施工与安全监测",
            True,
        ),
        ("ENT-009", "三一灯塔工厂完成 ERP 数字化改造", "生产线效率提升", False),
    ),
)
def test_stream_prefilter_keeps_only_direct_engineering_lifecycle_facts(
    registry_code: str,
    title: str,
    body: str,
    expected: bool,
) -> None:
    manifest = _load_manifest()
    stream = next(
        source.streams[0] for source in manifest.sources if source.registry_code == registry_code
    )

    assert stream.accepts(CandidateMetadata(title=title, body=body)) is expected


def test_manufacturer_effects_cannot_be_promoted_to_independent_verification() -> None:
    sany = _load_manifest().sources[1].streams[0]

    assert sany.claim_basis_policy is ClaimBasisPolicy.MANUFACTURER_CLAIM
    assert sany.allows_claim_basis(ClaimBasisPolicy.MANUFACTURER_CLAIM) is True
    assert sany.allows_claim_basis(ClaimBasisPolicy.INDEPENDENT_VERIFICATION) is False


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
    manifest = _load_manifest()

    await record_discovery_dispositions(manifest, repository)

    assert [(row[0], row[1], row[2]) for row in repository.recorded] == [
        ("ENT-003", "crec-subsidiary-project-updates", SourceResearchDisposition.MANUAL_SHADOW),
        ("ENT-009", "sany-construction-cases", SourceResearchDisposition.ADMISSION_READY),
    ]
    assert all(len(row[3]) == 64 for row in repository.recorded)
