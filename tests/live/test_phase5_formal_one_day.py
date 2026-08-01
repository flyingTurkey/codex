from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.verify_phase5_formal_one_day import (
    append_sample,
    evaluate_operation,
    load_samples,
    write_final_report,
)

START = datetime(2026, 8, 3, 1, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


def _passing_samples() -> list[dict[str, object]]:
    samples: list[dict[str, object]] = []
    for offset in range(0, 8 * 60 + 1, 15):
        worker_started = START - timedelta(hours=1)
        if offset >= 240:
            worker_started = START + timedelta(hours=4)
        samples.append(
            {
                "sampled_at": (START + timedelta(minutes=offset)).isoformat(),
                "services": {
                    "worker": worker_started.isoformat(),
                    "ai-worker": worker_started.isoformat(),
                    "publisher": worker_started.isoformat(),
                },
            }
        )
    return samples


def _passing_final() -> dict[str, object]:
    return {
        "database_revision": "0058_phase5_technical_exception_acl",
        "run": {
            "state": "COMPLETED",
            "stop_reason": "WORKDAY_COMPLETE",
            "wall_started_at": START.isoformat(),
            "wall_deadline": (START + timedelta(hours=8)).isoformat(),
            "request_limit": 80,
            "byte_limit": 157_286_400,
            "response_limit": 52_428_800,
            "ai_cost_limit_microusd": 1_250_000,
            "failure_limit": 10,
            "failure_rate_bps": 3_000,
            "failure_rate_min_samples": 10,
        },
        "metrics": {
            "discovered": 1,
            "run_source_count": 1,
            "run_source_matches_stream": True,
            "run_stream_count": 1,
            "run_stream_mismatch": 0,
            "fetched": 1,
            "parsed": 1,
            "auto_filtered": 0,
            "ai_succeeded": 1,
            "published": 1,
            "failed": 0,
            "silent_failures": 0,
            "hanging": 0,
            "retries": 0,
            "duplicates": 0,
            "other_source_fetches": 0,
            "input_tokens": 1200,
            "output_tokens": 300,
            "cost_microusd": 2500,
            "accepted_claims": 2,
            "claim_evidence_links": 2,
            "claims_without_evidence": 0,
            "other_primary_types": 0,
            "higher_risk_published": 0,
            "fetch_latency_ms_p95": 800,
            "ai_latency_ms_p95": 1400,
            "unpublished": [],
        },
        "surfaces": {
            "all_status": 200,
            "all_contains_event": True,
            "feed_contains_event": True,
            "detail_status": 200,
            "detail_contains_event": True,
        },
    }


def test_phase5_one_day_accepts_only_the_complete_formal_story() -> None:
    result = evaluate_operation(_passing_samples(), _passing_final())

    assert result["decision"] == "PASS"
    assert result["reasons"] == []


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda samples, final: samples.__delitem__(slice(17, None)), "WINDOW_TOO_SHORT"),
        (
            lambda samples, final: final["metrics"].__setitem__(
                "other_source_fetches", 1
            ),
            "OTHER_SOURCE_RAN",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__(
                "run_source_count", 2
            ),
            "RUN_SOURCE_COUNT_INVALID",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__(
                "run_stream_mismatch", 1
            ),
            "RUN_STREAM_MISMATCH",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__(
                "other_primary_types", 1
            ),
            "CONTENT_TYPE_OUT_OF_SCOPE",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__(
                "higher_risk_published", 1
            ),
            "CONTENT_RISK_OUT_OF_SCOPE",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__("duplicates", 1),
            "DUPLICATE_OUTPUT",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__(
                "silent_failures", 1
            ),
            "SILENT_FAILURE",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__("hanging", 1),
            "PERMANENT_HANG",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__(
                "cost_microusd", 1_250_001
            ),
            "AI_BUDGET_EXCEEDED",
        ),
        (
            lambda samples, final: [
                sample["services"].__setitem__(
                    "worker", (START - timedelta(hours=1)).isoformat()
                )
                for sample in samples
            ],
            "RESTART_RECOVERY_NOT_PROVEN",
        ),
        (
            lambda samples, final: final["metrics"].__setitem__(
                "claims_without_evidence", 1
            ),
            "CLAIM_EVIDENCE_TRACE_INCOMPLETE",
        ),
        (
            lambda samples, final: final["surfaces"].__setitem__(
                "all_contains_event", False
            ),
            "ALL_PAGE_ITEM_MISSING",
        ),
        (
            lambda samples, final: final["surfaces"].__setitem__(
                "feed_contains_event", False
            ),
            "FEED_ITEM_MISSING",
        ),
    ],
)
def test_phase5_one_day_fails_closed_on_each_exit_invariant(
    mutation, reason: str
) -> None:
    samples = deepcopy(_passing_samples())
    final = deepcopy(_passing_final())
    mutation(samples, final)

    result = evaluate_operation(samples, final)

    assert result["decision"] == "NO_GO"
    assert reason in result["reasons"]


def test_phase5_one_day_rejects_wrong_revision_budget_and_sample_alignment() -> None:
    samples = _passing_samples()
    final = _passing_final()
    samples[0]["sampled_at"] = (START - timedelta(hours=1)).isoformat()
    final["database_revision"] = "0056_phase4_controlled_handoff"
    final["run"]["request_limit"] = 79

    result = evaluate_operation(samples, final)

    assert result["decision"] == "NO_GO"
    assert "DATABASE_REVISION_INVALID" in result["reasons"]
    assert "CONTROLLED_RUN_LIMITS_INVALID" in result["reasons"]
    assert "RUN_START_NOT_SAMPLED" in result["reasons"]


def test_phase5_evidence_log_is_append_only_and_final_report_is_immutable(
    tmp_path,
) -> None:
    log = tmp_path / "samples.jsonl"
    report = tmp_path / "final.json"
    first = _passing_samples()[0]
    second = _passing_samples()[1]

    append_sample(log, first)
    append_sample(log, second)

    assert load_samples(log) == [first, second]
    write_final_report(report, {"decision": "PASS"})
    with pytest.raises(FileExistsError):
        write_final_report(report, {"decision": "NO_GO"})


def test_make_live_routes_phase5_to_the_read_only_one_day_verifier() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "ifeq ($(LIVE_ACCEPTANCE_PROFILE),phase5-formal-one-day)" in makefile
    target = makefile.split("live-acceptance:", 1)[1].split("check-fast:", 1)[0]
    assert "scripts/verify_phase5_formal_one_day.py --action verify" in target
    assert "PHASE5_RUN_ID" in target
    assert "PHASE5_SOURCE_STREAM_ID" in target
