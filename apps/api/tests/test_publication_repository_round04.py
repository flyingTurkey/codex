from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import srbg_api.publication.repository as repository
from srbg_api.publication.service import PublicationDenied

ITEM_ID = UUID("019b0000-0000-7000-8000-000000044001")
EVENT_ID = UUID("019b0000-0000-7000-8000-000000044002")
CLAIM_ID = UUID("019b0000-0000-7000-8000-000000044003")
EVIDENCE_ID = UUID("019b0000-0000-7000-8000-000000044010")
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000044020")
SUBMITTER_ID = UUID("019b0000-0000-7000-8000-000000044021")
TARGET_SUBMITTER_ID = UUID("019b0000-0000-7000-8000-000000044022")


def _claim_row(
    *,
    claim_id: UUID = CLAIM_ID,
    claim_type: str = "deaths",
    value: object = 52,
    decision: str | None = "ACCEPT",
    verification_status: str = "CANDIDATE",
    excerpt: str = "事故造成52人死亡",
) -> dict[str, object]:
    return {
        "id": claim_id,
        "item_id": ITEM_ID,
        "claim_type": claim_type,
        "literal_value": value,
        "verification_status": verification_status,
        "field_decision_action": decision,
        "critical": True,
        "confidence_bps": 10000,
        "evidence_id": EVIDENCE_ID,
        "field_decision_evidence_id": EVIDENCE_ID,
        "paragraph_id": "html-p-0001",
        "char_start": 0,
        "char_end": len(excerpt),
        "excerpt": excerpt,
        "excerpt_sha256": sha256(excerpt.encode()).hexdigest(),
        "locator_type": "HTML_PARAGRAPH",
        "page_number": None,
        "document_text_block_id": None,
        "x0_mpt": None,
        "y0_mpt": None,
        "x1_mpt": None,
        "y1_mpt": None,
        "evidence_confidence_bps": 10000,
        "block_text": None,
    }


def test_safety_case_evidence_uses_latest_field_decision_not_parser_status() -> None:
    accepted = _claim_row()
    rejected_media = _claim_row(
        claim_id=UUID("019b0000-0000-7000-8000-000000044004"),
        claim_type="official_direct_causes",
        value=["媒体推测"],
        decision="REJECT",
        verification_status="ACCEPTED",
        excerpt="媒体推测",
    )

    result = repository._evaluate_evidence(  # pyright: ignore[reportPrivateUsage]
        [accepted, rejected_media],
        [{"paragraph_id": "html-p-0001", "text": "事故造成52人死亡"}],
        item_type="SAFETY_CASE",
    )

    assert result["claim_count"] == 1
    assert result["evidence_count"] == 1
    assert result["accepted_critical_claim_coverage_percent"] == 100
    assert result["bidirectional_refs_valid"] is True


def test_safety_case_evidence_validates_the_exact_human_selected_evidence() -> None:
    selected = _claim_row(excerpt="official evidence")
    unselected = {
        **selected,
        "evidence_id": UUID("019b0000-0000-7000-8000-000000044011"),
        "excerpt": "unselected broken locator",
        "excerpt_sha256": "0" * 64,
        "char_start": 999,
        "char_end": 1024,
    }

    result = repository._evaluate_evidence(  # pyright: ignore[reportPrivateUsage]
        [selected, unselected],
        [{"paragraph_id": "html-p-0001", "text": "official evidence"}],
        item_type="SAFETY_CASE",
    )

    assert result["evidence_count"] == 1
    assert result["bidirectional_refs_valid"] is True
    assert result["locators_verified"] is True
    assert result["excerpts_match_source"] is True
    assert repository._candidate_schema_valid(  # pyright: ignore[reportPrivateUsage]
        [selected, unselected], item_type="SAFETY_CASE"
    )


def test_safety_case_candidate_schema_accepts_only_typed_protected_candidates() -> None:
    assert repository._candidate_schema_valid(  # pyright: ignore[reportPrivateUsage]
        [_claim_row()], item_type="SAFETY_CASE"
    )
    assert not repository._candidate_schema_valid(  # pyright: ignore[reportPrivateUsage]
        [_claim_row(value=-1)], item_type="SAFETY_CASE"
    )
    assert not repository._candidate_schema_valid(  # pyright: ignore[reportPrivateUsage]
        [_claim_row(claim_type="site_operation_instruction", value="立即封路")],
        item_type="SAFETY_CASE",
    )


