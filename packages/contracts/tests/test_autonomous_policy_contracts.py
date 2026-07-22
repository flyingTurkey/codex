from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import (
    AutomatedDecisionReason,
    AutomatedDisposition,
    AutonomousClassificationCandidate,
    ExceptionKind,
    FeedSuppressionAction,
    FeedSuppressionCommand,
    FeedSuppressionRuleView,
    FeedSuppressionScope,
    OwnerExceptionCommand,
    OwnerExceptionEventType,
    OwnerExceptionEventView,
    OwnerExceptionView,
    PolicyEvaluationMode,
    PolicyEvaluationSummary,
    QualificationDecisionTrace,
    QualificationPolicyIdentity,
    SafetyOverrideability,
    ShadowDecisionView,
)


def _candidate(**overrides: object) -> dict[str, object]:
    return {
        "direct_relevance": "RELEVANT",
        "core_new_fact": "铁路隧道施工采用新的有害气体监测措施",
        "primary_type": "SAFETY_INTELLIGENCE",
        "engineering_objects": ["RAILWAY", "TUNNEL"],
        "specialty_facets": ["TUNNEL_GAS_MONITORING"],
        "equipment_domains": [],
        "content_form": "PROJECT_RECORD",
        "evidence_locators": ["html:p:8"],
        "ambiguity_indicators": [],
        "security_signals": [],
        "confidence": 0.98,
    } | overrides


def test_automated_disposition_is_the_frozen_shared_terminal_vocabulary() -> None:
    assert {value.value for value in AutomatedDisposition} == {
        "AUTO_ACCEPTED",
        "AUTO_FILTERED",
        "TECHNICAL_RETRY",
        "TECHNICAL_FAILED",
        "SAFETY_HOLD",
        "OWNER_SUPPRESSED",
    }


@pytest.mark.parametrize(
    "authority_field",
    [
        "publication_status",
        "source_authorized",
        "review_decision",
        "safety_resolved",
    ],
)
def test_model_candidate_cannot_submit_server_authority(authority_field: str) -> None:
    with pytest.raises(ValidationError):
        AutonomousClassificationCandidate.model_validate(_candidate(**{authority_field: True}))


def test_policy_identity_binds_every_version_and_server_digest() -> None:
    identity = QualificationPolicyIdentity.model_validate(
        {
            "policy_version": "qualification-policy-2.0.0",
            "global_rule_version": "global-rules-2.0.0",
            "source_stream_policy_version": "stream-policy-7",
            "ai_provider": "protocol-equivalent-test",
            "ai_model": "semantic-classifier-v2",
            "prompt_version": "autonomous-classify-2.0.0",
            "schema_version": "autonomous-classify-output-2.0.0",
            "code_version": "ead5820-test",
            "bundle_sha256": "a" * 64,
        }
    )

    assert identity.bundle_sha256 == "a" * 64
    with pytest.raises(ValidationError):
        QualificationPolicyIdentity.model_validate(
            identity.model_dump() | {"bundle_sha256": "client-claimed"}
        )


def test_shared_exception_suppression_and_shadow_vocabularies_are_closed() -> None:
    assert {value.value for value in ExceptionKind} == {"TECHNICAL", "SAFETY"}
    assert {value.value for value in SafetyOverrideability} == {
        "OWNER_DECIDABLE",
        "HARD_BLOCK",
    }
    assert {value.value for value in FeedSuppressionScope} == {
        "EVENT",
        "PRIMARY_TYPE",
        "ENGINEERING_OBJECT",
        "SPECIALTY_FACET",
        "EQUIPMENT_DOMAIN",
        "SOURCE",
        "CUSTOM_TOPIC",
    }
    assert {value.value for value in FeedSuppressionAction} == {"ACTIVATE", "REVOKE"}
    assert {value.value for value in OwnerExceptionEventType} == {
        "CREATED",
        "RETRY_REQUESTED",
        "OWNER_ALLOWED",
        "OWNER_DENIED",
        "AUTO_RESOLVED",
        "SOURCE_DISABLED",
    }
    assert {value.value for value in PolicyEvaluationMode} == {
        "OFFLINE_REPLAY",
        "SHADOW",
    }


