"""Pure rules for Event identity resolution.

These rules are deliberately independent from persistence so API, worker and
the resumable migration task cannot drift on identity decisions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

EVENT_TYPE_BY_ITEM_TYPE: Mapping[str, str] = {
    "DIGITAL_CASE": "DIGITAL_PROJECT",
    "JOURNAL_PAPER": "RESEARCH_RESULT",
    "SOFTWARE_PRODUCT": "PRODUCT_RELEASE",
    "IOT_PRODUCT": "PRODUCT_RELEASE",
    "LOW_ALTITUDE_EQUIPMENT": "PRODUCT_RELEASE",
    "AI_EQUIPMENT": "PRODUCT_RELEASE",
    "SAFETY_REGULATION": "REGULATION_CHANGE",
    "SAFETY_CASE": "SAFETY_INCIDENT",
}


class MatchDecision(StrEnum):
    AUTO_BIND = "AUTO_BIND"
    CANDIDATE = "CANDIDATE"


class AliasCycleError(ValueError):
    """Raised when corrupted aliases would make a redirect loop."""


@dataclass(frozen=True, slots=True)
class EventAlias:
    canonical_event_id: UUID


def classify_match(*, exact_identity: bool, hard_conflicts: Sequence[str]) -> MatchDecision:
    """Permit automation only for an exact identity with no hard conflict."""

    if exact_identity and not hard_conflicts:
        return MatchDecision.AUTO_BIND
    return MatchDecision.CANDIDATE


def resolve_canonical_event(
    event_id: UUID, aliases: Mapping[UUID, EventAlias], *, maximum_hops: int = 32
) -> UUID:
    """Resolve an Event alias defensively without ever emitting a redirect loop."""

    current = event_id
    visited: set[UUID] = set()
    for _ in range(maximum_hops):
        if current in visited:
            raise AliasCycleError(f"event alias cycle at {current}")
        visited.add(current)
        alias = aliases.get(current)
        if alias is None or alias.canonical_event_id == current:
            return current
        current = alias.canonical_event_id
    raise AliasCycleError(f"event alias chain exceeds {maximum_hops} hops")
