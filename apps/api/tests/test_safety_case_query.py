from datetime import UTC, datetime
from inspect import getsource
from uuid import UUID

from srbg_api.safety_regulations.query import (
    PostgresIntelligenceQueryService,
    _claims_and_evidence,
    _format_minor_currency,
    _item_row,
    _item_summary,
    _safety_fact_value,
)

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
ITEM_ID = UUID("019b0000-0000-7000-8000-000000042001")
EVENT_ID = UUID("019b0000-0000-7000-8000-000000042002")
REVISION_ID = UUID("019b0000-0000-7000-8000-000000042003")


def _case_row(*, published: bool) -> dict[str, object]:
    return {
        "id": ITEM_ID,
        "item_type": "SAFETY_CASE",
        "title": "梅大高速茶阳路段“5·1”塌方灾害调查评估报告",
        "original_url": "https://yjgl.gd.gov.cn/example.html",
        "source_published_at": NOW,
        "first_discovered_at": NOW,
        "activity_at": NOW,
        "updated_at": NOW,
        "review_status": "APPROVED" if published else "PENDING",
        "source_name": "广东省应急管理厅",
        "publication_status": "PUBLISHED" if published else None,
        "publication_revision_id": REVISION_ID if published else None,
        "version_count": 1,
        "latest_change_type": "INITIAL",
        "latest_change_review_state": "APPROVED" if published else None,
        "source_unavailable": False,
        "evidence_count": 5,
        "event_id": EVENT_ID,
        "report_stage": "FINAL_INVESTIGATION",
        "incident_status": "FINAL_INVESTIGATION_REPORT",
        "accident_type": "GEOLOGICAL_DISASTER",
        "engineering_type": "HIGHWAY",
        "occurred_at": datetime(2024, 4, 30, 17, 57, tzinfo=UTC),
        "region_name": "广东省梅州市大埔县",
        "deaths": 48,
        "injuries": 30,
        "loss_amount_minor": None,
        "loss_currency": None,
        "official_direct_causes": ["长时间持续性降水与多种因素叠加耦合"],
        "responsibility_findings": None,
        "rectification_has_open_issues": None,
        "similar_scenario_tags": ["HIGHWAY_OPERATION_GEOLOGICAL_RISK"],
        "prevention_measure_tags": ["MONITORING_AND_EARLY_WARNING"],
        "conflicted_fields": ["deaths"],
    }


def test_published_safety_case_uses_case_summary_and_hides_conflicted_field() -> None:
    item = _item_summary(_case_row(published=True))  # type: ignore[arg-type]

    assert item.content_type == "SAFETY_CASE"
    assert item.type_summary is not None
    assert item.type_summary.kind == "SAFETY_CASE"
    assert item.type_summary.event_id == EVENT_ID
    assert item.type_summary.deaths is None
    assert item.type_summary.injuries == 30
    assert [value.value for value in item.type_summary.conflicted_fields or []] == ["DEATH_COUNT"]
    assert item.type_summary.responsibility_findings is None


def test_pending_safety_case_keeps_the_round02_r3_whitelist() -> None:
    item = _item_summary(_case_row(published=False))  # type: ignore[arg-type]

    assert item.content_type == "SAFETY_CASE"
    assert item.publication_revision_id is None
    assert item.type_summary is None
    assert item.one_sentence_fact is None
    assert item.evidence_count is None


def test_public_event_projection_hides_r4_values_and_unpublished_facts() -> None:
    source = getsource(PostgresIntelligenceQueryService.get_event)

    assert "publication.status IN ('PUBLISHED','WITHDRAWN')" in source
    assert "header_publication.status = 'PUBLISHED'" in source
    assert source.count("item.risk_level = 'R3'") >= 2
    assert "conflict_rows" in source
    assert "public_safety_case_accepted_claim" in source
    assert "public_safety_case_conflict" in source
    assert "current_value_snapshot" not in source
    assert "candidate_value_snapshot" not in source
    assert "current_claim_id" not in source
    assert "candidate_claim_id" not in source
    assert "chosen_claim_id" not in source
    assert "ARRAY[]::uuid[] AS evidence_ids" in source


def test_event_header_ignores_r4_link_state_and_uses_only_safe_published_members() -> None:
    source = getsource(PostgresIntelligenceQueryService.get_event)

    assert "WITH safe_members AS" in source
    assert "membership.event_id AS id" in source
    assert "header_item.risk_level = 'R3'" in source
    assert "header_item.review_status = 'APPROVED'" in source
    assert "header_publication.status = 'PUBLISHED'" in source
    assert "ORDER BY earliest.source_published_at ASC NULLS LAST" in source
    assert source.count("ORDER BY identity.source_published_at DESC NULLS LAST") == 5
    assert "ORDER BY latest.source_published_at DESC NULLS LAST" in source
    assert "confirmed_event.title" not in source
    assert "confirmed_event.incident_status" not in source


def test_public_item_conflict_filters_never_read_conflict_participant_ids() -> None:
    for callable_ in (PostgresIntelligenceQueryService.get_feed, _item_row):
        source = getsource(callable_)
        assert "public_safety_case_conflict" in source
        assert "current_claim_id" not in source
        assert "candidate_claim_id" not in source


def test_public_item_hides_the_losing_claim_after_conflict_resolution() -> None:
    source = getsource(_claims_and_evidence)

    assert "public_safety_case_accepted_claim effective" in source
    assert "effective.claim_id = c.id" in source
    assert "current_claim_id" not in source
    assert "candidate_claim_id" not in source
    assert ":include_candidates" in source


def test_timeline_attaches_the_primary_relation_to_its_later_source_item() -> None:
    source = getsource(PostgresIntelligenceQueryService.get_event)

    assert "confirmed.source_item_id = i.id" in source
    assert "confirmed.relation_type = 'CORRECTS'" in source


def test_safety_case_evidence_projection_uses_latest_human_field_decision() -> None:
    for callable_ in (
        PostgresIntelligenceQueryService.get_feed,
        _item_row,
        _claims_and_evidence,
    ):
        source = getsource(callable_)
        assert "claim_field_decision" in source
        assert "ORDER BY decision.created_at DESC, decision.id DESC" in source


def test_loss_fact_formatter_preserves_minor_units_and_explicit_currency() -> None:
    assert _format_minor_currency(12_345_678, "CNY") == "123,456.78 人民币元"
    assert _format_minor_currency(501, "USD") == "5.01 USD"


def test_formal_findings_keep_structured_list_values() -> None:
    findings = ["持续降雨导致地下水累积", "多种因素叠加耦合"]

    assert _safety_fact_value("official_direct_causes", findings) == findings
