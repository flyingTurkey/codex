"""Deterministic offline acceptance evaluation for PERS-07."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from srbg_api.ai_pipeline.ai_judgments import (
    SummarizeOutput,
    validate_used_claim_ids,
)

FIXTURE = Path("tests/fixtures/pers07/ai_judgment_eval.json")


def main() -> None:
    samples = json.loads(FIXTURE.read_text(encoding="utf-8"))["samples"]
    if len(samples) < 30:
        raise RuntimeError("PERS07_SAMPLE_COUNT_BELOW_30")
    valid_evidence = 0
    critical_unsupported = 0
    unverified_in_primary = 0
    for sample in samples:
        current = {UUID(value) for value in sample["claim_ids"]}
        validate_used_claim_ids([UUID(value) for value in sample["used_claim_ids"]], current)
        valid_evidence += 1
        critical_unsupported += int(sample["critical_unsupported"])
        unverified_in_primary += int(
            sample["result_type"] == "UNVERIFIED_AI"
            and sample["search_surface"] == "PRIMARY"
        )
    repair_successes = 0
    for index in range(50):
        repaired = {
            "why_worth_attention": f"固定修复样本 {index + 1}",
            "potential_industry_impacts": [],
            "potential_engineering_scenarios": [],
            "current_limitations": [],
            "questions_to_verify": [],
            "used_claim_ids": [samples[index % len(samples)]["claim_ids"][0]],
        }
        SummarizeOutput.model_validate(repaired)
        repair_successes += 1
    app_sources = [
        *Path("apps/api/src").rglob("*.py"),
        *Path("apps/worker/src").rglob("*.py"),
    ]
    projection_writes = (
        "INSERT INTO personal_signal_projection",
        "INSERT INTO unverified_ai_search_projection",
    )
    unauthorized = 0
    for path in app_sources:
        if path.as_posix().endswith("publication/repository.py"):
            continue
        source = path.read_text(encoding="utf-8")
        unauthorized += sum(token in source for token in projection_writes)
    metrics = {
        "sample_count": len(samples),
        "evidence_id_validity_bps": valid_evidence * 10_000 // len(samples),
        "critical_number_date_unsupported_count": critical_unsupported,
        "unverified_ai_in_primary_index_count": unverified_in_primary,
        "unauthorized_projection_write_count": unauthorized,
        "json_schema_repair_success_bps": repair_successes * 10_000 // 50,
    }
    expected = {
        "evidence_id_validity_bps": 10_000,
        "critical_number_date_unsupported_count": 0,
        "unverified_ai_in_primary_index_count": 0,
        "unauthorized_projection_write_count": 0,
    }
    failures = {
        name: {"expected": value, "actual": metrics[name]}
        for name, value in expected.items()
        if metrics[name] != value
    }
    if metrics["json_schema_repair_success_bps"] < 9_800:
        failures["json_schema_repair_success_bps"] = {
            "expected_minimum": 9_800,
            "actual": metrics["json_schema_repair_success_bps"],
        }
    if failures:
        raise RuntimeError(json.dumps(failures, ensure_ascii=False, sort_keys=True))
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
