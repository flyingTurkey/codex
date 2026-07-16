from pathlib import Path

import pytest
from srbg_api.document_vault.security import (
    UploadRejected,
    inspect_fixture,
    inspect_fixture_bytes,
    validate_filename,
)

FIXTURES = Path(__file__).parent / "fixtures" / "source"


def test_filename_rejects_paths_and_disguised_extensions() -> None:
    with pytest.raises(UploadRejected):
        validate_filename("../report.pdf")
    with pytest.raises(UploadRejected):
        validate_filename("report.pdf.exe")


def test_filename_rejects_del_and_returns_nfc() -> None:
    with pytest.raises(UploadRejected, match="invalid filename"):
        validate_filename("unsafe\x7f.html")

    assert validate_filename("cafe\u0301.html") == "café.html"


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


def test_declarative_discovery_fixture_mime_is_bounded_and_non_executable() -> None:
    rss = inspect_fixture_bytes(
        b"<rss><channel><item><title>One</title></item></channel></rss>",
        "feed.xml",
        "application/rss+xml",
        max_bytes=4096,
        max_pdf_pages=10,
    )
    assert rss.detected_mime == "application/xml"
    assert rss.document_kind == "DISCOVERY_XML"

    api = inspect_fixture_bytes(
        b'{"items":[{"id":"one"}]}',
        "feed.json",
        "application/json",
        max_bytes=4096,
        max_pdf_pages=10,
    )
    assert api.detected_mime == "application/json"
    assert api.document_kind == "DISCOVERY_JSON"

    with pytest.raises(UploadRejected, match="XML"):
        inspect_fixture_bytes(
            b'<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><rss>&xxe;</rss>',
            "feed.xml",
            "application/xml",
            max_bytes=4096,
            max_pdf_pages=10,
        )
    with pytest.raises(UploadRejected, match="JSON"):
        inspect_fixture_bytes(
            b'{"items": [}',
            "feed.json",
            "application/json",
            max_bytes=4096,
            max_pdf_pages=10,
        )


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


@pytest.mark.parametrize(
    "active_html",
    [
        b"<!doctype html><html><script>alert(1)</script></html>",
        b'<!doctype html><html><body onload="alert(1)"></body></html>',
        b'<!doctype html><html><iframe src="https://attacker.invalid"></iframe></html>',
        b'<!doctype html><html><meta http-equiv="refresh" content="0;url=x"></html>',
        b'<!doctype html><html><object data="payload"></object></html>',
        b'<!doctype html><html><a href="javascript:alert(1)">x</a></html>',
        b'<!doctype html><html><a href="java&#x73;cript:alert(1)">x</a></html>',
        b'<!doctype html><html><a href="java&#115;cript:alert(1)">x</a></html>',
        b'<!doctype html><html><form action="https://attacker.invalid"></form></html>',
        b'<!doctype html><html><link rel="stylesheet" href="https://x.invalid"></html>',
        b'<!doctype html><html><style>@import "https://x.invalid/a.css";</style></html>',
        b'<!doctype html><html><base href="https://attacker.invalid/"></html>',
    ],
)
def test_html_active_content_is_rejected_before_storage(
    tmp_path: Path,
    active_html: bytes,
) -> None:
    artifact = tmp_path / "active.html"
    artifact.write_bytes(active_html)

    with pytest.raises(UploadRejected, match="active content"):
        inspect_fixture(
            artifact,
            "active.html",
            "text/html",
            max_bytes=4096,
            max_pdf_pages=10,
        )
