from pathlib import Path

import pytest
from srbg_api.document_vault.security import (
    UploadRejected,
    inspect_fixture,
    validate_filename,
)

FIXTURES = Path(__file__).parent / "fixtures" / "source"


def test_filename_rejects_paths_and_disguised_extensions() -> None:
    with pytest.raises(UploadRejected):
        validate_filename("../report.pdf")
    with pytest.raises(UploadRejected):
        validate_filename("report.pdf.exe")


def test_html_and_pdf_mime_are_detected_from_bytes_not_extension(tmp_path: Path) -> None:
    html = FIXTURES / "round01-sample.html"
    inspected = inspect_fixture(html, "fixture.html", "text/html", max_bytes=4096, max_pdf_pages=10)
    assert inspected.detected_mime == "text/html"
    assert inspected.title == "第 01 轮来源准入固定样本"

    pdf = FIXTURES / "round01-sample.pdf"
    inspected_pdf = inspect_fixture(
        pdf,
        "fixture.pdf",
        "application/pdf",
        max_bytes=4096,
        max_pdf_pages=10,
    )
    assert inspected_pdf.detected_mime == "application/pdf"
    assert inspected_pdf.document_kind == "PDF"

    with pytest.raises(UploadRejected):
        inspect_fixture(html, "fixture.pdf", "application/pdf", max_bytes=4096, max_pdf_pages=10)


def test_pdf_active_actions_and_size_limit_are_rejected(tmp_path: Path) -> None:
    malicious = tmp_path / "malicious.pdf"
    malicious.write_bytes(
        b"%PDF-1.7\n1 0 obj << /Type /Catalog /OpenAction 2 0 R /JavaScript 3 0 R >>\n%%EOF"
    )
    with pytest.raises(UploadRejected, match="active content"):
        inspect_fixture(
            malicious,
            "malicious.pdf",
            "application/pdf",
            max_bytes=1024,
            max_pdf_pages=10,
        )

    too_large = tmp_path / "large.html"
    too_large.write_bytes(b"<html>" + b"x" * 1024 + b"</html>")
    with pytest.raises(UploadRejected, match="too large"):
        inspect_fixture(too_large, "large.html", "text/html", max_bytes=100, max_pdf_pages=10)
