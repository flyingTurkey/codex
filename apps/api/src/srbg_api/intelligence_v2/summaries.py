"""Deterministic source-excerpt construction from active accepted-claim evidence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptedEvidence:
    claim_id: str
    locator: str
    text: str
    active: bool = True


@dataclass(frozen=True)
class SourceExcerpt:
    text: str
    claim_ids: tuple[str, ...]
    evidence_locators: tuple[str, ...]


def build_source_excerpt(evidence: list[AcceptedEvidence]) -> SourceExcerpt:
    active = [item for item in evidence if item.active and item.claim_id and item.locator]
    if not active:
        raise ValueError("SOURCE_EXCERPT_REQUIRES_ACTIVE_ACCEPTED_CLAIM")
    # A source excerpt is one continuous passage, never a stitched model paraphrase.
    selected = active[0]
    text = " ".join(selected.text.split())
    if not text or len(text) > 500:
        raise ValueError("SOURCE_EXCERPT_LENGTH_INVALID")
    return SourceExcerpt(text, (selected.claim_id,), (selected.locator,))
