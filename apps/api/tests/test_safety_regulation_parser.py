import base64
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from srbg_api.acquisition.contracts import SourceAdapter, SourceConnector
from srbg_api.safety_regulations.parser import MemSafetyRegulationParser
from srbg_api.safety_regulations.source import MemSafetyRegulationAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "source"


def _fixture_bytes(name: str) -> bytes:
    return base64.b64decode((FIXTURES / name).read_text(encoding="ascii"))


def test_fixture_manifest_binds_captured_bytes_to_official_urls() -> None:
    manifest = json.loads(
        (FIXTURES / "round02-mem-fixture-manifest.json").read_text(encoding="utf-8")
    )

    for response in manifest["responses"]:
        content = _fixture_bytes(response["file"])
        assert len(content) == response["byte_length"]
        assert sha256(content).hexdigest() == response["sha256"]
        assert response["url"].startswith("https://www.mem.gov.cn/")


def test_source_connector_is_only_a_compatibility_alias() -> None:
    assert SourceConnector is SourceAdapter


def test_mem_list_discovery_finds_target_and_resolves_canonical_url() -> None:
    adapter = MemSafetyRegulationAdapter()

    records = adapter.discover_from_html(
        _fixture_bytes("round02-mem-list.html.b64"),
        list_url=("https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/index_1.shtml"),
        discovered_at=datetime(2026, 7, 14, 1, 9, 4, tzinfo=UTC),
    )

    target = next(record for record in records if record.external_id == "t20160603_405633")
    assert target.title == "生产安全事故应急预案管理办法"
    assert target.url.endswith("/201606/t20160603_405633.shtml")
    assert target.published_at == datetime(2016, 6, 3, tzinfo=UTC)


def test_mem_detail_parser_extracts_rules_and_binds_claims_to_numbered_paragraphs() -> None:
    parsed = MemSafetyRegulationParser().parse(
        _fixture_bytes("round02-mem-detail.html.b64"),
        document_version_id="019b0000-0000-7000-8000-000000002101",
        canonical_url=(
            "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/201606/t20160603_405633.shtml"
        ),
    )

    assert parsed.title == "生产安全事故应急预案管理办法"
    assert parsed.issuing_authority == "应急管理部"
    assert parsed.document_number == "国家安全生产监督管理总局令第88号"
    assert parsed.published_at == datetime(2016, 6, 3, 10, 28, tzinfo=UTC)
    assert parsed.regulation_status == "UNKNOWN"
    assert parsed.classification == "DEPARTMENT_RULE"
    assert parsed.paragraphs[0].paragraph_id == "html-p-0001"
    assert any(paragraph.text.startswith("第一条") for paragraph in parsed.paragraphs)

    claims = {claim.claim_type: claim for claim in parsed.claims}
    assert set(claims) == {"title", "issuing_authority", "document_number", "published_at"}
    assert all(claim.evidence for claim in claims.values())
    for claim in claims.values():
        for evidence in claim.evidence:
            assert evidence.paragraph_id.startswith("html-p-")
            assert evidence.excerpt_sha256 == sha256(evidence.excerpt.encode()).hexdigest()


def test_mem_detail_parser_rules_support_a_new_mem_order_number_and_date() -> None:
    html = """<!doctype html>
    <html><head>
      <meta name="ArticleTitle" content="生产安全新规定">
      <meta name="ContentSource" content="应急管理部">
      <meta name="ColumnName" content="规章">
      <meta name="PubDate" content="2026-07-01 09:30:00">
    </head><body><div class="TRS_Editor">
      <p>生产安全新规定</p>
      <p>中华人民共和国应急管理部令 第 42 号</p>
      <p>应急管理部</p>
      <p>2026 年 7 月 1 日</p>
    </div></body></html>""".encode()

    parsed = MemSafetyRegulationParser().parse(
        html,
        document_version_id="019b0000-0000-7000-8000-000000002102",
        canonical_url="https://www.mem.gov.cn/gk/example.shtml",
    )

    assert parsed.document_number == "中华人民共和国应急管理部令第42号"
    assert parsed.published_at == datetime(2026, 7, 1, 1, 30, tzinfo=UTC)
    published_claim = next(claim for claim in parsed.claims if claim.claim_type == "published_at")
    assert published_claim.evidence[0].excerpt == "2026 年 7 月 1 日"
