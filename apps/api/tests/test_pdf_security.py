from dataclasses import replace
from io import BytesIO
from pathlib import Path
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
VALID_PDF = (
    Path(__file__).parent / "fixtures" / "source" / "round01-sample.pdf"
).read_bytes()


def _minimal_pdf(extra: bytes = b"") -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog" + extra + b">>endobj\n%%EOF"


def _xref_pdf(objects: tuple[bytes, ...]) -> bytes:
    document = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(document)


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


def test_pdf_widget_external_action_is_rejected_after_name_decoding() -> None:
    widget = _xref_pdf(
        (
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] "
                b"/Annots [4 0 R] >>"
            ),
            (
                b"<< /Type /Annot /Subtype /Wid#67et /Rect [0 0 10 10] "
                b"/A << /S /Sub#6ditForm /F (https://attacker.invalid/) >> >>"
            ),
        )
    )

    with pytest.raises(SecurityViolation, match="PDF_ACTIVE_ACTION"):
        inspect_pdf_bytes(
            widget,
            filename="widget.pdf",
            declared_mime="application/pdf",
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
                ("attachments/rule.pdf", VALID_PDF),
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
            _zip([("safe.pdf", VALID_PDF), (entry, content)]),
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


def test_pdf_polyglot_payload_is_rejected() -> None:
    polyglot = _minimal_pdf() + b"PK\x03\x04hidden-archive"

    with pytest.raises(SecurityViolation, match="POLYGLOT"):
        inspect_pdf_bytes(
            polyglot,
            filename="test-only.pdf",
            declared_mime="application/pdf",
            policy=POLICY,
        )


@pytest.mark.parametrize(
    "active_html",
    [
        b"<!doctype html><SCRIPT>alert(1)</SCRIPT>",
        b'<!doctype html><body onload="x()"></body>',
        b'<!doctype html><meta http-equiv="refresh" content="0;url=x">',
        b'<!doctype html><a href="javascript:x()">x</a>',
    ],
)
def test_active_html_inside_zip_is_rejected(active_html: bytes) -> None:
    with pytest.raises(SecurityViolation, match="HTML_ACTIVE_CONTENT"):
        inspect_zip_bytes(
            _zip([("active.html", active_html)]),
            filename="test-only.zip",
            declared_mime="application/zip",
            policy=POLICY,
        )


def test_zip_rejects_bytes_after_the_declared_end_of_central_directory() -> None:
    polyglot = _zip([("safe.pdf", VALID_PDF)]) + b"<script>alert(1)</script>"

    with pytest.raises(SecurityViolation, match="ZIP_POLYGLOT"):
        inspect_zip_bytes(
            polyglot,
            filename="test-only.zip",
            declared_mime="application/zip",
            policy=POLICY,
        )


@pytest.mark.parametrize(
    ("unsafe_pdf", "code"),
    [
        (VALID_PDF.replace(b"%%EOF", b"/JavaScript 9 0 R\n%%EOF"), "PDF_ACTIVE_ACTION"),
        (VALID_PDF.replace(b"%%EOF", b"/Encrypt 9 0 R\n%%EOF"), "PDF_ENCRYPTED"),
        (VALID_PDF + b"PK\x03\x04hidden-archive", "PDF_POLYGLOT"),
    ],
)
def test_pdf_entries_receive_full_recursive_inspection(
    unsafe_pdf: bytes,
    code: str,
) -> None:
    with pytest.raises(SecurityViolation, match=code):
        inspect_zip_bytes(
            _zip([("attachments/unsafe.pdf", unsafe_pdf)]),
            filename="test-only.zip",
            declared_mime="application/zip",
            policy=POLICY,
        )


def test_zip_html_entry_must_obey_the_per_file_byte_limit() -> None:
    policy = replace(
        POLICY,
        max_file_bytes=200,
        max_uncompressed_bytes=1_000,
        max_compression_ratio=1_000,
    )

    with pytest.raises(SecurityViolation, match="FILE_SIZE_LIMIT"):
        inspect_zip_bytes(
            _zip(
                [
                    (
                        "oversized.html",
                        b"<!doctype html><html><body>" + b"A" * 300 + b"</body></html>",
                    )
                ]
            ),
            filename="test-only.zip",
            declared_mime="application/zip",
            policy=policy,
        )


@pytest.mark.parametrize(
    ("entry_name", "code"),
    [
        ("a" * 251 + ".html", "ZIP_PATH_LIMIT"),
        ("attachments/bad\x1fname.html", "ZIP_PATH_INVALID"),
    ],
)
def test_zip_entry_metadata_is_bounded_before_extraction(
    entry_name: str,
    code: str,
) -> None:
    with pytest.raises(SecurityViolation, match=code):
        inspect_zip_bytes(
            _zip([(entry_name, b"<!doctype html><html></html>")]),
            filename="test-only.zip",
            declared_mime="application/zip",
            policy=POLICY,
        )
