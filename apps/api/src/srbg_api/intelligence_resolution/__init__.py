"""Explainable identity resolution, clustering, lineage, and scoring."""

from srbg_api.intelligence_resolution.domain import (
    CandidateAssessment,
    DeduplicationDocument,
    ScoreValue,
    SourceLineage,
    assess_duplicate,
    calculate_scores,
    count_independent_sources,
    exact_identity_matches,
)

__all__ = [
    "CandidateAssessment",
    "DeduplicationDocument",
    "ScoreValue",
    "SourceLineage",
    "assess_duplicate",
    "calculate_scores",
    "count_independent_sources",
    "exact_identity_matches",
]
