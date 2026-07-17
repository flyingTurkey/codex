"""Bounded local PERS-06 extraction: bibliography and explicit scalar facts only."""

from __future__ import annotations

import re
from dataclasses import dataclass

from srbg_api.ai_pipeline.preparation import DocumentBlock


@dataclass(frozen=True, slots=True)
class LocalEvidenceCandidate:
    candidate_id: str
    field: str
    value: str | int
    block_id: str
    excerpt: str
    attribution: str | None = None


def extract_local_evidence_candidates(
    *, title: str, source_name: str, blocks: tuple[DocumentBlock, ...]
) -> tuple[LocalEvidenceCandidate, ...]:
    candidates: list[LocalEvidenceCandidate] = []
    for field, bibliography_value in (("title", title), ("publisher", source_name)):
        block = next(
            (row for row in blocks if bibliography_value and bibliography_value in row.text),
            None,
        )
        if block is not None:
            candidates.append(
                LocalEvidenceCandidate(
                    candidate_id=f"local-{field}",
                    field=field,
                    value=bibliography_value,
                    block_id=block.block_id,
                    excerpt=_bounded_excerpt(block.text, bibliography_value),
                    attribution=source_name if field == "publisher" else None,
                )
            )
    patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "document_no",
            re.compile(
                r"(?:文号|文件编号)\s*[\uff1a:]\s*([^,\s\uff0c\u3002\uff1b;]{3,40})"
            ),
        ),
        (
            "model_no",
            re.compile(r"(?:型号|产品型号)\s*[\uff1a:]\s*([A-Za-z0-9._/-]{2,40})"),
        ),
        ("published_at", re.compile(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?")),
        ("death_count", re.compile(r"死亡\s*(\d+)\s*(?:人|名)")),
        ("injury_count", re.compile(r"(?:受伤|重伤|轻伤)\s*(\d+)\s*(?:人|名)")),
        (
            "direct_loss",
            re.compile(
                r"(?:直接经济损失|投入金额|金额)\s*([0-9]+(?:\.[0-9]+)?\s*(?:元|万元|亿元))"
            ),
        ),
    )
    for block in blocks:
        for field, pattern in patterns:
            match = pattern.search(block.text)
            if match is None or any(row.field == field for row in candidates):
                continue
            raw = match.group(0)
            scalar_value: str | int = match.group(1)
            if field in {"death_count", "injury_count"}:
                scalar_value = int(scalar_value)
            elif field == "published_at":
                scalar_value = (
                    f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
                )
            candidates.append(
                LocalEvidenceCandidate(
                    candidate_id=f"local-{field}",
                    field=field,
                    value=scalar_value,
                    block_id=block.block_id,
                    excerpt=raw,
                )
            )
    return tuple(candidates)


def _bounded_excerpt(text: str, needle: str) -> str:
    start = max(0, text.find(needle) - 80)
    return text[start : start + 500]
