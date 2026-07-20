import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
RECORD_PATH = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t14_mohurd_source_stream_research.json"
)
SCHEMA_PATH = (
    ROOT
    / "docs"
    / "codex-kit"
    / "assets"
    / "validation"
    / "t14_source_stream_research.schema.json"
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_mohurd_research_record_matches_the_versioned_contract() -> None:
    schema = _load(SCHEMA_PATH)
    record = _load(RECORD_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(record)


def test_bounded_research_is_admission_ready_without_mutating_control_state() -> None:
    record = _load(RECORD_PATH)

    assert record["ticket"] == {
        "issue": 15,
        "parent_spec": 1,
        "blocked_by": [{"issue": 8, "state": "CLOSED"}],
        "closure_eligible": True,
    }
    assert record["research_outcome"] == {
        "stream_readiness": "BOUNDED",
        "source_research_disposition": "ADMISSION_READY",
        "admission_ready": True,
        "blocking_reason_codes": [],
    }
    assert record["control_state_mutations"] == {
        "desired_enabled_changed": False,
        "source_admission_written": False,
        "runtime_state_changed": False,
        "pause_appended": False,
        "real_collection_executed": False,
    }
    verification = record["verification"]
    assert verification["robots"] == {
        "url": "https://www.mohurd.gov.cn/robots.txt",
        "status": 404,
        "result": "VERIFIED_NOT_PUBLISHED_NOT_PERMISSION",
    }
    assert verification["terms"]["result"] == "VERIFIED_NO_SEPARATE_TERMS"
    assert verification["copyright"]["result"] == "VERIFIED_RESTRICTED"
    assert verification["access_boundary"]["result"] == "VERIFIED_PUBLIC_NO_BYPASS"


def test_three_bounded_streams_remain_one_source_and_exclude_the_portal_root() -> None:
    record = _load(RECORD_PATH)
    source = record["source"]
    assert isinstance(source, dict)
    streams = record["streams"]
    assert isinstance(streams, list)

    assert source["source_code"] == "GOV-005"
    assert source["institution"] == "住房和城乡建设部"
    assert source["source_count_credit"] == 1
    assert source["registry_status"] == "CANDIDATE"
    assert source["enabled"] is False
    assert len(streams) == 3
    assert {stream["theme_filter"] for stream in streams} == {"F", "G", "K"}
    assert {stream["connector_type"] for stream in streams} == {"LIST_DETAIL"}

    for stream in streams:
        assert stream["source_code"] == "GOV-005"
        assert stream["collection_entry"].endswith("/gongkai/fdzdgknr/gkml/index.html")
        assert stream["collection_entry"] != source["official_origin"]
        assert stream["allowed_hosts"] == ["www.mohurd.gov.cn"]
        assert stream["path_boundaries"] == {
            "list": "/gongkai/fdzdgknr/gkml/",
            "detail": "/gongkai/zc/wjk/art/",
            "attachment_gateway": "/api-gateway/jpaas-web-server/front/document/download",
            "attachment_final": "/cms_files/filemanager/1150240553/attach/",
        }
        assert stream["expected_mime_types"] == [
            "text/html",
            "application/json",
            "application/pdf",
        ]
        assert stream["stream_readiness"] == "BOUNDED"
        assert stream["source_research_disposition"] == "ADMISSION_READY"
        assert stream["admission_ready"] is True
        assert stream["access_frequency"]["authorized"] is False


def test_w2_pair_preserves_mining_and_tunnel_gas_semantics() -> None:
    record = _load(RECORD_PATH)

    assert record["w2_pair"] == {
        "mohurd_stream_id": "GOV-005-G",
        "mine_safety_stream": {
            "institution": "国家矿山安全监察局",
            "name": "通知公告",
            "collection_entry": (
                "https://www.chinamine-safety.gov.cn/"
                "zfxxgk/fdzdgknr/tzgg/index.shtml"
            ),
            "existing_research_ref": (
                "docs/research/2026-07-19-civil-engineering-authoritative-source-expansion.md#s19-国家矿山安全监察局通知公告"
            ),
        },
        "mining_gas_engineering_object": "MINING",
        "grants_tunnel_gas_monitoring_coverage": False,
    }
