from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import (
    GoldAnnotationRequest,
    GoldSampleKind,
    GoldTaskCreateRequest,
    OperatorTaskCompleteRequest,
    OperatorTaskCreateRequest,
    OperatorWorkCategory,
    OperatorWorkSessionHeartbeatRequest,
    OperatorWorkSessionStart,
    PilotSourceResumeRequest,
    PilotWindowCompleteRequest,
    PilotWindowCreateRequest,
    PilotWindowState,
    UserRole,
)


def _source_codes() -> list[str]:
    return [f"GOV-{index:03d}" for index in range(1, 21)]


def test_round17_contracts_freeze_window_and_source_cohort() -> None:
    request = PilotWindowCreateRequest(
        roster_version="r17-sources-v0.1",
        metric_definition_version="phase2-round17-metrics-v1.0.0",
        gold_definition_version="phase2-round17-gold-v1.0.0",
        baseline_commit="b08513965e931f363283384037fc1c1f068a1b1c",
        config_version="round17-config-v1",
        database_revision="0017b_round17_pilot",
        source_codes=_source_codes(),
        reason="prepare the approved Round 17 pilot cohort",
    )

    assert request.environment == "PREPRODUCTION"
    assert request.duration_hours == 168
    assert len(request.source_codes) == 20
    assert PilotWindowState.RUNNING.value == "RUNNING"

    with pytest.raises(ValidationError):
        PilotWindowCreateRequest(
            **(request.model_dump() | {"source_codes": _source_codes()[:-1]})
        )
    with pytest.raises(ValidationError):
        PilotWindowCreateRequest(
            **(request.model_dump() | {"source_codes": [*_source_codes()[:-1], "GOV-001"]})
        )


def test_round17_lifecycle_commands_are_versioned_and_reason_bounded() -> None:
    resume = PilotSourceResumeRequest(
        expected_version=4,
        reason="resume after the authoritative source approval was repaired",
    )
    complete = PilotWindowCompleteRequest(
        expected_version=5,
        reason="complete the elapsed observation window with honest source states",
    )

    assert resume.expected_version == 4
    assert complete.expected_version == 5
    with pytest.raises(ValidationError):
        PilotSourceResumeRequest.model_validate(
            {"expected_version": 0, "reason": "too early"}
        )
    with pytest.raises(ValidationError):
        PilotWindowCompleteRequest.model_validate(
            {
                "expected_version": 5,
                "reason": "complete elapsed observation window",
                "force": True,
            }
        )


def test_gold_and_work_inputs_are_bounded_and_cannot_carry_source_body() -> None:
    annotation = GoldAnnotationRequest(
        task_id=UUID("019b1700-0000-7000-8000-000000000101"),
        sample_kind=GoldSampleKind.CLAIM_EVIDENCE,
        decision_code="SUPPORTED",
        label_value="publication_date=2026-07-16",
        evidence_ids=[UUID("019b1700-0000-7000-8000-000000000102")],
        related_sample_refs=[],
    )
    assert annotation.sample_kind is GoldSampleKind.CLAIM_EVIDENCE

    session = OperatorWorkSessionStart(
        task_id=UUID("019b1700-0000-7000-8000-000000000103"),
    )
    assert session.task_id.version == 7
    assert OperatorWorkSessionHeartbeatRequest(expected_version=1).expected_version == 1
    with pytest.raises(ValidationError):
        OperatorWorkSessionStart.model_validate(
            {
                "task_id": "019b1700-0000-7000-8000-000000000103",
                "body": "forbidden source text",
            }
        )
    with pytest.raises(ValidationError):
        OperatorWorkSessionHeartbeatRequest.model_validate(
            {"expected_version": 1, "note": "forbidden operational text"}
        )


def test_operator_task_contract_separates_leo_control_from_yinzi_execution() -> None:
    task = OperatorTaskCreateRequest(
        window_id=UUID("019b1700-0000-7000-8000-000000000103"),
        source_id=UUID("019b1700-0000-7000-8000-000000000104"),
        category=OperatorWorkCategory.EXCEPTION_HANDLING,
        reason="assign one bounded source exception task to yinzi",
    )
    assert task.source_id is not None and task.source_id.version == 7
    assert OperatorTaskCompleteRequest(
        expected_version=2,
        reason="close the stopped and reviewed operator task",
    ).expected_version == 2
    with pytest.raises(ValidationError):
        OperatorTaskCreateRequest.model_validate(
            task.model_dump() | {"url": "https://forbidden.example/source"}
        )
    with pytest.raises(ValidationError):
        OperatorTaskCompleteRequest.model_validate(
            {
                "expected_version": 2,
                "reason": "close the stopped task",
                "active_seconds": 300,
            }
        )


def test_round17_adds_only_the_bounded_human_gold_roles() -> None:
    assert UserRole.GOLD_ANNOTATOR.value == "gold_annotator"
    assert UserRole.GOLD_ARBITRATOR.value == "gold_arbitrator"


def test_gold_task_cannot_use_free_text_as_sample_identity() -> None:
    with pytest.raises(ValidationError):
        GoldTaskCreateRequest.model_validate(
            {
                "sample_kind": "DOCUMENT",
                "sample_ref": "copied-source-body",
                "assigned_annotator_ids": [
                    "019b1700-0000-7000-8000-000000000111"
                ],
                "critical_safety": False,
                "reason": "assign approved gold sample",
            }
        )
