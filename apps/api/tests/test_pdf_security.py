from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from srbg_api.pdf_processing.security import (
    FileSecurityPolicy,
    SecurityViolation,
    inspect_pdf_bytes,
    inspect_zip_bytes,
)

POLICY = FileSecurityPolicy(
    max_file_bytes=50 * 1024 * 1024,
    max_pdf_pages=1000,
    max_ocr_pages=200,
    max_zip_entries=100,
    max_uncompressed_bytes=200 * 1024 * 1024,
    max_compression_ratio=100,
    max_page_pixels=40_000_000,
)


def _minimal_pdf(extra: bytes = b"") -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog" + extra + b">>endobj\n%%EOF"


@pytest.mark.parametrize(
    ("marker", "code"),
    [
        (b"/OpenAction 2 0 R /JavaScript 3 0 R", "PDF_ACTIVE_ACTION"),
        (b"/AA 2 0 R /JS(test)", "PDF_ACTIVE_ACTION"),
        (b"/Launch 2 0 R", "PDF_EXTERNAL_LAUNCH"),
        (b"/EmbeddedFiles 2 0 R", "PDF_EMBEDDED_FILE"),
        (b"/Encrypt 2 0 R", "PDF_ENCRYPTED"),
    ],
)
def test_pdf_active_or_embedded_content_is_quarantined(marker: bytes, code: str) -> None:
    with pytest.raises(SecurityViolation, match=code):
        inspect_pdf_bytes(
            _minimal_pdf(marker),
            filename="test-only.pdf",
            declared_mime="application/pdf",
            policy=POLICY,
        )


def test_pdf_declared_mime_and_extension_must_match_detected_bytes() -> None:
    with pytest.raises(SecurityViolation, match="MIME_MISMATCH"):
        inspect_pdf_bytes(
            _minimal_pdf(),
            filename="test-only.html",
            declared_mime="text/html",
            policy=POLICY,
        )


def _zip(entries: list[tuple[ZipInfo | str, bytes]]) -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return target.getvalue()


def test_flat_zip_returns_a_bounded_attachment_tree() -> None:
    result = inspect_zip_bytes(
        _zip(
            [
                ("notice.html", b"<!doctype html><title>test only</title>"),
                ("attachments/rule.pdf", _minimal_pdf()),
            ]
        ),
        filename="test-only.zip",
        declared_mime="application/zip",
        policy=POLICY,
    )

    assert [(entry.normalized_path, entry.depth) for entry in result.entries] == [
        ("notice.html", 0),
        ("attachments/rule.pdf", 1),
    ]


@pytest.mark.parametrize(
    ("entry", "code"),
    [
        ("../escape.pdf", "ZIP_PATH_TRAVERSAL"),
        ("nested/archive.zip", "ZIP_NESTED_ARCHIVE"),
        ("payload.exe", "ZIP_MIME_NOT_ALLOWED"),
    ],
)
def test_any_unsafe_zip_entry_quarantines_the_whole_archive(entry: str, code: str) -> None:
    if entry.endswith(".pdf"):
        content = _minimal_pdf()
    elif entry.endswith(".zip"):
        content = b"PK\x03\x04"
    else:
        content = b"MZ"
    with pytest.raises(SecurityViolation, match=code):
        inspect_zip_bytes(
            _zip([("safe.pdf", _minimal_pdf()), (entry, content)]),
            filename="test-only.zip",
            declared_mime="application/zip",
            policy=POLICY,
        )


def test_zip_symlink_and_compression_bomb_are_rejected() -> None:
    symlink = ZipInfo("linked.pdf")
    symlink.create_system = 3
    symlink.external_attr = 0o120777 << 16
    with pytest.raises(SecurityViolation, match="ZIP_SYMLINK"):
        inspect_zip_bytes(
            _zip([(symlink, b"target")]),
            filename="test-only.zip",
            declared_mime="application/zip",
            policy=POLICY,
        )

    with pytest.raises(SecurityViolation, match="ZIP_COMPRESSION_RATIO"):
        inspect_zip_bytes(
            _zip([("bomb.html", b"0" * 1_000_000)]),
            filename="test-only.zip",
            declared_mime="application/zip",
            policy=POLICY,
        )
