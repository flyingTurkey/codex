from __future__ import annotations

import pytest

from scripts.authorize_intelligence_v2_owner_gold_override import (
    build_historical_owner_gold_approval,
)


def _rows(version: str) -> list[dict[str, object]]:
    buckets = ["POSITIVE"] * 15 + ["BOUNDARY"] * 3 + ["NEGATIVE"] * 22
    return [
        {
            "case_id": f"case-{index}",
            "corpus_version": version,
            "annotator_kind": "HUMAN_OWNER",
            "bucket": bucket,
        }
        for index, bucket in enumerate(buckets)
    ]


def test_historical_override_accepts_existing_owner_labels_without_production_grant() -> None:
    approval = build_historical_owner_gold_approval(
        corpus_version="owner-gold-2026-07-20.1",
        rows=_rows("owner-gold-2026-07-20.1"),
        no_go_sha256="a" * 64,
        labels_sha256="b" * 64,
        approval_timestamp="2026-07-20T17:00:00+00:00",
    )

    assert approval["decision"] == "GO"
    assert approval["authorization"] == "HISTORICAL_OWNER_LABELS_ACCEPTED"
    assert approval["production_auto_pass_eligible"] is False
    assert approval["observed_distribution"] == {
        "POSITIVE": 15,
        "BOUNDARY": 3,
        "NEGATIVE": 22,
    }
    assert approval["label_count"] == 40


def test_historical_override_refuses_missing_or_non_owner_labels() -> None:
    rows = _rows("owner-gold-2026-07-20.1")
    rows[0]["annotator_kind"] = "MODEL"
    with pytest.raises(ValueError, match="HISTORICAL_OWNER_LABELS_INVALID"):
        build_historical_owner_gold_approval(
            corpus_version="owner-gold-2026-07-20.1",
            rows=rows,
            no_go_sha256="a" * 64,
            labels_sha256="b" * 64,
            approval_timestamp="2026-07-20T17:00:00+00:00",
        )

