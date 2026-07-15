import json
from pathlib import Path

from srbg_api.intelligence_resolution.evaluation import evaluate_fixture_files

FIXTURES = Path("apps/api/tests/fixtures/round08")


def test_round08_internal_gold_structure_and_thresholds() -> None:
    pair_path = FIXTURES / "dedup_pairs.v1.jsonl"
    event_path = FIXTURES / "event_clusters.v1.jsonl"
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))

    assert len(pair_path.read_text(encoding="utf-8").splitlines()) == 300
    assert len(event_path.read_text(encoding="utf-8").splitlines()) == 100
    assert manifest["evaluation_tier"] == "INTERNAL_TEST_FIXTURE"
    assert manifest["human_adjudicated"] is False
    assert manifest["auto_merge_enabled"] is False

    result = evaluate_fixture_files(pair_path, event_path)
    assert result.pair_count == 300
    assert result.event_count == 100
    assert result.precision_bps >= 9_800
    assert result.recall_bps >= 9_300
    assert result.cluster_purity_bps >= 9_500
    assert result.auto_merge_enabled is False