def test_safety_case_evidence_allows_accepted_non_protected_metadata() -> None:
    title = {
        **_claim_row(
            claim_type="title",
            value="Official rectification follow-up",
            decision=None,
            verification_status="ACCEPTED",
            excerpt="Official rectification follow-up",
        ),
        "critical": False,
    }

    result = repository._evaluate_evidence(  # pyright: ignore[reportPrivateUsage]
        [title],
        [
            {
                "paragraph_id": "html-p-0001",
                "text": "Official rectification follow-up",
            }
        ],
        item_type="SAFETY_CASE",
    )

    assert result["claim_count"] == 1
    assert result["evidence_count"] == 1
    assert repository._candidate_schema_valid(  # pyright: ignore[reportPrivateUsage]
        [title], item_type="SAFETY_CASE"
    )


def test_safety_case_candidate_schema_rejects_accepted_operational_content() -> None:
    operational = {
        **_claim_row(
            claim_type="operational_instructions",
            value="Close the road immediately",
            decision=None,
            verification_status="ACCEPTED",
            excerpt="Close the road immediately",
        ),
        "critical": False,
    }

    assert not repository._candidate_schema_valid(  # pyright: ignore[reportPrivateUsage]
        [operational], item_type="SAFETY_CASE"
    )


def test_revoked_protected_claim_returns_to_unreviewed_queue() -> None:
    pending = _claim_row(decision=None)
    revoked = _claim_row(
        claim_id=UUID("019b0000-0000-7000-8000-000000044012"),
        decision="REVOKE",
    )
    rejected = _claim_row(
        claim_id=UUID("019b0000-0000-7000-8000-000000044013"),
        decision="REJECT",
    )

    assert (
        repository._unreviewed_protected_claim_count(  # pyright: ignore[reportPrivateUsage]
            [pending, revoked, rejected]
        )
        == 2
    )


@pytest.mark.asyncio
async def test_protected_claim_cannot_be_accepted_before_confirmed_event_link() -> None:
    connection = _ClaimDecisionConnection(event_id=None, latest_action=None)

    with pytest.raises(PublicationDenied) as denied:
        await repository._decide_safety_case_claim(  # pyright: ignore[reportPrivateUsage]
            connection,  # type: ignore[arg-type]
            claim_id=CLAIM_ID,
            action="ACCEPT",
            reviewer_id=REVIEWER_ID,
            reason="reviewed official fact",
            decided_at=datetime(2024, 5, 3, tzinfo=UTC),
        )

    assert denied.value.reasons == ("SAFETY_CASE_EVENT_ASSIGNMENT_REQUIRED",)
    assert connection.inserted_decision is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("latest_action", "new_action"),
    (("ACCEPT", "REJECT"), ("REJECT", "ACCEPT")),
)
async def test_protected_claim_decision_cannot_be_flipped(
    latest_action: str,
    new_action: str,
) -> None:
    connection = _ClaimDecisionConnection(
        event_id=EVENT_ID,
        latest_action=latest_action,
    )

    with pytest.raises(PublicationDenied) as denied:
        await repository._decide_safety_case_claim(  # pyright: ignore[reportPrivateUsage]
            connection,  # type: ignore[arg-type]
            claim_id=CLAIM_ID,
            action=new_action,
            reviewer_id=REVIEWER_ID,
            reason="attempted decision flip",
            decided_at=datetime(2024, 5, 3, tzinfo=UTC),
        )

    assert denied.value.reasons == ("CLAIM_ALREADY_DECIDED",)
    assert connection.inserted_decision is False


