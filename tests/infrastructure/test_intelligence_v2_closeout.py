import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from srbg_api.intelligence_v2.gold_calibration import (
    CalibrationFact,
    SliceMetrics,
    calibration_fact_sha256,
)
from srbg_contracts import (
    EngineeringObject,
    EquipmentFacet,
    PrimaryIntelligenceType,
    SpecialtyFacet,
)

from scripts.intelligence_v2_closeout import (
    build_closeout_report,
    load_owner_qualification,
    main,
)

START = datetime(2026, 7, 19, tzinfo=UTC)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(value, ensure_ascii=False) for value in values) + "\n",
        encoding="utf-8",
    )


def _write_protocol_calibration_fact(path: Path) -> None:
    """Write a protocol fixture; this is not Owner Gold or closeout evidence."""

    metric = SliceMetrics(sample_count=1, precision_bps=10_000, recall_bps=10_000)
    fact = CalibrationFact(
        fact_version="intelligence-v2-owner-gold-calibration-2.0.0",
        corpus_version="owner-gold-2026-07-20.4",
        rule_version="intelligence-v2-qualification-1.0.0",
        model_id="deepseek-v4-flash",
        prompt_version="ai01-classify-v1",
        calibrated_at=START,
        label_authority="HUMAN_OWNER",
        decision="GO",
        reasons=(),
        authorizes_auto_pass=True,
        auto_pass_threshold_bps=9300,
        precision_bps=10_000,
        recall_bps=10_000,
        locked_negative_leaks=0,
        primary_type_slices={value: metric for value in PrimaryIntelligenceType},
        engineering_object_slices={value: metric for value in EngineeringObject},
        specialty_facet_slices={value: metric for value in SpecialtyFacet},
        equipment_domain_slices={value: metric for value in EquipmentFacet},
        evidence_manifest_sha256="f" * 64,
        prediction_seal_sha256="e" * 64,
        fact_sha256="",
    )
    fact = replace(fact, fact_sha256=calibration_fact_sha256(fact))
    payload = asdict(fact)
    payload["calibrated_at"] = fact.calibrated_at.isoformat()
    _write_json(path, payload)


def test_owner_qualification_rejects_generated_or_non_owner_labels(tmp_path: Path) -> None:
    path = tmp_path / "qualification.jsonl"
    _write_jsonl(
        path,
        [
            {
                "case_id": "case-1",
                "bucket": "POSITIVE",
                "expected_relevant": True,
                "predicted_relevant": True,
                "locked_negative": False,
                "annotator_kind": "MODEL",
                "content_sha256": "a" * 64,
                "raw_object_sha256": "b" * 64,
                "locator": "html:p:1",
                "primary_type": "SAFETY_INTELLIGENCE",
                "engineering_object": "TUNNEL",
                "rule_version": "intelligence-v2-qualification-1.0.0",
            }
        ],
    )
    with pytest.raises(ValueError, match="HUMAN_OWNER"):
        load_owner_qualification(path, tmp_path / "missing-predictions.jsonl")


def test_closeout_report_is_no_go_when_real_evidence_is_missing(tmp_path: Path) -> None:
    report = build_closeout_report(tmp_path, acceptance_profile="production")
    assert report["decision"] == "NO_GO"
    assert "OWNER_GOLD_INCOMPLETE" in report["reasons"]
    assert "AI_RUNTIME_WINDOW_INCOMPLETE" in report["reasons"]
    assert "SOURCE_ASSESSMENT_INCOMPLETE" in report["reasons"]
    assert "ARCHIVE_PREFLIGHT_INCOMPLETE" in report["reasons"]
    assert "READINESS_CONTEXT_INCOMPLETE" in report["reasons"]
    assert report["context"]["baseline_commit"] is None
    assert len(report["manifest_sha256"]) == 64


