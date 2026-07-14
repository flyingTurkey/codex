"""Explainable, deterministic document version classification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Literal

from srbg_api.pdf_processing.normalization import normalize_text

CriticalFieldName = Literal["document_number", "published_at", "effective_at", "legal_effect"]


@dataclass(frozen=True, slots=True)
class CriticalFieldValues:
    document_number: str | None = None
    published_at: str | None = None
    effective_at: str | None = None
    legal_effect: str | None = None


@dataclass(frozen=True, slots=True)
class ChangeDocument:
    normalized_body: str
    semantic_body_sha256: str
    metadata_sha256: str
    critical_fields: CriticalFieldValues = field(default_factory=CriticalFieldValues)

    @classmethod
    def from_text(cls, value: str) -> ChangeDocument:
        normalized = normalize_text(value)
        digest = sha256(normalized.encode("utf-8")).hexdigest()
        return cls(
            normalized_body=normalized,
            semantic_body_sha256=digest,
            metadata_sha256=sha256(b"{}").hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class CriticalFieldChange:
    field: CriticalFieldName
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class VersionChangeResult:
    change_type: Literal["METADATA_ONLY", "CONTENT_UPDATE"]
    material: bool
    changed_token_count: int
    changed_token_ratio_bps: int
    critical_fields: tuple[CriticalFieldChange, ...]


_HARD_TOKENS = re.compile(r"\d|不得|禁止|不再|废止|失效|施行|实施|有效|无效|修订|替代|撤销|停止")


def classify_version_change(
    previous: ChangeDocument, current: ChangeDocument
) -> VersionChangeResult:
    critical_changes = _critical_changes(previous.critical_fields, current.critical_fields)
    if previous.semantic_body_sha256 == current.semantic_body_sha256:
        return VersionChangeResult(
            change_type="CONTENT_UPDATE" if critical_changes else "METADATA_ONLY",
            material=bool(critical_changes),
            changed_token_count=0,
            changed_token_ratio_bps=0,
            critical_fields=critical_changes,
        )

    before_tokens = previous.normalized_body.split()
    after_tokens = current.normalized_body.split()
    matcher = SequenceMatcher(a=before_tokens, b=after_tokens, autojunk=False)
    changed_count = 0
    changed_values: list[str] = []
    for operation, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        before_segment = before_tokens[before_start:before_end]
        after_segment = after_tokens[after_start:after_end]
        changed_count += max(len(before_segment), len(after_segment))
        changed_values.extend(before_segment)
        changed_values.extend(after_segment)
    denominator = max(len(before_tokens), len(after_tokens), 1)
    ratio_bps = min(10000, round(changed_count * 10000 / denominator))
    hard_token_changed = any(_HARD_TOKENS.search(value) for value in changed_values)
    material = (
        bool(critical_changes) or hard_token_changed or changed_count >= 10 or ratio_bps >= 50
    )
    return VersionChangeResult(
        change_type="CONTENT_UPDATE",
        material=material,
        changed_token_count=changed_count,
        changed_token_ratio_bps=ratio_bps,
        critical_fields=critical_changes,
    )


def _critical_changes(
    before: CriticalFieldValues, after: CriticalFieldValues
) -> tuple[CriticalFieldChange, ...]:
    result: list[CriticalFieldChange] = []
    for name in ("document_number", "published_at", "effective_at", "legal_effect"):
        old_value = getattr(before, name)
        new_value = getattr(after, name)
        if old_value != new_value:
            result.append(
                CriticalFieldChange(
                    field=name,
                    before=old_value,
                    after=new_value,
                )
            )
    return tuple(result)