def test_owner_override_is_not_a_reason_or_authority_in_the_new_path() -> None:
    assert "OWNER_OVERRIDE_GO" not in {value.value for value in AutomatedDecisionReason}
    with pytest.raises(ValueError):
        AutomatedDecisionReason("OWNER_OVERRIDE_GO")


def test_decision_trace_allows_at_most_one_semantic_readjudication() -> None:
    payload = {
        "decision_id": "019b1d00-0000-7000-8000-000000000041",
        "document_version_id": "019b1d00-0000-7000-8000-000000000042",
        "raw_object_id": "019b1d00-0000-7000-8000-000000000043",
        "normalized_input_sha256": "b" * 64,
        "policy": {
            "policy_version": "qualification-policy-2.0.0",
            "global_rule_version": "global-rules-2.0.0",
            "source_stream_policy_version": "stream-policy-7",
            "ai_provider": "protocol-equivalent-test",
            "ai_model": "semantic-classifier-v2",
            "prompt_version": "autonomous-classify-2.0.0",
            "schema_version": "autonomous-classify-output-2.0.0",
            "code_version": "ead5820-test",
            "bundle_sha256": "a" * 64,
        },
        "disposition": "AUTO_FILTERED",
        "reason_codes": ["AI_AMBIGUITY_UNRESOLVED"],
        "rule_signals": ["PRIMARY_TYPE_TIE"],
        "model_candidate": _candidate(direct_relevance="AMBIGUOUS", primary_type=None),
        "evidence_locators": ["html:p:8"],
        "semantic_recheck_count": 1,
        "decided_at": "2026-07-21T08:00:00Z",
    }
    assert QualificationDecisionTrace.model_validate(payload).semantic_recheck_count == 1
    with pytest.raises(ValidationError):
        QualificationDecisionTrace.model_validate(payload | {"semantic_recheck_count": 2})


def test_owner_exception_contract_separates_technical_and_safety_controls() -> None:
    base = {
        "id": "019b1d00-0000-7000-8000-000000000051",
        "kind": "SAFETY",
        "status": "OPEN",
        "overrideability": "HARD_BLOCK",
        "reason_codes": ["SAFETY_SIGNAL"],
        "attempt_count": 0,
        "version": 1,
        "opened_at": "2026-07-21T08:00:00Z",
        "updated_at": "2026-07-21T08:00:00Z",
    }
    assert OwnerExceptionView.model_validate(base).overrideability == "HARD_BLOCK"
    assert OwnerExceptionView.model_validate(base).technical_reason_code is None
    with pytest.raises(ValidationError):
        OwnerExceptionView.model_validate(
            base | {"kind": "TECHNICAL", "overrideability": "OWNER_DECIDABLE"}
        )
    technical = OwnerExceptionView.model_validate(
        base
        | {
            "kind": "TECHNICAL",
            "overrideability": None,
            "technical_reason_code": "PROVIDER_TIMEOUT",
        }
    )
    assert technical.technical_reason_code == "PROVIDER_TIMEOUT"
    with pytest.raises(ValidationError):
        OwnerExceptionView.model_validate(base | {"technical_reason_code": "PROVIDER_TIMEOUT"})
    with pytest.raises(ValidationError):
        OwnerExceptionView.model_validate(
            base
            | {
                "kind": "TECHNICAL",
                "overrideability": None,
                "technical_reason_code": "unsafe reason",
            }
        )


