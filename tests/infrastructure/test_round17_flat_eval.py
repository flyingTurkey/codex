import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch

import scripts.round17_flat_eval as flat_eval
from scripts.round17_flat_eval import evaluate


def test_flat_eval_blocks_when_real_evidence_and_reference_are_missing(tmp_path: Path) -> None:
    result = evaluate(
        tmp_path / "round17-flat-evidence.json",
        tmp_path / "leo-reference-manifest.json",
        now=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert result["decision"] == "BLOCKED"
    assert {issue["code"] for issue in result["issues"]} >= {
        "REQUIRED_EVIDENCE_MISSING",
        "REQUIRED_REFERENCE_MISSING",
    }


def test_flat_eval_contract_has_no_dual_annotator_or_individual_kpi() -> None:
    source = Path("scripts/round17_flat_eval.py").read_text(encoding="utf-8")

    assert "LEO_SINGLE_EXPERT_REFERENCE_SET" in source
    assert "LOWER_THAN_DUAL_EXPERT_GOLD" in source
    assert "yinzi" not in source
    assert "baixuejiao" not in source
    assert "operator_daily_minutes" not in source
    assert "individual_performance" not in source


def test_flat_eval_accepts_only_a_complete_single_expert_contract(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    authority: dict[str, Any] = {
        "roster_version": "r17-sources-v0.1",
        "metric_definition_version": "phase2-round17-metrics-v1.0.0",
        "reference_definition_version": "phase2-round17-leo-reference-v1.0.0",
        "sources": [{"source_code": f"SRC-{index:02d}"} for index in range(20)],
    }
    authority_bytes = flat_eval._canonical_json(authority)
    authority_hash = sha256(authority_bytes).hexdigest()
    authority_path = tmp_path / "authority.json"
    signed_path = tmp_path / "signed.json"
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    signed_path.write_text(
        json.dumps(
            {
                "approval_document": authority,
                "approval_document_sha256": authority_hash,
            }
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    ref = {"uri": "artifact.json", "sha256": sha256(artifact.read_bytes()).hexdigest()}
    reference = {
        "schema_version": "round17-leo-reference-v1",
        "authority_document_sha256": authority_hash,
        "definition_version": "phase2-round17-leo-reference-v1.0.0",
        "annotator_actor_id": flat_eval.LEO,
        "reference_model": "LEO_SINGLE_EXPERT_REFERENCE_SET",
        "assurance": "LOWER_THAN_DUAL_EXPERT_GOLD",
        "counts": flat_eval.EXPECTED_COUNTS,
        "frozen_at": "2026-07-08T00:00:00Z",
        "records_ref": ref,
    }
    evidence = {
        "schema_version": "round17-flat-evidence-v1",
        "authority_document_sha256": authority_hash,
        "database_revision": "0017c_round17_flat_pilot",
        "roster_version": "r17-sources-v0.1",
        "metric_definition_version": "phase2-round17-metrics-v1.0.0",
        "reference_definition_version": "phase2-round17-leo-reference-v1.0.0",
        "window": {
            "started_at": "2026-07-01T00:00:00Z",
            "ended_at": "2026-07-08T00:00:00Z",
            "duration_hours": 168,
            "continuous_hours_proven": 168,
            "state": "COMPLETED",
            "monitor_query_ref": ref,
        },
        "sources": [
            {
                "source_code": source["source_code"],
                "honest_status": "NO_UPDATE_HEALTHY",
                "health_evidence_ref": ref,
            }
            for source in authority["sources"]
        ],
        "metric_results": {
            name: {"numerator": 1, "denominator": 1} for name in flat_eval.RATE_THRESHOLDS_BPS
        },
        "absolute_gates": {name: 0 for name in flat_eval.ZERO_GATES},
        "published_critical_evidence": {
            "published_claim_count": 1,
            "with_current_evidence_count": 1,
        },
        "north_star": {"successful_events": 1, "expected_high_value_events": 1},
        "fault_drill": {
            "approved_by": flat_eval.LEO,
            "environment": "TEST",
            "evidence_ref": ref,
        },
    }
    evidence_path = tmp_path / "evidence.json"
    reference_path = tmp_path / "reference.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    reference_path.write_text(json.dumps(reference), encoding="utf-8")
    monkeypatch.setattr(flat_eval, "ROOT", tmp_path)
    monkeypatch.setattr(flat_eval, "AUTHORITY", authority_path)
    monkeypatch.setattr(flat_eval, "SIGNED", signed_path)

    result = evaluate(
        evidence_path,
        reference_path,
        now=datetime(2026, 7, 9, tzinfo=UTC),
    )

    assert result["decision"] == "PASSED"
    assert result["issues"] == []
