from datetime import UTC, datetime

from srbg_api.acquisition.contracts import FetchedAttachment, FetchResult
from srbg_api.config import Settings
from srbg_api.source_registry.service import _file_security_policy


def test_fetch_result_adds_public_attachments_without_breaking_html_adapters() -> None:
    html = FetchResult(
        url="https://example.test/index.html",
        status_code=200,
        content=b"<html></html>",
        content_type="text/html",
        etag=None,
        last_modified=None,
        fetched_at=datetime(2026, 7, 14, tzinfo=UTC),
    )
    pdf = FetchedAttachment(
        url="https://example.test/files/rule.pdf",
        filename="rule.pdf",
        content=b"%PDF-test-only",
        content_type="application/pdf",
    )

    assert html.attachments == ()
    assert FetchResult(
        url=html.url,
        status_code=html.status_code,
        content=html.content,
        content_type=html.content_type,
        etag=None,
        last_modified=None,
        fetched_at=html.fetched_at,
        attachments=(pdf,),
    ).attachments == (pdf,)


def test_pdf_resource_budgets_have_safe_configurable_defaults() -> None:
    settings = Settings()

    assert settings.fixture_max_bytes == 50 * 1024 * 1024
    assert settings.fixture_max_pdf_pages == 1000
    assert settings.pdf_max_ocr_pages == 200
    assert settings.attachment_max_entries == 100
    assert settings.attachment_max_uncompressed_bytes == 200 * 1024 * 1024
    assert settings.attachment_max_compression_ratio == 100
    assert settings.pdf_max_page_pixels == 40_000_000


def test_source_service_assembles_all_attachment_security_limits_from_settings() -> None:
    settings = Settings(
        fixture_max_bytes=123_456,
        fixture_max_pdf_pages=321,
        pdf_max_ocr_pages=45,
        attachment_max_entries=17,
        attachment_max_uncompressed_bytes=654_321,
        attachment_max_compression_ratio=23,
        pdf_max_page_pixels=7_654_321,
    )

    policy = _file_security_policy(settings)

    assert policy.max_file_bytes == 123_456
    assert policy.max_pdf_pages == 321
    assert policy.max_ocr_pages == 45
    assert policy.max_zip_entries == 17
    assert policy.max_uncompressed_bytes == 654_321
    assert policy.max_compression_ratio == 23
    assert policy.max_page_pixels == 7_654_321
