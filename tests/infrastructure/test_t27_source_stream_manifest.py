import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
VALIDATION = ROOT / "docs" / "codex-kit" / "assets" / "validation"
MANIFEST_PATH = VALIDATION / "t27_chts_tunnel_construction_source_stream_discovery.json"
SCHEMA_PATH = VALIDATION / "t27_source_stream_discovery.schema.json"


def test_t27_manifest_matches_its_versioned_schema() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(payload)


def test_t27_manifest_can_close_research_ticket_without_claiming_operational_evidence() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert payload["closure_eligible"] is True
    assert payload["owner_gold_evidence"] is None
    assert payload["deepseek_real_schema_success"] is None
    assert payload["runtime_window_evidence"] is None
    assert payload["closeout_go_evidence"] is None
    assert all(source["desired_enabled"] is False for source in payload["sources"])
    streams = [stream for source in payload["sources"] for stream in source["streams"]]
    assert all(stream["source_admission"] is None for stream in streams)
    assert all(stream["actual_running"] is False for stream in streams)
    assert all(stream["pause_appended"] is False for stream in streams)
    assert all(stream["coverage_credit_granted"] is False for stream in streams)
