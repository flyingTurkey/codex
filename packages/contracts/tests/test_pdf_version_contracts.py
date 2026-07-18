from datetime import UTC, datetime
from uuid import UUID

import pytest
import srbg_contracts.models as models
from pydantic import ValidationError

VERSION_ID = UUID("019b0000-0000-7000-8000-000000006001")
ITEM_ID = UUID("019b0000-0000-7000-8000-000000006002")


def test_item_summary_adds_composable_document_states_without_changing_api_version() -> None:
    item = models.ItemSummary(
        id=ITEM_ID,
        publication_revision_id=None,
        domain="SAFETY",
        content_type="SAFETY_REGULATION",
        title="【测试专用】施工安全规定",
        source_name="测试机关",
        source_published_at=datetime(2026, 7, 1, tzinfo=UTC),
        first_discovered_at=datetime(2026, 7, 14, tzinfo=UTC),
        activity_at=datetime(2026, 7, 14, tzinfo=UTC),
        original_url="https://example.test/rule.pdf",
        review_status="PENDING",
        document_states=["UPDATED", "RE_REVIEW_PENDING", "SOURCE_UNAVAILABLE"],
        has_version_history=True,
    )

    payload = item.model_dump(mode="json", exclude_unset=True)

    assert models.CONTENT_SCHEMA_VERSION == "1.1.0"
    assert payload["document_states"] == [
        "UPDATED",
        "RE_REVIEW_PENDING",
        "SOURCE_UNAVAILABLE",
    ]
    assert payload["has_version_history"] is True


def test_pdf_ocr_evidence_locator_is_page_and_coordinate_addressed() -> None:
    evidence = models.EvidenceView(
        id=UUID("019b0000-0000-7000-8000-000000006003"),
        claim_ids=[UUID("019b0000-0000-7000-8000-000000006004")],
        document_version_id=VERSION_ID,
        locator=models.PdfOcrLocator(
            type="PDF_OCR",
            page_number=2,
            block_id=UUID("019b0000-0000-7000-8000-000000006005"),
            bbox=models.PageBoundingBox(x0=1200, y0=2400, x1=18000, y1=4100),
            confidence_bps=9712,
        ),
        excerpt="【测试专用】自2026年8月1日起施行",
        excerpt_sha256="a" * 64,
        original_url="https://example.test/rule.pdf",
    )

    assert evidence.locator.type == "PDF_OCR"
    assert evidence.locator.page_number == 2
    assert evidence.locator.confidence_bps == 9712


def test_pdf_locator_rejects_zero_page_or_inverted_box() -> None:
    with pytest.raises(ValidationError):
        models.PdfTextLocator(
            type="PDF_TEXT",
            page_number=0,
            block_id=UUID("019b0000-0000-7000-8000-000000006005"),
            bbox=models.PageBoundingBox(x0=200, y0=100, x1=100, y1=200),
        )


def test_version_timeline_diff_and_page_contracts_are_bounded_and_typed() -> None:
    timeline = models.VersionTimelineResponse(
        item_id=ITEM_ID,
        versions=[
            models.VersionTimelineEntry(
                version_id=VERSION_ID,
                version_number=1,
                processing_state="READY",
                change_type="INITIAL",
                material=False,
                review_state="NO_REVIEW_REQUIRED",
                acquired_at=datetime(2026, 7, 14, tzinfo=UTC),
                is_current=True,
            )
        ],
    )
    diff = models.VersionDiffResponse(
        item_id=ITEM_ID,
        from_version_id=VERSION_ID,
        to_version_id=UUID("019b0000-0000-7000-8000-000000006006"),
        change_type="METADATA_ONLY",
        material=False,
        changed_token_count=2,
        changed_token_ratio_bps=4,
        pages=[
            models.PageDiff(
                page_number=1,
                category="HEADER_FOOTER",
                hunks=[models.DiffHunk(operation="REPLACE", before="第1页", after="第 1 页")],
            )
        ],
        critical_fields=[],
    )
    page = models.DocumentPageView(
        document_version_id=VERSION_ID,
        page_number=1,
        page_count=3,
        width_mpt=595000,
        height_mpt=842000,
        rotation=0,
        text_source="NATIVE",
        preview_url=f"/api/v1/document-versions/{VERSION_ID}/pages/1/preview",
    )

    assert timeline.versions[0].processing_state == "READY"
    assert diff.pages[0].category == "HEADER_FOOTER"
    assert page.preview_url.endswith("/pages/1/preview")