def test_suppression_command_is_preference_only_and_rejects_authority_fields() -> None:
    command = {
        "action": "ACTIVATE",
        "scope": "SOURCE",
        "target_key": "source:example",
        "feedback_reason": "OWNER_PREFERENCE",
    }
    assert FeedSuppressionCommand.model_validate(command).scope == "SOURCE"
    with pytest.raises(ValidationError):
        FeedSuppressionCommand.model_validate(command | {"publication_authorized": True})
    with pytest.raises(ValidationError):
        FeedSuppressionCommand.model_validate(command | {"action": "REVOKE"})

    superseded_rule = "019b1d00-0000-7000-8000-000000000053"
    revoked = FeedSuppressionCommand.model_validate(
        command | {"action": "REVOKE", "supersedes_rule_id": superseded_rule}
    )
    view = FeedSuppressionRuleView.model_validate(
        revoked.model_dump()
        | {
            "id": "019b1d00-0000-7000-8000-000000000054",
            "effective_at": "2026-07-21T08:00:00Z",
            "created_at": "2026-07-21T08:00:00Z",
        }
    )
    assert view.supersedes_rule_id == UUID(superseded_rule)


def test_owner_exception_commands_exclude_server_generated_events() -> None:
    command = {
        "exception_id": "019b1d00-0000-7000-8000-000000000055",
        "event_type": "OWNER_ALLOWED",
        "expected_version": 1,
    }
    assert OwnerExceptionCommand.model_validate(command).event_type == "OWNER_ALLOWED"
    with pytest.raises(ValidationError):
        OwnerExceptionCommand.model_validate(command | {"event_type": "AUTO_RESOLVED"})
    with pytest.raises(ValidationError):
        OwnerExceptionCommand.model_validate(command | {"event_type": "SOURCE_DISABLED"})
    event = OwnerExceptionEventView.model_validate(
        command
        | {
            "id": "019b1d00-0000-7000-8000-000000000057",
            "idempotency_key": "019b1d00-0000-7000-8000-000000000056",
            "created_at": "2026-07-21T08:00:00Z",
        }
    )
    assert event.expected_version == 1


def test_offline_and_shadow_contracts_can_never_authorize_production() -> None:
    evaluation = {
        "id": "019b1d00-0000-7000-8000-000000000053",
        "policy": {
            "policy_version": "qualification-policy-2.0.0",
            "global_rule_version": "global-rules-2.0.0",
            "source_stream_policy_version": "stream-policy-7",
            "ai_provider": "protocol-equivalent-test",
            "ai_model": "semantic-classifier-v2",
            "prompt_version": "autonomous-classify-2.0.0",
            "schema_version": "autonomous-classify-output-2.0.0",
            "code_version": "ead5820-test",
            "bundle_sha256": "a" * 64,
        },
        "mode": "OFFLINE_REPLAY",
        "benchmark_version": "private-v4",
        "corpus_manifest_sha256": "b" * 64,
        "total_cases": 40,
        "auto_accepted_count": 20,
        "auto_filtered_count": 20,
        "precision_bps": 9000,
        "recall_bps": 9000,
        "locked_negative_leaks": 0,
        "schema_valid_bps": 10000,
        "new_owner_semantic_tasks": 0,
        "gate_passed": True,
        "authorizes_production": False,
        "evaluated_at": "2026-07-21T08:00:00Z",
    }
    assert PolicyEvaluationSummary.model_validate(evaluation).gate_passed is True
    with pytest.raises(ValidationError):
        PolicyEvaluationSummary.model_validate(evaluation | {"authorizes_production": True})
    for invalid in (
        {"total_cases": 0, "auto_accepted_count": 0, "auto_filtered_count": 0},
        {"precision_bps": 8999},
        {"recall_bps": 8999},
        {"locked_negative_leaks": 1},
        {"schema_valid_bps": 9999},
    ):
        with pytest.raises(ValidationError):
            PolicyEvaluationSummary.model_validate(evaluation | invalid)

    shadow = {
        "id": "019b1d00-0000-7000-8000-000000000054",
        "evaluation_id": evaluation["id"],
        "document_version_id": "019b1d00-0000-7000-8000-000000000055",
        "disposition": "AUTO_FILTERED",
        "reason_codes": ["POLICY_GATE_FAILED"],
        "affects_production": False,
        "decided_at": "2026-07-21T08:00:00Z",
    }
    assert ShadowDecisionView.model_validate(shadow).affects_production is False
    with pytest.raises(ValidationError):
        ShadowDecisionView.model_validate(shadow | {"affects_production": True})
