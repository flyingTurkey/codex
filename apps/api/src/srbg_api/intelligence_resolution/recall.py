"""Composable rule and optional pgvector candidate recall."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from srbg_api.intelligence_resolution.domain import (
    CandidateAssessment,
    DeduplicationDocument,
    assess_duplicate,
)


class PgVectorSearch(Protocol):
    async def __call__(
        self, query: DeduplicationDocument, *, limit: int
    ) -> list[tuple[DeduplicationDocument, int]]: ...


@dataclass(frozen=True, slots=True)
class RecalledCandidate:
    document: DeduplicationDocument
    assessment: CandidateAssessment
    recall_methods: tuple[str, ...]


class PgVectorRecallProvider:
    """Optional recall provider; it never makes a merge decision."""

    def __init__(self, *, enabled: bool, search: PgVectorSearch) -> None:
        self.enabled = enabled
        self._search = search

    async def recall(
        self, query: DeduplicationDocument, *, limit: int = 100
    ) -> list[tuple[DeduplicationDocument, int]]:
        if not self.enabled:
            return []
        return await self._search(query, limit=limit)


def merge_rule_and_vector_recall(
    query: DeduplicationDocument,
    *,
    rule_candidates: list[DeduplicationDocument],
    vector_candidates: list[tuple[DeduplicationDocument, int]],
) -> list[RecalledCandidate]:
    combined: dict[str, tuple[DeduplicationDocument, int | None, set[str]]] = {}
    for document in rule_candidates:
        key = document.canonical_url or f"{document.source_id}:{document.external_id}"
        combined[key] = (document, None, {"RULE"})
    for document, similarity in vector_candidates:
        key = document.canonical_url or f"{document.source_id}:{document.external_id}"
        current = combined.get(key)
        if current is None:
            combined[key] = (document, similarity, {"PGVECTOR"})
        else:
            combined[key] = (
                current[0],
                max(current[1] or 0, similarity),
                current[2] | {"PGVECTOR"},
            )
    return [
        RecalledCandidate(
            document=document,
            assessment=assess_duplicate(query, document, vector_similarity_bps=similarity),
            recall_methods=tuple(sorted(methods)),
        )
        for document, similarity, methods in combined.values()
    ]