def test_safety_case_privacy_and_reputational_facts_fail_closed() -> None:
    assert repository._privacy_projection(  # pyright: ignore[reportPrivateUsage]
        item_type="SAFETY_CASE",
        privacy_status="CLEAR",
        reputational_risk_reviewed=False,
    ) == {
        "status": "PENDING_REVIEW",
        "scanner_version": "rules-1.0.0",
        "reputational_risk_reviewed": False,
    }
    assert (
        repository._privacy_projection(  # pyright: ignore[reportPrivateUsage]
            item_type="SAFETY_CASE",
            privacy_status="REDACTED_AND_APPROVED",
            reputational_risk_reviewed=True,
        )["status"]
        == "REDACTED_AND_APPROVED"
    )
    assert (
        repository._privacy_projection(  # pyright: ignore[reportPrivateUsage]
            item_type="SAFETY_REGULATION",
            privacy_status=None,
            reputational_risk_reviewed=None,
        )["status"]
        == "CLEAR"
    )


def test_formal_basis_distinguishes_null_empty_and_findings() -> None:
    assert repository._formal_basis_state(None) == "NO_FORMAL_BASIS"  # pyright: ignore[reportPrivateUsage]
    assert repository._formal_basis_state([]) == "FORMAL_REVIEWED_NO_FINDING"  # pyright: ignore[reportPrivateUsage]
    assert repository._formal_basis_state(["正式认定"]) == "FORMAL_REVIEWED_FINDINGS"  # pyright: ignore[reportPrivateUsage]


def test_profile_metadata_claims_require_matching_accepted_evidenced_values() -> None:
    report_stage = {
        **_claim_row(
            claim_id=UUID("019b0000-0000-7000-8000-000000044030"),
            claim_type="report_stage",
            value="RECTIFICATION",
            decision=None,
            verification_status="ACCEPTED",
            excerpt="整改措施落实情况",
        ),
        "critical": False,
    }
    incident_status = {
        **_claim_row(
            claim_id=UUID("019b0000-0000-7000-8000-000000044031"),
            claim_type="incident_status",
            value="RECTIFICATION_FOLLOW_UP",
            decision=None,
            verification_status="ACCEPTED",
            excerpt="整改措施落实情况评估报告",
        ),
        "critical": False,
        "paragraph_id": "html-p-0002",
    }
    facts = {
        "item_id": ITEM_ID,
        "safety_report_stage": "RECTIFICATION",
        "safety_incident_status": "RECTIFICATION_FOLLOW_UP",
        "safety_accident_type": None,
        "safety_engineering_type": None,
        "safety_occurred_at": None,
        "safety_region_name": None,
        "safety_project_name": None,
        "safety_rectification_has_open_issues": None,
        "safety_similar_scenario_tags": [],
        "safety_prevention_measure_tags": [],
    }
    paragraphs = [
        {
            "paragraph_id": "html-p-0001",
            "text": "整改措施落实情况",
        },
        {"paragraph_id": "html-p-0002", "text": "整改措施落实情况评估报告"},
    ]

    assert repository._profile_metadata_claims_authorized(  # pyright: ignore[reportPrivateUsage]
        facts, [report_stage, incident_status], paragraphs
    )
    assert not repository._profile_metadata_claims_authorized(  # pyright: ignore[reportPrivateUsage]
        facts, [report_stage], paragraphs
    )
    mismatched = {**incident_status, "literal_value": "CLOSED"}
    assert not repository._profile_metadata_claims_authorized(  # pyright: ignore[reportPrivateUsage]
        facts, [report_stage, mismatched], paragraphs
    )
    wrong_item = {
        **incident_status,
        "item_id": UUID("019b0000-0000-7000-8000-000000044099"),
    }
    assert not repository._profile_metadata_claims_authorized(  # pyright: ignore[reportPrivateUsage]
        facts, [report_stage, wrong_item], paragraphs
    )
    broken_evidence = {**incident_status, "excerpt_sha256": "0" * 64}
    assert not repository._profile_metadata_claims_authorized(  # pyright: ignore[reportPrivateUsage]
        facts, [report_stage, broken_evidence], paragraphs
    )
    unrelated_excerpt = "确认死亡人数24人"
    unrelated = {
        **incident_status,
        "excerpt": unrelated_excerpt,
        "excerpt_sha256": sha256(unrelated_excerpt.encode()).hexdigest(),
        "char_end": len(unrelated_excerpt),
        "paragraph_id": "html-p-0003",
    }
    assert not repository._profile_metadata_claims_authorized(  # pyright: ignore[reportPrivateUsage]
        facts,
        [report_stage, unrelated],
        [*paragraphs, {"paragraph_id": "html-p-0003", "text": unrelated_excerpt}],
    )


