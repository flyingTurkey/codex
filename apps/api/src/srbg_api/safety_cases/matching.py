"""Deterministic safety-event matching and raw-document deduplication."""

from __future__ import annotations

import re

from srbg_api.safety_cases.domain import (
    DedupDisposition,
    EventIdentity,
    EventMatchResult,
    ReportStage,
)

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
EVENT_MATCH_ALGORITHM_VERSION = "safety-event-match-v1"


def score_event_match(existing: EventIdentity, incoming: EventIdentity) -> EventMatchResult:
    """Score a candidate without ever confirming the event association.

    Candidate threshold and identity guards are intentionally fixed and explainable.  A score can
    only enqueue human review; it can never write ``event_item`` itself.
    """

    dimension_scores = {
        "date": 25 if _same_date(existing, incoming) else 0,
        "region": 20 if _same_text(existing.region, incoming.region) else 0,
        "project": 30 if _same_text(existing.project, incoming.project) else 0,
        "subject": 15 if _shared_subject(existing.subjects, incoming.subjects) else 0,
        "accident_type": (10 if _same_text(existing.accident_type, incoming.accident_type) else 0),
    }
    total = sum(dimension_scores.values())
    identity_guard = bool(dimension_scores["project"] or dimension_scores["subject"]) and bool(
        dimension_scores["date"] or dimension_scores["region"]
    )
    forms_candidate = total >= 60 and identity_guard
    return EventMatchResult(
        total=total,
        dimension_scores=dimension_scores,
        forms_candidate=forms_candidate,
        requires_human_review=forms_candidate,
        algorithm_version=EVENT_MATCH_ALGORITHM_VERSION,
    )


def safety_document_disposition(
    *,
    existing_stage: ReportStage,
    incoming_stage: ReportStage,
    existing_raw_sha256: str,
    incoming_raw_sha256: str,
    existing_url: str,
    incoming_url: str,
    title_similarity_bps: int,
) -> DedupDisposition:
    """Keep event stages separate; fuzzy similarity is linkage evidence, never deletion proof."""

    for digest in (existing_raw_sha256, incoming_raw_sha256):
        if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise ValueError("raw SHA-256 must contain 64 lowercase hexadecimal characters")
    if not 0 <= title_similarity_bps <= 10_000:
        raise ValueError("title_similarity_bps must be between 0 and 10000")
    if not existing_url or not incoming_url:
        raise ValueError("document URLs must not be empty")

    if existing_stage is not incoming_stage:
        return DedupDisposition.PRESERVE_AND_LINK
    if existing_raw_sha256 == incoming_raw_sha256:
        return DedupDisposition.EXACT_RAW_DUPLICATE
    return DedupDisposition.PRESERVE_AS_DISTINCT


def _same_date(existing: EventIdentity, incoming: EventIdentity) -> bool:
    return existing.occurred_on is not None and existing.occurred_on == incoming.occurred_on


def _same_text(existing: str | None, incoming: str | None) -> bool:
    return (
        existing is not None
        and incoming is not None
        and _normalize(existing) == _normalize(incoming)
    )


def _shared_subject(existing: tuple[str, ...], incoming: tuple[str, ...]) -> bool:
    existing_normalized = {_normalize(value) for value in existing if value.strip()}
    incoming_normalized = {_normalize(value) for value in incoming if value.strip()}
    return bool(existing_normalized & incoming_normalized)


def _normalize(value: str) -> str:
    return _NON_WORD.sub("", value).casefold()
