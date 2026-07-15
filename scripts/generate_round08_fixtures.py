# ruff: noqa: RUF001
"""Generate deterministic, non-production Round 08 evaluation fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path("apps/api/tests/fixtures/round08")


def _document(index: int, *, duplicate: bool, side: str) -> dict[str, object]:
    project = f"测试高速{index:03d}"
    if not duplicate and side == "right":
        project = f"对照高速{index:03d}"
    external = f"fixture-{index:03d}" if duplicate else f"fixture-{index:03d}-{side}"
    return {
        "canonical_url": f"https://fixtures.invalid/{external}",
        "source_id": "fixture-source" if duplicate else f"fixture-source-{side}",
        "external_id": external,
        "doi": None,
        "issuer": None,
        "document_number": None,
        "content_sha256": (f"{index:064x}"[-64:] if duplicate else None),
        "title": f"{project}桥梁施工数字化进展",
        "body": f"{project}桥梁施工形成第{index}号内测元数据，不包含真实正文。",
        "entities": [project, "桥梁施工"],
        "occurred_at": "2026-07-15T00:00:00+00:00",
        "region": "四川",
        "project": project,
        "contract_section": "测试标段",
        "model_no": None,
        "accident_stage": None,
        "relation_hint": None,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> str:
    content = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        for row in rows
    )
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode()).hexdigest()


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    pairs = [
        {
            "id": f"pair-{index:03d}",
            "expected_duplicate": index <= 150,
            "left": _document(index, duplicate=index <= 150, side="left"),
            "right": _document(index, duplicate=index <= 150, side="right"),
        }
        for index in range(1, 301)
    ]
    events = [
        {
            "id": f"event-{index:03d}",
            "event_type": (
                "SAFETY_INCIDENT",
                "REGULATION_CHANGE",
                "DIGITAL_PROJECT",
                "RESEARCH_RESULT",
                "PRODUCT_RELEASE",
            )[(index - 1) % 5],
            "gold_cluster": f"gold-{index:03d}",
            "item_ids": [f"event-{index:03d}-item-{member}" for member in range(1, 4)],
            "predicted_clusters": [f"predicted-{index:03d}"] * 3,
        }
        for index in range(1, 101)
    ]
    pair_sha = _write_jsonl(ROOT / "dedup_pairs.v1.jsonl", pairs)
    event_sha = _write_jsonl(ROOT / "event_clusters.v1.jsonl", events)
    manifest = {
        "version": "round08-internal-v1",
        "evaluation_tier": "INTERNAL_TEST_FIXTURE",
        "human_adjudicated": False,
        "auto_merge_enabled": False,
        "dedup_pair_count": 300,
        "event_cluster_count": 100,
        "files": {
            "dedup_pairs.v1.jsonl": {"sha256": pair_sha},
            "event_clusters.v1.jsonl": {"sha256": event_sha},
        },
        "notice": "仅含合成元数据；指标不代表生产人工金标效果。",
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
