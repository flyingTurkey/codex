import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
import srbg_contracts.models as models
from pydantic import ValidationError

EVENT_ID = UUID("019b0000-0000-7000-8000-000000009001")
ITEM_ID = UUID("019b0000-0000-7000-8000-000000009002")
CLAIM_ID = UUID("019b0000-0000-7000-8000-000000009003")
EVIDENCE_ID = UUID("019b0000-0000-7000-8000-000000009004")
CONFLICT_ID = UUID("019b0000-0000-7000-8000-000000009005")


def test_safety_case_profile_metadata_authorization_field_set_is_closed() -> None:
    assert {field.value for field in models.SafetyCaseProfileMetadataField} == {
        "report_stage",
        "incident_status",
        "accident_type",
        "engineering_type",
        "occurred_at",
        "region_name",
        "project_name",
        "rectification_has_open_issues",
        "similar_scenario_tags",
        "prevention_measure_tags",
    }


def test_event_candidate_generation_response_is_always_pending_human_review() -> None:
    response = models.EventCandidateGenerationResponse(
        candidate_id=CLAIM_ID,
        status="PENDING_REVIEW",
        requires_human_review=True,
    )

    assert response.model_dump(mode="json") == {
        "candidate_id": str(CLAIM_ID),
        "status": "PENDING_REVIEW",
        "requires_human_review": True,
    }

    with pytest.raises(ValidationError):
        models.EventCandidateGenerationResponse(
            candidate_id=CLAIM_ID,
            status="PENDING_REVIEW",
            requires_human_review=False,
        )
    with pytest.raises(ValidationError):
        models.EventCandidateGenerationResponse(candidate_id=CLAIM_ID)


def test_reviewer_claim_projection_exposes_optional_field_decision_status() -> None:
    pending = models.ClaimView(
        id=CLAIM_ID,
        claim_type="deaths",
        label="死亡人数",
        value="52",
        evidence_ids=[EVIDENCE_ID],
        decision_status="PENDING",
    )
    legacy = models.ClaimView(
        id=CLAIM_ID,
        claim_type="title",
        label="标题",
        value="测试标题",
        evidence_ids=[EVIDENCE_ID],
    )

    assert pending.decision_status == "PENDING"
    assert "decision_status" not in legacy.model_dump(exclude_unset=True)

    with pytest.raises(ValidationError):
        models.ClaimView(
            id=CLAIM_ID,
            claim_type="deaths",
            label="死亡人数",
            value="52",
            evidence_ids=[EVIDENCE_ID],
            decision_status="PUBLISHED",
        )


def test_safety_regulation_type_summary_payload_remains_backward_compatible() -> None:
    summary = models.SafetyRegulationTypeSummary(
        kind="SAFETY_REGULATION",
        document_number="应急管理部令第 88 号",
        issuing_authority="应急管理部",
        regulation_status="UNKNOWN",
        classification="DEPARTMENT_RULE",
    )

    assert summary.model_dump(mode="json") == {
        "kind": "SAFETY_REGULATION",
        "document_number": "应急管理部令第 88 号",
        "issuing_authority": "应急管理部",
        "regulation_status": "UNKNOWN",
        "classification": "DEPARTMENT_RULE",
    }