def test_closeout_cli_requires_explicit_acceptance_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["intelligence_v2_closeout.py", "--evidence-root", "."])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_closeout_report_accepts_complete_hashed_evidence(tmp_path: Path) -> None:
    runtime = []
    for minute in range(24 * 60 + 1):
        observed_at = START + timedelta(minutes=minute)
        runtime.append(
            {
                "observed_at": observed_at.isoformat(),
                "worker_heartbeat_at": observed_at.isoformat(),
                "queue_healthy": True,
                "budget_healthy": True,
                "last_real_schema_success_at": (
                    START + timedelta(hours=(minute // 360) * 6)
                ).isoformat(),
                "external_balance_state": "SUFFICIENT_AT_LAST_REAL_CALL",
            }
        )
    _write_jsonl(tmp_path / "runtime.jsonl", runtime)

    qualification: list[dict[str, object]] = []
    qualification_predictions: list[dict[str, object]] = []
    for bucket, count, relevant in (
        ("POSITIVE", 20, True),
        ("BOUNDARY", 10, True),
        ("NEGATIVE", 10, False),
    ):
        for index in range(count):
            content_sha256 = f"{len(qualification) + 1:064x}"
            qualification.append(
                {
                    "case_id": f"{bucket}-{index}",
                    "bucket": bucket,
                    "expected_relevant": relevant,
                    "locked_negative": bucket == "NEGATIVE",
                    "annotator_kind": "HUMAN_OWNER",
                    "content_sha256": content_sha256,
                    "raw_object_sha256": f"{len(qualification) + 1001:064x}",
                    "annotated_at": START.isoformat(),
                    "corpus_version": "owner-gold-2026-07-20.4",
                    "schema_version": "intelligence-v2-owner-gold-2.0.0",
                    "evidence_locator": f"html:p:{index}",
                    "primary_type": "INDUSTRY_UPDATE" if relevant else None,
                    "engineering_objects": ["HIGHWAY"] if relevant else [],
                    "specialty_facets": [],
                    "equipment_domains": [],
                    "rule_version": "intelligence-v2-qualification-1.0.0",
                    "model_id": "deepseek-v4-flash",
                    "prompt_version": "ai01-classify-v1",
                }
            )
            qualification_predictions.append(
                {
                    "case_id": f"{bucket}-{index}",
                    "content_sha256": content_sha256,
                    "input_sha256": content_sha256,
                    "corpus_version": "owner-gold-2026-07-20.4",
                    "rule_version": "intelligence-v2-qualification-1.0.0",
                    "model_id": "deepseek-v4-flash",
                    "prompt_version": "ai01-classify-v1",
                    "schema_version": "intelligence-v2-owner-gold-2.0.0",
                    "predicted_at": (START - timedelta(minutes=1)).isoformat(),
                    "predicted_relevant": relevant,
                    "primary_type": "INDUSTRY_UPDATE" if relevant else None,
                    "confidence_bps": 9300,
                }
            )
    _write_jsonl(tmp_path / "qualification.jsonl", qualification)
    _write_jsonl(tmp_path / "qualification-predictions.jsonl", qualification_predictions)
    _write_protocol_calibration_fact(tmp_path / "qualification-calibration.json")

    _write_jsonl(
        tmp_path / "feed.jsonl",
        [
            {
                "projection_id": f"event-{index}",
                "owner_relevant": True,
                "risk_tier": "R1",
                "unaccepted_claims": 0,
                "unsupported_facts": 0,
                "annotator_kind": "HUMAN_OWNER",
                "snapshot_sha256": "b" * 64,
                "content_sha256": f"{index + 2001:064x}",
                "raw_object_sha256": f"{index + 3001:064x}",
                "rule_version": "intelligence-v2-feed-inspection-1.0.0",
            }
            for index in range(200)
        ],
    )
    rollout = json.loads(
        Path("docs/codex-kit/assets/validation/civil_engineering_source_rollout_v2.json").read_text(
            encoding="utf-8"
        )
    )
    assessments: list[dict[str, object]] = []
    for batch_index, batch in enumerate(rollout["batches"], 1):
        started_at = START if batch_index == 1 else START + timedelta(days=15)
        ended_at = started_at + timedelta(days=14 if batch_index == 1 else 3)
        for index, institution in enumerate(batch["institutions"]):
            assessments.append(
                {
                    "institution": institution,
                    "batch": batch_index,
                    "wave": index // 2 + 1,
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                    "sample_cutoff": ended_at.isoformat(),
                    "lookback_days": 90,
                    "sample_manifest_sha256": f"{index + batch_index * 100:064x}",
                    "sample_size": 30,
                    "verdict": "ADMIT",
                    "metrics": {
                        "robots_allowed": True,
                        "terms_allowed": True,
                        "copyright_reviewed": True,
                        "public_network_safe": True,
                        "hard_negative_evaluated": True,
                        "fetch_success_bps": 9800,
                        "parse_evidence_success_bps": 9500,
                        "metadata_success_bps": 9800,
                        "useful_yield_bps": 5000,
                        "duplicate_bps": 3000,
                        "hard_negative_leaks": 0,
                    },
                }
            )
    _write_json(
        tmp_path / "sources.json",
        {
            "rule_version": "civil-source-rollout-v2.0.0",
            "assessments": assessments,
        },
    )
    _write_json(
        tmp_path / "engineering.json",
        {
            "lint": True,
            "typecheck": True,
            "test": True,
            "contract_test": True,
            "security_check": True,
            "fixture_replay": True,
            "quality_gate": True,
            "web_e2e": True,
            "web_a11y": True,
        },
    )
    _write_json(
        tmp_path / "compensation.json",
        {
            "injected_transient_count": 5,
            "recovered_count": 5,
            "injected_permanent_count": 1,
            "permanent_error_observed_count": 1,
            "duplicate_side_effects": 0,
            "stale_version_recoveries": 0,
            "permanent_error_retries": 0,
        },
    )
    _write_json(
        tmp_path / "preflight.json",
        {
            "backup_receipt_verified": True,
            "object_inventory_verified": True,
            "audit_tail_anchor_verified": True,
            "v1_archive_sha256_verified": True,
            "mutation_performed": False,
        },
    )
    _write_json(
        tmp_path / "context.json",
        {
            "baseline_commit": "a" * 40,
            "migration_head": "0039_t04_content_candidates",
            "environment": "isolated-production-equivalent-acceptance",
            "campaign_id": "019c0000-0000-7000-8000-000000000001",
        },
    )

    report = build_closeout_report(tmp_path, acceptance_profile="production")
    assert report["decision"] == "GO", report["reasons"]
    assert report["reasons"] == []
    assert report["context"]["baseline_commit"] == "a" * 40
    assert report["context"]["time_window"]["start"] == START.isoformat()
    assert report["checks"]["qualification"]["auto_pass_threshold_bps"] == 9300
    assert {item["path"] for item in report["context"]["evidence_refs"]} >= {
        "runtime.jsonl",
        "qualification.jsonl",
        "qualification-calibration.json",
        "feed.jsonl",
        "sources.json",
        "preflight.json",
    }


def test_one_hour_unlabelled_evidence_is_engineering_go_but_production_no_go(
    tmp_path: Path,
) -> None:
    runtime = []
    for minute in range(61):
        observed_at = START + timedelta(minutes=minute)
        runtime.append(
            {
                "observed_at": observed_at.isoformat(),
                "worker_heartbeat_at": observed_at.isoformat(),
                "queue_healthy": True,
                "budget_healthy": True,
                "last_real_schema_success_at": START.isoformat(),
                "external_balance_state": "SUFFICIENT_AT_LAST_REAL_CALL",
            }
        )
    _write_jsonl(tmp_path / "runtime.jsonl", runtime)
    _write_jsonl(
        tmp_path / "feed.jsonl",
        [
            {
                "projection_id": f"event-{index}",
                "risk_tier": "R1",
                "unaccepted_claims": 0,
                "unsupported_facts": 0,
                "evidence_kind": "SERVER_PROJECTION_AUDIT",
                "snapshot_sha256": "b" * 64,
                "content_sha256": f"{index + 1:064x}",
                "raw_object_sha256": f"{index + 1001:064x}",
                "rule_version": "intelligence-v2-feed-structural-engineering-1.0.0",
            }
            for index in range(200)
        ],
    )
    rollout = json.loads(
        Path("docs/codex-kit/assets/validation/civil_engineering_source_rollout_v2.json").read_text(
            encoding="utf-8"
        )
    )
    assessments: list[dict[str, object]] = []
    for batch_index, batch in enumerate(rollout["batches"], 1):
        for index, institution in enumerate(batch["institutions"]):
            assessments.append(
                {
                    "institution": institution,
                    "batch": batch_index,
                    "wave": index // 2 + 1,
                    "started_at": START.isoformat(),
                    "ended_at": (START + timedelta(hours=1)).isoformat(),
                    "sample_cutoff": (START + timedelta(hours=1)).isoformat(),
                    "lookback_days": 90,
                    "sample_manifest_sha256": f"{index + batch_index * 100:064x}",
                    "sample_size": 30,
                    "verdict": "ADMIT",
                    "metrics": {
                        "robots_allowed": True,
                        "terms_allowed": True,
                        "copyright_reviewed": True,
                        "public_network_safe": True,
                        "hard_negative_evaluated": True,
                        "fetch_success_bps": 9800,
                        "parse_evidence_success_bps": 9500,
                        "metadata_success_bps": 9800,
                        "useful_yield_bps": 5000,
                        "duplicate_bps": 3000,
                        "hard_negative_leaks": 0,
                    },
                }
            )
    _write_json(
        tmp_path / "sources.json",
        {
            "rule_version": "civil-source-rollout-v2-engineering-1.0.0",
            "assessments": assessments,
        },
    )
    _write_json(
        tmp_path / "engineering.json",
        {
            gate: True
            for gate in (
                "lint",
                "typecheck",
                "test",
                "contract_test",
                "security_check",
                "fixture_replay",
                "quality_gate",
                "web_e2e",
                "web_a11y",
            )
        },
    )
    _write_json(
        tmp_path / "compensation.json",
        {
            "injected_transient_count": 3,
            "recovered_count": 3,
            "injected_permanent_count": 1,
            "permanent_error_observed_count": 1,
            "duplicate_side_effects": 0,
            "stale_version_recoveries": 0,
            "permanent_error_retries": 0,
        },
    )
    _write_json(
        tmp_path / "preflight.json",
        {
            "backup_receipt_verified": True,
            "object_inventory_verified": True,
            "audit_tail_anchor_verified": True,
            "v1_archive_sha256_verified": True,
            "mutation_performed": False,
        },
    )
    _write_json(
        tmp_path / "context.json",
        {
            "baseline_commit": "a" * 40,
            "migration_head": "0039_t04_content_candidates",
            "environment": "isolated-production-equivalent-acceptance",
            "campaign_id": "019c0000-0000-7000-8000-000000000001",
        },
    )

    engineering = build_closeout_report(tmp_path, acceptance_profile="engineering")
    production = build_closeout_report(tmp_path, acceptance_profile="production")

    assert engineering["decision"] == "GO"
    assert engineering["acceptance_profile"] == "ENGINEERING_CLOSEOUT"
    assert engineering["reasons"] == []
    assert "OWNER_GOLD_INCOMPLETE" in production["reasons"]
    assert "AI_RUNTIME_WINDOW_INCOMPLETE" in production["reasons"]
    assert "SOURCE_ASSESSMENT_INCOMPLETE" in production["reasons"]
    assert production["decision"] == "NO_GO"
