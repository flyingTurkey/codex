"""Rules and adapters for automated source discovery and qualification."""

from srbg_api.source_automation.domain import (
    AuthorizedCandidateDecision,
    AutomationRuleViolation,
    QualificationAssessment,
    QualificationFacts,
    authorize_candidate_decision,
    evaluate_qualification,
    validate_batch_enable,
)

__all__ = [
    "AuthorizedCandidateDecision",
    "AutomationRuleViolation",
    "QualificationAssessment",
    "QualificationFacts",
    "authorize_candidate_decision",
    "evaluate_qualification",
    "validate_batch_enable",
]