def test_safety_case_type_summary_exposes_reviewed_fields_without_scores() -> None:
    summary = models.SafetyCaseTypeSummary(
        kind="SAFETY_CASE",
        event_id=EVENT_ID,
        report_stage="FINAL_INVESTIGATION",
        incident_status="FINAL_INVESTIGATION_REPORT",
        hazard_type="GEOLOGICAL_DISASTER",
        engineering_type="HIGHWAY",
        occurred_at=datetime(2024, 5, 1, 2, 10, tzinfo=UTC),
        region="广东省梅州市大埔县",
        deaths=52,
        injuries=30,
        loss_amount_minor=123_000_000,
        loss_currency="CNY",
        conflicted_fields=[],
        official_direct_causes=[],
        responsibility_findings=None,
        rectification_has_open_issues=True,
        similar_scenario_tags=["HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
        prevention_measure_tags=["MONITORING_AND_EARLY_WARNING"],
    )

    payload = summary.model_dump(mode="json", exclude_unset=True)

    assert payload["kind"] == "SAFETY_CASE"
    assert payload["official_direct_causes"] == []
    assert payload["responsibility_findings"] is None
    assert payload["loss_amount_minor"] == 123_000_000
    assert payload["rectification_has_open_issues"] is True
    assert "scores" not in payload


def test_r3_restricted_safety_case_can_omit_every_sensitive_summary_field() -> None:
    item = models.ItemSummary(
        id=ITEM_ID,
        publication_revision_id=None,
        domain="SAFETY",
        content_type="SAFETY_CASE",
        title="梅大高速茶阳路段塌方灾害初报",
        source_name="大埔县人民政府",
        source_published_at=datetime(2024, 5, 1, 8, tzinfo=UTC),
        first_discovered_at=datetime(2026, 7, 14, tzinfo=UTC),
        activity_at=datetime(2026, 7, 14, tzinfo=UTC),
        original_url="https://example.test/initial-report",
        review_status="PENDING",
    )

    payload = item.model_dump(mode="json", exclude_unset=True)

    assert payload["content_type"] == "SAFETY_CASE"
    assert "type_summary" not in payload
    assert "one_sentence_fact" not in payload


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("DEATH_COUNT", {"deaths": 52}),
        ("INJURY_COUNT", {"injuries": 30}),
        ("LOSS_AMOUNT_MINOR", {"loss_amount_minor": 1}),
        ("OFFICIAL_DIRECT_CAUSES", {"official_direct_causes": ["原因"]}),
        ("RESPONSIBILITY_FINDINGS", {"responsibility_findings": ["责任"]}),
    ],
)
def test_conflicted_safety_case_fields_cannot_leak_current_values(
    field: str, kwargs: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        models.SafetyCaseTypeSummary(
            kind="SAFETY_CASE",
            conflicted_fields=[field],
            **kwargs,
        )


def test_event_detail_links_confirmed_facts_to_existing_item_evidence() -> None:
    reviewed_at = datetime(2025, 1, 22, 8, tzinfo=UTC)
    timeline_item = models.EventItem(
        item_id=ITEM_ID,
        title="梅大高速茶阳路段塌方灾害调查报告",
        report_stage="FINAL_INVESTIGATION",
        incident_status="FINAL_INVESTIGATION_REPORT",
        source_name="广东省应急管理厅",
        source_published_at=reviewed_at,
        original_url="https://example.test/investigation",
        review_status="APPROVED",
        publication_revision_id=None,
        relation_type="INVESTIGATES",
        evidence_count=4,
    )
    detail = models.EventDetail(
        id=EVENT_ID,
        event_type="SAFETY_INCIDENT",
        title="梅大高速茶阳路段塌方灾害",
        project_name="梅大高速",
        occurred_at=datetime(2024, 5, 1, 2, 10, tzinfo=UTC),
        region="广东省梅州市大埔县",
        hazard_type="GEOLOGICAL_DISASTER",
        engineering_type="HIGHWAY",
        incident_status="FINAL_INVESTIGATION_REPORT",
        rectification_has_open_issues=True,
        confirmed_facts=[
            models.ConfirmedFact(
                source_item_id=ITEM_ID,
                claim_id=CLAIM_ID,
                field="DEATH_COUNT",
                label="死亡人数",
                value=52,
                unit="人",
                evidence_ids=[EVIDENCE_ID],
                reviewed_at=reviewed_at,
            )
        ],
        unverified_facts=[
            models.UnverifiedFact(
                source_item_id=ITEM_ID,
                claim_id=CLAIM_ID,
                conflict_id=CONFLICT_ID,
                field="INJURY_COUNT",
                label="受伤人数",
                status="CONFLICTING",
                reason="不同阶段官方数字不一致, 等待人工裁决",
                evidence_ids=[EVIDENCE_ID],
            )
        ],
        timeline=models.EventTimeline(event_id=EVENT_ID, items=[timeline_item]),
        relations=[],
        similar_scenario_tags=["HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
        prevention_measure_tags=["MONITORING_AND_EARLY_WARNING"],
    )

    payload = detail.model_dump(mode="json")

    assert payload["confirmed_facts"][0]["source_item_id"] == str(ITEM_ID)
    assert payload["unverified_facts"][0]["value"] is None
    assert payload["unverified_facts"][0]["display_value"] == "待核实"
    assert payload["timeline"]["items"][0]["relation_type"] == "INVESTIGATES"
    assert payload["rectification_has_open_issues"] is True


def test_conflicting_unverified_fact_requires_conflict_id_and_never_accepts_value() -> None:
    with pytest.raises(ValidationError):
        models.UnverifiedFact(
            source_item_id=ITEM_ID,
            claim_id=CLAIM_ID,
            field="DEATH_COUNT",
            label="死亡人数",
            status="CONFLICTING",
            reason="数字冲突",
            evidence_ids=[EVIDENCE_ID],
        )

    with pytest.raises(ValidationError):
        models.UnverifiedFact(
            source_item_id=ITEM_ID,
            claim_id=CLAIM_ID,
            conflict_id=CONFLICT_ID,
            field="DEATH_COUNT",
            label="死亡人数",
            value=52,
            status="CONFLICTING",
            reason="数字冲突",
            evidence_ids=[EVIDENCE_ID],
        )


def test_claim_conflict_review_decision_is_bounded_and_auditable() -> None:
    request = models.ClaimConflictDecisionRequest(
        action="ACCEPT_CANDIDATE",
        reason="正式调查报告取代初报数字",
    )
    response = models.ClaimConflictDecisionResponse(
        conflict_id=CONFLICT_ID,
        status="RESOLVED",
        action="ACCEPT_CANDIDATE",
        resolved_claim_id=CLAIM_ID,
        resolved_at=datetime(2025, 1, 22, 9, tzinfo=UTC),
    )

    assert request.action == "ACCEPT_CANDIDATE"
    assert response.status == "RESOLVED"

    with pytest.raises(ValidationError):
        models.ClaimConflictDecisionRequest(action="PUBLISH", reason="绕过人工审核")

    with pytest.raises(ValidationError):
        models.ClaimConflictDecisionResponse(
            conflict_id=CONFLICT_ID,
            status="RESOLVED",
            action="ACCEPT_CANDIDATE",
            resolved_claim_id=None,
            resolved_at=None,
        )

    with pytest.raises(ValidationError):
        models.ClaimConflictDecisionResponse(
            conflict_id=CONFLICT_ID,
            status="PENDING_REVIEW",
            action="KEEP_CURRENT",
            resolved_claim_id=CLAIM_ID,
            resolved_at=datetime(2025, 1, 22, 9, tzinfo=UTC),
        )


def test_taxonomy_and_published_sample_use_controlled_round04_vocabulary() -> None:
    taxonomy = Path("docs/codex-kit/assets/taxonomy.yaml").read_text(encoding="utf-8")
    items = json.loads(Path("docs/codex-kit/assets/sample_items.json").read_text(encoding="utf-8"))
    safety_case = next(item for item in items if item["item_type"] == "SAFETY_CASE")

    assert 'version: "1.2.0"' in taxonomy
    assert "safety_case_report_stages:" in taxonomy
    for stage in (
        "INITIAL_REPORT",
        "FOLLOW_UP_REPORT",
        "FINAL_INVESTIGATION",
        "ENFORCEMENT",
        "RECTIFICATION",
    ):
        assert f"  - {stage}" in taxonomy
    assert "prevention_measure_tags:" in taxonomy
    assert "  - MONITORING_AND_EARLY_WARNING" in taxonomy
    assert "similar_scenario_tags:" in taxonomy
    assert "  - HIGHWAY_OPERATION_GEOLOGICAL_RISK" in taxonomy
    assert safety_case["schema_version"] == "1.1.0"
    assert safety_case["profile"]["report_stage"] == "FINAL_INVESTIGATION"
    assert safety_case["profile"]["official_direct_causes"] is None
    assert safety_case["profile"]["responsibility_findings"] is None


def test_published_content_schema_is_versioned_and_hides_conflicted_values() -> None:
    schema = json.loads(
        Path("docs/codex-kit/assets/content.schema.json").read_text(encoding="utf-8")
    )
    profile = schema["$defs"]["safety_case_profile"]

    assert schema["$id"].endswith("intelligence-item-1.1.0.json")
    assert schema["properties"]["schema_version"]["const"] == "1.1.0"
    assert set(profile["properties"]["report_stage"]["enum"]) == {
        "INITIAL_REPORT",
        "FOLLOW_UP_REPORT",
        "FINAL_INVESTIGATION",
        "ENFORCEMENT",
        "RECTIFICATION",
    }
    assert profile["properties"]["official_direct_causes"]["type"] == ["array", "null"]
    assert profile["properties"]["responsibility_findings"]["type"] == ["array", "null"]
    assert len(profile["allOf"]) >= 5
