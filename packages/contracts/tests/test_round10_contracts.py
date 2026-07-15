from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import (
    CollectionCreateRequest,
    CollectionPatchRequest,
    DailyReport,
    DailyReportItem,
    DailyReportSection,
    FingerprintResponse,
    SaveItemRequest,
    SearchContext,
    VersionResponse,
)
from srbg_contracts.export import SCHEMA_MODELS

UUID7_A = UUID("019b0000-0000-7000-8000-000000001001")
UUID7_B = UUID("019b0000-0000-7000-8000-000000001002")
NOW = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)


def test_round10_search_context_is_bounded_and_explainable() -> None:
    context = SearchContext(
        match_kind="EXACT_IDENTIFIER",
        matched_fields=["DOCUMENT_NUMBER"],
        matched_identifiers=["川交规\u30142026\u301510号"],
        semantic_status="DISABLED",
    )

    assert context.match_kind == "EXACT_IDENTIFIER"
    assert context.matched_fields == ["DOCUMENT_NUMBER"]
    with pytest.raises(ValidationError):
        SearchContext(
            match_kind="BODY",
            matched_fields=["body"],
            matched_identifiers=[],
            semantic_status="DISABLED",
            raw_body_snippet="must never be exposed",
        )


def test_round10_saved_item_and_collection_inputs_reject_unbounded_values() -> None:
    assert SaveItemRequest(item_id=UUID7_A, collection_id=None).item_id == UUID7_A
    assert CollectionCreateRequest(name="隧道监测专题").name == "隧道监测专题"
    assert CollectionPatchRequest(name="桥梁安全", archived=False).archived is False

    with pytest.raises(ValidationError):
        CollectionCreateRequest(name="x" * 101)
    with pytest.raises(ValidationError):
        CollectionPatchRequest()


def test_round10_daily_report_is_a_fixed_revision_snapshot() -> None:
    item = DailyReportItem(
        item_id=UUID7_A,
        publication_revision_id=UUID7_B,
        position=1,
        title="四川隧道监测预警更新",
        summary="已接受事实摘要",
        current_state="PUBLISHED",
        original_url="https://example.com/report",
    )
    report = DailyReport(
        id=UUID7_A,
        report_date="2026-07-15",
        status="DRAFT",
        snapshot_at=NOW,
        published_at=None,
        requires_regeneration=False,
        sections=[DailyReportSection(kind="TODAY_HIGHLIGHTS", title="今日重点", items=[item])],
    )

    assert report.sections[0].items[0].publication_revision_id == UUID7_B
    assert report.sections[0].items[0].position == 1


def test_round10_fingerprint_and_version_publish_capabilities() -> None:
    fingerprint = FingerprintResponse(
        generated_at=NOW,
        feed_generation=4,
        search_generation=3,
        hot_topics_generation=2,
        latest_daily_report_id=None,
        fingerprint="sha256:" + "a" * 64,
    )
    version = VersionResponse(
        search_schema_version="1.0.0",
        semantic_search_enabled=False,
    )

    assert fingerprint.search_generation == 3
    assert version.search_schema_version == "1.0.0"


def test_round10_contracts_are_in_deterministic_schema_export() -> None:
    assert {
        "collection-create-request.schema.json",
        "collection-patch-request.schema.json",
        "collection-summary.schema.json",
        "daily-draft-request.schema.json",
        "daily-report.schema.json",
        "fingerprint-response.schema.json",
        "save-item-request.schema.json",
        "search-context.schema.json",
    }.issubset(SCHEMA_MODELS)
