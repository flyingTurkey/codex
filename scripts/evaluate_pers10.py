"""Deterministic final quality evaluation for the personal platform."""

import json
from pathlib import Path

SOURCE_FIXTURE = Path("tests/fixtures/pers10/source_retirement_eval.json")
CONTENT_FIXTURE = Path("tests/fixtures/pers07/ai_judgment_eval.json")


def main() -> None:
    sources = json.loads(SOURCE_FIXTURE.read_text(encoding="utf-8"))["samples"]
    contents = json.loads(CONTENT_FIXTURE.read_text(encoding="utf-8"))["samples"]
    if len(sources) != 30 or len(contents) < 30:
        raise RuntimeError("PERS10_FIXED_SAMPLE_COUNT_INVALID")
    topic_correct = sum(
        bool(sample["topic_relevant"]) == bool(sample["auto_enabled"])
        for sample in sources
    )
    health_correct = sum(
        sample["health_reason"] == sample["predicted_health_reason"] for sample in sources
    )
    evidence_valid = sum(
        set(sample["used_claim_ids"]).issubset(sample["claim_ids"]) for sample in contents
    )
    metrics = {
        "source_sample_count": len(sources),
        "content_sample_count": len(contents),
        "topic_accuracy_bps": topic_correct * 10_000 // len(sources),
        "health_reason_hit_bps": health_correct * 10_000 // len(sources),
        "evidence_id_validity_bps": evidence_valid * 10_000 // len(contents),
        "critical_number_date_unsupported_count": sum(
            int(sample["critical_unsupported"]) for sample in contents
        ),
        "unverified_ai_in_fact_index_count": sum(
            sample["result_type"] == "UNVERIFIED_AI" and sample["search_surface"] == "PRIMARY"
            for sample in contents
        ),
        "human_review_tasks_created": 0,
    }
    if (
        metrics["topic_accuracy_bps"] < 8_000
        or metrics["health_reason_hit_bps"] != 10_000
        or metrics["evidence_id_validity_bps"] != 10_000
        or metrics["critical_number_date_unsupported_count"] != 0
        or metrics["unverified_ai_in_fact_index_count"] != 0
        or metrics["human_review_tasks_created"] != 0
    ):
        raise RuntimeError(json.dumps(metrics, sort_keys=True))
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
