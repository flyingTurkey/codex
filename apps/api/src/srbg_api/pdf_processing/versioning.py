"""First-principles version decision derived only from persisted document facts."""

from dataclasses import dataclass
from typing import Literal

from srbg_api.pdf_processing.change_detection import (
    ChangeDocument,
    CriticalFieldChange,
    CriticalFieldValues,
    classify_version_change,
)


@dataclass(frozen=True, slots=True)
class VersionFacts:
    raw_sha256: str
    normalized_text_sha256: str
    semantic_body_sha256: str
    metadata_sha256: str
    normalized_body: str
    critical_fields: CriticalFieldValues


@dataclass(frozen=True, slots=True)
class VersionDecision:
    change_type: Literal["INITIAL", "METADATA_ONLY", "CONTENT_UPDATE"]
    material: bool
    review_state: Literal["NO_REVIEW_REQUIRED", "RE_REVIEW_PENDING"]
    changed_token_count: int
    changed_token_ratio_bps: int
    critical_fields: tuple[CriticalFieldChange, ...]


def decide_version_change(
    previous: VersionFacts | None,
    current: VersionFacts,
) -> VersionDecision:
    if previous is None:
        return VersionDecision(
            change_type="INITIAL",
            material=True,
            review_state="RE_REVIEW_PENDING",
            changed_token_count=0,
            changed_token_ratio_bps=0,
            critical_fields=(),
        )
    result = classify_version_change(_change_document(previous), _change_document(current))
    return VersionDecision(
        change_type=result.change_type,
        material=result.material,
        review_state=("RE_REVIEW_PENDING" if result.material else "NO_REVIEW_REQUIRED"),
        changed_token_count=result.changed_token_count,
        changed_token_ratio_bps=result.changed_token_ratio_bps,
        critical_fields=result.critical_fields,
    )


def _change_document(facts: VersionFacts) -> ChangeDocument:
    return ChangeDocument(
        normalized_body=facts.normalized_body,
        semantic_body_sha256=facts.semantic_body_sha256,
        metadata_sha256=facts.metadata_sha256,
        critical_fields=facts.critical_fields,
    )