def test_profile_metadata_value_comparison_is_type_safe_and_canonical() -> None:
    equal = repository._profile_metadata_values_equal  # pyright: ignore[reportPrivateUsage]

    assert equal(
        "occurred_at",
        profile_value=datetime(2024, 5, 1, tzinfo=UTC),
        claim_value="2024-05-01T08:00:00+08:00",
    )
    assert not equal(
        "occurred_at",
        profile_value=datetime(2024, 5, 1, tzinfo=UTC),
        claim_value="2024-05-01T00:00:00",
    )
    assert equal(
        "similar_scenario_tags",
        profile_value=["HIGHWAY_OPERATION_GEOLOGICAL_RISK", "TUNNEL_GEOLOGICAL_RISK"],
        claim_value=["TUNNEL_GEOLOGICAL_RISK", "HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
    )
    assert not equal(
        "similar_scenario_tags",
        profile_value=["TUNNEL_GEOLOGICAL_RISK"],
        claim_value=["TUNNEL_GEOLOGICAL_RISK", "TUNNEL_GEOLOGICAL_RISK"],
    )
    assert equal(
        "rectification_has_open_issues",
        profile_value=False,
        claim_value=False,
    )
    assert not equal(
        "rectification_has_open_issues",
        profile_value=False,
        claim_value=0,
    )
    assert not repository._profile_metadata_value_is_present(None)  # pyright: ignore[reportPrivateUsage]
    assert not repository._profile_metadata_value_is_present([])  # pyright: ignore[reportPrivateUsage]
    assert repository._profile_metadata_value_is_present(False)  # pyright: ignore[reportPrivateUsage]


def test_profile_metadata_evidence_requires_deterministic_semantic_support() -> None:
    supports = repository._profile_metadata_evidence_semantically_supports  # pyright: ignore[reportPrivateUsage]

    assert supports("report_stage", "FINAL_INVESTIGATION", "调查评估组发布调查评估报告")
    assert not supports("report_stage", "FINAL_INVESTIGATION", "确认死亡人数52人")
    assert supports("report_stage", "INITIAL_REPORT", "截至6月12日18时,经现场核查")
    assert supports("incident_status", "UNDER_INVESTIGATION", "新闻发布会通报将继续救援")
    assert supports("accident_type", "ROADBED_COLLAPSE", "高速公路路堤发生塌方灾害")
    assert supports("engineering_type", "EXPRESSWAY", "梅大高速公路")
    assert supports(
        "occurred_at",
        "2024-05-01T01:57:00+08:00",
        "2024 年5 月1 日凌晨1 时57 分许发生灾害",
    )
    assert supports(
        "occurred_at",
        "2024-04-30T17:57:00Z",
        "2024 年5 月1 日凌晨1 时57 分许发生灾害",
    )
    assert not supports(
        "occurred_at",
        "2024-05-01T01:57:00+08:00",
        "2024年5月1日凌晨2时30分发生灾害",
    )
    assert supports("region_name", "广东省", "事故发生在广东省梅州市")
    assert supports("project_name", "梅大高速", "梅大高速茶阳路段发生灾害")
    assert supports(
        "similar_scenario_tags",
        ["HIGHWAY_OPERATION_GEOLOGICAL_RISK", "ROADBED_SLOPE_INSTABILITY"],
        "高速公路地质灾害导致路堤边坡塌方",
    )
    assert not supports(
        "similar_scenario_tags",
        ["HIGHWAY_OPERATION_GEOLOGICAL_RISK", "ROADBED_SLOPE_INSTABILITY"],
        "高速公路加强日常管理",
    )
    assert supports(
        "prevention_measure_tags",
        [
            "MONITORING_AND_EARLY_WARNING",
            "INSPECTION_AND_MAINTENANCE",
            "RESPONSIBILITY_AND_OVERSIGHT",
        ],
        "落实监测预警、巡查养护和责任监管",
    )
    assert supports("rectification_has_open_issues", True, "仍然存在薄弱环节")
    assert "截至5月1日" not in Path(repository.__file__).read_text(encoding="utf-8")


def test_follow_up_metadata_fixture_has_field_specific_semantic_support() -> None:
    values: dict[str, object] = {
        "report_stage": "FOLLOW_UP_REPORT",
        "incident_status": "UNDER_INVESTIGATION",
        "accident_type": "ROADBED_COLLAPSE",
        "engineering_type": "EXPRESSWAY",
        "region_name": "广东省",
        "project_name": "梅大高速",
        "similar_scenario_tags": [
            "HIGHWAY_OPERATION_GEOLOGICAL_RISK",
            "ROADBED_SLOPE_INSTABILITY",
        ],
        "prevention_measure_tags": ["MONITORING_AND_EARLY_WARNING"],
    }
    excerpts = {
        "report_stage": "梅州举行梅大高速茶阳路段塌方救援新闻发布会",
        "incident_status": "接下来,梅州继续组织力量争分夺秒科学救援",
        "accident_type": "5月1日2时01分许,梅大高速茶阳路段发生塌方灾害",
        "engineering_type": "5月1日2时01分许,梅大高速茶阳路段发生塌方灾害",
        "region_name": "广东省公安厅技术专家表示",
        "project_name": "5月1日2时01分许,梅大高速茶阳路段发生塌方灾害",
        "similar_scenario_tags": "5月1日2时01分许,梅大高速茶阳路段发生塌方灾害",
        "prevention_measure_tags": "持续加强气象监测和预报预警",
    }
    rows: list[dict[str, object]] = []
    paragraphs: list[dict[str, object]] = []
    for index, (field, value) in enumerate(values.items(), start=1):
        excerpt = excerpts[field]
        paragraph_id = f"html-p-{index:04d}"
        rows.append(
            {
                **_claim_row(
                    claim_id=UUID(int=100 + index),
                    claim_type=field,
                    value=value,
                    decision=None,
                    verification_status="ACCEPTED",
                    excerpt=excerpt,
                ),
                "critical": False,
                "paragraph_id": paragraph_id,
            }
        )
        paragraphs.append({"paragraph_id": paragraph_id, "text": excerpt})
    facts = {
        "item_id": ITEM_ID,
        "safety_report_stage": values["report_stage"],
        "safety_incident_status": values["incident_status"],
        "safety_accident_type": values["accident_type"],
        "safety_engineering_type": values["engineering_type"],
        "safety_occurred_at": None,
        "safety_region_name": values["region_name"],
        "safety_project_name": values["project_name"],
        "safety_rectification_has_open_issues": None,
        "safety_similar_scenario_tags": values["similar_scenario_tags"],
        "safety_prevention_measure_tags": values["prevention_measure_tags"],
    }

    for row in rows:
        field = str(row["claim_type"])
        assert repository._profile_metadata_evidence_semantically_supports(  # pyright: ignore[reportPrivateUsage]
            field,
            row["literal_value"],
            str(row["excerpt"]),
        ), field
        assert repository._located_evidence_is_valid(  # pyright: ignore[reportPrivateUsage]
            row,
            paragraphs,
        ), field
    assert repository._profile_metadata_claims_authorized(  # pyright: ignore[reportPrivateUsage]
        facts, rows, paragraphs
    )


@pytest.mark.asyncio
async def test_confirmed_event_link_populates_subject_identity_dimension() -> None:
    connection = _EventItemDecisionConnection()

    await repository._decide_event_item_candidate(  # pyright: ignore[reportPrivateUsage]
        connection,  # type: ignore[arg-type]
        candidate_id=CLAIM_ID,
        action="ACCEPT",
        reviewer_id=REVIEWER_ID,
        reason="confirmed same incident",
        decided_at=datetime(2024, 5, 3, tzinfo=UTC),
    )

    assert connection.event_update_parameters is not None
    assert json.loads(str(connection.event_update_parameters["subject_names"])) == [
        "广东博大高速公路有限公司梅大分公司"
    ]


def test_newer_confirmed_material_replaces_non_null_event_identity_facts() -> None:
    source = getsource(repository._decide_event_item_candidate)  # pyright: ignore[reportPrivateUsage]

    for field in (
        "occurred_at",
        "region_code",
        "region_name",
        "project_name",
        "accident_type",
        "engineering_type",
    ):
        assert f"{field} = COALESCE(:{field}, {field})" in source


def test_publication_and_future_conflicts_ignore_resolved_losing_claims() -> None:
    publication_source = getsource(repository._PostgresPublicationTransaction.authoritative_context)  # pyright: ignore[reportPrivateUsage]
    decision_source = getsource(repository._decide_safety_case_claim)  # pyright: ignore[reportPrivateUsage]

    for source in (publication_source, decision_source):
        assert "resolved.status = 'RESOLVED'" in source
        assert "resolution.chosen_claim_id" in source


@pytest.mark.asyncio
@pytest.mark.parametrize("reviewer_id", (SUBMITTER_ID, TARGET_SUBMITTER_ID))
async def test_event_relation_rejects_either_endpoint_submitter(reviewer_id: UUID) -> None:
    connection = _EventRelationDecisionConnection()

    with pytest.raises(PublicationDenied) as denied:
        await repository._decide_event_relation_candidate(  # pyright: ignore[reportPrivateUsage]
            connection,  # type: ignore[arg-type]
            candidate_id=CLAIM_ID,
            action="ACCEPT",
            reviewer_id=reviewer_id,
            reason="must not self-approve either endpoint",
            decided_at=datetime(2024, 5, 3, tzinfo=UTC),
        )

    assert denied.value.reasons == ("DUTIES_NOT_SEPARATED",)
    assert connection.inserted_decision is False


def test_currency_detection_prefers_explicit_currency_over_generic_yuan_suffix() -> None:
    assert repository._explicit_currency_from_evidence("损失100万美元") == "USD"  # pyright: ignore[reportPrivateUsage]
    assert repository._explicit_currency_from_evidence("损失80万欧元") == "EUR"  # pyright: ignore[reportPrivateUsage]
    assert repository._explicit_currency_from_evidence("损失500万元人民币") == "CNY"  # pyright: ignore[reportPrivateUsage]
    assert repository._explicit_currency_from_evidence("损失500万元") == "CNY"  # pyright: ignore[reportPrivateUsage]


def test_controlled_tags_reject_free_text_operational_instructions() -> None:
    assert repository._controlled_tags_only(  # pyright: ignore[reportPrivateUsage]
        ["HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
        ["MONITORING_AND_EARLY_WARNING"],
    )
    assert not repository._controlled_tags_only(  # pyright: ignore[reportPrivateUsage]
        ["HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
        ["立即封路并安排人员现场处置"],
    )


def test_event_relation_stage_semantics_reject_misclassified_lifecycle_links() -> None:
    valid = (
        ("FOLLOW_UP", "FOLLOW_UP_REPORT", "INITIAL_REPORT"),
        ("INVESTIGATES", "FINAL_INVESTIGATION", "FOLLOW_UP_REPORT"),
        ("PENALIZES", "ENFORCEMENT", "FINAL_INVESTIGATION"),
        ("RECTIFIES", "RECTIFICATION", "ENFORCEMENT"),
        ("CORRECTS", "FOLLOW_UP_REPORT", "INITIAL_REPORT"),
    )
    for relation_type, source_stage, target_stage in valid:
        assert repository._event_relation_stages_valid(  # pyright: ignore[reportPrivateUsage]
            relation_type,
            source_stage=source_stage,
            target_stage=target_stage,
            source_order_at=(
                datetime(2024, 5, 2, tzinfo=UTC) if relation_type == "CORRECTS" else None
            ),
            target_order_at=(
                datetime(2024, 5, 1, tzinfo=UTC) if relation_type == "CORRECTS" else None
            ),
        )

    assert not repository._event_relation_stages_valid(  # pyright: ignore[reportPrivateUsage]
        "PENALIZES",
        source_stage="FOLLOW_UP_REPORT",
        target_stage="INITIAL_REPORT",
    )
    assert not repository._event_relation_stages_valid(  # pyright: ignore[reportPrivateUsage]
        "RECTIFIES",
        source_stage="RECTIFICATION",
        target_stage="INITIAL_REPORT",
    )
    assert not repository._event_relation_stages_valid(  # pyright: ignore[reportPrivateUsage]
        "CORRECTS",
        source_stage="INITIAL_REPORT",
        target_stage="FOLLOW_UP_REPORT",
        source_order_at=datetime(2024, 5, 1, tzinfo=UTC),
        target_order_at=datetime(2024, 5, 2, tzinfo=UTC),
    )


def test_event_incident_status_advances_monotonically_and_ignores_terminal_overlays() -> None:
    assert (
        repository._advanced_incident_status(  # pyright: ignore[reportPrivateUsage]
            "INITIAL_OFFICIAL_REPORT", "UNDER_INVESTIGATION"
        )
        == "UNDER_INVESTIGATION"
    )
    assert (
        repository._advanced_incident_status(  # pyright: ignore[reportPrivateUsage]
            "UNDER_INVESTIGATION", "FINAL_INVESTIGATION_REPORT"
        )
        == "FINAL_INVESTIGATION_REPORT"
    )
    assert (
        repository._advanced_incident_status(  # pyright: ignore[reportPrivateUsage]
            "RECTIFICATION_FOLLOW_UP", "INITIAL_OFFICIAL_REPORT"
        )
        == "RECTIFICATION_FOLLOW_UP"
    )
    assert (
        repository._advanced_incident_status(  # pyright: ignore[reportPrivateUsage]
            "FINAL_INVESTIGATION_REPORT", "CORRECTED"
        )
        == "FINAL_INVESTIGATION_REPORT"
    )
    assert (
        repository._advanced_incident_status(  # pyright: ignore[reportPrivateUsage]
            "FINAL_INVESTIGATION_REPORT", "WITHDRAWN"
        )
        == "FINAL_INVESTIGATION_REPORT"
    )


def test_safety_case_revision_snapshot_contains_only_reviewed_profile_projection() -> None:
    snapshot = repository._publication_snapshot(  # pyright: ignore[reportPrivateUsage]
        {
            "item_id": ITEM_ID,
            "item_type": "SAFETY_CASE",
            "title": "梅大高速茶阳路段“5·1”塌方灾害调查报告",
            "source_name": "广东省应急管理厅事故调查报告",
            "original_url": "https://yjgl.gd.gov.cn/example",
            "source_published_at": None,
            "event_id": EVENT_ID,
            "safety_report_stage": "FINAL_INVESTIGATION",
            "safety_incident_status": "FINAL_INVESTIGATION_REPORT",
            "safety_accident_type": "GEOLOGICAL_DISASTER",
            "safety_engineering_type": "HIGHWAY",
            "safety_occurred_at": None,
            "safety_region_name": "广东省梅州市大埔县",
            "safety_project_name": "梅大高速茶阳路段",
            "safety_deaths": 52,
            "safety_injuries": 30,
            "safety_loss_amount_minor": None,
            "safety_loss_currency": None,
            "safety_official_direct_causes": [],
            "safety_responsibility_findings": None,
            "safety_rectification_has_open_issues": None,
            "safety_similar_scenario_tags": ["HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
            "safety_prevention_measure_tags": ["MONITORING_AND_EARLY_WARNING"],
        }
    )

    assert snapshot["profile_type"] == "SAFETY_CASE"
    assert snapshot["event_id"] == str(EVENT_ID)
    assert snapshot["official_direct_causes"] == []
    assert snapshot["responsibility_findings"] is None
    assert "document_number" not in snapshot
    assert "current_value_snapshot" not in snapshot
    assert "candidate_value_snapshot" not in snapshot


def test_publication_facts_are_item_type_discriminated_not_regulation_inner_joined() -> None:
    source = repository.__file__
    assert source is not None
    text_value = Path(source).read_text(encoding="utf-8")

    assert "LEFT JOIN safety_regulation_profile" in text_value
    assert "LEFT JOIN safety_case_profile" in text_value
    assert '"2.1.0",\n            "3.0.0",' in text_value
    assert '"7.0.0",' in text_value
    assert "source.authority_level IN ('A0','A1')" in text_value
    assert '"CORRECTED"' in text_value
    assert 'action="WITHDRAWN"' in text_value


class _MappingResult:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self._row = row

    def mappings(self) -> _MappingResult:
        return self

    def first(self) -> dict[str, object] | None:
        return self._row


class _ClaimDecisionConnection:
    def __init__(self, *, event_id: UUID | None, latest_action: str | None) -> None:
        self.event_id = event_id
        self.latest_action = latest_action
        self.inserted_decision = False

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> _MappingResult:
        del parameters
        sql = str(statement)
        if "SELECT claim.id, claim.item_id" in sql:
            return _MappingResult(
                {
                    "id": CLAIM_ID,
                    "item_id": ITEM_ID,
                    "claim_type": "deaths",
                    "literal_value": 24,
                    "submitted_by": SUBMITTER_ID,
                    "authority_level": "A1",
                    "report_stage": "INITIAL_REPORT",
                    "evidence_id": EVIDENCE_ID,
                    "evidence_role": "PRIMARY_OFFICIAL",
                }
            )
        if "SELECT claim.item_id, claim.claim_type" in sql:
            return _MappingResult(
                {
                    "item_id": ITEM_ID,
                    "claim_type": "deaths",
                    "literal_value": 24,
                    "excerpt": "24 deaths",
                }
            )
        if "INSERT INTO claim_field_decision" in sql:
            self.inserted_decision = True
        return _MappingResult()

    async def scalar(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> Any:
        del parameters
        sql = str(statement)
        if "SELECT event_id FROM event_item" in sql:
            return self.event_id
        if "SELECT decision.action FROM claim_field_decision" in sql:
            return self.latest_action
        return None


class _EventItemDecisionConnection:
    def __init__(self) -> None:
        self.event_update_parameters: dict[str, object] | None = None

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> _MappingResult:
        sql = str(statement)
        if "SELECT candidate.id, candidate.event_id" in sql:
            return _MappingResult(
                {
                    "id": CLAIM_ID,
                    "event_id": EVENT_ID,
                    "item_id": ITEM_ID,
                    "submitted_by": SUBMITTER_ID,
                    "incident_status": "INITIAL_OFFICIAL_REPORT",
                    "occurred_at": datetime(2024, 5, 1, 1, 57, tzinfo=UTC),
                    "region_code": "440000",
                    "region_name": "广东省",
                    "project_name": "梅大高速",
                    "subject_names": ["广东博大高速公路有限公司梅大分公司"],
                    "accident_type": "ROADBED_COLLAPSE",
                    "engineering_type": "EXPRESSWAY",
                }
            )
        if sql.lstrip().startswith("UPDATE event"):
            self.event_update_parameters = dict(parameters or {})
        return _MappingResult()

    async def scalar(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> Any:
        del parameters
        if "SELECT incident_status FROM event" in str(statement):
            return "UNVERIFIED_LEAD"
        return None


class _EventRelationDecisionConnection:
    def __init__(self) -> None:
        self.inserted_decision = False

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> _MappingResult:
        del parameters
        sql = str(statement)
        if "SELECT candidate.id, candidate.event_id" in sql:
            return _MappingResult(
                {
                    "id": CLAIM_ID,
                    "event_id": EVENT_ID,
                    "source_item_id": ITEM_ID,
                    "target_item_id": UUID("019b0000-0000-7000-8000-000000044098"),
                    "relation_type": "FOLLOW_UP",
                    "submitted_by": SUBMITTER_ID,
                    "source_item_type": "SAFETY_CASE",
                    "target_item_type": "SAFETY_CASE",
                    "source_submitted_by": SUBMITTER_ID,
                    "target_submitted_by": TARGET_SUBMITTER_ID,
                }
            )
        if "INSERT INTO event_relation_decision" in sql:
            self.inserted_decision = True
        return _MappingResult()
